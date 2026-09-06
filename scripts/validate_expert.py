#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_expert.py — o braco DECLARATIVO dirigindo a planta.

Gemeo de validate_c_vs_python.py, que faz o mesmo com o braco procedural. Os
dois existem para serem comparados: se a base de regras de expert/regras.py
disser exatamente o que os 19 blocos `if` do fonte dizem, as duas corridas tem
de produzir os mesmos bytes — e os mesmos que simulador.py.

A diferenca entre os dois arquivos e so quem decide:

    validate_c_vs_python.py   BracoProcedural  — 19 blocos `if` transcritos
    validate_expert.py        motor.Motor      — 19 registros interpretados

A planta e a mesma, o transporte e o mesmo, a saida e comparada do mesmo jeito.

SOBRE O sys.path

    Em processo, reactor/ entra ANTES de expert/. Os dois pacotes tem f32.py e
    saida.py, e o codigo dos dois pares e identico — mas precisam resolver para
    o MESMO modulo, senao haveria dois ContextVar de captura e o texto da planta
    cairia num buffer e o das regras noutro. tests/test_equivalencia_regras.py
    confere que os pares sao mesmo identicos.

USO — a mesma linha de comando de simulador.py

    echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' \
        | python3 scripts/validate_expert.py --tmax=1440 > /dev/null

    --api=URL     fala com o reator por HTTP em vez de importar a planta
    --arquivo=N   arquivo de amostras (padrao Modelagem_Reator_expert.txt)
    --capturar    passa a saida pelo buffer que a API usa
"""

import os
import re
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# expert/ por ultimo: f32 e saida vem de reactor/ (identicos), o resto de expert/
for _dir in (os.environ.get("DIR_EXPERT") or os.path.join(_RAIZ, "expert"),
             os.environ.get("DIR_MODULOS") or os.path.join(_RAIZ, "reactor")):
    if os.path.isdir(_dir):
        sys.path.insert(0, _dir)

import saida                                                    # noqa: E402
from motor import Motor                                         # noqa: E402
from planta import PlantaRemota                                 # noqa: E402
from regras import BASE                                         # noqa: E402

ARQUIVO_PADRAO = "Modelagem_Reator_expert.txt"

_RE_FLOAT = re.compile(r'\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')
_RE_INT = re.compile(r'\s*[+-]?\d+')


def atof(s):
    m = _RE_FLOAT.match(s)
    return float(m.group(0)) if m else 0.0


def atoi(s):
    m = _RE_INT.match(s)
    return int(m.group(0)) if m else 0


# Os nomes de transiente que a linha de comando aceita. Ficam aqui, e nao vindo
# de physics, porque este script tambem roda DENTRO do conteiner do expert, onde
# a planta nao existe — em modo --api o que se manda e o NOME, e o mapeamento
# para o codigo interno e da planta.
NOMES_TRANSIENTE = ("runback-bap", "runback-circ", "runback-400",
                    "runback-300", "runback-150", "rampa")


def main(argv):
    transiente = None
    alvo = taxa = 0.0
    t_transiente = 10
    tmax = 700000.0
    arquivo = ARQUIVO_PADRAO
    capturar = False
    api = None

    for arg in argv[1:]:
        if arg.startswith("--transiente="):
            val = arg[13:]
            if val not in NOMES_TRANSIENTE:
                sys.stderr.write("Transiente desconhecido: %s\n" % val)
                return 1
            transiente = val
        elif arg.startswith("--alvo="):
            alvo = atof(arg[7:])
        elif arg.startswith("--taxa="):
            taxa = atof(arg[7:])
        elif arg.startswith("--t-transiente="):
            t_transiente = atoi(arg[15:])
        elif arg.startswith("--tmax="):
            tmax = atof(arg[7:])
        elif arg.startswith("--arquivo="):
            arquivo = arg[10:]
        elif arg == "--capturar":
            capturar = True
        elif arg.startswith("--api="):
            api = arg[6:]
        else:
            sys.stderr.write("Argumento desconhecido: %s\n" % arg)
            return 1
    if transiente == "rampa" and taxa <= 0:
        sys.stderr.write("--transiente=rampa exige --alvo=<MW> e --taxa=<MW/min> positiva\n")
        return 1

    tokens = sys.stdin.read().split()
    v = [atof(x) for x in tokens] + [0.0] * 7
    pot_turbina, cboro, posicao_barra, tempodilute, t1, t2, delta_i = v[:7]
    win = os.environ.get('WIN_ORIGINAL', '') not in ('', '0')

    def corrida():
        if api:
            planta = PlantaRemota(api, {
                "pot_turbina": pot_turbina, "cboro": cboro,
                "posicao_barra": int(posicao_barra), "tempodilute": int(tempodilute),
                "t1": t1, "t2": t2, "delta_i": delta_i, "tmax": tmax,
                "transiente": transiente, "t_transiente": t_transiente,
                "alvo": alvo, "taxa": taxa, "win_original": win,
                "arquivo": os.path.basename(arquivo),
            })
            try:
                Motor(planta, BASE).executa()
            finally:
                planta.encerra()
        else:
            # So aqui a planta e necessaria — e so aqui ela e importada.
            from physics import Planta, TRANSIENTES, TR_NENHUM
            planta = Planta(arquivo=arquivo, win_original=win)
            planta.inicializa(pot_turbina, cboro, int(posicao_barra), int(tempodilute),
                              t1, t2, delta_i, tmax=tmax,
                              transiente=TRANSIENTES.get(transiente, TR_NENHUM),
                              t_transiente=t_transiente, alvo=alvo, taxa=taxa)
            Motor(planta, BASE).executa()

    if capturar:
        with saida.captura() as buf:
            corrida()
        sys.stdout.buffer.write(bytes(buf))
    else:
        corrida()
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    try:
        codigo = main(sys.argv)
    except BrokenPipeError:
        codigo = 0
    sys.exit(codigo)
