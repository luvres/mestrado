#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models.py — os contratos da API do reator.

Uma observacao sobre nomes: os campos usam snake_case, mas as CHAVES do dicionario
`estado` mantem os nomes originais do fonte (DeltaT, DesvioDeltaI, PosicaoBarra,
LimiteInsercao...). Isso e deliberado — o mapa das 19 regras em
steps/03-regras-controle.md usa esses nomes, e renomea-los aqui obrigaria a
traduzir mentalmente a cada leitura de regra.
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

TRANSIENTE = Literal[
    "runback-bap",     # desarme da bomba de agua de alimentacao principal -> 300 MW
    "runback-circ",    # desarme da bomba de agua de circulacao -> 400 MW
    "runback-400",
    "runback-300",
    "runback-150",
    "rampa",           # variacao lenta: exige alvo (MW) e taxa (MW/min) > 0
]


class ParametrosPartida(BaseModel):
    """Os 7 valores que o operador digita na partida, mais o cenario.

    Os padroes sao os do cenario 1 da dissertacao
    (`650 1800 210 4 -0.3 -0.8 0`, ver steps/01-porte-linux-simulador.md).
    """

    pot_turbina: float = Field(650, description="Potencia inicial da turbina (MW), 32 a 650")
    cboro: float = Field(1800, description="Concentracao inicial de boro (ppm)")
    posicao_barra: int = Field(210, description="Posicao inicial do banco de controle D (passos)")
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
    transiente: Optional[TRANSIENTE] = Field(None, description="Transiente de carga a injetar")
    t_transiente: int = Field(10, description="Minuto em que o transiente e aplicado")
    alvo: float = Field(0.0, description="Alvo de carga na turbina (MW) — so para rampa")
    taxa: float = Field(0.0, description="Taxa de variacao de carga (MW/min) — so para rampa")

    win_original: bool = Field(
        False,
        description="Semantica literal do original .txt no ramo Pbase<0 "
                    "(equivale a `gcc -DWIN_ORIGINAL`); ver steps/01.",
    )
    arquivo: Optional[str] = Field(
        None,
        description="Nome do arquivo de amostras. So o nome, sem diretorio — "
                    "ele e criado em SAIDA_DIR. Padrao: um nome por sessao.",
    )

    @model_validator(mode="after")
    def _rampa_exige_taxa(self):
        if self.transiente == "rampa" and self.taxa <= 0:
            raise ValueError("transiente 'rampa' exige alvo (MW) e taxa (MW/min) positiva")
        return self


class AcaoDiluir(BaseModel):
    """Tirar boro. Consequente de R1, R3 e R5.

    `vazao` (lpm) e decisao do controlador: R1 e R3 escolhem entre v1, v2 e a
    rampa -a.DeltaT+b conforme a faixa de DeltaT; R5 usa o dobro. A duracao nao
    vem aqui — e `tempodilute`, dado do operador que a planta ja conhece.
    """

    tipo: Literal["diluir"]
    vazao: float = Field(description="Vazao de diluicao em lpm")


class AcaoBorar(BaseModel):
    """Pôr boro. Consequente de R8, R10, R11 e R12.

    As quatro regras calculam VazaoBoro e Vboro por formulas diferentes. Os dois
    vem no corpo — e nao so Vboro, que e o unico que entra na fisica — porque
    VazaoBoro e variavel de estado do modelo, e o produto que gera Vboro tem de
    ser arredondado a 32 bits do lado de quem o calcula.
    """

    tipo: Literal["borar"]
    vazao_boro: float = Field(description="Vazao de boro em lpm (saturada em 20 na R8)")
    vboro: float = Field(description="Volume de boro em litros")


class AcaoBarra(BaseModel):
    """Mover o banco D. Consequente de R2, R4, R6, R7, R9 e R13 a R16."""

    tipo: Literal["barra"]
    passos: int = Field(description="Passos com sinal: +1, +2, -1 ou -2")


Acao = Annotated[Union[AcaoDiluir, AcaoBorar, AcaoBarra], Field(discriminator="tipo")]


class CorpoAcao(BaseModel):
    acao: Acao


class Resposta(BaseModel):
    """O que toda chamada que mexe na planta devolve."""

    sessao: str
    # Union, e nao float: com `dict[str, float]` o pydantic converteria
    # PosicaoBarra=210 em 210.0, desmentindo o que /reactor/tipos declara. O
    # cliente que confia no tipo para reproduzir o arredondamento do C receberia
    # float onde o C tem int. Na uniao em modo "smart" cada valor conserva o seu.
    estado: dict[str, Union[int, float]]
    saida_b64: str = Field(
        description="Os BYTES que ESTA chamada imprimiu, em base64. Quem fecha a "
                    "malha decodifica e concatena na ordem das chamadas, e obtem "
                    "byte a byte a saida padrao do simulador monolitico.\n\n"
                    "Base64, e nao texto, porque a saida do simulador e um fluxo "
                    "de BYTES e nao uma string: `printf(\"%c\",177)` no C escreve "
                    "UM byte (o '▒' do codepage 437), que nao e UTF-8 valido. "
                    "Esta planta em particular nunca emite esse byte — quem emite "
                    "sao as regras R18 e R19, do lado do expert — mas o campo tem "
                    "o mesmo contrato nos dois servicos, para que 'carrega os "
                    "bytes exatos desta chamada' valha sem ressalva.",
    )
    pode_continuar: bool = Field(
        description="t < tmax. E so METADE da condicao do laco original — a "
                    "outra metade (`termino != \"fim\"`) e posta por R19 e "
                    "pertence a quem controla.",
    )


class Sessao(BaseModel):
    sessao: str
    arquivo: str
    criada_em: str
    passos: int = Field(description="Quantas vezes /passo foi chamado")
    acoes: int = Field(description="Quantas atuacoes foram aplicadas")
