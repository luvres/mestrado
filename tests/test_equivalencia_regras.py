#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_equivalencia_regras.py — a base declarativa diz o que o fonte C diz?

expert/regras.py guarda o antecedente de cada regra como TEXTO do fonte C. Este
modulo confere esse texto contra o proprio
V8_Reatividade_SimuladorIgor_linux.c, regra a regra, pela linha declarada em
`Regra.linha_c`.

A comparacao nao e de string: os dois lados passam pela MESMA canonizacao por
AST (expressoes.canoniza), entao espacos, quebras de linha e parenteses
redundantes somem e a estrutura do operador fica. `((A))` bate com `(A)`;
`A && B || C` NAO bate com `A && (B || C)`.

E o teste que impede a deriva silenciosa: se alguem mexer numa condicao do C
sem mexer na base — ou o contrario — a regra correspondente falha, dizendo qual.
"""

import os
import re

import pytest

from conftest import DIR_EXPERT, FONTE_C, exige

exige("expert")

import sys                                                        # noqa: E402
sys.path.insert(0, DIR_EXPERT)

from expressoes import canoniza                                   # noqa: E402
from regras import BASE, REGRAS                                   # noqa: E402


def _linhas_c():
    with open(FONTE_C, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


LINHAS = _linhas_c() if os.path.exists(FONTE_C) else []


def _condicao_na_linha(n):
    """O que esta dentro do `if (...)` que comeca na linha n (1-based).

    O `if` pode ocupar mais de uma linha; junta-se ate os parenteses fecharem.
    """
    texto = ""
    saldo = 0
    comecou = False
    for linha in LINHAS[n - 1:n + 5]:
        for ch in linha:
            if ch == "(":
                saldo += 1
                comecou = True
                if saldo == 1:
                    continue          # o parentese do proprio `if`
            elif ch == ")":
                saldo -= 1
                if saldo == 0:
                    return texto
            if comecou and saldo >= 1:
                texto += ch
        texto += " "
    raise AssertionError("parenteses nao fecharam a partir da linha %d" % n)


@pytest.mark.skipif(not LINHAS, reason="fonte C nao montado em FONTE_C")
@pytest.mark.parametrize("regra", REGRAS, ids=lambda r: r.id)
def test_condicao_bate_com_o_fonte_c(regra):
    do_c = _condicao_na_linha(regra.linha_c)
    assert canoniza(do_c) == canoniza(regra.condicao.texto_c), (
        "%s (linha %d do .c)\n  .c   : %s\n  base : %s"
        % (regra.id, regra.linha_c, canoniza(do_c), canoniza(regra.condicao.texto_c)))


@pytest.mark.skipif(not LINHAS, reason="fonte C nao montado em FONTE_C")
@pytest.mark.parametrize("bloco", [b for b in BASE if b.guarda is not None],
                         ids=lambda b: b.nome)
def test_guarda_do_bloco_bate_com_o_fonte_c(bloco):
    """As duas guardas de despacho do `main` (L1168 e L1173)."""
    do_c = _condicao_na_linha(bloco.linha_guarda)
    assert canoniza(do_c) == canoniza(bloco.guarda.texto_c), (
        "%s (linha %d)\n  .c   : %s\n  base : %s"
        % (bloco.nome, bloco.linha_guarda, canoniza(do_c), canoniza(bloco.guarda.texto_c)))


def test_a_base_tem_as_19_regras():
    assert len(REGRAS) == 19
    assert [r.id for r in REGRAS] == ["R%d" % i for i in range(1, 20)]


def test_a_conta_de_acoes_fecha_com_o_passo_3():
    """steps/03-regras-controle.md §3: 3 diluicoes, 4 boracoes, 9 barras, 3 sinalizacoes.

    Aqui saem 5 efeitos de alarme, e nao 3, porque R11 e R12 tem consequente
    partido (§5.4): alarme com a condicao externa, boracao so com ela E ΔI<0.
    Contando REGRAS que so sinalizam, voltam a ser 3.
    """
    from collections import Counter
    c = Counter(e.tipo for r in REGRAS for e in r.efeitos)
    assert c["diluir"] == 3
    assert c["borar"] == 4
    assert c["barra"] == 9
    assert c["alarme"] == 5
    so_sinalizam = [r.id for r in REGRAS
                    if all(e.tipo == "alarme" for e in r.efeitos)]
    assert so_sinalizam == ["R17", "R18", "R19"]


def test_as_regras_so_leem_as_grandezas_do_passo_3():
    """steps/03 §2: sete grandezas, mais Cboro so na R19."""
    permitidas = {"DeltaT", "DesvioDeltaI", "VariacaoDeltaI", "DeltaI",
                  "PosicaoBarra", "LimiteInsercao", "BD", "Cboro"}
    lidas = set()
    for r in REGRAS:
        lidas |= set(r.condicao.nomes)
        for e in r.efeitos:
            if e.quando is not None:
                lidas |= set(e.quando.nomes)
    assert lidas <= permitidas, "regra lendo grandeza fora do §2: %s" % (lidas - permitidas)
    # Cboro so aparece na R19, e DeltaI so nos consequentes partidos de R11/R12.
    assert [r.id for r in REGRAS if "Cboro" in r.condicao.nomes] == ["R19"]


def test_nucleo_numerico_identico_ao_do_reactor():
    """expert/f32.py e reactor/f32.py tem de ser o mesmo arquivo.

    Se divergirem, os dois lados arredondam diferente e a malha para de bater
    byte a byte — por um motivo que nao apareceria em nenhuma condicao de regra.
    """
    from conftest import DIR_REACTOR
    a = os.path.join(DIR_REACTOR, "f32.py")
    b = os.path.join(DIR_EXPERT, "f32.py")
    if not (os.path.exists(a) and os.path.exists(b)):
        pytest.skip("os dois pacotes nao estao visiveis daqui")
    marca_i, marca_f = "# --- inicio do bloco copiado", "# --- fim do bloco copiado"

    def bloco(caminho):
        dentro, saida_ = False, []
        for linha in open(caminho, encoding="utf-8"):
            if marca_i in linha:
                dentro = True
            elif marca_f in linha:
                dentro = False
            elif dentro:
                saida_.append(linha)
        return "".join(saida_)

    assert bloco(a) == bloco(b) != ""
