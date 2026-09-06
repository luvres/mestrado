#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regras.py — a base: as 19 regras como dado.

Cada regra e um registro, nao codigo. O antecedente e o texto C literal (ver
expressoes.py); o consequente e um dos QUATRO tipos fechados que a Varredura 1
do Passo 3 encontrou — diluir, borar, mover barra, alarmar — parametrizado por
expressoes que tambem sao texto C.

Este modulo nao executa nada. Quem interpreta os registros e motor.py, e essa
separacao e o ponto: a estrategia de resolucao de conflito (prioridade = ordem
do fonte, disparo multiplo por ciclo) fica num lugar so, explicita e trocavel,
em vez de estar diluida em 19 blocos `if`.

TRES FATOS ESTRUTURAIS QUE A BASE PRECISA REPRESENTAR

  1. A guarda e do BLOCO, avaliada uma vez na entrada — nao de cada regra.
     No fonte, `if (DeltaT<-0.1) CompensacaoQueima()` (L1168) e a primeira linha
     da funcao (L717) repetem a mesma guarda, e depois R1..R4 sao testadas em
     sequencia SEM reavaliar. Isso importa: se R1 dilui e ΔT sobe acima de -0,1,
     R2, R3 e R4 ainda sao avaliadas. Por isso Bloco tem guarda, e Regra nao.

  2. Consequente partido (steps/03 §5.4). Em R11 e R12 o alarme sai com a
     condicao externa, e a boracao so com a condicao externa E `DeltaI<0`. Sao,
     a rigor, dois consequentes com antecedentes distintos sob o mesmo
     cabecalho. Aqui isso e literal: a regra tem dois efeitos, e o segundo tem
     `quando`.

  3. A selecao de vazao e por FAIXA, e a rampa e descontinua nos extremos
     (steps/03 §5.5). Nao se interpola: testam-se os tres ramos em sequencia,
     como no fonte, e cada um que passa imprime e fixa a vazao.

