#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cenarios.py — le cenarios.json e traduz para as tres sintaxes que os
consumidores precisam.

POR QUE ESTE MODULO EXISTE

    Os 6 cenarios sao um conjunto de numeros so, mas cada consumidor precisa
    deles numa forma diferente:

        stdin do simulador   "650 1800 210 4 -0.3 -0.8 0"
        linha de comando     --transiente=rampa --alvo=650 --taxa=1 --tmax=1440
        corpo da API         {"pot_turbina":650, "transiente":"rampa", ...}

    Se cada consumidor derivasse a sua forma por conta propria, o arquivo unico
    resolveria a duplicacao dos NUMEROS e criaria uma duplicacao das REGRAS DE
    TRADUCAO — que e o mesmo problema com outra cara. Por isso a traducao mora
    aqui, uma vez.

USO COMO MODULO

    from cenarios import cenario, entrada, flags, corpo_api, descricao
    flags(4)        -> "--transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440"

USO NA LINHA DE COMANDO (para o shell)

    python3 scripts/cenarios.py --entrada 4     -> 32 1800 144 4 -0.3 -0.8 0
    python3 scripts/cenarios.py --flags 4       -> --transiente=rampa --alvo=650 ...
    python3 scripts/cenarios.py --json 4        -> "pot_turbina":32, "posicao_barra":144, ...
    python3 scripts/cenarios.py --descricao 4   -> rampa 32 → 650 MW a 1 MW/min
    python3 scripts/cenarios.py --numeros       -> 1 2 3 4 5 6
"""

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = os.path.join(RAIZ, "cenarios.json")

# Os 7 valores do operador, na ordem exata dos prompts do simulador original.
# Essa ordem e contrato com o .c: mudar aqui quebra a entrada de stdin.
ORDEM_PROMPTS = ("pot_turbina", "cboro", "posicao_barra", "tempodilute",
                 "t1", "t2", "delta_i")


def _carrega():
    with open(ARQUIVO, encoding="utf-8") as f:
        return json.load(f)["cenarios"]


CENARIOS = _carrega()


def numeros():
    return sorted(CENARIOS, key=int)


def cenario(n):
    c = CENARIOS.get(str(n))
    if c is None:
        raise KeyError("cenário %s não existe em cenarios.json" % n)
    return c


def descricao(n):
    return cenario(n)["descricao"]


def _numero(v):
    """Formata sem casa decimal supérflua: 650 e não 650.0, mas -0.3 intacto."""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def entrada(n):
    """Os 7 valores como o simulador os lê do stdin, separados por espaço."""
    c = cenario(n)
    return " ".join(_numero(c[k]) for k in ORDEM_PROMPTS)


def flags(n):
    """A linha de comando de ./simulador e de simulador.py.

    Os 7 valores NAO entram aqui — eles vao pelo stdin. O que entra e o cenario:
    transiente, seus parametros, e o horizonte.
    """
    c = cenario(n)
    saida = []
    if c["transiente"]:
        saida.append("--transiente=%s" % c["transiente"])
        if c["transiente"] == "rampa":
            saida.append("--alvo=%s" % _numero(c["alvo"]))
            saida.append("--taxa=%s" % _numero(c["taxa"]))
        saida.append("--t-transiente=%s" % _numero(c["t_transiente"]))
    if c["tmax"] is not None:
        saida.append("--tmax=%s" % _numero(c["tmax"]))
    return " ".join(saida)


def corpo_api(n, **extra):
    """O corpo de POST /expert/initialize (ou /reactor/initialize).

    Campos nulos sao OMITIDOS, nao mandados como null: `tmax` ausente significa
    "use o padrao do servico", e `transiente` ausente significa "sem transiente".
    Mandar null em tmax seria erro de validacao (o modelo exige gt=0).

    `reactor_url` tambem fica de fora de proposito: o padrao do servico ja e o
    endereco certo, e ele so resolve dentro da rede dos conteineres — quem chama
    de fora nao teria como preenche-lo.
    """
    c = cenario(n)
    corpo = {k: c[k] for k in ORDEM_PROMPTS}
    for k in ("tmax", "transiente", "t_transiente", "alvo", "taxa"):
        if c[k] is not None:
            corpo[k] = c[k]
    corpo.update(extra)
    return corpo


def json_parcial(n):
    """O corpo da API como fragmento de JSON sem as chaves externas, para o
    shell colar dentro de um `-d '{...}'` que ele mesmo monta."""
    itens = corpo_api(n).items()
    return ", ".join('"%s":%s' % (k, json.dumps(v, ensure_ascii=False))
                     for k, v in itens)


def main(argv):
    if len(argv) == 2 and argv[1] == "--numeros":
        print(" ".join(numeros()))
        return 0
    if len(argv) != 3:
        sys.stderr.write(__doc__.split("USO NA LINHA DE COMANDO")[1])
        return 1
    opcao, n = argv[1], argv[2]
    try:
        if opcao == "--entrada":
            print(entrada(n))
        elif opcao == "--flags":
            print(flags(n))
        elif opcao == "--json":
            print(json_parcial(n))
        elif opcao == "--descricao":
            print(descricao(n))
        else:
            sys.stderr.write("opção desconhecida: %s\n" % opcao)
            return 1
    except KeyError as e:
        sys.stderr.write("%s\n" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
