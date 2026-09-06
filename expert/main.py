#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — o sistema especialista: as 19 regras, sem nenhuma fisica.

O ESPELHO DO reactor/

    O reator tem os efeitos e nenhuma decisao. Aqui e o contrario: ha as 19
    regras de steps/03-regras-controle.md e nenhum modelo de planta. Este
    servico nao sabe quanto boro se mistura em 132.440 kg de agua, nem quanto
    tempo leva a homogeneizacao — ele pede, e o reator responde com o estado
    novo.

QUEM FECHA A MALHA

    Este servico. O reator e passivo: nao tem laco proprio, nao conhece a URL
    de ninguem, nao chama nada. A dependencia e de mao unica, e por isso a URL
    da planta chega no CORPO de POST /expert/initialize — e o expert que escolhe
    com qual reator falar.

A BASE E DADO, NAO CODIGO

    regras.py guarda as 19 regras como registros, com o antecedente no texto
    literal do fonte C. motor.py as interpreta. GET /expert/regras devolve a
    base inteira — e a mesma coisa que decide, nao uma documentacao paralela
    que pode envelhecer.

    A estrategia de resolucao de conflito esta num lugar so, em motor.py:
    prioridade = ordem do fonte, disparo multiplo por ciclo, estado relido a
    cada regra. steps/03 §5.1 mostrou que qualquer outra escolha — a classica
    "casa todas, dispara uma, recomeca" inclusive — nao reproduz o simulador.