O texto impresso faz parte da regra, e nao do efeito na planta: R1 e R5 mandam
a mesma diluicao e imprimem coisas diferentes. Por isso ele esta aqui.
"""

from expressoes import expressao

# ---------------------------------------------------------------------------
# Os quatro tipos de consequente
# ---------------------------------------------------------------------------


class Efeito:
    """Base. Subclasses sao registros; quem as executa e motor.py."""

    quando = None          # condicao extra do efeito (consequente partido)

    def _compila(self, quando):
        self.quando = expressao(quando)


class Diluir(Efeito):
    """Tirar boro. R1, R3, R5.

    `faixas` sao (condicao, vazao), testadas em sequencia. Uma faixa com
    condicao None e incondicional (R3, que nao escolhe: usa sempre v2).
    """

    tipo = "diluir"

    def __init__(self, faixas, texto, quando=None):
        self.faixas = [(expressao(c), expressao(v)) for c, v in faixas]
        self.texto = texto
        self._compila(quando)


class Borar(Efeito):
    """Por boro. R8, R10, R11, R12.

    `satura` e o teto da R8 (`if (VazaoBoro>20) VazaoBoro=20`). `volume` e
    avaliado com VazaoBoro ja no espaco de nomes — e por isso que ele aparece
    como `VazaoBoro*2` e nao com a formula repetida: o arredondamento a 32 bits
    do produto tem de acontecer sobre o valor ja saturado.
    """

    tipo = "borar"

    def __init__(self, vazao, volume, texto, satura=None, quando=None):
        self.vazao = expressao(vazao)
        self.volume = expressao(volume)
        self.texto = texto
        self.satura = satura
        self._compila(quando)


class MoverBarra(Efeito):
    """Mexer no banco D. R2, R4, R6, R7, R9, R13 a R16.

    `passos` segue a mesma forma de faixas de Diluir porque R9 escolhe entre -1
    e -2 dentro da mesma decisao de mover (steps/03 §4 e §5).
    """

    tipo = "barra"

    def __init__(self, passos, texto, quando=None):
        self.passos = [(expressao(c), expressao(p)) for c, p in passos]
        self.texto = texto
        self._compila(quando)


class Alarmar(Efeito):
    """Sinalizar sem atuar. R17, R18, R19.

    `cabecalho` e uma lista de (formato, grandeza-ou-None). `enche` e o numero
    de bytes 177 ('▒' do codepage 437) que o fonte imprime depois — 0 em R17,
    onde o laco esta comentado. `encerra` marca o fim de ciclo da R19.

    `despejo` distingue os DOIS tipos de alarme do simulador, e a distincao e
    real: R17, R18 e R19 despejam o bloco de estado inteiro (t, Z, Pot, Tmed...)
    depois do cabecalho; os alarmes de limite de insercao de R11 e R12 imprimem
    so a linha e seguem. O bloco em si esta em motor.py porque e identico nos
    tres que o usam — o que e dado da regra e SE ele sai.
    """

    tipo = "alarme"

    def __init__(self, cabecalho, enche=0, encerra=False, despejo=False, quando=None):
        self.cabecalho = cabecalho
        self.enche = enche
        self.encerra = encerra
        self.despejo = despejo
        self._compila(quando)


# ---------------------------------------------------------------------------
# Regra e Bloco
# ---------------------------------------------------------------------------


class Regra:
    def __init__(self, id, condicao, efeitos, linha_c, descricao):
        self.id = id
        self.condicao = expressao(condicao)
        self.efeitos = efeitos
        self.linha_c = linha_c          # linha do `if` no .c, para o teste de equivalencia
        self.descricao = descricao

    def __repr__(self):
        return "Regra(%s)" % self.id


class Bloco:
    """Um grupo de regras sob a mesma guarda de despacho."""

    def __init__(self, nome, regras, guarda=None, linha_guarda=None):
        self.nome = nome
        self.guarda = expressao(guarda)
        self.linha_guarda = linha_guarda
        self.regras = regras


# ---------------------------------------------------------------------------
# A BASE — prioridade = ordem de leitura, exatamente a ordem do fonte
# ---------------------------------------------------------------------------

# Textos repetidos em varias regras.
_DELTA_T = "\n\nDeltaT: %f\n\n"
_INICIA_DIL = "\n\nIniciada a Diluicao na Vazao de %.0f lpm"
_INICIA_DIL_DI = "\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm"

# As tres faixas de vazao de diluicao (L722, 727, 732 do .c). R5 usa as mesmas
# com o dobro (L790, 795, 800).
_FAIXAS = [("DeltaT >= t1", "v1"),
           ("DeltaT <= t2", "v2"),
           ("DeltaT > t2 && DeltaT < t1", "(-a*DeltaT)+b")]
_FAIXAS_DOBRO = [("DeltaT >= t1", "2*v1"),
                 ("DeltaT <= t2", "2*v2"),
                 ("DeltaT > t2 && DeltaT < t1", "2*((-a*DeltaT)+b)")]


BASE = [

    # =======================================================================
    Bloco("CompensacaoQueima", guarda="DeltaT < -0.1", linha_guarda=1168, regras=[
        # A guarda esta escrita DUAS vezes no fonte — L1168 e L717, primeira
        # linha da funcao. E redundante: a segunda nunca e falsa quando a
        # primeira passou. Aqui ela existe uma vez.

        Regra("R1", "(VariacaoDeltaI>=0 || DeltaT<-0.3) || (PosicaoBarra>=222 || DesvioDeltaI>-3)",
              [Diluir(_FAIXAS, _INICIA_DIL)],
              linha_c=720, descricao="diluir, vazao por faixa de DeltaT"),

        Regra("R2", "(DesvioDeltaI<0 && (VariacaoDeltaI<=0 || DeltaT<-0.3) && PosicaoBarra<222)",
              [MoverBarra([(None, "1")], "\n\nCOMPENSACAO DA QUEIMA POR RETIRADA DE BARRA\n\n")],
              linha_c=748, descricao="barra +1"),

        Regra("R3", "(DeltaT<-0.8) && (DesvioDeltaI>=0 || PosicaoBarra>=222)",
              [Diluir([(None, "v2")], _INICIA_DIL)],
              linha_c=757, descricao="diluir na vazao maxima v2"),

        Regra("R4", "(DeltaT<-0.8) && (DesvioDeltaI<4) && (PosicaoBarra<222)",
              [MoverBarra([(None, "2")], "\n\nCORRECAO DA TEMPERATURA MEDIA POR RETIRADA DE BARRA\n\n")],
              linha_c=773, descricao="barra +2"),
    ]),

    # =======================================================================
    Bloco("Corrige_DeltaI", guarda="DesvioDeltaI > 2 || DesvioDeltaI < -2",
          linha_guarda=1173, regras=[

        Regra("R5", "(DesvioDeltaI>=0 && DeltaT<=0.4) || (DesvioDeltaI>4.5 && DeltaT<2)",
              [Diluir(_FAIXAS_DOBRO, _INICIA_DIL_DI)],
              linha_c=789, descricao="diluir com vazao dobrada"),

        Regra("R6", "DesvioDeltaI<0 && DeltaT<0.8 && PosicaoBarra<222",
              [MoverBarra([(None, "1")], "\n\nCORRECAO DO DELTA I POR RETIRADA DE BARRA\n\n")],
              linha_c=816, descricao="barra +1"),

        Regra("R7", "(DeltaT>-0.6) && (DesvioDeltaI>4.5) && (PosicaoBarra>(LimiteInsercao+11) || DesvioDeltaI>5)",
              [MoverBarra([(None, "-1")], "\n\nCORRECAO DA DELTA I POR INSERCAO DE BARRA\n\n")],
              linha_c=826, descricao="barra -1"),

        Regra("R8", "((DesvioDeltaI<-4 && PosicaoBarra>=222) && DeltaT>-1) || (DesvioDeltaI<-10 && DeltaT>-3)",
              [Borar("(-DesvioDeltaI)*6", "VazaoBoro*2", "\n\nCORRECAO DO DELTA I POR BORACAO\n\n",
                     satura=20)],
              linha_c=838, descricao="borar, vazao saturada em 20 lpm"),
    ]),

    # =======================================================================
    Bloco("laco", guarda=None, regras=[

        Regra("R9", "(DeltaT>0.6) && (DesvioDeltaI>=-2.2) && (PosicaoBarra>(LimiteInsercao+11) || DeltaT>1.5)",
              [MoverBarra([("DeltaT < 1", "-1"), (None, "-2")],
                          "\n\nCORRECAO DA TEMPERATURA MEDIA POR INSERCAO DE BARRA\n\n")],
              linha_c=1176, descricao="barra -1 se DeltaT<1, senao -2"),

        Regra("R10", "(DeltaT>0.8) && (DesvioDeltaI<0)",
              [Borar("DeltaT*10", "VazaoBoro*4", "\n\nCORRECAO DO DELTA T POR BORACAO\n\n")],
              linha_c=1193, descricao="borar"),

        Regra("R11", "PosicaoBarra<=(LimiteInsercao+10) && PosicaoBarra>LimiteInsercao",
              [Alarmar([("\n\nALARME ATIVADO: LIMITE DE INSERCAO BAIXO\n\n", None)]),
               Borar("(LimiteInsercao-PosicaoBarra+11)*2", "VazaoBoro*2",
                     "\n\nLIMITE DE INSERCAO BAIXO ATINGIDO - BORACAO NORMAL\n\n",
                     quando="DeltaI<0")],
              linha_c=1206, descricao="alarme de limite baixo; borar se DeltaI<0"),

        Regra("R12", "PosicaoBarra<=LimiteInsercao",
              [Alarmar([("\n\nALARME ATIVADO: LIMITE DE INSERCAO MUITO BAIXO\n\n", None)]),
               Borar("(LimiteInsercao+1-PosicaoBarra)*5", "VazaoBoro*2",
                     "\n\nLIMITE DE INSERCAO MUITO BAIXO ATINGIDO - BORACAO DE EMERGENCIA\n\n",
                     quando="DeltaI<0")],
              linha_c=1224, descricao="alarme de limite muito baixo; boracao de emergencia se DeltaI<0"),

        Regra("R13", "(PosicaoBarra<(BD-3)) && (DesvioDeltaI<4.2) && (DeltaT<0.8)",
              [MoverBarra([(None, "1")], "\n\nCORRECAO DA POSICAO DE BARRA\n\n")],
              linha_c=1241, descricao="barra +1"),

        Regra("R14", "(PosicaoBarra>(BD+10)) && (DesvioDeltaI>=-3) && (DeltaT>-0.4)",
              [MoverBarra([(None, "-1")], "\n\nCORRECAO DA POSICAO DE BARRA\n\n")],
              linha_c=1250, descricao="barra -1"),

        Regra("R15", "(PosicaoBarra<(LimiteInsercao+11)) && (DesvioDeltaI<4) && (DeltaT<0.5)",
              [MoverBarra([(None, "1")], "\n\nCORRECAO DA POSICAO DE BARRA\n\n")],
              linha_c=1259, descricao="barra +1"),

        Regra("R16", "(PosicaoBarra>220) && (DesvioDeltaI>=-1.5) && (DeltaT>-0.25)",
              [MoverBarra([(None, "-1")], "\n\nCORRECAO DA POSICAO DE BARRA\n\n")],
              linha_c=1268, descricao="barra -1"),

        Regra("R17", "DesvioDeltaI>5 || DesvioDeltaI<-5",
              [Alarmar([("\n\n\n\t\t\t\t\tDELTA I: %f\n", "DeltaI"),
                        # o .c usa "%C" (glibc: alias de %lc); com 37 imprime '%'
                        ("\n\n\n\t\t\t\t\tALARME DE DELTA I FORA DA BANDA ALVO 5% \n", None),
                        ("t\t\t\t\t****************************************\n", None),
                        ("\t\t\t\t\t", None)],
                       enche=0, despejo=True)],   # o laco de '▒' esta comentado no fonte
              linha_c=1284, descricao="alarme de Delta I fora da banda alvo"),

        Regra("R18", "DeltaT>1.67 || DeltaT<-1.67",
              [Alarmar([("\n\n\n\t\t\t\t  TEMPERATURA MEDIA DO SRR: %.1f\n", "Tmed"),
                        ("\n\n\n\t\t\t\tO ALARME DESVIO DE TEMPERATURA 1,67°C\n", None),
                        ("t\t\t\t\t****************************************\n", None),
                        ("\t\t\t\t", None)],
                       enche=37, despejo=True)],
              linha_c=1306, descricao="alarme de desvio de temperatura 1,67 °C"),

        Regra("R19", "Cboro<8",
              [Alarmar([("\n\n\n\t\t\t\t\tO FIM DO CICLO - PARABENS!!!!!\n", None),
                        ("\t\t\t\t\t", None)],
                       enche=30, encerra=True, despejo=True)],
              linha_c=1327, descricao="fim do ciclo"),
    ]),
]


REGRAS = [r for b in BASE for r in b.regras]
POR_ID = {r.id: r for r in REGRAS}
BLOCO_DE = {r.id: b.nome for b in BASE for r in b.regras}
