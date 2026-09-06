#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — o simulador de reatividade como servico, sem nenhuma regra de controle.

GRANULARIDADE DA API (a decisao que estrutura tudo)

    A API e de ACAO, nao de ciclo. Nao existe um endpoint que receba as 19
    decisoes de um minuto e as aplique: o expert avalia R1, aplica, recebe o
    estado novo, avalia R2 sobre ele, e assim por diante.

    Isso nao e preferencia de estilo. steps/03-regras-controle.md §5.1: as
    regras do simulador nao sao atomicas nem exclusivas — varias disparam no
    mesmo minuto, em ordem fixa, e cada uma enxerga o estado que a anterior
    deixou (CorrigeTmedDeltaBarra ja reescreveu Tmed e DeltaT antes de o `if`
    seguinte ser avaliado). Uma API de ciclo obrigaria o expert a ter um modelo
    da planta para prever esses estados intermediarios — ou seja, desfaria a
    separacao que este passo existe para fazer.

    O preco e o numero de chamadas: um minuto com quatro atuacoes custa cinco
    idas e voltas. E o preco certo.

CONTRATO DE SAIDA

    Toda resposta traz `saida`: o texto que aquela chamada imprimiu. Concatenados
    na ordem das chamadas, os trechos reproduzem byte a byte a saida padrao de
    simulador.py. E o que torna a separacao falsificavel — nao basta chegar aos
    mesmos numeros, e preciso chegar por dentro do mesmo caminho.

DEPENDENCIA DE MAO UNICA

    Este servico nao chama ninguem. Nao conhece a URL do expert, nao tem cliente
    HTTP, nao tem laco proprio. Quem fecha a malha e o expert.
