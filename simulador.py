#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulador.py — porte fiel, em Python, de V8_Reatividade_SimuladorIgor_linux.c

Este arquivo NAO e uma reimplementacao do modelo: e uma transcricao linha a linha
do porte em C, que por sua vez e transcricao do codigo original do Igor
(V8_Reatividade_SimuladorIgor.txt). A ordem das funcoes, os nomes das variaveis,
a ordem das operacoes, os textos impressos e ate os comentarios do original foram
preservados. O criterio de aceitacao e byte a byte: a mesma linha de comando deve
produzir o mesmo Modelagem_Reator_py.txt e a mesma saida padrao que o binario C.

Para isso duas semanticas do C precisam ser emuladas explicitamente, porque o
Python so tem um tipo numerico de ponto flutuante (o `double` do C):

1. `float` de 32 bits. No C, a maioria das variaveis e `float`; as do Xe/Iodo sao
   `double`. Toda a decisao do modelo (diluir, borar, mover barra) sai de
   comparacoes de ponto flutuante, e a memoria do projeto registra que +-0,001 no
   ultimo decimal desloca um evento e desfaz a fase do resto da corrida. Logo,
   calcular tudo em `double` NAO reproduziria o C. Aqui:
     - a classe F embrulha um valor `float` de 32 bits e arredonda o resultado de
       cada operacao, como o gcc faz em SSE (FLT_EVAL_METHOD=0);
     - F op F  -> F ;  F op int -> F ;  F op double -> double  (regras do C89);
     - `Reator.__setattr__` arredonda no armazenamento, conforme o tipo declarado
       da variavel no C — e o que da a garantia, e nao a atencao do transcritor.

2. Conversao float->int truncando para zero, inclusive o caso patologico
   (inf/NaN -> valor "inteiro indefinido" do x86). Ver _para_int().

Diferencas deliberadas em relacao ao .c, todas sem efeito numerico:

 - `lambda` e palavra reservada em Python; virou `lambda_`.
 - `printf("%c",177)` emite UM byte 177 (o '▒' do codepage 437). Em Python o
   equivalente seria dois bytes em UTF-8, entao esses dois lacos usam
   putc_raw(b'\xb1'), que escreve o mesmo byte do C.
 - `#ifdef WIN_ORIGINAL` (macro de compilacao) virou a variavel de ambiente
   WIN_ORIGINAL=1, com o mesmo efeito de `gcc -DWIN_ORIGINAL`.

Uso — identico ao do binario C (ver steps/01-porte-linux-simulador.md):

    rm -f Modelagem_Reator_py.txt
    echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' \
        | python3 simulador.py --tmax=1440 > /dev/null
