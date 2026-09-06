#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_equivalencia_braco_python.py — os dois bracos concordam?

O sistema especialista tem duas representacoes das mesmas 19 regras:

    scripts/validate_c_vs_python.py   PROCEDURAL — 19 blocos `if` transcritos do
                                      .c, o instrumento que validou o Passo 4
    expert/regras.py + motor.py       DECLARATIVO — 19 registros interpretados,
                                      o que roda no servico

Elas existem para serem confrontadas. test_equivalencia_regras.py ja confere a
declarativa contra o fonte C; aqui a procedural entra como terceiro voto, por
duas frentes:

  1. ESTRUTURA — as condicoes que o braco procedural testa, na ordem em que as
     testa, contem as 19 da base declarativa nessa mesma ordem. Os dois fazem as
     mesmas perguntas, na mesma sequencia.

  2. COMPORTAMENTO — os dois dirigindo o MESMO reator produzem os mesmos bytes.
     E o teste caro; roda com horizonte curto. A bateria completa esta em
     scripts/verifica_expert.sh.

Uma divergencia entre os bracos e o achado mais informativo que esta suite pode
produzir: ela localiza o erro no que os distingue — a representacao das regras —
em vez de deixar a duvida entre regra, motor e planta.
"""

import ast
import os
import subprocess
import sys

import pytest

from conftest import BRACO_PY, DECL_PY, DIR_EXPERT, REACTOR_API_URL, exige

exige("expert")

sys.path.insert(0, DIR_EXPERT)

from expressoes import canoniza                                    # noqa: E402
from regras import BASE, REGRAS                                    # noqa: E402

# ciclo() entra porque e la que estao as DUAS guardas de despacho (L1168 e
# L1173 do .c). A de CompensacaoQueima aparece duas vezes no fonte — dentro da
# funcao tambem — e o braco reproduz isso.
METODOS_DE_REGRA = ("CompensacaoQueima", "Corrige_DeltaI", "regras_do_laco", "ciclo")


def _condicoes_do_braco():
    """Todo `if` dos tres metodos de regra, canonizado, em ordem de fonte.

    O `e.` das leituras de estado sai, para que `e.DeltaT < -0.1` e `DeltaT<-0.1`
    virem a mesma coisa. Nao ha risco de colisao: `e` e o unico objeto que as
    regras consultam.
    """
    arvore = ast.parse(open(BRACO_PY, encoding="utf-8").read())
    achadas = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name in METODOS_DE_REGRA:
            for interno in ast.walk(no):
                if isinstance(interno, ast.If):
                    texto = ast.unparse(interno.test).replace("e.", "")
                    achadas.append((interno.lineno, canoniza(texto)))
    achadas.sort()
    return [c for _, c in achadas]


def _e_subsequencia(pequena, grande):
    it = iter(grande)
    return all(any(x == y for y in it) for x in pequena)


@pytest.mark.skipif(not os.path.exists(BRACO_PY),
                    reason="braco procedural nao montado em BRACO_PY")
def test_o_braco_procedural_faz_as_mesmas_perguntas_na_mesma_ordem():
    do_braco = _condicoes_do_braco()
    da_base = [canoniza(r.condicao.texto_c) for r in REGRAS]

    faltando = [r.id for r, c in zip(REGRAS, da_base) if c not in do_braco]
    assert not faltando, (
        "condicoes da base que o braco procedural nao testa: %s" % faltando)

    assert _e_subsequencia(da_base, do_braco), (
        "as 19 condicoes aparecem no braco, mas nao na ordem da base — a "
        "prioridade das regras nao e a mesma nos dois")


@pytest.mark.skipif(not os.path.exists(BRACO_PY),
                    reason="braco procedural nao montado em BRACO_PY")
def test_as_guardas_de_despacho_tambem_estao_no_braco():
    do_braco = _condicoes_do_braco()
    for bloco in BASE:
        if bloco.guarda is None:
            continue
        assert canoniza(bloco.guarda.texto_c) in do_braco, (
            "a guarda do bloco %s nao aparece no braco procedural" % bloco.nome)


@pytest.mark.parametrize("flags,entrada", [
    (["--tmax=240"], "650 1800 210 4 -0.3 -0.8 0"),
    (["--tmax=240", "--transiente=runback-bap", "--t-transiente=10"],
     "650 1800 210 4 -0.3 -0.8 0"),          # alcanca R18 (byte 177 cru)
    (["--tmax=300"], "650 1800 150 4 -0.3 -0.8 -4"),   # alcanca R11 e R12
])
@pytest.mark.skipif(not (os.path.exists(BRACO_PY) and os.path.exists(DECL_PY)),
                    reason="os dois bracos precisam estar montados em /ref")
def test_os_dois_bracos_produzem_os_mesmos_bytes(tmp_path, flags, entrada):
    """Ambos contra o MESMO reator, por HTTP. Nada alem das regras difere."""
    stdin = ("\n".join(entrada.split()) + "\n").encode()
    amb = dict(os.environ)

    def roda(script, arquivo):
        return subprocess.run(
            [sys.executable, script, "--api=" + REACTOR_API_URL,
             "--arquivo=" + arquivo] + flags,
            input=stdin, capture_output=True, cwd=tmp_path, env=amb)

    proc = roda(BRACO_PY, "Modelagem_Reator_proc_teste.txt")
    decl = roda(DECL_PY, "Modelagem_Reator_decl_teste.txt")
    assert proc.returncode == 0, proc.stderr.decode()[-2000:]
    assert decl.returncode == 0, decl.stderr.decode()[-2000:]
    assert decl.stdout == proc.stdout, (
        "os bracos divergiram: procedural %d bytes, declarativo %d bytes"
        % (len(proc.stdout), len(decl.stdout)))
    assert len(proc.stdout) > 1000, "a corrida nao produziu saida"
