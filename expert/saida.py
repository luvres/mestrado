#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
saida.py — captura do que o controlador imprime.

Gemeo de reactor/saida.py: mesmo codigo, so o docstring muda. Os dois servicos
precisam do mesmo mecanismo porque a saida padrao do simulador monolitico e
INTERCALADA entre os dois lados — o expert imprime "Iniciada a Diluicao na Vazao
de 5 lpm", a planta responde "Diluicao Encerrada" e o resto do efeito, e a regra
seguinte volta a imprimir. Remontar essa sequencia byte a byte e o criterio de
aceitacao do Passo 5.

Por isso printf() escreve num buffer da sessao corrente, instalado por captura().
O buffer vive num ContextVar, e nao numa global: as rotas sincronas do FastAPI
rodam num threadpool, e o anyio copia o contexto para a thread — assim duas
sessoes simultaneas nao misturam saida.

O texto que vem da planta pelo campo `saida` de cada resposta HTTP e reemitido
aqui, no instante da chamada. E o que mantem a ordem.

# --- daqui para baixo, identico a reactor/saida.py -------------------------
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
