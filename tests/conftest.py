#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conftest.py — onde estao os modulos sob teste e qual servico esta rodando.

A suite entra nos conteineres por montagem read-only (ver docker-compose.yml) e
roda DENTRO da imagem, contra os modulos que estao efetivamente servindo a API:

    podman exec reactor-simulator python -m pytest /tests
    podman exec reactor-expert-system python -m pytest /tests

Nao e detalhe de conveniencia. Testar uma copia dos modulos no host provaria
que a copia funciona; o que interessa e que o que esta no ar funciona — com a
versao de Python da imagem, as versoes fixadas em requirements.txt e as mesmas
variaveis de ambiente.

Os dois conteineres montam a MESMA pasta tests/. SERVICO diz qual deles esta
executando, e cada modulo de teste se pula sozinho quando nao e a sua vez.

Fora do conteiner a suite tambem roda, a partir da raiz do repositorio: os
caminhos caem nos equivalentes do repo, e o que depende do servico no ar e
pulado se a porta nao responder.
"""

import base64
import os
import sys
import urllib.error
import urllib.request

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _caminho(env, *fallback):
    v = os.environ.get(env)
    if v and os.path.exists(v):
        return v
    return os.path.join(_RAIZ, *fallback)


SERVICO = os.environ.get("SERVICO") or "reactor"

# DIR_MODULOS e sempre "os modulos que estao servindo ESTA API" — /api dentro de
# qualquer um dos dois conteineres. Os testes que precisam nomear um servico
# especifico usam DIR_REACTOR/DIR_EXPERT, que resolvem para /api quando e o
# servico corrente e para a pasta do repositorio quando se roda fora.
DIR_MODULOS = _caminho("DIR_MODULOS", SERVICO)
DIR_REACTOR = DIR_MODULOS if SERVICO == "reactor" else _caminho("DIR_REACTOR", "reactor")
DIR_EXPERT = DIR_MODULOS if SERVICO == "expert" else _caminho("DIR_EXPERT", "expert")
PORTE_PY = _caminho("PORTE_PY", "simulador.py")
BRACO_PY = _caminho("BRACO_PY", "scripts", "validate_c_vs_python.py")
DECL_PY = _caminho("DECL_PY", "scripts", "validate_expert.py")
FONTE_C = _caminho("FONTE_C", "V8_Reatividade_SimuladorIgor_linux.c")
REACTOR_API_URL = os.environ.get("REACTOR_API_URL", "http://localhost:8008")
EXPERT_API_URL = os.environ.get("EXPERT_API_URL", "http://localhost:8009")

sys.path.insert(0, DIR_MODULOS)


def saida(resposta):
    """Os bytes de `saida_b64` como texto, para os testes lerem.

    A API transporta BYTES, nao texto: R18 e R19 imprimem o byte 177 cru (o '▒'
    do codepage 437), que nao e UTF-8 valido. Aqui basta decodificar tolerando
    esses bytes — os testes procuram trechos ASCII.
    """
    return base64.b64decode(resposta["saida_b64"]).decode("utf-8", "replace")


def so_para(servico):
    """Marca um modulo de teste como pertencente a um dos dois servicos."""
    return pytest.mark.skipif(
        SERVICO != servico,
        reason="teste do servico %s; aqui SERVICO=%s" % (servico, SERVICO),
    )


def exige(servico):
    """Pula o modulo INTEIRO, ainda na coleta, se nao for o servico corrente.

    Diferente de so_para(): a marca so age na hora de rodar cada teste, e ate la
    o modulo ja foi importado. Modulos que importam os modulos do OUTRO servico
    (expert/regras.py, por exemplo) precisam parar antes disso — no conteiner do
    reactor esses modulos nao existem, e o import quebraria a coleta inteira.
    """
    if SERVICO != servico:
        pytest.skip("teste do servico %s; aqui SERVICO=%s" % (servico, SERVICO),
                    allow_module_level=True)


class Cliente:
    """Cliente HTTP minimo, so com a stdlib.

    De proposito: a imagem do servico nao carrega requests nem httpx, e nao vai
    carregar por causa de teste. O que se quer verificar aqui e o contrato HTTP,
    que urllib exercita tao bem quanto qualquer biblioteca.
    """

    def __init__(self, base):
        self.base = base.rstrip("/")

    def _abre(self, req):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                corpo = r.read().decode("utf-8")
                return r.status, (__import__("json").loads(corpo) if corpo else None)
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8")
            return e.code, (__import__("json").loads(corpo) if corpo else None)

    def get(self, rota):
        return self._abre(urllib.request.Request(self.base + rota))

    def post(self, rota, corpo=None):
        dados = __import__("json").dumps(corpo).encode("utf-8")
        return self._abre(urllib.request.Request(
            self.base + rota, data=dados,
            headers={"Content-Type": "application/json"}))

    def delete(self, rota):
        return self._abre(urllib.request.Request(self.base + rota, method="DELETE"))


@pytest.fixture(scope="session")
def api_expert():
    c = Cliente(EXPERT_API_URL)
    try:
        codigo, _ = c.get("/health")
    except Exception as e:
        pytest.skip("expert nao responde em %s: %s" % (EXPERT_API_URL, e))
    if codigo != 200:
        pytest.skip("/health do expert respondeu %s" % codigo)
    return c


@pytest.fixture(scope="session")
def api():
    c = Cliente(REACTOR_API_URL)
    try:
        codigo, _ = c.get("/health")
    except Exception as e:
        pytest.skip("servico nao responde em %s: %s" % (REACTOR_API_URL, e))
    if codigo != 200:
        pytest.skip("/health respondeu %s em %s" % (codigo, REACTOR_API_URL))
    return c


@pytest.fixture
def sessao(api):
    """Uma sessao de reator do cenario 1, encerrada no fim do teste."""
    criadas = []

    def cria(**kw):
        params = dict(pot_turbina=650, cboro=1800, posicao_barra=210,
                      tempodilute=4, t1=-0.3, t2=-0.8, delta_i=0, tmax=1440)
        params.update(kw)
        codigo, r = api.post("/reactor/initialize", params)
        assert codigo == 200, r
        criadas.append(r["sessao"])
        return r

    yield cria
    for sid in criadas:
        api.delete("/reactor/" + sid)
