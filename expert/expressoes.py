#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
expressoes.py — as condicoes do C como dado.

A ideia que sustenta a base de regras declarativa: um antecedente como

    (VariacaoDeltaI>=0 || DeltaT<-0.3) || (PosicaoBarra>=222 || DesvioDeltaI>-3)

nao precisa ser reescrito em Python. Ele pode ser guardado COMO ESTA, texto do
fonte C, e compilado. Duas consequencias:

  1. Nao ha duas representacoes para divergir. A regra nao tem uma condicao "no
     papel" e outra "no codigo" — tem uma so, que e ao mesmo tempo o que se le
     em GET /expert/regras e o que decide.
  2. tests/test_equivalencia_regras.py compara esse texto com a linha do
     V8_Reatividade_SimuladorIgor_linux.c de onde ele veio, canonizando os dois
     pela mesma AST. Nao e comparacao de string frouxa: `((A))` e `(A)` batem,
     e `A && B || C` nao bate com `A && (B || C)`.

A traducao e minima porque C e Python quase nao diferem aqui: `||` vira `or`,
`&&` vira `and`, e so. A precedencia relativa e a mesma nas duas linguagens
(`&&` mais forte que `||`, comparacoes mais fortes que ambos), entao nenhum
parentese precisa ser inventado. Nenhuma condicao do simulador encadeia
comparacoes (`a < b < c`), que e o unico ponto onde Python mudaria o sentido.

A avaliacao acontece contra um espaco de nomes onde cada grandeza ja vem no tipo
C declarado por GET /reactor/tipos — `float` de 32 bits, `int` ou `double`. E o
que faz `LimiteInsercao+11` e `(-DesvioDeltaI)*6` arredondarem nos mesmos pontos
que o C.
"""

import ast
import re

# eval sem builtins: uma expressao de regra so pode olhar as grandezas da
# observacao. Nao ha por que ela alcancar open(), __import__ ou qualquer outra
# coisa — e a base de regras e dado, entao vale trata-la como dado.
_SEM_BUILTINS = {"__builtins__": {}}

_OPERADORES = ((r"\|\|", " or "), (r"&&", " and "))


def para_python(texto_c):
    """`||` -> `or`, `&&` -> `and`. Nada mais muda."""
    s = texto_c
    for padrao, troca in _OPERADORES:
        s = re.sub(padrao, troca, s)
    return s


def canoniza(texto_c):
    """Forma canonica da expressao: mesma AST, mesma string.

    E o que torna a comparacao com o fonte C exata em vez de aproximada —
    espacos, quebras de linha e parenteses redundantes somem, e a estrutura
    do operador fica.
    """
    return ast.unparse(ast.parse(para_python(texto_c), mode="eval"))


class Expressao:
    """Uma expressao do fonte C, guardada como texto e compilada uma vez."""

    __slots__ = ("texto_c", "texto_py", "canonica", "_codigo", "_nomes")

    def __init__(self, texto_c):
        self.texto_c = texto_c.strip()
        self.texto_py = para_python(self.texto_c)
        arvore = ast.parse(self.texto_py, mode="eval")
        self.canonica = ast.unparse(arvore)
        self._codigo = compile(arvore, "<regra>", "eval")
        self._nomes = frozenset(
            n.id for n in ast.walk(arvore) if isinstance(n, ast.Name))

    @property
    def nomes(self):
        """As grandezas que a expressao lê. Serve para conferir que a regra só
        enxerga o que steps/03-regras-controle.md §2 diz que ela enxerga."""
        return self._nomes

    def __call__(self, espaco):
        return eval(self._codigo, _SEM_BUILTINS, espaco)

    def __repr__(self):
        return "Expressao(%r)" % self.texto_c

    def __str__(self):
        return self.texto_c


def expressao(texto_c):
    """Aceita None (regra sem aquela parte) para o codigo chamador ficar limpo."""
    return None if texto_c is None else Expressao(texto_c)
