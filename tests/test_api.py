#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_api.py — o contrato HTTP da planta.

O que se verifica aqui nao e a fisica (disso cuida test_genealogia.py, byte a
byte contra o porte fiel), e sim que a API entrega o que o expert vai precisar:

  - a observacao completa, com os nomes do fonte e o tipo C de cada grandeza;
  - uma atuacao por chamada, com o estado resultante na resposta;
  - o texto impresso por cada chamada, para a saida padrao ser remontavel;
  - sessoes isoladas;
  - e, principalmente, que o servico NAO decide nada.
"""

import ast
import os

import pytest

from conftest import saida, so_para

pytestmark = so_para("reactor")

# steps/03-regras-controle.md §2: o que o controlador enxerga.
GRANDEZAS_DAS_REGRAS = [
    "DeltaT", "DesvioDeltaI", "VariacaoDeltaI", "DeltaI",
    "PosicaoBarra", "LimiteInsercao", "BD", "Cboro",
]


def test_health(api):
    codigo, r = api.get("/health")
    assert codigo == 200
    assert r["status"] == "ok"
    assert r["servico"] == "reactor"


def test_tipos_cobre_as_grandezas_das_regras(api):
    codigo, tipos = api.get("/reactor/tipos")
    assert codigo == 200
    for g in GRANDEZAS_DAS_REGRAS:
        assert g in tipos, "%s nao esta na observacao" % g
    # Os tipos importam: e por eles que o cliente sabe onde arredondar a 32 bits.
    assert tipos["PosicaoBarra"] == "int"
    assert tipos["BD"] == "int"
    assert tipos["tempodilute"] == "int"
    assert tipos["tmax"] == "double"
    assert tipos["DeltaT"] == "float"


def test_initialize_produz_o_estado_do_cenario_1(sessao):
    r = sessao()
    e = r["estado"]
    assert r["pode_continuar"] is True
    assert e["Cboro"] == 1800.0
    assert e["PosicaoBarra"] == 210
    assert e["Tmed"] == e["Tref"]          # a partida e em equilibrio
    assert e["DeltaT"] == 0.0
    # Derivados de Cboro=1800 conferidos em steps/03-regras-controle.md §5.5
    assert e["v1"] == pytest.approx(5.0047, abs=1e-4)
    assert e["v2"] == pytest.approx(19.8442, abs=1e-4)
    assert e["a"] == pytest.approx(2 * e["v1"], abs=1e-6)
    assert e["b"] == pytest.approx(e["v1"], abs=1e-6)
    # O prologo imprime os prompts do operador, mesmo sem teclado.
    assert "Digite a Potencia Inicial da Turbina" in saida(r)


def test_passo_avanca_um_minuto_e_nada_mais(sessao, api):
    r = sessao()
    sid = r["sessao"]
    _, r1 = api.post("/reactor/%s/passo" % sid, None)
    assert r1["estado"]["t"] == 1.0
    # Pot=100% => LimiteInsercao = 2,58.100-85 = 173 ; BD = 0,73.100+144 = 217
    assert r1["estado"]["LimiteInsercao"] == pytest.approx(173.0, abs=1e-3)
    assert r1["estado"]["BD"] == 217
    assert saida(r1), "o passo tem de devolver o que imprimiu"


def test_servico_nao_decide_nada(sessao, api):
    """Passos ate DEPOIS de a planta pedir controle, sem nenhuma atuacao.

    E o teste central deste passo, e o horizonte foi escolhido para que ele
    signifique alguma coisa. Com Cboro=1800 a queima derruba Tmed de 0,1 °C a
    cada `taxatemp` = (2601-1800)/6,31 = 126 minutos: DeltaT vale -0,1 em t=126
    e -0,2 em t=252. A guarda de R1-R4 e `DeltaT < -0,1`, estrita — so passa a
    valer no segundo degrau. Por isso 300 minutos, e nao 120: no monolito, R1 ja
    teria diluido bem antes do fim desta corrida.

    Aqui nao acontece nada. E o que se quer provar.
    """
    r = sessao()
    sid = r["sessao"]
    for _ in range(300):
        _, r = api.post("/reactor/%s/passo" % sid, None)
    e = r["estado"]
    assert e["t"] == 300.0
    assert e["DeltaT"] < -0.1, "o cenario nem chegou a pedir controle"
    assert e["PosicaoBarra"] == 210, "a barra se moveu sem ninguem mandar"
    assert e["Cboro"] == 1800.0, "a concentracao mudou sem diluicao nem boracao"


@pytest.mark.parametrize("passos", [1, 2, -1, -2])
def test_acao_barra(sessao, api, passos):
    r = sessao()
    sid = r["sessao"]
    _, r = api.post("/reactor/%s/passo" % sid, None)
    p0, t0 = r["estado"]["PosicaoBarra"], r["estado"]["t"]
    _, r = api.post("/reactor/%s/acao" % sid,
                    {"acao": {"tipo": "barra", "passos": passos}})
    assert r["estado"]["PosicaoBarra"] == p0 + passos
    assert r["estado"]["t"] == t0 + 2       # movimentacao de barra custa 2 min
    assert "MOVIMENTACAO DE BARRA" in saida(r)


def test_acao_diluir_tira_boro_e_consome_tempodilute_mais_homogeneizacao(sessao, api):
    r = sessao()
    sid = r["sessao"]
    _, r = api.post("/reactor/%s/passo" % sid, None)
    c0, t0 = r["estado"]["Cboro"], r["estado"]["t"]
    vazao = r["estado"]["v1"]
    _, r = api.post("/reactor/%s/acao" % sid,
                    {"acao": {"tipo": "diluir", "vazao": vazao}})
    assert r["estado"]["Cboro"] < c0
    # tempodilute (4) + thom (18 minutos de homogeneizacao da massa do SRR)
    assert r["estado"]["t"] == t0 + 4 + 18
    assert "Diluicao Encerrada" in saida(r)


def test_acao_borar_poe_boro(sessao, api):
    r = sessao()
    sid = r["sessao"]
    _, r = api.post("/reactor/%s/passo" % sid, None)
    c0, t0 = r["estado"]["Cboro"], r["estado"]["t"]
    _, r = api.post("/reactor/%s/acao" % sid,
                    {"acao": {"tipo": "borar", "vazao_boro": 10.0, "vboro": 20.0}})
    assert r["estado"]["Cboro"] > c0
    assert r["estado"]["t"] == t0 + 18      # so a homogeneizacao
    assert "Volume de Boro adicionado" in saida(r)


def test_acao_desconhecida_e_recusada(sessao, api):
    sid = sessao()["sessao"]
    codigo, _ = api.post("/reactor/%s/acao" % sid,
                         {"acao": {"tipo": "desligar", "passos": 1}})
    assert codigo == 422


def test_rampa_sem_taxa_e_recusada(api):
    codigo, _ = api.post("/reactor/initialize",
                         {"transiente": "rampa", "alvo": 650, "taxa": 0})
    assert codigo == 422


def test_sessao_inexistente(api):
    codigo, _ = api.get("/reactor/naoexiste/estado")
    assert codigo == 404
    codigo, _ = api.post("/reactor/naoexiste/passo", None)
    assert codigo == 404


def test_sessoes_sao_isoladas(sessao, api):
    a = sessao()["sessao"]
    b = sessao(posicao_barra=180)["sessao"]
    assert a != b
    for _ in range(3):
        api.post("/reactor/%s/passo" % a, None)
    _, ra = api.get("/reactor/%s/estado" % a)
    _, rb = api.get("/reactor/%s/estado" % b)
    assert ra["estado"]["t"] == 3.0
    assert rb["estado"]["t"] == 0.0
    assert rb["estado"]["PosicaoBarra"] == 180


def test_encerrar_sessao(sessao, api):
    sid = sessao()["sessao"]
    codigo, r = api.delete("/reactor/" + sid)
    assert codigo == 200 and r["encerrada"] is True
    codigo, _ = api.get("/reactor/%s/estado" % sid)
    assert codigo == 404


def test_nomes_de_transiente_batem_com_os_da_planta(api):
    """Os drivers de validacao trazem a lista de nomes por conta propria.

    Eles rodam dentro do conteiner do expert, onde physics nao existe, entao nao
    podem importa-la de la. Este teste e o que impede as duas listas de derivar:
    o que a API aceita tem de ser exatamente o que os drivers oferecem.
    """
    import physics
    from conftest import BRACO_PY, DECL_PY
    for caminho in (BRACO_PY, DECL_PY):
        if not os.path.exists(caminho):
            continue
        arvore = ast.parse(open(caminho, encoding="utf-8").read())
        nomes = None
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Assign) and len(no.targets) == 1
                    and getattr(no.targets[0], "id", None) == "NOMES_TRANSIENTE"):
                nomes = set(ast.literal_eval(no.value))
        assert nomes is not None, "%s nao declara NOMES_TRANSIENTE" % caminho
        assert nomes == set(physics.TRANSIENTES), (
            "%s: %s" % (caminho, nomes ^ set(physics.TRANSIENTES)))


def test_interno_expoe_o_estado_completo(sessao, api):
    sid = sessao()["sessao"]
    codigo, r = api.get("/reactor/%s/interno" % sid)
    assert codigo == 200
    interno = r["interno"]
    # As globais do .c: as do modelo de Xe/Iodo nao aparecem na observacao.
    for nome in ("Nxeb", "Nig", "lambdaXe", "Sigmaf", "erro", "thom", "Msrr"):
        assert nome in interno, "%s deveria estar no despejo interno" % nome
    assert len(interno) > len(r.get("estado", {}))
