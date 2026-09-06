#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
planta.py — o cliente do reator.

A planta vista de fora: mesma interface que reactor/physics.Planta expoe, so que
cada metodo e um POST. O motor nao sabe a diferenca — e por isso que as 19
regras nao mudam uma linha entre rodar contra o servico e rodar contra um objeto
em memoria.

Duas responsabilidades alem de falar HTTP:

  1. GUARDAR O ESTADO. Cada resposta ja traz o estado resultante, entao ler o
     estado entre duas regras nao custa requisicao nenhuma — so as atuacoes
     custam. Um ciclo do cenario 1 gasta em media pouco mais de uma chamada.

  2. REEMITIR O TEXTO. A resposta traz o que aquela chamada imprimiu, e ele e
     reemitido AQUI, no instante da chamada. E o que faz a saida remontada ficar
     na ordem do simulador monolitico: o expert imprime "Iniciada a Diluicao",
     a planta responde "Diluicao Encerrada" e o efeito, a regra seguinte
     continua.

Usa urllib da stdlib, e nao requests/httpx: e uma chamada JSON simples, sincrona,
para um servico da mesma rede. Nao vale uma dependencia a mais na imagem, e a
suite de testes ja fala HTTP do mesmo jeito.
"""

import base64
import json
import urllib.error
import urllib.request

from saida import putc_raw

TEMPO_LIMITE = 600


class ErroDoReator(RuntimeError):
    """O reator recusou ou nao respondeu."""


class PlantaRemota:

    def __init__(self, url_reator, parametros):
        self.base = url_reator.rstrip("/")
        r = self._post("/reactor/initialize", parametros)
        self.sid = r["sessao"]
        self._tipos = self._get("/reactor/tipos")
        self._aplica(r)

    # -- transporte ------------------------------------------------------

    def _abre(self, req):
        try:
            with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode("utf-8", "replace")[:500]
            raise ErroDoReator("%s %s -> %d: %s"
                               % (req.get_method(), req.full_url, e.code, detalhe))
        except urllib.error.URLError as e:
            raise ErroDoReator("nao alcancei %s: %s" % (req.full_url, e.reason))

    def _get(self, rota):
        return self._abre(urllib.request.Request(self.base + rota))

    def _post(self, rota, corpo):
        return self._abre(urllib.request.Request(
            self.base + rota, data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST"))

    def _aplica(self, r):
        self._estado = r["estado"]
        self._pode = r["pode_continuar"]
        # putc_raw, e nao printf: sao bytes, e printf codificaria em UTF-8.
        putc_raw(base64.b64decode(r["saida_b64"]))

    # -- a interface que o motor usa -------------------------------------

    def tipos(self):
        return self._tipos

    def estado(self):
        return self._estado

    def pode_continuar(self):
        return self._pode

    def passo(self):
        self._aplica(self._post("/reactor/%s/passo" % self.sid, {}))

    def diluir(self, vazao):
        self._aplica(self._post("/reactor/%s/acao" % self.sid,
                                {"acao": {"tipo": "diluir", "vazao": float(vazao)}}))

    def borar(self, vazao_boro, vboro):
        self._aplica(self._post("/reactor/%s/acao" % self.sid,
                                {"acao": {"tipo": "borar",
                                          "vazao_boro": float(vazao_boro),
                                          "vboro": float(vboro)}}))

    def mover_barra(self, passos):
        self._aplica(self._post("/reactor/%s/acao" % self.sid,
                                {"acao": {"tipo": "barra", "passos": int(passos)}}))

    def encerra(self):
        try:
            self._abre(urllib.request.Request(
                self.base + "/reactor/" + self.sid, method="DELETE"))
        except ErroDoReator:
            pass       # encerrar e cortesia; a sessao expira com o servico