"""

import math
import os
import re
import struct
import sys

# ---------------------------------------------------------------------------
# Emulacao do `float` de 32 bits do C
# ---------------------------------------------------------------------------

_empacota_f = struct.Struct('f').pack
_desempacota_f = struct.Struct('f').unpack


def f32(x):
    """Arredonda um double para o `float` de 32 bits mais proximo — o que o C
    faz ao armazenar num `float` e ao concluir cada operacao entre `float`s."""
    try:
        return _desempacota_f(_empacota_f(x))[0]
    except OverflowError:                      # C satura em +-inf, sem excecao
        return math.inf if x > 0 else -math.inf


def _divide(a, b):
    """Divisao IEEE: no C, dividir por zero da +-inf ou NaN, nao uma excecao."""
    if b == 0.0:
        if a != a or a == 0.0:
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


class F(float):
    """Um `float` do C (32 bits).

    Herda de float para que comparacoes, `%`-formatacao e uso como argumento de
    funcao de <math.h> ja funcionem promovendo a double, exatamente como o C faz.
    Os operadores aritmeticos seguem as conversoes usuais do C89:
        F + F    -> F       (arredondado a 32 bits, como o SSE)
        F + int  -> F       (o int e convertido para float antes)
        F + float-> double  (o float e promovido; nao ha arredondamento)
    """
    __slots__ = ()

    def __new__(cls, x):
        return float.__new__(cls, f32(x))

    def __add__(self, o):
        if isinstance(o, F):
            return F(float(self) + float(o))
        if isinstance(o, int):
            return F(float(self) + o)
        return float(self) + o
    __radd__ = __add__

    def __sub__(self, o):
        if isinstance(o, F):
            return F(float(self) - float(o))
        if isinstance(o, int):
            return F(float(self) - o)
        return float(self) - o

    def __rsub__(self, o):
        if isinstance(o, F):
            return F(float(o) - float(self))
        if isinstance(o, int):
            return F(o - float(self))
        return o - float(self)

    def __mul__(self, o):
        if isinstance(o, F):
            return F(float(self) * float(o))
        if isinstance(o, int):
            return F(float(self) * o)
        return float(self) * o
    __rmul__ = __mul__

    def __truediv__(self, o):
        if isinstance(o, F):
            return F(_divide(float(self), float(o)))
        if isinstance(o, int):
            return F(_divide(float(self), o))
        return _divide(float(self), o)

    def __rtruediv__(self, o):
        if isinstance(o, F):
            return F(_divide(float(o), float(self)))
        if isinstance(o, int):
            return F(_divide(o, float(self)))
        return _divide(o, float(self))

    def __neg__(self):
        return F(-float(self))

    def __pos__(self):
        return self


_INT_INDEFINIDO = -2147483648


def _para_int(x):
    """Conversao float->int do C: trunca para zero. Fora da faixa de `int` (e em
    inf/NaN) o C tem comportamento indefinido; o x86 produz 0x80000000, que e o
    que se reproduz aqui em vez de levantar OverflowError."""
    if isinstance(x, int):
        return x
    x = float(x)
    if x != x or x >= 2147483648.0 or x < -2147483648.0:
        return _INT_INDEFINIDO
    return int(x)


# ---------------------------------------------------------------------------
# Substitutos de <stdio.h> / <stdlib.h>
# ---------------------------------------------------------------------------

_saida = sys.stdout.buffer


def printf(fmt, *args):
    _saida.write((fmt % args if args else fmt).encode('utf-8'))


def putc_raw(b):
    """printf("%c", n) com n>127: o C escreve UM byte, nao UTF-8."""
    _saida.write(b)


def fprintf_stderr(fmt, *args):
    sys.stdout.flush()
    sys.stderr.write(fmt % args if args else fmt)


_RE_FLOAT = re.compile(r'\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')
_RE_INT = re.compile(r'\s*[+-]?\d+')


def atof(s):
    m = _RE_FLOAT.match(s)
    return float(m.group(0)) if m else 0.0


def atoi(s):
    m = _RE_INT.match(s)
    return int(m.group(0)) if m else 0


def _fluxo_entrada():
    for linha in sys.stdin:
        for token in linha.split():
            yield token


_entrada = _fluxo_entrada()


def _token():
    try:
        return next(_entrada)
    except StopIteration:
        return None            # EOF: o scanf do C deixa a variavel intacta


def scanf_float(atual):
    t = _token()
    return atual if t is None else atof(t)


def scanf_int(atual):
    t = _token()
    return atual if t is None else atoi(t)


def scanf_str(atual):
    t = _token()
    return atual if t is None else t[:15]      # "%15s"


# Substituir funcoes do conio.h para Linux
def getch():
    return _token()


def kbhit():
    return 0                   # Sempre retorna 0 (sem tecla pressionada)


def system_color():
    pass                       # Funcao vazia - sem cores no Linux


# Semantica literal do original .txt, equivalente a `gcc -DWIN_ORIGINAL`
WIN_ORIGINAL = os.environ.get('WIN_ORIGINAL', '') not in ('', '0')


# Injecao nao-interativa de transiente de carga (via linha de comando).
# O caminho interativo original (digitar "v") permanece intacto; os dois
# caminhos chamam os mesmos helpers AplicaRunback()/AplicaRampa().
TR_NENHUM = 0
TR_RUNBACK_BAP = 1     # desarme da bomba de agua de alimentacao principal -> 300 MW
TR_RUNBACK_CIRC = 2    # desarme da bomba de agua de circulacao -> 400 MW
TR_RUNBACK_400 = 3
TR_RUNBACK_300 = 4
TR_RUNBACK_150 = 5
TR_RAMPA = 6           # variacao lenta: --alvo=<MW> --taxa=<MW/min>


class Reator:
    """As variaveis globais do C e as funcoes que operam sobre elas.

    Os tres conjuntos abaixo repetem o bloco de declaracoes do .c. Sao eles que
    fazem `__setattr__` aplicar a semantica de armazenamento do C: arredondar
    para 32 bits num `float`, truncar para zero num `int`.
    """

    _FLOAT = frozenset("""
        Tref Tmedantes Tmed VariacaoTmed DeltaIantes DeltaI AlvoDeltaI
        DesvioDeltaI VariacaoDeltaI Cboro Cboro1 DeltaT Vazao Vagua VaguaTemp
        t1 t2 v1 v2 a b t ty valor razao Msrr alfaboro alfamoderador thom
        betaeff Ptopo Ptopo0 Pbase Pbase0 Pbase1 erazao Deltaro Trx lambda_
        inversoTrx DeltaPbase DeltaPtopo Pot taxatempreal y Vboro VazaoBoro
        LimiteInsercao ConvertXe_Ro Ro RoAntes PbaseAntes PotAntes erro
        DefPotAntes DefPot PotAlvo AlvoTurbina AlvoTref TaxaTurbina ModuloTref
        ModuloTaxa PotTurbina PotTurbinaTemp argAlvo argTaxa
    """.split())

    _INT = frozenset("""
        PosicaoBarra DeltaBarra tempo Retira1passo correcao aux i tempodilute
        x diferenca taxatemp z tXe BD Runbackmanual
        transienteTipo tTransiente transienteAplicado
    """.split())

    _DOUBLE = frozenset("""
        tmax Nxeb Nxeg Nxe0 Nxeg0 NxeAntes lambdaXe sigmaXe Fnb Fnb0 Fng Fng0
        gamaI Sigmaf gamaXe lambdaI Ni0 Nig0 Nib Nig
    """.split())

    def __setattr__(self, nome, v):
        if nome in self._FLOAT:
            v = F(v)
        elif nome in self._INT:
            v = _para_int(v)
        elif nome in self._DOUBLE:
            v = float(v)
        object.__setattr__(self, nome, v)

    def __init__(self):
        # Variaveis globais do C: duracao estatica, zero-inicializadas.
        for nome in self._FLOAT:
            setattr(self, nome, 0)
        for nome in self._INT:
            setattr(self, nome, 0)
        for nome in self._DOUBLE:
            setattr(self, nome, 0)
        # Inicializadores explicitos do .c
        self.transienteTipo = TR_NENHUM
        self.tTransiente = 10        # minuto de aplicacao do transiente
        self.transienteAplicado = 0
        self.tmax = 700000           # limite de horizonte da simulacao (minutos)
        self.termino = ''            # char termino[10]
        self.TipoVariacao = ''       # char TipoVariacao[16]
        self.Runback = ''            # char Runback[16]
        self.funcaocarga = ''        # char funcaocarga[16]

    # -----------------------------------------------------------------------

    def GravaDados(self):
        try:
            arquivo = open("Modelagem_Reator_py.txt", "a", encoding="utf-8")
        except OSError:
            printf("Problemas na abertura do arquivo!\n")
            sys.exit(1)
        else:
            arquivo.write("%.0f       %.2f     %.1f          %.1f      %.3f"
                          "        %.0f       %d     %.0f\n"
                          % (self.t, self.Pot, self.PotTurbina, self.Tmed,
                             self.DeltaI, self.Cboro, self.PosicaoBarra,
                             self.VaguaTemp))
        arquivo.close()
        return

    # Helpers extraidos de VariacaodeCarga(): mesmo estado para o caminho
    # interativo e para a injecao automatica.

    def AplicaRunback(self, trefNovo, alvoTrefNovo):
        trefNovo, alvoTrefNovo = F(trefNovo), F(alvoTrefNovo)   # parametros float
        self.Tref = trefNovo
        self.AlvoTref = alvoTrefNovo
        self.PotAlvo = (self.Tref - 291.7) / 0.113
        self.y = self.t
        self.ty = self.t
        self.tXe = 0
        self.RoAntes = self.Ro
        self.Nig0 = self.Nig
        self.Nxeg0 = self.Nxeg
        return

    def AplicaRampa(self, alvoTurbina, taxa):
        alvoTurbina, taxa = F(alvoTurbina), F(taxa)             # parametros float
        self.AlvoTurbina = alvoTurbina
        self.TaxaTurbina = taxa
        self.AlvoTref = 291.7 + (0.0173846 * self.AlvoTurbina)
        self.ModuloTref = (self.AlvoTref - self.Tref)
        self.ModuloTaxa = self.TaxaTurbina
        if self.AlvoTref < self.Tref:

            self.TaxaTurbina = -self.TaxaTurbina

            self.ModuloTref = -(self.AlvoTref - self.Tref)
        self.y = self.t
        self.ty = self.t
        self.tXe = 0
        self.RoAntes = self.Ro
        self.Nig0 = self.Nig
        self.Nxeg0 = self.Nxeg
        return

    # Aplica o transiente escolhido por linha de comando, com as mesmas
    # guardas de potencia usadas no menu interativo.
    def AplicaTransienteAuto(self):
        if self.transienteTipo == TR_RUNBACK_BAP:
            if self.PotTurbina > 301:
                self.AplicaRunback(296.92, 296.92)
        elif self.transienteTipo == TR_RUNBACK_CIRC:
            if self.PotTurbina > 401:
                self.AplicaRunback(298.65, 298.65)
        elif self.transienteTipo == TR_RUNBACK_400:
            if self.PotTurbina > 401:
                self.AplicaRunback(298.65, 298.5)
        elif self.transienteTipo == TR_RUNBACK_300:
            if self.PotTurbina > 301:
                self.AplicaRunback(296.92, 296.92)
        elif self.transienteTipo == TR_RUNBACK_150:
            if self.PotTurbina > 150:
                self.AplicaRunback(294.31, 294.31)
        elif self.transienteTipo == TR_RAMPA:
            self.AplicaRampa(self.argAlvo, self.argTaxa)
        return

    def VariacaodeCarga(self):

        printf("\n\nVariacao de Carga Rapida ou Lenta%c (r/l): ", 63)
        self.TipoVariacao = scanf_str(self.TipoVariacao)

        if self.TipoVariacao == "r":

            printf("\n\nDesarme Bomba de Agua de Agua de Alimentacao Principal%c (s/n): ", 63)
            self.Runback = scanf_str(self.Runback)
            if self.Runback == "s":
                if self.PotTurbina > 301:
                    printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO DESARME DA BOMBA DE AGUA DE ALIMENTACAO PRINCIPAL")
                    printf("\nPOTENCIA DA TURBINA: 300MW")
                    printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN", 37)
                    self.AplicaRunback(296.92, 296.92)
                else:
                    printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO")
                return

            printf("\n\nDesarme Bomba de Agua de Circulacao%c (s/n): ", 63)
            self.Runback = scanf_str(self.Runback)
            if self.Runback == "s":
                if self.PotTurbina > 401:
                    printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO DESARME DA BOMBA DE AGUA DE CIRCULACAO")
                    printf("\nPOTENCIA DA TURBINA: 400MW")
                    printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN", 37)
                    self.AplicaRunback(298.65, 298.65)
                else:
                    printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO")
                return

            printf("\n\nReducao Rapida de Carga Manual%c (400/300/150 ou n para nao): ", 63)
            self.Runbackmanual = scanf_int(self.Runbackmanual)

            if self.Runbackmanual == 400:
                if self.PotTurbina > 401:
                    printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO RUNBACK PARA 400 MW")
                    printf("\nPOTENCIA DA TURBINA: 400MW")
                    printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN", 37)
                    self.AplicaRunback(298.65, 298.5)  # AlvoTref=298.5 e do original (aparente typo, preservado)
                else:
                    printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO")
                return

            if self.Runbackmanual == 300:
                if self.PotTurbina > 301:
                    printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO RUNBACK PARA 300 MW")
                    printf("\nPOTENCIA DA TURBINA: 300MW")
                    printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN", 37)
                    self.AplicaRunback(296.92, 296.92)
                else:
                    printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO")
                return

            if self.Runbackmanual == 150:
                if self.PotTurbina > 150:
                    printf("\n\nREDUCAO RAPIDA DE CARGA DEVIDO AO RUNBACK PARA 150 MW")
                    printf("\nPOTENCIA DA TURBINA: 150MW")
                    printf("\nREDUCAO DE POTENCIA DO REATOR EM ANDAMENTO NA TAXA DE 5%c/MIN", 37)
                    self.AplicaRunback(294.31, 294.31)
                else:
                    printf("\n\nPOTENCIA DA TURBINA NO VALOR ALVO")
                return

        if self.TipoVariacao == "l":

            printf("\n\nDigite o Valor Alvo de Carga na Turbina em MW: ")
            self.AlvoTurbina = scanf_float(self.AlvoTurbina)

            printf("\nDigite a Taxa de Variacao de Carga na Turbina em MW/min: ")
            self.TaxaTurbina = scanf_float(self.TaxaTurbina)

            self.AplicaRampa(self.AlvoTurbina, self.TaxaTurbina)

    def CalculaAlvoDeltaI(self):

        # if (Cboro>=1440) {
        # AlvoDeltaI= (71.43-Pot)/28.57; }

        if self.Cboro >= 1080:
            self.AlvoDeltaI = self.Pot / 100          # (71.43-Pot)/28.57;

        # if (Cboro<1440 && Cboro>=1080) {
        # AlvoDeltaI= (57.14-Pot)/28.57; }

        if self.Cboro < 1080 and self.Cboro >= 720:
            self.AlvoDeltaI = (57.14 - self.Pot) / 28.57

        # if (Cboro<1080 && Cboro>=720) {
        # AlvoDeltaI= (42.86-Pot)/28.57; }

        # if (Cboro<720 && Cboro>=360) {
        # AlvoDeltaI= (28.57-Pot)/28.57; }

        # if (Cboro<360) {
        # AlvoDeltaI= (14.29-Pot)/28.57; }

        if self.Cboro < 720:
            self.AlvoDeltaI = (42.86 - self.Pot) / 28.57

        return

    def CalculaDeltaI(self):

        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI
        self.DeltaIantes = self.DeltaI
        printf("\n\nPbase: %f", self.Pbase)
        printf("\n\nPtopo: %f", self.Ptopo)
        # printf("\n\nPbaseAntes: %f", PbaseAntes);
        printf("\n\nPbase/PbaseAntes: %f", self.Pbase / self.PbaseAntes)
        printf("\n\nerro: %f", self.erro)
        self.Fnb = self.Fnb0 * (self.Pbase / self.PbaseAntes)  # ((Pbase/PbaseAntes)-erro)
        printf("\n\nFnb: %f", self.Fnb)

        # printf("\nPotencia na Base do Reator Antes da Oscilacao do Xe: %f%c",Pbase,37);
        # printf("\nPotencia no Topo do Reator Antes da Oscilacao do Xe: %f%c",Ptopo,37);
        printf("\nDelta I Antes da Oscilacao do Xe: %f", self.DeltaI)

        # EQUAÇÃO DO XENONIO E IODO- BASE

        self.NxeAntes = self.Nxeb

        self.Nib = (self.Ni0 * math.pow(2.7182818282, ((-self.lambdaI) * (self.z * 60)))
                    + (self.gamaI * self.Sigmaf * self.Fnb)
                    * (1 - math.pow(2.7182818282, ((-self.lambdaI) * (self.z * 60)))) / self.lambdaI)

        self.Nxeb = ((self.Nxe0 * (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fnb) * (self.z * 60)))))
                     + ((self.gamaI + self.gamaXe) * self.Sigmaf * self.Fnb
                        * (1 - (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fnb) * (self.z * 60)))))
                        / (self.lambdaXe + self.sigmaXe * self.Fnb))
                     + ((self.gamaI * self.Sigmaf * self.Fnb - self.lambdaI * self.Ni0)
                        * ((math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fnb) * (self.z * 60))))
                           - (math.pow(2.7182818282, (-(self.lambdaI * (self.z * 60))))))
                        / (self.lambdaXe - self.lambdaI + self.sigmaXe * self.Fnb)))

        # printf("\n\nValor da concentracao do Iodo: %f", Nib);
        # printf("\n\nValor da concentracao do Xe: %f", Nxeb);

        # REGRA DE CONVERSÃO DA CONCENTRAÇÃO DE Xe PARA REATIVIDADE - BASE

        self.RoAntes = self.NxeAntes * self.ConvertXe_Ro
        self.Ro = self.Nxeb * self.ConvertXe_Ro
        printf("\n\nRoAntes: %f", self.RoAntes)
        printf("\n\nRo: %f", self.Ro)
        self.Deltaro = self.Ro - self.RoAntes
        if self.Deltaro > 400:
            self.Deltaro = 400
        if (self.Deltaro < 0.0001 and self.Deltaro > -0.0001) or self.DeltaI == 0:
            self.Deltaro = 0

        # printf("\nValor de Reatividade Devido ao Xe: %f", Ro);
        printf("\nValor do Delta de Reatividade Devido ao Xe: %f\n", self.Deltaro)

        # ALTERAÇÃO Pbase

        if self.Deltaro != 0:
            self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
            printf("\nTrx: %f\n", self.Trx)
            self.Pbase0 = self.Pbase
            self.inversoTrx = 1 / self.Trx
            self.Pbase = self.Pbase * math.pow(2.72, self.inversoTrx)
            if self.Pbase < 0:
                self.Pbase = 0
            self.DeltaPbase = self.Pbase - self.Pbase0
            self.Ptopo = self.Ptopo - self.DeltaPbase
            if self.Ptopo < 0:
                self.Ptopo = 0

        # NOVO DELTA I

        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI
        self.VariacaoDeltaI = self.DeltaI - self.DeltaIantes

        printf("\nPotencia na Base do Reator Apos a Oscilacao do Xe: %f%c", self.Pbase, 37)
        printf("\nPotencia no Topo do Reator Apos a Oscilacao do Xe: %f%c", self.Ptopo, 37)
        # printf("\nPotencia no Topo do Reator Apos a Oscilacao do Xe: %f%c",Ptopo,37);
        printf("\nDelta I Apos a Oscilacao do Xe: %f\n", self.DeltaI)

        # printf("\nNxeAntes: %f\n",NxeAntes);
        # printf("\nNxeb: %f\n",Nxeb);

        if (self.Nxeb - self.NxeAntes) < 1000 and (self.Nxeb - self.NxeAntes) > -1000:

            self.atualizadadosXe()

        # ALTERA A POTENCIA DO REATOR DEVIDO AO EFEITO GLOBAL DO XE DEVIDO A TRANSIENTES DE CARGA
        # if (tXe<4320) {
        printf("\n\nFngAntes: %f", self.Fng)
        self.Fng = self.Fng0 * (self.Pot / self.PotAntes)
        printf("\n\nPot/PotAntes: %f", self.Pot / self.PotAntes)
        printf("\n\nFng: %f", self.Fng)
        printf("\n\ntXe: %d", self.tXe)

        self.NxeAntes = self.Nxeg

        self.Nig = (self.Nig0 * math.pow(2.7182818282, ((-self.lambdaI) * (self.tXe * 60)))
                    + (self.gamaI * self.Sigmaf * self.Fng)
                    * (1 - math.pow(2.7182818282, ((-self.lambdaI) * (self.tXe * 60)))) / self.lambdaI)

        self.Nxeg = ((self.Nxeg0 * (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fng) * (self.tXe * 60)))))
                     + ((self.gamaI + self.gamaXe) * self.Sigmaf * self.Fng
                        * (1 - (math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fng) * (self.tXe * 60)))))
                        / (self.lambdaXe + self.sigmaXe * self.Fng))
                     + ((self.gamaI * self.Sigmaf * self.Fng - self.lambdaI * self.Nig0)
                        * ((math.pow(2.7182818282, (-(self.lambdaXe + self.sigmaXe * self.Fng) * (self.tXe * 60))))
                           - (math.pow(2.7182818282, (-(self.lambdaI * (self.tXe * 60))))))
                        / (self.lambdaXe - self.lambdaI + self.sigmaXe * self.Fng)))

        self.RoAntes = self.NxeAntes * self.ConvertXe_Ro
        self.Ro = self.Nxeg * self.ConvertXe_Ro
        printf("\n\nRoAntes: %f", self.RoAntes)
        printf("\n\nRo: %f", self.Ro)
        self.Deltaro = self.Ro - self.RoAntes
        if self.Deltaro > 400:
            self.Deltaro = 400
        if (self.Deltaro < 0.0001 and self.Deltaro > -0.0001) or self.DeltaI == 0:
            self.Deltaro = 0
        # Defeito de Potência Antes da Variação Devido ao Xe
        self.DefPotAntes = (self.Cboro - 3806.7024) * self.Pot / 150.88

        # printf("\nValor de Reatividade Devido ao Xe: %f", Ro);
        printf("\nValor do Delta de Reatividade Devido ao Xe: %f\n", self.Deltaro)
        if self.Deltaro != 0:
            self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
            printf("\nTrxPot: %f\n", self.Trx)
            printf("\nPotencia do Reator Antes do Variacao do Xe: %f\n", self.Pot)
            self.inversoTrx = 1 / self.Trx
            self.Pot = self.Pot * math.pow(2.72, self.inversoTrx)
            if self.Pot < 0:
                self.Pot = 0
            self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
            self.Pbase = (2 * self.Pot - self.DeltaI) / 2
            self.PbaseAntes = self.Pot
            if self.Pot != 0:
                self.erro = self.DeltaI * ((1 / self.PotAntes) - (1 / self.Pot))
            printf("\nPotencia variando devido ao Xe: %f\n", self.Pot)
            self.DefPot = (self.Cboro - 3806.7024) * self.Pot / 150.88
            printf("\nTemperatura Media Antes da Variacao do Xe: %.1f\n", self.Tmed)
            self.Tmed = self.Tmed + ((self.DefPot - self.DefPotAntes) / self.alfamoderador)
            printf("\nTemperatura Media Apos da Variacao de Potencia Devido ao Xe: %.1f\n", self.Tmed)
            # getch();
        if (((self.Nxeb - self.NxeAntes) < 1000 and (self.Nxeb - self.NxeAntes) > -1000)
                or self.tXe >= 4320):

            self.atualizadadosXeg()

        return

    def atualizadadosXe(self):

        printf("\n\nATUALIZA DADOS")
        self.z = 0
        self.RoAntes = self.Ro
        self.Ni0 = self.Nib
        self.Nxe0 = self.Nxeb
        return

    def atualizadadosXeg(self):

        printf("\n\nATUALIZA DADOS GLOBAIS")
        self.tXe = 0
        self.RoAntes = self.Ro
        self.Nig0 = self.Nig
        self.Nxeg0 = self.Nxeg
        return

    # Funcoes Diluicao

    def CorrigeTmedDiluicao(self):
        printf("\n\nVolume de agua pura adicionado: %.0f", self.Vagua)
        self.Cboro1 = self.Cboro
        printf("\n\nConcentracao de Boro do SRR Antes da Diluicao: %f ppm", self.Cboro1)
        self.razao = self.Vagua / self.Msrr
        self.erazao = math.pow(2.72, self.razao)
        self.Cboro = self.Cboro / (self.erazao)
        printf("\nConcentracao de Boro do SRR Apos a Diluicao: %f ppm", self.Cboro)
        # ATUALIZACAO DOS PARAMETROS QUE VARIAM COM A CONCENTRACAO DE BORO
        printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d\n", self.taxatemp)
        self.alfamoderador = 0.02849 * self.Cboro - 75.02849
        printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C", self.alfamoderador)
        self.alfaboro = 0.0005363 * self.Cboro - 7.285363
        printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n", self.alfaboro)
        self.v1 = -0.05307 * self.Cboro + 100.5307
        if self.v1 <= 0:
            self.v1 = 5
        printf("\nValor da Vazao de Diluicao Minima: %.0f lpm", self.v1)
        self.v2 = -0.24022 * self.Cboro + 452.24022
        if self.v2 <= 0:
            self.v2 = 10
        printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", self.v2)
        self.a = 2 * self.v1
        printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f", self.a)
        self.b = self.v1
        printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n", self.b)
        printf("\nPosicao do Banco de Controle D: %d\n", self.PosicaoBarra)
        # FIM DA ATUALIZACAO CBORO

        self.Deltaro = (self.Cboro - self.Cboro1) * self.alfaboro
        printf("\n\nVariacao de Reatividade Devido a Diluicao: %f pcm", self.Deltaro)
        printf("\n\n\nATENCAO: O SRR ESTA AQUECENDO DEVIDO A DILUICAO\n\n")
        self.i = _para_int(self.thom)
        while self.i > 0:
            self.Tmedantes = self.Tmed
            self.Tmed = (-(self.Deltaro / self.thom) / self.alfamoderador) + self.Tmed
            self.aux = self.thom + 1 - self.i
            printf("\nTmed%d: %f °C", self.aux, self.Tmed)
            self.DeltaT = self.Tmed - self.Tref
            self.VariacaoTmed = self.Tmed - self.Tmedantes
            # sleep(1);
            self.t = self.t + 1
            self.z = self.z + 1
            self.tXe = self.tXe + 1
            self.i = self.i - 1
        printf("\n\n\nA ESTABILIZACAO DA TEMPERATURA DO SRR FOI ATINGIDA\n\n")
        printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",
               self.Tmed, self.DeltaT)
        return

    def CorrigeDeltaIDiluicao(self):
        self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
        printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f", self.Trx)
        self.Pbase0 = self.Pbase
        printf("\nPotencia na Base do Reator Antes da Diluicao: %f%c", self.Pbase, 37)
        self.inversoTrx = 1 / self.Trx
        self.Pbase1 = self.Pbase * math.pow(2.72, self.inversoTrx)
        self.DeltaPbase = (self.Pbase1 - self.Pbase0) * 0.9
        self.Pbase = self.Pbase + self.DeltaPbase
        if self.Pbase < 0:
            self.Pbase = 0
        printf("\nPotencia na Base do Reator Apos da Diluicao: %f%c", self.Pbase, 37)
        self.Ptopo = self.Ptopo - self.DeltaPbase
        if self.Ptopo < 0:
            self.Ptopo = 0
        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI

        # CALCULA DELTA I Xe APÓS DILUIÇÃO

        self.CalculaDeltaI()

        return

    # Funcões Boração

    def CorrigeTmedBoracao(self):
        printf("\n\nVolume de Boro adicionado: %.0f", self.Vboro)
        self.Cboro1 = self.Cboro
        printf("\n\nConcentracao de Boro do SRR Antes da Boracao: %f ppm", self.Cboro1)
        self.razao = -self.Vboro / self.Msrr
        self.erazao = math.pow(2.72, self.razao)
        self.Cboro = 7200 - (7200 - self.Cboro) * self.erazao
        printf("\nConcentracao de Boro do SRR Apos a Boracao: %f ppm", self.Cboro)

        # ATUALIZACAO DOS PARAMETROS QUE VARIAM COM A CONCENTRACAO DE BORO
        self.taxatempreal = (2601 - self.Cboro) / 6.31   # (2619-Cboro)/6.16;
        self.taxatemp = self.taxatempreal                # tempo de redução de 0,1ºC
        printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d\n", self.taxatemp)
        self.alfamoderador = 0.02849 * self.Cboro - 75.02849
        printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C", self.alfamoderador)
        self.alfaboro = 0.0005363 * self.Cboro - 7.285363
        printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n", self.alfaboro)
        self.v1 = -0.05307 * self.Cboro + 100.5307
        if self.v1 <= 0:
            self.v1 = 5
        printf("\nValor da Vazao de Diluicao Minima: %.0f lpm", self.v1)
        self.v2 = -0.24022 * self.Cboro + 452.24022
        if self.v2 <= 0:
            self.v2 = 10
        printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", self.v2)
        self.a = 2 * self.v1
        printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f", self.a)
        self.b = self.v1
        printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n", self.b)
        printf("\nPosicao do Banco de Controle D: %d\n", self.PosicaoBarra)
        # FIM DA ATUALIZACAO CBORO

        self.Deltaro = (self.Cboro - self.Cboro1) * self.alfaboro
        printf("\n\nVariacao de Reatividade Devido a Boracao: %f pcm", self.Deltaro)
        printf("\n\n\nATENCAO: O SRR ESTA RESFRIANDO DEVIDO A BORACAO\n\n")
        self.i = _para_int(self.thom)
        while self.i > 0:
            self.Tmedantes = self.Tmed
            self.Tmed = (-(self.Deltaro / self.thom) / self.alfamoderador) + self.Tmed
            self.aux = self.thom + 1 - self.i
            printf("\nTmed%d: %f °C", self.aux, self.Tmed)
            self.DeltaT = self.Tmed - self.Tref
            self.VariacaoTmed = self.Tmed - self.Tmedantes
            # sleep(1);
            self.t = self.t + 1
            self.z = self.z + 1
            self.tXe = self.tXe + 1
            self.i = self.i - 1
        printf("\n\n\nA ESTABILIZACAO DA TEMPERATURA DO SRR FOI ATINGIDA\n\n")
        printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",
               self.Tmed, self.DeltaT)
        return

    def CorrigeDeltaIBoracao(self):
        self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
        printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f", self.Trx)
        self.Pbase0 = self.Pbase
        printf("\nPotencia na Base do Reator Antes da Boracao: %f%c", self.Pbase, 37)
        self.inversoTrx = 1 / self.Trx
        self.Pbase1 = self.Pbase * math.pow(2.72, self.inversoTrx)
        self.DeltaPbase = (self.Pbase1 - self.Pbase0) * 1.6
        self.Pbase = self.Pbase + self.DeltaPbase
        if self.Pbase < 0:
            self.Pbase = 0
        printf("\nPotencia na Base do Reator Apos da Boracao: %f%c", self.Pbase, 37)
        self.Ptopo = self.Ptopo - self.DeltaPbase
        if self.Ptopo < 0:
            self.Ptopo = 0
        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI

        # CALCULA DELTA I Xe APÓS BORAÇÃO

        self.CalculaDeltaI()

        return

    # Funcoes DeltaBarra

    def CorrigeTmedDeltaBarra(self):

        if self.PosicaoBarra >= 100:
            self.Deltaro = 6.5 * self.DeltaBarra
        else:
            self.Deltaro = 20 * self.DeltaBarra
        self.DeltaBarra = 0
        printf("\n\nVARIACAO DE REATIVIDADE DEVIDO A MOVIMENTACAO DE BARRA: %f pcm", self.Deltaro)
        self.Tmedantes = self.Tmed
        printf("\nTemperatura Media antes da Movimentacao de Barra: %f °C", self.Tmed)
        self.Tmed = (-(self.Deltaro / self.alfamoderador)) + self.Tmed
        self.DeltaT = self.Tmed - self.Tref
        self.VariacaoTmed = self.Tmed - self.Tmedantes
        # sleep(1);
        self.t = self.t + 2
        self.z = self.z + 2
        self.tXe = self.tXe + 2
        printf("\n\nTemperatura Media do SRR: %.2f °C  // Diferenca Tmed - Tref (DeltaT): %f °C \n\n",
               self.Tmed, self.DeltaT)
        return

    def CorrigeDeltaIDeltaBarra(self):
        self.Trx = (self.betaeff - self.Deltaro) / (self.lambda_ * self.Deltaro)
        printf("\nPeriodo do Reator Devido a Insercao de Reatividade: %f", self.Trx)
        self.Ptopo0 = self.Ptopo
        printf("\nPotencia no Topo do Reator Antes da Movimentacao de Barra: %f%c", self.Ptopo, 37)
        self.inversoTrx = 1 / self.Trx
        self.Ptopo = self.Ptopo * math.pow(2, self.inversoTrx)
        self.DeltaPtopo = self.Ptopo - self.Ptopo0
        printf("\nPotencia no Topo do Reator Apos da Movimentacao de Barra: %f%c", self.Ptopo, 37)
        self.Pbase = self.Pbase - self.DeltaPtopo
        self.DeltaI = self.Ptopo - self.Pbase
        self.DesvioDeltaI = self.DeltaI - self.AlvoDeltaI
        # CALCULA DELTA I Xe APÓS DILUIÇÃO

        self.CalculaDeltaI()

        return

    # Funcao Compensacao da Queima

    def CompensacaoQueima(self):

        if self.DeltaT < -0.1:
            # if (VariacaoTmed <=0) {

            if ((self.VariacaoDeltaI >= 0 or self.DeltaT < -0.3)
                    or (self.PosicaoBarra >= 222 or self.DesvioDeltaI > -3)):

                if self.DeltaT >= self.t1:
                    self.Vazao = self.v1
                    printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                    printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                    self.tempo = self.t
                if self.DeltaT <= self.t2:
                    self.Vazao = self.v2
                    printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                    printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                    self.tempo = self.t
                if self.DeltaT > self.t2 and self.DeltaT < self.t1:
                    self.Vazao = (-self.a * self.DeltaT) + self.b
                    printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                    printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                    self.tempo = self.t
                # sleep(1); //tempodilute
                self.t = self.t + self.tempodilute
                self.z = self.z + self.tempodilute
                self.tXe = self.tXe + self.tempodilute
                printf("\n\nDiluicao Encerrada")
                self.Vagua = self.Vazao * (self.t - self.tempo)
                self.Vazao = 0
                self.VaguaTemp = self.Vagua + self.VaguaTemp
                self.CorrigeTmedDiluicao()
                self.CorrigeDeltaIDiluicao()
            if (self.DesvioDeltaI < 0
                    and (self.VariacaoDeltaI <= 0 or self.DeltaT < -0.3)
                    and self.PosicaoBarra < 222):
                printf("\n\nCOMPENSACAO DA QUEIMA POR RETIRADA DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                self.PosicaoBarra = self.PosicaoBarra + 1
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
                self.DeltaBarra = 1
                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

            if (self.DeltaT < -0.8) and (self.DesvioDeltaI >= 0 or self.PosicaoBarra >= 222):
                self.Vazao = self.v2
                printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                printf("\n\nIniciada a Diluicao na Vazao de %.0f lpm", self.Vazao)
                self.tempo = self.t
                # sleep(1); //tempodilute
                self.t = self.t + self.tempodilute
                self.z = self.z + self.tempodilute
                self.tXe = self.tXe + self.tempodilute
                printf("\n\nDiluicao Encerrada")
                self.Vagua = self.Vazao * (self.t - self.tempo)
                self.Vazao = 0
                self.VaguaTemp = self.Vagua + self.VaguaTemp
                self.CorrigeTmedDiluicao()
                self.CorrigeDeltaIDiluicao()
            if (self.DeltaT < -0.8) and (self.DesvioDeltaI < 4) and (self.PosicaoBarra < 222):
                printf("\n\nCORRECAO DA TEMPERATURA MEDIA POR RETIRADA DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                self.PosicaoBarra = self.PosicaoBarra + 2
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
                self.DeltaBarra = 2
                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

        return

    # Funcao corrige delta I

    def Corrige_DeltaI(self):
        if ((self.DesvioDeltaI >= 0 and self.DeltaT <= 0.4)
                or (self.DesvioDeltaI > 4.5 and self.DeltaT < 2)):
            if self.DeltaT >= self.t1:
                self.Vazao = 2 * self.v1
                printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm", self.Vazao)
                self.tempo = self.t
            if self.DeltaT <= self.t2:
                self.Vazao = 2 * self.v2
                printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm", self.Vazao)
                self.tempo = self.t
            if self.DeltaT > self.t2 and self.DeltaT < self.t1:
                self.Vazao = 2 * ((-self.a * self.DeltaT) + self.b)
                printf("\n\nDeltaT: %f\n\n", self.DeltaT)
                printf("\n\nIniciada a Correcao do Delta I por Diluicao na Vazao de %.0f lpm", self.Vazao)
                self.tempo = self.t
            # sleep(1); //tempodilute
            self.t = self.t + self.tempodilute
            self.z = self.z + self.tempodilute
            self.tXe = self.tXe + self.tempodilute
            printf("\n\nDiluicao Encerrada")
            self.Vagua = self.Vazao * (self.t - self.tempo)
            self.Vazao = 0
            self.VaguaTemp = self.Vagua + self.VaguaTemp
            self.CorrigeTmedDiluicao()
            self.CorrigeDeltaIDiluicao()
        if self.DesvioDeltaI < 0 and self.DeltaT < 0.8 and self.PosicaoBarra < 222:

            printf("\n\nCORRECAO DO DELTA I POR RETIRADA DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
            self.PosicaoBarra = self.PosicaoBarra + 1
            printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
            self.DeltaBarra = self.DeltaBarra + 1
            self.CorrigeTmedDeltaBarra()
            self.CorrigeDeltaIDeltaBarra()

        if ((self.DeltaT > -0.6) and (self.DesvioDeltaI > 4.5)
                and (self.PosicaoBarra > (self.LimiteInsercao + 11) or self.DesvioDeltaI > 5)):

            printf("\n\nCORRECAO DA DELTA I POR INSERCAO DE BARRA\n\n")
            printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
            self.PosicaoBarra = self.PosicaoBarra - 1
            printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
            self.DeltaBarra = -1
            self.CorrigeTmedDeltaBarra()
            self.CorrigeDeltaIDeltaBarra()

        if (((self.DesvioDeltaI < -4 and self.PosicaoBarra >= 222) and self.DeltaT > -1)
                or (self.DesvioDeltaI < -10 and self.DeltaT > -3)):

            # Cálculo do Volume de Boro

            self.VazaoBoro = (-self.DesvioDeltaI) * 6
            if self.VazaoBoro > 20:
                self.VazaoBoro = 20
            self.Vboro = self.VazaoBoro * 2

            printf("\n\nCORRECAO DO DELTA I POR BORACAO\n\n")

            self.CorrigeTmedBoracao()
            self.CorrigeDeltaIBoracao()

            # getch();
        return

    # PROGRAMA PRINCIPAL

    def main(self, argv):

        # Argumentos opcionais; sem nenhum deles o comportamento e o de antes.
        for arg in argv[1:]:
            if arg.startswith("--transiente="):
                val = arg[13:]
                if val == "runback-bap":
                    self.transienteTipo = TR_RUNBACK_BAP
                elif val == "runback-circ":
                    self.transienteTipo = TR_RUNBACK_CIRC
                elif val == "runback-400":
                    self.transienteTipo = TR_RUNBACK_400
                elif val == "runback-300":
                    self.transienteTipo = TR_RUNBACK_300
                elif val == "runback-150":
                    self.transienteTipo = TR_RUNBACK_150
                elif val == "rampa":
                    self.transienteTipo = TR_RAMPA
                else:
                    fprintf_stderr("Transiente desconhecido: %s\n", val)
                    return 1
            elif arg.startswith("--alvo="):
                self.argAlvo = atof(arg[7:])
            elif arg.startswith("--taxa="):
                self.argTaxa = atof(arg[7:])
            elif arg.startswith("--t-transiente="):
                self.tTransiente = atoi(arg[15:])
            elif arg.startswith("--tmax="):
                self.tmax = atof(arg[7:])
            else:
                fprintf_stderr("Argumento desconhecido: %s\n", arg)
                return 1
        if self.transienteTipo == TR_RAMPA and self.argTaxa <= 0:
            fprintf_stderr("--transiente=rampa exige --alvo=<MW> e --taxa=<MW/min> positiva\n")
            return 1

        system_color()
        printf("\n\t\t\t\t\t******************************")
        printf("\n\t\t\t\t\tCONTROLE AUTOMATICO DO REATOR")
        printf("\n\t\t\t\t\t******************************\n")
        printf("\t\t\t\t\t")
        self.termino = "inicio"
        try:
            arquivo = open("Modelagem_Reator_py.txt", "a", encoding="utf-8")
        except OSError:
            printf("Problemas na abertura do arquivo!\n")
            sys.exit(1)
        else:
            # fwrite(&Pot, sizeof(Pot), 1, arquivo);
            arquivo.write("Tempo    Pot Rx    Pot Turbina     Tmed   Delta I  Cboro  Banco D  Volume de Água\n\n\n")

            # fwrite(&Pot, sizeof(100),2, arquivo);
        arquivo.close()

        # for(i=0; i<29; i++) {
        #     printf("%c",177); }

        printf("\n\n\nDigite a Potencia Inicial da Turbina em MW (32 a 650MW): ")
        self.PotTurbina = scanf_float(self.PotTurbina)
        self.Pot = self.PotTurbina / 6.5
        self.PotAlvo = self.Pot
        self.Tref = 0.113 * self.Pot + 291.7
        self.Tmed = self.Tref
        self.AlvoTref = self.Tref
        printf("\nValor da Temperatura Media Inicial do SRR %.1f°C", self.Tmed)
        # scanf("%f",&Tmed);
        printf("\n\nDigite o Valor da Concentracao Inicial de Boro (ppm): ")
        self.Cboro = scanf_float(self.Cboro)
        printf("\nDigite a Posicao Inicial do Banco de Controle D (passos): ")
        self.PosicaoBarra = scanf_int(self.PosicaoBarra)
        # printf("\nDigite o Valor do Coeficiente de Reatividade do Boro (pcm/ppm): ");
        # scanf("%f",&alfaboro);
        # printf("\nDigite o Valor do Coeficiente de Temperatura do Moderador (pcm/°C): ");
        # scanf("%f",&alfamoderador);
        printf("\nDigite o Intervalo de Tempo por Diluicao (minutos): ")
        self.tempodilute = scanf_int(self.tempodilute)
        printf("\nDigite o Delta de Temperatura para a Vazao Minima (°C): ")
        self.t1 = scanf_float(self.t1)
        printf("\nDigite o Delta de Temperatura para a Vazao Maxima (°C): ")
        self.t2 = scanf_float(self.t2)
        # printf("\nDigite o Valor da Vazao de Diluicao Minima (lpm): ");
        # scanf("%d",&v1);
        # printf("\nDigite o Valor da Vazao de Diluicao Maxima (lpm): ");
        # scanf("%d",&v2);
        # printf("\nDigite o Valor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: ");
        # scanf("%d",&a);
        # printf("\nDigite o Valor do Coeficiente B da Equacao de Diluicao: Vazao= -A.DeltaT + B: ");
        # scanf("%d",&b);
        self.Msrr = 132440
        # printf("\nDigite o Tempo de Homogeneizacao da Massa do SRR (minutos): ");
        # scanf("%f",&thom);
        self.thom = 18
        printf("\nDigite o Delta I Inicial: ")
        self.DeltaI = scanf_float(self.DeltaI)
        printf("\n\nPARA INSERIR UMA VARIACAO DE CARGA DIGITE v EM QUALQUER MOMENTO DO CICLO DE OPERACAO\n\n\n")

        self.lambda_ = 0.1   # λ médio;
        self.DeltaT = self.Tmed - self.Tref
        self.t = 0
        self.x = 0
        self.y = 0
        self.ty = 0
        if self.Cboro > 800:
            self.betaeff = 594   # 594pcm no IDC
        else:
            self.betaeff = 522   # 522pcm no FDC
        self.taxatempreal = (2601 - self.Cboro) / 6.31   # (2568-Cboro)/6.4;
        self.taxatemp = self.taxatempreal                # tempo de redução de 0,1ºC
        printf("\nTaxa de Reducao de 0,1°C na Temperatura do SRR Devido a Queima: %d", self.taxatemp)
        self.alfamoderador = 0.02849 * self.Cboro - 75.02849
        printf("\nCoeficiente de Temperatura do Moderador: %f pcm/°C", self.alfamoderador)
        self.alfaboro = 0.0005363 * self.Cboro - 7.285363
        printf("\nValor do Coeficiente de Reatividade do Boro: %f pcm/ppm\n", self.alfaboro)
        self.v1 = -0.05307 * self.Cboro + 100.5307
        if self.v1 <= 0:
            self.v1 = 5
        printf("\nValor da Vazao de Diluicao Minima: %.0f lpm", self.v1)
        self.v2 = -0.24022 * self.Cboro + 452.24022
        if self.v2 <= 0:
            self.v2 = 10
        printf("\nValor da Vazao de Diluicao Maxima: %.0f lpm", self.v2)
        self.a = 2 * self.v1
        printf("\nValor do Coeficiente A da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f", self.a)
        self.b = self.v1
        printf("\nValor do Coeficiente B da Equacao de Diluicao Vazao= -A.DeltaT + B: %.0f\n", self.b)

        self.TaxaTurbina = 0

        # PARAMENTROS REFERENTES AO XE NO MAIN

        self.Nxe0 = (self.Pot / 100) * 3.70461 * math.pow(10, 14)   # 3.70461*pow(10,14);
        self.Nxeb = self.Nxe0
        self.Nxeg = self.Nxe0
        self.Nxeg0 = self.Nxe0
        self.Ni0 = (self.Pot / 100) * 9.589 * math.pow(10, 14)      # 9.589*pow(10,14);
        self.Nib = self.Ni0
        self.Nig = self.Ni0
        self.Nig0 = self.Ni0
        self.lambdaXe = 2.116 * math.pow(10, -5)
        self.sigmaXe = 2.6 * math.pow(10, -18)
        self.gamaI = 0.056
        self.Sigmaf = 0.01
        self.gamaXe = 0.056
        self.lambdaI = 2.92 * math.pow(10, -5)
        self.ConvertXe_Ro = -6.8636 * math.pow(10, -12)

        self.lambda_ = 0.1
        self.betaeff = 594

        self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
        self.Pbase = (2 * self.Pot - self.DeltaI) / 2
        self.Fnb0 = 5 * math.pow(10, 13) * self.Pot / 100
        self.Fng0 = self.Fnb0
        # Ro=-2542.696533;
        self.RoAntes = self.Nxe0 * self.ConvertXe_Ro

        self.PotAntes = self.Pot
        self.PbaseAntes = self.Pot

        self.z = 0
        self.tXe = 0
        self.erro = 0
        self.VaguaTemp = 0

        # PROGRAMA

        # Loop até fim de ciclo (boro < 8 ppm) ou limite de horizonte
        # (--tmax, default ~486 dias)
        while self.termino != "fim" and self.t < self.tmax:
            # sleep(1);
            self.t = self.t + 1
            self.z = self.z + 1
            self.tXe = self.tXe + 1
            self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
            self.Pbase = (2 * self.Pot - self.DeltaI) / 2
            # Corrige Tmed conforme a queima
            self.taxatempreal = (2601 - self.Cboro) / 6.31
            self.taxatemp = self.taxatempreal        # tempo de redução de 0,1ºC
            self.valor = (self.t / self.taxatemp)
            self.aux = self.valor
            if self.aux == self.valor:
                self.Tmedantes = self.Tmed
                self.Tmed = self.Tmed - 0.1
                self.x = self.x + 1
                self.DeltaT = self.Tmed - self.Tref
                self.VariacaoTmed = self.Tmed - self.Tmedantes
            if self.aux > self.x:
                self.diferenca = self.aux - self.x
                self.Tmedantes = self.Tmed
                self.Tmed = self.Tmed - (0.1 * self.diferenca)
                self.x = self.aux
                self.DeltaT = self.Tmed - self.Tref
                self.VariacaoTmed = self.Tmed - self.Tmedantes
            # Fim da correção de Tmed conforme a queima

            self.LimiteInsercao = 2.58 * (self.Pot) - 85

            # Ajuste da Carga Programada

            if self.TaxaTurbina != 0:
                while self.t >= self.ty:
                    self.ty = self.ty + 1
                    if self.ModuloTref > (self.ModuloTaxa * 0.0173846):
                        self.Tref = self.Tref + (self.TaxaTurbina * 0.0173846)
                        self.PotAlvo = (self.Tref - 291.7) / 0.113
                        self.ModuloTref = (self.AlvoTref - self.Tref)
                        if self.AlvoTref < self.Tref:
                            self.ModuloTref = -(self.AlvoTref - self.Tref)
                        printf("\nModuloTref=%.2f\n", self.ModuloTref)
                    if self.ModuloTref <= (self.ModuloTaxa * 0.0173846):
                        self.Tref = self.AlvoTref
                        self.TaxaTurbina = 0
                        self.PotAlvo = (self.Tref - 291.7) / 0.113
            while (self.t >= self.y
                   and (self.Pot > (self.PotAlvo + 0.015) or (self.Pot < (self.PotAlvo - 0.015)))):
                self.y = self.y + 1
                self.i = 0
                while self.i < 500:
                    # printf("\n\ni:%d",i);
                    if self.Pot > self.PotAlvo:
                        self.Pot = self.Pot - 0.01
                        self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
                        self.Pbase = (2 * self.Pot - self.DeltaI) / 2
                        self.PbaseAntes = self.Pot
                        # tXe=0;
                        if self.Pot != 0:
                            self.erro = self.DeltaI * ((1 / self.PotAntes) - (1 / self.Pot))
                        # printf("\n\nErro corrigido: %f",erro);
                        printf("\n\nPOTENCIA DO REATOR: %f%c", self.Pot, 37)
                        if self.TaxaTurbina != 0:
                            self.PotTurbina = 6.5 * self.Pot
                            printf("\nPOTENCIA DA TURBINA: %f", self.PotTurbina)
                    if self.Pot < self.PotAlvo:
                        self.Pot = self.Pot + 0.01
                        self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
                        self.Pbase = (2 * self.Pot - self.DeltaI) / 2
                        self.PbaseAntes = self.Pot
                        # tXe=0;
                        printf("\n\nPOTENCIA DO REATOR: %f%c", self.Pot, 37)
                        if self.TaxaTurbina != 0:
                            self.PotTurbina = 6.5 * self.Pot
                            printf("\nPOTENCIA DA TURBINA: %f", self.PotTurbina)
                    if (self.Pot <= (self.PotAlvo + 0.015)) and (self.Pot >= (self.PotAlvo - 0.015)):
                        break
                    self.i = self.i + 1
            self.CalculaAlvoDeltaI()
            self.CalculaDeltaI()

            printf("\n\n\nt=%.0f", self.t)
            # sleep(1);
            printf("\nZ=%d", self.z)
            printf("\nPot=%.2f", self.Pot)
            if (self.Pot <= (self.PotAlvo + 0.015)) and (self.Pot >= (self.PotAlvo - 0.015)):
                self.PotTurbina = 6.5 * self.Pot
                printf("\nPotTurbina=%.1f", self.PotTurbina)
            self.PotTurbinaTemp = 6.5 * self.Pot
            printf("\nPotTurbinaTemp=%.1f", self.PotTurbinaTemp)
            printf("\nAlvoTref=%.2f", self.AlvoTref)
            printf("\nTmed=%.1f", self.Tmed)
            printf("\nTref=%.1f", self.Tref)
            printf("\nAlvo DeltaI=%f", self.AlvoDeltaI)
            printf("\nDeltaI=%f", self.DeltaI)
            printf("\nDesvioDeltaI=%f", self.DesvioDeltaI)
            printf("\nVariacaoDeltaI=%f", self.VariacaoDeltaI)
            printf("\nPosicao Barra=%d", self.PosicaoBarra)
            printf("\nPosicao de referencia BD=%d", self.BD)
            printf("\nCboro=%f\n\n\n", self.Cboro)

            self.GravaDados()

            # Injecao automatica do transiente, no mesmo ponto do laco em que o
            # operador digitaria "v" no programa original.
            if (self.transienteTipo != TR_NENHUM and self.transienteAplicado == 0
                    and self.t >= self.tTransiente):
                self.transienteAplicado = 1
                printf("\n\nTRANSIENTE APLICADO EM t=%.0f\n", self.t)
                self.AplicaTransienteAuto()

            if kbhit():
                self.funcaocarga = scanf_str(self.funcaocarga)
                if self.funcaocarga == "v":
                    printf("Variacao de Carga")
                    self.VariacaodeCarga()

            # CALCULA DELTA I NO LOOP DO MAIN

            self.Ptopo = (2 * self.Pot + self.DeltaI) / 2
            self.Pbase = (2 * self.Pot - self.DeltaI) / 2
            if self.Ptopo < 0:
                self.Ptopo = 0
            if WIN_ORIGINAL:
                if self.Pbase < 0:
                    self.Ptopo = 0   # semantica literal do original .txt (aparente troca de variavel)
            else:
                if self.Pbase < 0:
                    self.Pbase = 0   # corrigido: era "Ptopo=0" (aparente troca de variavel)

            self.BD = 0.73 * self.Pot + 144
            printf("BD: %d", self.BD)

            if self.DeltaT < -0.1:
                self.CompensacaoQueima()

            if self.DesvioDeltaI > 2 or self.DesvioDeltaI < -2:
                self.Corrige_DeltaI()

            if ((self.DeltaT > 0.6) and (self.DesvioDeltaI >= -2.2)
                    and (self.PosicaoBarra > (self.LimiteInsercao + 11) or self.DeltaT > 1.5)):
                printf("\n\nCORRECAO DA TEMPERATURA MEDIA POR INSERCAO DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                if self.DeltaT < 1:
                    self.PosicaoBarra = self.PosicaoBarra - 1
                    self.DeltaBarra = -1
                else:
                    self.PosicaoBarra = self.PosicaoBarra - 2
                    self.DeltaBarra = -2
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)

                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

            if (self.DeltaT > 0.8) and (self.DesvioDeltaI < 0):

                # Volume de Boro

                self.VazaoBoro = self.DeltaT * 10
                self.Vboro = self.VazaoBoro * 4

                printf("\n\nCORRECAO DO DELTA T POR BORACAO\n\n")

                self.CorrigeTmedBoracao()
                self.CorrigeDeltaIBoracao()

            if self.PosicaoBarra <= (self.LimiteInsercao + 10) and self.PosicaoBarra > self.LimiteInsercao:

                printf("\n\nALARME ATIVADO: LIMITE DE INSERCAO BAIXO\n\n")

                if self.DeltaI < 0:

                    # Volume de Boro

                    self.VazaoBoro = (self.LimiteInsercao - self.PosicaoBarra + 11) * 2
                    self.Vboro = self.VazaoBoro * 2

                    printf("\n\nLIMITE DE INSERCAO BAIXO ATINGIDO - BORACAO NORMAL\n\n")

                    self.CorrigeTmedBoracao()
                    self.CorrigeDeltaIBoracao()

            if self.PosicaoBarra <= self.LimiteInsercao:

                printf("\n\nALARME ATIVADO: LIMITE DE INSERCAO MUITO BAIXO\n\n")

                if self.DeltaI < 0:
                    # Volume de Boro

                    self.VazaoBoro = (self.LimiteInsercao + 1 - self.PosicaoBarra) * 5
                    self.Vboro = self.VazaoBoro * 2

                    printf("\n\nLIMITE DE INSERCAO MUITO BAIXO ATINGIDO - BORACAO DE EMERGENCIA\n\n")

                    self.CorrigeTmedBoracao()
                    self.CorrigeDeltaIBoracao()

            if ((self.PosicaoBarra < (self.BD - 3)) and (self.DesvioDeltaI < 4.2)
                    and (self.DeltaT < 0.8)):
                printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                self.PosicaoBarra = self.PosicaoBarra + 1
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
                self.DeltaBarra = 1
                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

            if ((self.PosicaoBarra > (self.BD + 10)) and (self.DesvioDeltaI >= -3)
                    and (self.DeltaT > -0.4)):
                printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                self.PosicaoBarra = self.PosicaoBarra - 1
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
                self.DeltaBarra = -1
                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

            if ((self.PosicaoBarra < (self.LimiteInsercao + 11)) and (self.DesvioDeltaI < 4)
                    and (self.DeltaT < 0.5)):
                printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                self.PosicaoBarra = self.PosicaoBarra + 1
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
                self.DeltaBarra = 1
                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

            if ((self.PosicaoBarra > 220) and (self.DesvioDeltaI >= -1.5)
                    and (self.DeltaT > -0.25)):
                printf("\n\nCORRECAO DA POSICAO DE BARRA\n\n")
                printf("\n\nPosicao Anterior do Banco D: %d passos", self.PosicaoBarra)
                self.PosicaoBarra = self.PosicaoBarra - 1
                printf("\n\nPosicao Atual do Banco D: %d passos\n", self.PosicaoBarra)
                self.DeltaBarra = -1
                self.CorrigeTmedDeltaBarra()
                self.CorrigeDeltaIDeltaBarra()

            # valor=(t/1000);
            # aux=valor;
            # if (aux==valor) {
            # printf("\n\nDigite fim para terminar ou qualquer tecla para continuar: ");
            # scanf ("%s", &termino);
            # }

            if self.DesvioDeltaI > 5 or self.DesvioDeltaI < -5:
                printf("\n\n\n\t\t\t\t\tDELTA I: %f\n", self.DeltaI)
                printf("\n\n\n\t\t\t\t\tALARME DE DELTA I FORA DA BANDA ALVO 5%c \n", 37)   # o .c usa "%C" (glibc: alias de %lc); com 37 imprime '%' nos dois
                printf("t\t\t\t\t****************************************\n")
                printf("\t\t\t\t\t")
                # for(i=0; i<35; i++) {
                #     printf("%c",177); }
                printf("\n\n\nt=%.0f", self.t)
                printf("\nZ=%d", self.z)
                printf("\nPot=%.2f", self.Pot)
                printf("\nTmed=%.1f", self.Tmed)
                printf("\nTref=%.1f", self.Tref)
                printf("\nAlvo DeltaI=%f", self.AlvoDeltaI)
                printf("\nDeltaI=%f", self.DeltaI)
                printf("\nDesvioDeltaI=%f", self.DesvioDeltaI)
                printf("\nVariacaoDeltaI=%f", self.VariacaoDeltaI)
                printf("\nPosicao Barra=%d", self.PosicaoBarra)
                printf("\nCboro=%f\n\n\n", self.Cboro)
                # getch(); // Removido para execução automática
                # return(0);

            if self.DeltaT > 1.67 or self.DeltaT < -1.67:
                printf("\n\n\n\t\t\t\t  TEMPERATURA MEDIA DO SRR: %.1f\n", self.Tmed)
                printf("\n\n\n\t\t\t\tO ALARME DESVIO DE TEMPERATURA 1,67°C\n")
                printf("t\t\t\t\t****************************************\n")
                printf("\t\t\t\t")
                self.i = 0
                while self.i < 37:
                    putc_raw(b'\xb1')     # printf("%c",177): UM byte, nao UTF-8
                    self.i = self.i + 1
                printf("\n\n\nt=%.0f", self.t)
                printf("\nZ=%d", self.z)
                printf("\nPot=%.2f", self.Pot)
                printf("\nTmed=%.1f", self.Tmed)
                printf("\nTref=%.1f", self.Tref)
                printf("\nAlvo DeltaI=%f", self.AlvoDeltaI)
                printf("\nDeltaI=%f", self.DeltaI)
                printf("\nDesvioDeltaI=%f", self.DesvioDeltaI)
                printf("\nVariacaoDeltaI=%f", self.VariacaoDeltaI)
                printf("\nPosicao Barra=%d", self.PosicaoBarra)
                printf("\nCboro=%f\n\n\n", self.Cboro)
                # getch(); // Removido para execução automática
                # return(0);

            if self.Cboro < 8:
                printf("\n\n\n\t\t\t\t\tO FIM DO CICLO - PARABENS!!!!!\n")
                printf("\t\t\t\t\t")
                self.i = 0
                while self.i < 30:
                    putc_raw(b'\xb1')     # printf("%c",177): UM byte, nao UTF-8
                    self.i = self.i + 1
                printf("\n\n\nt=%.0f", self.t)
                printf("\nZ=%d", self.z)
                printf("\nPot=%.2f", self.Pot)
                printf("\nTmed=%.1f", self.Tmed)
                printf("\nTref=%.1f", self.Tref)
                printf("\nAlvo DeltaI=%f", self.AlvoDeltaI)
                printf("\nDeltaI=%f", self.DeltaI)
                printf("\nDesvioDeltaI=%f", self.DesvioDeltaI)
                printf("\nVariacaoDeltaI=%f", self.VariacaoDeltaI)
                printf("\nPosicao Barra=%d", self.PosicaoBarra)
                printf("\nCboro=%f\n\n\n", self.Cboro)
                self.termino = "fim"   # Força o fim para o caso de sair por aqui
                # getch(); // Removido para execução automática
                # return(0);

        printf("\n\nFim do Programa\n\n")
        # getch(); // Removido para execução automática
        return 0


if __name__ == '__main__':
    sys.setrecursionlimit(100000)
    try:
        codigo = Reator().main(sys.argv)
        _saida.flush()
    except BrokenPipeError:
        codigo = 0
    sys.exit(codigo)
