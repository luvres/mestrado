#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
saida.py — captura do que o simulador imprime.

No simulador.py os printf() vao para sys.stdout.buffer. Num servico HTTP nao ha
stdout que faca sentido: cada chamada tem de devolver o texto que aquela chamada
produziu, para que um cliente consiga remontar a saida padrao inteira na ordem
original e compara-la byte a byte com a do porte fiel.

Por isso printf() escreve num buffer da sessao corrente, instalado por captura().
O buffer vive num ContextVar, e nao numa global: as rotas sincronas do FastAPI
rodam num threadpool, e o anyio copia o contexto para a thread — assim duas
sessoes simultaneas nao misturam saida.

As assinaturas de printf() e putc_raw() sao identicas as de simulador.py de
proposito: as funcoes de fisica sao transcricao literal, e as chamadas nao mudam.
"""

import contextvars
import sys
from contextlib import contextmanager

_buffer = contextvars.ContextVar('_buffer', default=None)


@contextmanager
def captura():
    """Instala um buffer novo e o devolve; o texto sai em .getvalue()."""
    buf = bytearray()
    token = _buffer.set(buf)
    try:
        yield buf
    finally:
        _buffer.reset(token)


def printf(fmt, *args):
    buf = _buffer.get()
    dados = (fmt % args if args else fmt).encode('utf-8')
    if buf is None:                            # fora de captura(): modo script
        sys.stdout.buffer.write(dados)
    else:
        buf.extend(dados)


def tamanho():
    """Quantos bytes ja foram acumulados na captura corrente.

    Serve para o servico limitar o TAMANHO da propria resposta, e nao so o
    numero de ciclos: o volume de texto por ciclo varia muito ao longo de uma
    corrida (uma diluicao imprime ~2 KB, um minuto sem atuacao imprime ~1 KB),
    entao "20 mil ciclos" nao e um limite de memoria.
    """
    buf = _buffer.get()
    return 0 if buf is None else len(buf)


def putc_raw(b):
    """printf("%c", n) com n>127: o C escreve UM byte, nao UTF-8."""
    buf = _buffer.get()
    if buf is None:
        sys.stdout.buffer.write(b)
    else:
        buf.extend(b)