"""

import base64
import os
import threading
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import saida
from models import (Corrida, Disparos, EfeitoDescrito, ParametrosPartida,
                    RegraDescrita, Resposta)
from motor import Motor
from planta import ErroDoReator, PlantaRemota
from regras import BASE, REGRAS

MAX_SESSOES = int(os.environ.get("MAX_SESSOES", "32"))

# Teto de bytes por resposta de /executar. NAO e negociavel pelo cliente: o
# servico e que decide quanto se compromete a alocar. Uma resposta carrega o
# texto inteiro do trecho, e serializa-la em base64 dentro de JSON custa varias
# copias do buffer — deixar isso sem limite e deixar o cliente escolher quando o
# servico morre por memoria.
MAX_SAIDA_BYTES = int(os.environ.get("MAX_SAIDA_BYTES", str(8 * 1024 * 1024)))

app = FastAPI(
    title="Sistema Especialista de Reatividade PWR — as 19 regras",
    description=__doc__,
    version="0.1.0",
)


class _Sessao:
    def __init__(self, sid, motor):
        self.sid = sid
        self.motor = motor
        self.criada_em = datetime.now(timezone.utc).isoformat()
        self.trava = threading.Lock()


_sessoes: dict[str, _Sessao] = {}
_trava_registro = threading.Lock()


def _pega(sid):
    with _trava_registro:
        s = _sessoes.get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="sessao %s nao existe" % sid)
    return s


def _responde(s, buf, disparadas=()):
    m = s.motor
    return Resposta(
        sessao=s.sid,
        sessao_reator=m.planta.sid,
        estado=m.planta.estado(),
        saida_b64=base64.b64encode(bytes(buf)).decode("ascii"),
        disparadas=list(disparadas),
        ciclos=m.ciclos,
        termino=m.termino,
        pode_continuar=m.pode_continuar(),
    )


# ---------------------------------------------------------------------------

@app.get("/health", tags=["servico"])
def health():
    return {"status": "ok", "servico": "expert",
            "regras": len(REGRAS), "sessoes": len(_sessoes)}


@app.get("/expert/regras", response_model=list[RegraDescrita], tags=["base de regras"])
def lista_regras():
    """A base inteira, como ela e guardada.

    O campo `condicao` e o texto do fonte C, nao uma parafrase — e o mesmo
    texto que o motor compila e avalia. tests/test_equivalencia_regras.py
    confere cada um contra a linha correspondente do .c.
    """
    saida_ = []
    prioridade = 0
    for bloco in BASE:
        for regra in bloco.regras:
            prioridade += 1
            efeitos = []
            for e in regra.efeitos:
                detalhe = {}
                if e.tipo == "diluir":
                    detalhe = {"texto": e.texto,
                               "faixas": [{"quando": str(c) if c else "sempre",
                                           "vazao": str(v)} for c, v in e.faixas]}
                elif e.tipo == "borar":
                    detalhe = {"texto": e.texto, "vazao": str(e.vazao),
                               "volume": str(e.volume), "satura": e.satura}
                elif e.tipo == "barra":
                    detalhe = {"texto": e.texto,
                               "passos": [{"quando": str(c) if c else "senao",
                                           "passos": str(p)} for c, p in e.passos]}
                else:
                    detalhe = {"linhas": [f for f, _ in e.cabecalho],
                               "enche": e.enche, "despejo": e.despejo,
                               "encerra": e.encerra}
                efeitos.append(EfeitoDescrito(
                    tipo=e.tipo,
                    quando=str(e.quando) if e.quando is not None else None,
                    detalhe=detalhe))
            saida_.append(RegraDescrita(
                id=regra.id, bloco=bloco.nome, prioridade=prioridade,
                condicao=str(regra.condicao),
                guarda_do_bloco=str(bloco.guarda) if bloco.guarda is not None else None,
                linha_c=regra.linha_c, descricao=regra.descricao, efeitos=efeitos))
    return saida_


@app.post("/expert/initialize", response_model=Resposta, tags=["sessao"])
def initialize(params: ParametrosPartida):
    """Abre uma sessao no reator indicado e prepara o motor sobre ela."""
    with _trava_registro:
        if len(_sessoes) >= MAX_SESSOES:
            raise HTTPException(status_code=429,
                                detail="limite de %d sessoes atingido" % MAX_SESSOES)
    sid = uuid.uuid4().hex[:12]
    corpo = params.model_dump(exclude={"reactor_url"})
    if corpo.get("arquivo"):
        corpo["arquivo"] = os.path.basename(corpo["arquivo"])
    try:
        with saida.captura() as buf:
            planta = PlantaRemota(params.reactor_url, corpo)
    except ErroDoReator as e:
        raise HTTPException(status_code=502, detail=str(e))

    s = _Sessao(sid, Motor(planta, BASE))
    with _trava_registro:
        _sessoes[sid] = s
    return _responde(s, buf)


@app.post("/expert/{sid}/ciclo", response_model=Resposta, tags=["controle"])
def ciclo(sid: str):
    """Um minuto: a planta avanca, depois as 19 regras na ordem do fonte.

    `disparadas` traz os ids das que dispararam. Varias por ciclo e o normal —
    e o que a estrategia de disparo multiplo significa na pratica.
    """
    s = _pega(sid)
    with s.trava:
        if not s.motor.pode_continuar():
            raise HTTPException(status_code=409,
                                detail="corrida encerrada (termino=%r)" % s.motor.termino)
        try:
            with saida.captura() as buf:
                disparadas = s.motor.ciclo()
        except ErroDoReator as e:
            raise HTTPException(status_code=502, detail=str(e))
        return _responde(s, buf, disparadas)


@app.post("/expert/{sid}/executar", response_model=Resposta, tags=["controle"])
def executar(sid: str, corrida: Corrida):
    """Roda a malha fechada ate R19 declarar fim de ciclo, t alcancar tmax,
    `max_ciclos` minutos, ou MAX_SAIDA_BYTES de texto — o que vier primeiro.

    O ultimo criterio e do SERVICO, e nao do cliente. Por isso a resposta pode
    trazer menos ciclos do que se pediu: quem fecha a malha tem de repetir a
    chamada enquanto `pode_continuar` for verdadeiro. A corrida completa
    (~500 mil ciclos, mais de 400 MB) so e possivel assim.
    """
    s = _pega(sid)
    with s.trava:
        try:
            with saida.captura() as buf:
                s.motor.executa(max_ciclos=corrida.max_ciclos,
                                max_bytes=MAX_SAIDA_BYTES)
        except ErroDoReator as e:
            raise HTTPException(status_code=502, detail=str(e))
        return _responde(s, buf)


@app.get("/expert/{sid}/estado", tags=["controle"])
def estado(sid: str):
    s = _pega(sid)
    with s.trava:
        return {"sessao": sid, "sessao_reator": s.motor.planta.sid,
                "estado": s.motor.planta.estado(), "ciclos": s.motor.ciclos,
                "termino": s.motor.termino,
                "pode_continuar": s.motor.pode_continuar()}


@app.get("/expert/{sid}/disparos", response_model=Disparos, tags=["controle"])
def disparos(sid: str):
    """Quantas vezes cada regra disparou.

    Responde a pendencia registrada em steps/03-regras-controle.md §7: "nao foi
    medido quantas vezes cada regra dispara, nem quais disparam juntas. Sem isso
    nao se sabe quais das 19 sao exercitadas pelos cenarios da dissertacao e
    quais sao inalcancaveis."
    """
    s = _pega(sid)
    with s.trava:
        contagem = dict(s.motor.disparos)
        return Disparos(
            sessao=sid, ciclos=s.motor.ciclos, disparos=contagem,
            nunca_dispararam=[r.id for r in REGRAS if r.id not in contagem])


@app.delete("/expert/{sid}", tags=["sessao"])
def encerra(sid: str):
    with _trava_registro:
        s = _sessoes.pop(sid, None)
    if s is None:
        raise HTTPException(status_code=404, detail="sessao %s nao existe" % sid)
    s.motor.planta.encerra()
    return {"sessao": sid, "encerrada": True}


# ---------------------------------------------------------------------------
# A tela de demonstracao, servida pelo proprio expert em /app.
#
# POR QUE AQUI, E NAO NUM SEGUNDO PROCESSO
#
#     CORS e regra do navegador: uma pagina carregada de um endereco so le a
#     resposta de outro se o servidor de destino permitir por cabecalho, e
#     "endereco" e protocolo + host + porta — localhost:8000 e localhost:8009 ja
#     sao diferentes. Servida daqui, a pagina e a API sao a MESMA ORIGEM, e o
#     assunto some: sem CORSMiddleware, sem lista de origens para manter, e sem
#     um segundo processo para lembrar de ligar. `podman-compose up -d` sobe a
#     demo inteira. (PRD_FRONTEND.md §5.2 e §7.1.)
#
# O QUE ISTO **NAO** MUDA
#
#     Nenhuma rota da API, nenhum modelo, nenhuma regra. StaticFiles so devolve
#     bytes de arquivo sob /app; o /expert/* continua identico, e a aceitacao
#     byte a byte dos 6 cenarios nao passa por aqui.
#
# O diretorio chega por montagem (./static no docker-compose.yml), nao por COPY:
# editar a tela nao exige reconstruir a imagem. Se a montagem nao existir — rodar
# o servico solto, fora da compose — o servico sobe do mesmo jeito, sem /app, em
# vez de morrer na importacao.
DIR_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ARQ_CENARIOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cenarios.json")


@app.get("/app/cenarios.json", include_in_schema=False)
def cenarios_da_tela():
    """Os 6 cenarios, entregues ao navegador a partir da FONTE UNICA.

    cenarios.json mora na raiz do repositorio — scripts/cenarios.py e os testes
    leem o mesmo arquivo. Uma copia dentro de static/ seria uma segunda fonte,
    livre para envelhecer; por isso ele chega montado, de fora do diretorio
    servido, e sai por esta rota. Ela precede o mount de /app: o StaticFiles
    recusaria seguir um symlink para fora do diretorio, e e o Starlette que casa
    as rotas na ordem em que foram registradas.
    """
    if not os.path.isfile(ARQ_CENARIOS):
        raise HTTPException(status_code=404, detail="cenarios.json nao esta montado")
    return FileResponse(ARQ_CENARIOS, media_type="application/json")


class _AppEstatico(StaticFiles):
    """StaticFiles que pede revalidacao a cada carga.

    O diretorio entra por MONTAGEM justamente para que editar a tela nao exija
    reconstruir a imagem. Sem cabecalho de cache o navegador aplica cache
    heuristico e continua servindo o modulo antigo depois da edicao — o que anula
    o arranjo inteiro, e engana quem estiver conferindo uma mudanca. `no-cache`
    nao proibe guardar: obriga a revalidar, e o ETag que o StaticFiles ja emite
    resolve em 304 quando nada mudou.

    Vale so para /app. As rotas da API nao passam por aqui.
    """

    def file_response(self, *a, **kw):
        r = super().file_response(*a, **kw)
        r.headers["cache-control"] = "no-cache"
        return r


if os.path.isdir(DIR_APP):
    app.mount("/app", _AppEstatico(directory=DIR_APP, html=True), name="app")
