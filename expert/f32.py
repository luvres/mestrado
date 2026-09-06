#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
f32.py — nucleo numerico: a semantica de armazenamento do C.

O expert precisa disto tanto quanto a planta, e pelo mesmo motivo. Ele nao so
compara grandezas: ele CALCULA com elas. A vazao da rampa de diluicao
(`-a*DeltaT+b`), o volume de boro (`(-DesvioDeltaI)*6`), o limite de insercao
somado a 11 — tudo isso e aritmetica do lado do controle, e no C arredonda a 32
bits a cada operacao. Calcular em double decidiria igual quase sempre, e o
Passo 1 registrou o que "quase sempre" custa: +-0,001 desloca um evento de
diluicao e desfaz a fase do resto da corrida.

O bloco abaixo e COPIA LITERAL das linhas 52-157 de simulador.py, identico ao de
reactor/f32.py. Nao editar aqui: editar em simulador.py e reextrair.
tests/test_equivalencia_regras.py compara os dois blocos byte a byte.

    sed -n '52,157p' simulador.py
"""

import math
import struct

# --- inicio do bloco copiado de simulador.py (linhas 52-157) ---------------

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


# --- fim do bloco copiado de simulador.py ---------------------------------
