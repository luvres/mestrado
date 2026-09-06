#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_genealogia.py — a planta de reactor/ ainda e o porte fiel?

O Passo 2 provou simulador.py identico ao C byte a byte. O Passo 4 recortou esse
arquivo em duas partes e pos HTTP entre elas. Este modulo defende a heranca por
tres frentes, da mais barata para a mais cara:

  1. As partes copiadas sao copia MESMO — o texto marcado em f32.py e physics.py
     tem de aparecer, literal, dentro de simulador.py. Sem numeros de linha:
     procura-se pelo texto, entao a prova sobrevive a qualquer deslocamento.
  2. Nao sobrou regra dentro da planta — nenhum dos textos que identificam as 19
     regras aparece em physics.py.
  3. A corrida inteira bate byte a byte: planta + braco procedural contra o
     porte fiel, nas amostras e na saida padrao.

A frente 3 sozinha ja pegaria quase tudo, mas demora e diz pouco quando falha.
As frentes 1 e 2 falham apontando exatamente o que se mexeu.
"""

import os
import subprocess
import sys

import pytest

from conftest import BRACO_PY, DIR_MODULOS, PORTE_PY, so_para

pytestmark = so_para("reactor")

MARCA_INICIO = "# --- inicio do bloco copiado"
MARCA_FIM = "# --- fim do bloco copiado"


def _le(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _blocos_copiados(caminho):
    """Os trechos entre os marcadores, sem as linhas de marcador."""
    linhas = _le(caminho).splitlines(keepends=True)
    blocos, atual = [], None
    for linha in linhas:
        if MARCA_INICIO in linha:
            atual = []
        elif MARCA_FIM in linha:
            assert atual is not None, "marcador de fim sem inicio em %s" % caminho
            blocos.append("".join(atual))
            atual = None
        elif atual is not None:
            atual.append(linha)
    assert atual is None, "marcador de inicio sem fim em %s" % caminho
    return blocos


@pytest.mark.parametrize("modulo", ["f32.py", "physics.py"])
def test_blocos_marcados_sao_copia_literal_do_porte(modulo):
    """Todo bloco marcado como copiado existe, verbatim, em simulador.py."""
    fonte = _le(PORTE_PY)
    blocos = _blocos_copiados(os.path.join(DIR_MODULOS, modulo))
    assert blocos, "%s nao declara nenhum bloco copiado" % modulo
    for i, bloco in enumerate(blocos):
        corpo = bloco.strip("\n")
        assert corpo in fonte, (
            "bloco %d de %s nao aparece literalmente em %s.\n"
            "Alguem editou a copia em vez do original. Primeiras linhas:\n%s"
            % (i + 1, modulo, PORTE_PY, "\n".join(corpo.splitlines()[:5]))
        )


# Textos que so existem porque existe uma REGRA. Nenhum deles pode aparecer na
# planta: se aparecer, uma decisao de controle ficou do lado errado da fronteira.
TEXTOS_DE_REGRA = [
    "COMPENSACAO DA QUEIMA POR RETIRADA DE BARRA",
    "CORRECAO DA TEMPERATURA MEDIA POR RETIRADA DE BARRA",
    "CORRECAO DA TEMPERATURA MEDIA POR INSERCAO DE BARRA",
    "CORRECAO DO DELTA I POR RETIRADA DE BARRA",
    "CORRECAO DA DELTA I POR INSERCAO DE BARRA",
    "CORRECAO DO DELTA I POR BORACAO",
    "CORRECAO DO DELTA T POR BORACAO",
    "CORRECAO DA POSICAO DE BARRA",
    "Iniciada a Diluicao na Vazao",
    "Iniciada a Correcao do Delta I por Diluicao",
    "Posicao Anterior do Banco D",
    "Posicao Atual do Banco D",
    "ALARME ATIVADO: LIMITE DE INSERCAO",
    "ALARME DE DELTA I FORA DA BANDA ALVO",
    "ALARME DESVIO DE TEMPERATURA",
    "O FIM DO CICLO",
]


@pytest.mark.parametrize("texto", TEXTOS_DE_REGRA)
def test_nenhuma_regra_ficou_dentro_da_planta(texto):
    physics = _le(os.path.join(DIR_MODULOS, "physics.py"))
    # A docstring do modulo fala das regras; o teste olha so o codigo.
    corpo = physics.split('"""', 2)[-1]
    assert texto not in corpo, (
        "o texto de regra %r aparece em physics.py — a planta esta decidindo" % texto
    )


def test_planta_sozinha_nao_decide_nada():
    """Sem atuacao nenhuma, a planta nao mexe na barra nem na concentracao.

    E a versao executavel do teste anterior: se um `if` de controle tivesse
    sobrado, uma hora ele dispararia sozinho.
    """
    import physics
    import saida

    p = physics.Planta(arquivo=os.devnull)
    with saida.captura():
        p.inicializa(650, 1800, 210, 4, -0.3, -0.8, 0, tmax=1440, truncar=False)
        for _ in range(120):
            p.passo()
        e = p.estado()
    assert e["PosicaoBarra"] == 210
    assert e["Cboro"] == 1800.0
    assert e["t"] == 120


@pytest.mark.parametrize("flags,entrada", [
    (["--tmax=240"], "650 1800 210 4 -0.3 -0.8 0"),
    (["--tmax=240", "--transiente=runback-150", "--t-transiente=10"],
     "650 1800 210 4 -0.3 -0.8 0"),
    (["--tmax=300"], "650 1800 170 4 -0.3 -0.8 -1"),
])
def test_corrida_identica_ao_porte_fiel(tmp_path, flags, entrada):
    """planta + braco procedural == simulador.py, byte a byte.

    Horizontes curtos de proposito: a bateria completa (6 cenarios, ciclo
    inteiro, ~500 mil minutos) esta em scripts/verifica_fronteira_reactor.sh.
    Aqui o que se quer e uma rede de seguranca que rode em segundos a cada
    `pytest`, dentro do conteiner que esta servindo a API.
    """
    if not os.path.exists(BRACO_PY):
        pytest.skip("braco procedural nao montado em %s" % BRACO_PY)

    stdin = "\n".join(entrada.split()) + "\n"
    amb = dict(os.environ, DIR_MODULOS=DIR_MODULOS)

    mono = subprocess.run([sys.executable, PORTE_PY] + flags,
                          input=stdin.encode(), capture_output=True,
                          cwd=tmp_path, env=amb)
    sep = subprocess.run([sys.executable, BRACO_PY] + flags,
                         input=stdin.encode(), capture_output=True,
                         cwd=tmp_path, env=amb)
    assert mono.returncode == 0, mono.stderr.decode()[-2000:]
    assert sep.returncode == 0, sep.stderr.decode()[-2000:]

    assert sep.stdout == mono.stdout, (
        "a saida padrao divergiu (%d vs %d bytes)"
        % (len(mono.stdout), len(sep.stdout))
    )
    a = (tmp_path / "Modelagem_Reator_py.txt").read_bytes()
    b = (tmp_path / "Modelagem_Reator_api.txt").read_bytes()
    assert b == a, "o arquivo de amostras divergiu"
