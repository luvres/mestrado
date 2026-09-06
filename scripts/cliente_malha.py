#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cliente_malha.py — roda a malha fechada pelos DOIS servicos e remonta a saida.

Este cliente nao decide nada e nao calcula nada. Ele so:

    POST /expert/initialize      abre a sessao, guarda o texto do prologo
    POST /expert/{sid}/executar  em pedacos, guardando o texto de cada resposta
    concatena                    e escreve no stdout

O que sai e a saida padrao do simulador remontada, e ela tem de bater byte a
byte com a de simulador.py. E o criterio de aceitacao do Passo 5.

POR QUE EM PEDACOS

    `executar` sem teto roda a corrida inteira numa requisicao so. No cenario 6
    isso seriam ~500 mil ciclos e mais de 400 MB de texto num unico campo JSON —
    o servidor teria de manter tudo em memoria para serializar. Com
    --pedaco=N cada resposta cobre no maximo N minutos simulados, e o cliente
    concatena. O resultado e identico; o que muda e o pico de memoria.

USO

    python3 scripts/cliente_malha.py --expert=http://localhost:8009 \
        --reactor=http://reactor-simulator:8008 --tmax=1440 \
        --arquivo=Modelagem_Reator_malha.txt > malha.out
"""

import base64
import json
import sys
import urllib.error
import urllib.request

TEMPO_LIMITE = 1800


def chama(url, corpo=None, verbo="GET"):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=verbo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write("%s %s -> %d: %s\n"
                         % (verbo, url, e.code, e.read().decode("utf-8", "replace")[:500]))
        raise


def main(argv):
    expert = "http://localhost:8009"
    reactor = "http://reactor-simulator:8008"
    arquivo = "Modelagem_Reator_malha.txt"
    pedaco = 20000
    params = {"tmax": 700000.0}

    for arg in argv[1:]:
        if arg.startswith("--expert="):
            expert = arg[9:]
        elif arg.startswith("--reactor="):
            reactor = arg[10:]
        elif arg.startswith("--arquivo="):
            arquivo = arg[10:]
        elif arg.startswith("--pedaco="):
            pedaco = int(arg[9:])
        elif arg.startswith("--tmax="):
            params["tmax"] = float(arg[7:])
        elif arg.startswith("--transiente="):
            params["transiente"] = arg[13:]
        elif arg.startswith("--alvo="):
            params["alvo"] = float(arg[7:])
        elif arg.startswith("--taxa="):
            params["taxa"] = float(arg[7:])
        elif arg.startswith("--t-transiente="):
            params["t_transiente"] = int(arg[15:])
        elif arg == "--win-original":
            params["win_original"] = True
        else:
            sys.stderr.write("Argumento desconhecido: %s\n" % arg)
            return 1

    # Os 7 valores do operador, na ordem dos prompts — a mesma entrada dos
    # outros validadores, para a comparacao ser direta.
    v = [float(x) for x in sys.stdin.read().split()] + [0.0] * 7
    params.update(pot_turbina=v[0], cboro=v[1], posicao_barra=int(v[2]),
                  tempodilute=int(v[3]), t1=v[4], t2=v[5], delta_i=v[6],
                  reactor_url=reactor, arquivo=arquivo)

    r = chama(expert + "/expert/initialize", params, "POST")
    sid = r["sessao"]
    escreve = sys.stdout.buffer.write
    escreve(base64.b64decode(r["saida_b64"]))
    try:
        while r["pode_continuar"]:
            r = chama("%s/expert/%s/executar" % (expert, sid),
                      {"max_ciclos": pedaco}, "POST")
            escreve(base64.b64decode(r["saida_b64"]))
        d = chama("%s/expert/%s/disparos" % (expert, sid))
        sys.stderr.write("ciclos=%d disparos=%s nunca=%s\n"
                         % (d["ciclos"],
                            json.dumps(d["disparos"], sort_keys=True),
                            ",".join(d["nunca_dispararam"])))
    finally:
        chama("%s/expert/%s" % (expert, sid), None, "DELETE")
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    try:
        codigo = main(sys.argv)
    except BrokenPipeError:
        codigo = 0
    sys.exit(codigo)
