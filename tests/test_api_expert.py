#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_api_expert.py — o contrato HTTP do sistema especialista.

O espelho de test_api.py. La o teste central e que o servico NAO decide nada;
aqui e o contrario: que ele decide, que decide na ordem certa, e que nao sabe
fisica nenhuma.
"""

import pytest

from conftest import REACTOR_API_URL, saida, so_para

pytestmark = so_para("expert")

REGRAS_ESPERADAS = ["R%d" % i for i in range(1, 20)]


@pytest.fixture
def sessao_expert(api_expert):
    criadas = []

    def cria(**kw):
        params = dict(reactor_url=REACTOR_API_URL, pot_turbina=650, cboro=1800,
                      posicao_barra=210, tempodilute=4, t1=-0.3, t2=-0.8,
                      delta_i=0, tmax=1440)
        params.update(kw)
        codigo, r = api_expert.post("/expert/initialize", params)
        assert codigo == 200, r
        criadas.append(r["sessao"])
        return r

    yield cria
    for sid in criadas:
        api_expert.delete("/expert/" + sid)


def test_health(api_expert):
    codigo, r = api_expert.get("/health")
    assert codigo == 200
    assert r["servico"] == "expert"
    assert r["regras"] == 19


# ---------------------------------------------------------------------------
# A base de regras e dado, e o dado e o que decide
# ---------------------------------------------------------------------------

def test_regras_expoe_as_19_na_ordem_do_fonte(api_expert):
    codigo, regras = api_expert.get("/expert/regras")
    assert codigo == 200
    assert [r["id"] for r in regras] == REGRAS_ESPERADAS
    assert [r["prioridade"] for r in regras] == list(range(1, 20))
    # a linha do .c cresce junto com a prioridade: a ordem E a do fonte
    linhas = [r["linha_c"] for r in regras]
    assert linhas == sorted(linhas)


def test_condicao_publicada_e_o_texto_do_c(api_expert):
    codigo, regras = api_expert.get("/expert/regras")
    por_id = {r["id"]: r for r in regras}
    # R1, linha 720 do V8_Reatividade_SimuladorIgor_linux.c
    assert por_id["R1"]["condicao"] == (
        "(VariacaoDeltaI>=0 || DeltaT<-0.3) || (PosicaoBarra>=222 || DesvioDeltaI>-3)")
    assert por_id["R1"]["linha_c"] == 720
    # `||` e nao `or`: e o texto do fonte C, nao uma parafrase em Python
    assert "||" in por_id["R1"]["condicao"]


def test_guardas_de_bloco(api_expert):
    codigo, regras = api_expert.get("/expert/regras")
    por_id = {r["id"]: r for r in regras}
    for rid in ("R1", "R2", "R3", "R4"):
        assert por_id[rid]["bloco"] == "CompensacaoQueima"
        assert por_id[rid]["guarda_do_bloco"] == "DeltaT < -0.1"
    for rid in ("R5", "R6", "R7", "R8"):
        assert por_id[rid]["bloco"] == "Corrige_DeltaI"
        assert por_id[rid]["guarda_do_bloco"] == "DesvioDeltaI > 2 || DesvioDeltaI < -2"
    for rid in ("R9", "R13", "R19"):
        assert por_id[rid]["bloco"] == "laco"
        assert por_id[rid]["guarda_do_bloco"] is None


def test_consequente_partido_de_r11_e_r12(api_expert):
    """steps/03 §5.4: alarme com a condicao externa, boracao so com ela E DeltaI<0."""
    codigo, regras = api_expert.get("/expert/regras")
    por_id = {r["id"]: r for r in regras}
    for rid in ("R11", "R12"):
        efeitos = por_id[rid]["efeitos"]
        assert [e["tipo"] for e in efeitos] == ["alarme", "borar"]
        assert efeitos[0]["quando"] is None          # o alarme sai sempre
        assert efeitos[1]["quando"] == "DeltaI<0"    # a boracao, nao


def test_r9_escolhe_entre_menos_um_e_menos_dois(api_expert):
    codigo, regras = api_expert.get("/expert/regras")
    r9 = [r for r in regras if r["id"] == "R9"][0]
    passos = r9["efeitos"][0]["detalhe"]["passos"]
    assert passos == [{"quando": "DeltaT < 1", "passos": "-1"},
                      {"quando": "senao", "passos": "-2"}]


# ---------------------------------------------------------------------------
# A malha
# ---------------------------------------------------------------------------

def test_initialize_abre_sessao_no_reator(sessao_expert):
    r = sessao_expert()
    assert r["sessao"] and r["sessao_reator"]
    assert r["sessao"] != r["sessao_reator"]
    assert r["ciclos"] == 0
    assert r["termino"] == ""
    assert r["estado"]["Cboro"] == 1800.0
    assert "Digite a Potencia Inicial da Turbina" in saida(r)


def test_reator_inalcancavel_da_502(api_expert):
    codigo, r = api_expert.post("/expert/initialize",
                                {"reactor_url": "http://nao-existe-mesmo:8008"})
    assert codigo == 502


def test_ciclo_dispara_regras_e_devolve_quais(sessao_expert, api_expert):
    r = sessao_expert()
    sid = r["sessao"]
    codigo, r = api_expert.post("/expert/%s/ciclo" % sid, None)
    assert codigo == 200
    assert r["ciclos"] == 1
    assert r["disparadas"], "no cenario 1 o primeiro minuto ja dispara R13"
    assert all(d in REGRAS_ESPERADAS for d in r["disparadas"])


def test_disparo_multiplo_e_ordem(sessao_expert, api_expert):
    """A estrategia: varias regras por ciclo, sempre na ordem da base."""
    r = sessao_expert()
    sid = r["sessao"]
    prioridade = {rid: i for i, rid in enumerate(REGRAS_ESPERADAS)}
    viu_multiplo = False
    for _ in range(60):
        _, r = api_expert.post("/expert/%s/ciclo" % sid, None)
        d = r["disparadas"]
        if len(d) > 1:
            viu_multiplo = True
        assert [prioridade[x] for x in d] == sorted(prioridade[x] for x in d), \
            "regras dispararam fora da ordem do fonte: %s" % d
    assert viu_multiplo, "nenhum ciclo com disparo multiplo em 60 minutos"


def test_executar_ate_o_horizonte(sessao_expert, api_expert):
    r = sessao_expert(tmax=240)
    sid = r["sessao"]
    codigo, r = api_expert.post("/expert/%s/executar" % sid, {})
    assert codigo == 200
    assert r["estado"]["t"] >= 240
    assert r["pode_continuar"] is False
    assert "Fim do Programa" in saida(r)
    # depois de encerrada, pedir mais um ciclo e 409
    codigo, _ = api_expert.post("/expert/%s/ciclo" % sid, None)
    assert codigo == 409


def test_max_ciclos_limita_a_chamada(sessao_expert, api_expert):
    r = sessao_expert()
    sid = r["sessao"]
    _, r = api_expert.post("/expert/%s/executar" % sid, {"max_ciclos": 10})
    assert r["ciclos"] == 10
    assert r["pode_continuar"] is True
    assert "Fim do Programa" not in saida(r)


def test_disparos_respondem_a_pendencia_do_passo_3(sessao_expert, api_expert):
    """steps/03 §7: quais das 19 os cenarios da dissertacao exercitam."""
    r = sessao_expert(tmax=1440)
    sid = r["sessao"]
    api_expert.post("/expert/%s/executar" % sid, {})
    codigo, d = api_expert.get("/expert/%s/disparos" % sid)
    assert codigo == 200
    assert d["ciclos"] > 1000
    assert set(d["disparos"]) | set(d["nunca_dispararam"]) == set(REGRAS_ESPERADAS)
    # No cenario 1 so tres regras sao alcancadas: uma diluicao e duas de barra.
    assert set(d["disparos"]) == {"R1", "R9", "R13"}
    assert "R19" in d["nunca_dispararam"], "fim de ciclo nao ocorre em 1 dia"


def test_saida_carrega_bytes_e_nao_texto(sessao_expert, api_expert):
    """R18 imprime 37 bytes 177 crus. Se o campo fosse string UTF-8, quebraria.

    O cenario de runback leva DeltaT bem alem de 1,67 °C e alcanca R18 — foi
    exatamente este caso que revelou a necessidade de base64.
    """
    import base64
    r = sessao_expert(transiente="runback-bap", t_transiente=10, tmax=400)
    sid = r["sessao"]
    _, r = api_expert.post("/expert/%s/executar" % sid, {})
    crus = base64.b64decode(r["saida_b64"])
    assert b"\xb1" * 37 in crus, "os bytes 177 de R18 nao chegaram intactos"
    with pytest.raises(UnicodeDecodeError):
        crus.decode("utf-8")          # nao e texto UTF-8, e nunca foi


def test_sessao_inexistente(api_expert):
    codigo, _ = api_expert.get("/expert/naoexiste/estado")
    assert codigo == 404
    codigo, _ = api_expert.post("/expert/naoexiste/ciclo", None)
    assert codigo == 404


def test_rampa_sem_taxa_e_recusada(api_expert):
    codigo, _ = api_expert.post("/expert/initialize",
                                {"reactor_url": REACTOR_API_URL,
                                 "transiente": "rampa", "alvo": 650, "taxa": 0})
    assert codigo == 422


def test_encerrar_sessao(sessao_expert, api_expert):
    sid = sessao_expert()["sessao"]
    codigo, r = api_expert.delete("/expert/" + sid)
    assert codigo == 200 and r["encerrada"] is True
    codigo, _ = api_expert.get("/expert/%s/estado" % sid)
    assert codigo == 404
