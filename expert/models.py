#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models.py — os contratos da API do sistema especialista.
"""

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

TRANSIENTE = Literal["runback-bap", "runback-circ", "runback-400",
                     "runback-300", "runback-150", "rampa"]


class ParametrosPartida(BaseModel):
    """A URL do reator mais os 7 valores do operador.

    A URL vem no CORPO, e nao de variavel de ambiente, porque e o expert que
    escolhe com qual planta falar. O reator nao conhece o expert: a dependencia
    e de mao unica.
    """

    reactor_url: str = Field("http://reactor-simulator:8008",
                             description="Onde esta a planta")

    pot_turbina: float = Field(650, description="Potencia inicial da turbina (MW), 32 a 650")
    cboro: float = Field(1800, description="Concentracao inicial de boro (ppm)")
    posicao_barra: int = Field(210, description="Posicao inicial do banco D (passos)")
    # `gt=0` aqui NAO e faixa fisica — e o mesmo invariante do `tmax`.
    #
    # Os dois campos movem o relogio: `tempodilute` entra como `t += tempodilute`
    # na diluicao (C:738, 763, 806). Abaixo de -19 o saldo do ciclo fica negativo
    # (a homogeneizacao soma +18 e o laco do main soma +1), o tempo passa a andar
    # para tras, `Motor.pode_continuar` nunca fica falso e a corrida nao termina.
    #
    # Nenhum dos outros cinco campos ganha restricao, e de proposito: o C nao
    # valida nada, e um `ge`/`le` inventado aqui viraria contrato que o artefato
    # original nao tem. A faixa "32 a 650" da potencia continua sendo o texto do
    # prompt, no `description`, que e onde ela pode estar sem virar promessa.
    tempodilute: int = Field(4, gt=0,
                             description="Intervalo de tempo por diluicao (minutos)")
    t1: float = Field(-0.3, description="Delta de temperatura para a vazao minima (°C)")
    t2: float = Field(-0.8, description="Delta de temperatura para a vazao maxima (°C)")
    delta_i: float = Field(0.0, description="Delta I inicial")

    tmax: float = Field(700000, gt=0, description="Horizonte da simulacao (minutos)")
    transiente: Optional[TRANSIENTE] = None
    t_transiente: int = Field(10, description="Minuto em que o transiente e aplicado")
    alvo: float = Field(0.0, description="Alvo de carga na turbina (MW) — so para rampa")
    taxa: float = Field(0.0, description="Taxa de variacao (MW/min) — so para rampa")
    win_original: bool = False
    arquivo: Optional[str] = None

    @model_validator(mode="after")
    def _rampa_exige_taxa(self):
        if self.transiente == "rampa" and self.taxa <= 0:
            raise ValueError("transiente 'rampa' exige alvo (MW) e taxa (MW/min) positiva")
        return self


class Resposta(BaseModel):
    sessao: str
    sessao_reator: str
    estado: dict[str, Union[int, float]]
    saida_b64: str = Field(
        description="Os BYTES que ESTA chamada produziu — os das regras e os da "
                    "planta, ja intercalados na ordem do simulador monolitico — "
                    "em base64.\n\nBase64 porque texto nao serve: R18 imprime 37 "
                    "bytes 177 e R19 imprime 30, crus, como o `printf(\"%c\",177)` "
                    "do C. Nao sao UTF-8 valido, e nenhum campo string de JSON os "
                    "transporta sem perda.")
    disparadas: list[str] = Field(
        default_factory=list,
        description="Ids das regras que dispararam, na ordem em que dispararam. "
                    "Varias por ciclo: a estrategia e disparo multiplo.")
    ciclos: int
    termino: str = Field(description="'fim' depois que R19 declara fim de ciclo")
    pode_continuar: bool


class Corrida(BaseModel):
    max_ciclos: Optional[int] = Field(
        None, gt=0,
        description="Teto de minutos simulados nesta chamada.\n\nO servico impoe "
                    "um teto PROPRIO de bytes de saida (MAX_SAIDA_BYTES), entao a "
                    "resposta pode trazer menos ciclos do que se pediu — inclusive "
                    "quando este campo vem vazio. Quem fecha a malha repete a "
                    "chamada enquanto `pode_continuar` for verdadeiro; e assim que "
                    "a corrida completa, de ~500 mil ciclos, cabe em respostas de "
                    "tamanho limitado.")


class EfeitoDescrito(BaseModel):
    tipo: Literal["diluir", "borar", "barra", "alarme"]
    quando: Optional[str] = Field(None, description="Condicao propria do efeito "
                                                    "(consequente partido: R11, R12)")
    detalhe: dict[str, object] = Field(default_factory=dict)


class RegraDescrita(BaseModel):
    """Uma regra como ela e guardada: texto do fonte C, nao parafrase."""

    id: str
    bloco: str
    prioridade: int = Field(description="Ordem de avaliacao = ordem do fonte")
    condicao: str = Field(description="O antecedente, no texto do .c")
    guarda_do_bloco: Optional[str] = Field(None, description="Avaliada uma vez na "
                                                             "entrada do bloco")
    linha_c: int = Field(description="Linha do `if` em V8_Reatividade_SimuladorIgor_linux.c")
    descricao: str
    efeitos: list[EfeitoDescrito]


class Disparos(BaseModel):
    sessao: str
    ciclos: int
    disparos: dict[str, int]
    nunca_dispararam: list[str] = Field(
        description="Regras que os cenarios nao alcancam — pendencia registrada "
                    "em steps/03-regras-controle.md §7.")