"""

import base64
import os
import threading
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

import saida
from physics import (ARQUIVO_PADRAO, TRANSIENTES, TR_NENHUM, ErroDeGravacao,
                    Planta)
from models import CorpoAcao, ParametrosPartida, Resposta, Sessao

SAIDA_DIR = os.environ.get("SAIDA_DIR", ".")
MAX_SESSOES = int(os.environ.get("MAX_SESSOES", "64"))

app = FastAPI(
    title="Simulador de Reatividade PWR — planta",
    description=__doc__,
    version="0.1.0",
)


class _Sessao:
    """Uma planta e o cadeado que a serializa.

    A planta e uma maquina de estados sequencial: duas chamadas simultaneas na
    mesma sessao produziriam um estado que nenhuma execucao do simulador
    produziria. O cadeado e por sessao, e nao global, para que sessoes
    independentes nao se esperem.
    """

    def __init__(self, sid, planta, arquivo):
        self.sid = sid
        self.planta = planta
        self.arquivo = arquivo
        self.criada_em = datetime.now(timezone.utc).isoformat()
        self.trava = threading.Lock()
        self.passos = 0
        self.acoes = 0

    def resumo(self):
        return Sessao(sessao=self.sid, arquivo=self.arquivo,
                      criada_em=self.criada_em, passos=self.passos,
                      acoes=self.acoes)


_sessoes: dict[str, _Sessao] = {}
_trava_registro = threading.Lock()


def _pega(sid):
    with _trava_registro:
        s = _sessoes.get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="sessao %s nao existe" % sid)
    return s


def _responde(s, buf):
    return Resposta(
        sessao=s.sid,
        estado=s.planta.estado(),
        saida_b64=base64.b64encode(bytes(buf)).decode("ascii"),
        pode_continuar=s.planta.pode_continuar(),
    )


# ---------------------------------------------------------------------------

@app.get("/health", tags=["servico"])
def health():
    return {"status": "ok", "servico": "reactor", "sessoes": len(_sessoes)}


@app.get("/reactor/tipos", tags=["servico"])
def tipos():
    """O tipo C de cada grandeza de `estado`: 'float' (32 bits), 'int', 'double'.

    O cliente precisa disto para fazer as contas do lado do controle com o mesmo
    arredondamento do C. O JSON entrega double; sem o tipo declarado, a vazao da
    rampa e o volume de boro sairiam com precisao a mais, e +-0,001 desloca um
    evento de diluicao (ver steps/01-porte-linux-simulador.md).
    """
    return Planta().tipos()


@app.post("/reactor/initialize", response_model=Resposta, tags=["sessao"])
def initialize(params: ParametrosPartida):
    """Cria uma sessao e roda o prologo de main(): os 7 valores do operador e
    todos os derivados da concentracao de boro (v1, v2, a, b, alfaboro,
    alfamoderador, taxatemp) mais o estado inicial de Xe e Iodo."""
    with _trava_registro:
        if len(_sessoes) >= MAX_SESSOES:
            raise HTTPException(status_code=429,
                                detail="limite de %d sessoes atingido" % MAX_SESSOES)
        sid = uuid.uuid4().hex[:12]

    nome = os.path.basename(params.arquivo) if params.arquivo else \
        "Modelagem_Reator_%s.txt" % sid
    if not nome or nome in (".", ".."):
        raise HTTPException(status_code=422, detail="nome de arquivo invalido")
    caminho = os.path.join(SAIDA_DIR, nome)

    planta = Planta(arquivo=caminho, win_original=params.win_original)
    s = _Sessao(sid, planta, nome)

    try:
        with saida.captura() as buf:
            planta.inicializa(
                params.pot_turbina, params.cboro, params.posicao_barra,
                params.tempodilute, params.t1, params.t2, params.delta_i,
                tmax=params.tmax,
                transiente=TRANSIENTES.get(params.transiente, TR_NENHUM),
                t_transiente=params.t_transiente,
                alvo=params.alvo, taxa=params.taxa,
            )
    except ErroDeGravacao as e:
        raise HTTPException(status_code=500,
                            detail="nao foi possivel gravar em %s: %s" % (caminho, e))

    with _trava_registro:
        _sessoes[sid] = s
    return _responde(s, buf)


@app.get("/reactor/sessoes", response_model=list[Sessao], tags=["sessao"])
def lista_sessoes():
    with _trava_registro:
        return [s.resumo() for s in _sessoes.values()]


@app.delete("/reactor/{sid}", tags=["sessao"])
def encerra(sid: str):
    with _trava_registro:
        if _sessoes.pop(sid, None) is None:
            raise HTTPException(status_code=404, detail="sessao %s nao existe" % sid)
    return {"sessao": sid, "encerrada": True}


@app.post("/reactor/{sid}/passo", response_model=Resposta, tags=["planta"])
def passo(sid: str):
    """Avanca um minuto: relogio, queima de Tmed, limite de insercao, ajuste da
    carga programada, alvo de Delta I, oscilacao de Xe/Iodo, gravacao da amostra,
    injecao do transiente e a posicao de referencia BD.

    Para exatamente onde comeca o controle — a linha seguinte no fonte e o
    `if DeltaT < -0.1` que despacha R1-R4.
    """
    s = _pega(sid)
    with s.trava:
        try:
            with saida.captura() as buf:
                s.planta.passo()
        except ErroDeGravacao as e:
            raise HTTPException(status_code=500, detail=str(e))
        s.passos += 1
        return _responde(s, buf)


@app.post("/reactor/{sid}/acao", response_model=Resposta, tags=["planta"])
def acao(sid: str, corpo: CorpoAcao):
    """Aplica UMA atuacao e devolve o estado resultante.

    Uma so, e nao a lista do minuto: a regra seguinte tem de ser avaliada sobre
    o estado que esta deixou.
    """
    s = _pega(sid)
    a = corpo.acao
    with s.trava:
        with saida.captura() as buf:
            if a.tipo == "diluir":
                s.planta.diluir(a.vazao)
            elif a.tipo == "borar":
                s.planta.borar(a.vazao_boro, a.vboro)
            else:
                s.planta.mover_barra(a.passos)
        s.acoes += 1
        return _responde(s, buf)


@app.get("/reactor/{sid}/estado", tags=["planta"])
def estado(sid: str):
    """A observacao, sem avancar nada."""
    s = _pega(sid)
    with s.trava:
        return {"sessao": sid, "estado": s.planta.estado(),
                "pode_continuar": s.planta.pode_continuar()}


@app.get("/reactor/{sid}/interno", tags=["planta"])
def interno(sid: str):
    """Estado interno completo — as 104 variaveis globais do .c.

    Nao e para o controle: e para a validacao, que compara a planta com
    simulador.py variavel a variavel e nao so pelo arquivo de amostras.
    """
    s = _pega(sid)
    with s.trava:
        return {"sessao": sid, "interno": s.planta.interno()}
