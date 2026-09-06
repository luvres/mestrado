#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gera_graficos.py — um gráfico por cenário, com os 3 simuladores sobrepostos.

Lê o que scripts/gera_resultados.sh deixou em results/{C,python,API}/ e escreve
results/graficos/cenarioN.png (e .svg) com cinco painéis compartilhando o eixo do
tempo, cada um com as três curvas.

O PROBLEMA DE DESENHO, E COMO ELE FOI RESOLVIDO

    As três séries são IDÊNTICAS byte a byte. Desenhadas do jeito ingênuo, só a
    última apareceria, e o leitor não teria como distinguir "as três coincidem"
    de "só uma foi plotada" — que é justamente a conclusão que o gráfico existe
    para mostrar.

    Por isso as três recebem espessura decrescente e traço diferente:

        C        linha cheia, mais grossa
        python   tracejada, média          — as marcas cavalgam a linha cheia
        API      pontilhada, fina

    Assim a coincidência é visível: vê-se o tracejado e o pontilhado sobre a
    linha contínua. Um bloco no rodapé traz o SHA-256 comum, que é a prova
    numérica do que o olho vê.

CINCO PAINÉIS, E NÃO UM COM DOIS EIXOS

    Tmed anda perto de 303, o boro perto de 1800 e o Delta I perto de 0,5. Num
    eixo só, três das cinco grandezas viram linhas retas; com dois eixos, o
    gráfico passa a sugerir correlações que não existem. Painéis empilhados
    compartilhando o tempo é a forma correta.

Uso (dentro do contêiner de gráficos — ver scripts/gera_graficos.sh):
    python3 scripts/gera_graficos.py [--cenarios 1,2,3] [--sem-svg]
"""

import hashlib
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                        # noqa: E402
from matplotlib.ticker import MaxNLocator              # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(RAIZ, "results")
DEST = os.path.join(RES, "graficos")

# --- paleta ---------------------------------------------------------------
# Slots 1 a 3 da paleta categórica de referência, validados para todos os pares
# nos dois modos (CVD ΔE 9.2, visão normal ΔE 24.0). A ordem é o mecanismo de
# segurança para daltonismo — não trocar por gosto.
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
GRADE = "#e6e5e1"

# nível -> (cor, estilo de traço, espessura, ordem de desenho)
NIVEIS = (
    ("C",      "#2a78d6", "-",             2.4, 1),
    ("python", "#eb6834", (0, (7, 3)),     1.5, 2),
    ("API",    "#1baf7a", (0, (1.6, 2.4)), 1.1, 3),
)

# --- painéis: (coluna do arquivo, rótulo, unidade) ------------------------
# O arquivo tem 8 colunas:
#   0 Tempo  1 Pot Rx  2 Pot Turbina  3 Tmed  4 Delta I  5 Cboro  6 Banco D  7 Volume de Água
PAINEIS = (
    (1, "Potência do reator", "%"),
    (3, "Temperatura média do SRR", "°C"),
    (4, "Delta I", "%"),
    (6, "Banco de controle D", "passos"),
    (5, "Concentração de boro", "ppm"),
)

# As descrições vêm de cenarios.json, a fonte única dos 6 cenários.
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
from cenarios import descricao, numeros                       # noqa: E402

DESCRICAO = {int(n): descricao(n) for n in numeros()}

# Acima disto o traçado é decimado: 500 mil pontos não cabem num PNG de 1600 px
# de largura, e desenhá-los custa minutos sem mudar um pixel.
MAX_PONTOS = 4000


def le(caminho):
    """As 8 colunas do arquivo de amostras, como listas de float."""
    colunas = [[] for _ in range(8)]
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            if not linha[:1].isdigit():
                continue
            partes = linha.split()
            if len(partes) != 8:
                continue
            try:
                valores = [float(p) for p in partes]
            except ValueError:
                continue
            for i, v in enumerate(valores):
                colunas[i].append(v)
    return colunas


def decima(colunas, maximo=MAX_PONTOS):
    n = len(colunas[0])
    if n <= maximo:
        return colunas, 1
    passo = n // maximo + 1
    # O último ponto entra sempre: é onde o ciclo termina.
    idx = list(range(0, n, passo))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return [[c[i] for i in idx] for c in colunas], passo


def sha(caminho):
    return hashlib.sha256(open(caminho, "rb").read()).hexdigest()


def desenha(n, dados, shas, passo):
    fig, eixos = plt.subplots(
        len(PAINEIS), 1, figsize=(10.5, 12.5), sharex=True,
        gridspec_kw={"hspace": 0.25})
    fig.patch.set_facecolor(SUPERFICIE)

    for eixo, (coluna, rotulo, unidade) in zip(eixos, PAINEIS):
        eixo.set_facecolor(SUPERFICIE)
        for nivel, cor, traco, largura, ordem in NIVEIS:
            cols = dados[nivel]
            eixo.plot(cols[0], cols[coluna], color=cor, linestyle=traco,
                      linewidth=largura, zorder=ordem, label=nivel,
                      solid_capstyle="round", dash_capstyle="round")
        eixo.set_ylabel("%s\n(%s)" % (rotulo, unidade), fontsize=9.5,
                        color=TINTA_2, linespacing=1.5)
        # Grade recessiva e contínua — tracejar a grade compete com as séries.
        eixo.grid(True, color=GRADE, linewidth=0.6, linestyle="-")
        eixo.set_axisbelow(True)
        for lado in ("top", "right"):
            eixo.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            eixo.spines[lado].set_color(GRADE)
            eixo.spines[lado].set_linewidth(0.8)
        eixo.tick_params(colors=TINTA_2, labelsize=8.5, length=3, width=0.8)
        eixo.yaxis.set_major_locator(MaxNLocator(nbins=5))
        # Sem offset nem notacao cientifica: o boro tem de ser lido como
        # "1799,7 ppm", e nao como "-0,25" com um "+1.8e3" solto no canto.
        eixo.ticklabel_format(axis="y", style="plain", useOffset=False)

    eixos[-1].set_xlabel("tempo simulado (minutos)", fontsize=9.5, color=TINTA_2,
                         labelpad=8)

    # Legenda uma vez, no alto: identidade nunca fica só na cor.
    alcas, rotulos = eixos[0].get_legend_handles_labels()
    leg = fig.legend(alcas, rotulos, loc="upper right",
                     bbox_to_anchor=(0.985, 0.978), ncol=3, frameon=False,
                     fontsize=10, handlelength=3.2, columnspacing=1.8)
    for texto in leg.get_texts():
        texto.set_color(TINTA)

    fig.suptitle("Cenário %d — %s" % (n, DESCRICAO[n]),
                 x=0.075, y=0.980, ha="left", fontsize=15, color=TINTA)
    n_amostras = len(dados["C"][0])
    sub = "os três simuladores em cada painel · %s amostras" % f"{n_amostras:,}".replace(",", ".")
    if passo > 1:
        sub += " (traçado decimado 1:%d)" % passo
    fig.text(0.075, 0.955, sub, ha="left", fontsize=10, color=TINTA_2)

    # O bloco de identidade é o "relief" exigido pelo aviso de contraste da
    # paleta, e é também a prova numérica de que as três curvas coincidem.
    unico = len(set(shas.values())) == 1
    if unico:
        nota = ("As três curvas coincidem exatamente — os arquivos são idênticos "
                "byte a byte.\nSHA-256 comum: %s…" % shas["C"][:32])
    else:
        nota = "ATENÇÃO: os arquivos DIVERGEM entre si.\n" + \
               "  ".join("%s %s…" % (k, v[:12]) for k, v in shas.items())
    fig.text(0.075, 0.020, nota, ha="left", va="bottom", fontsize=8.5,
             color=TINTA_2, family="monospace", linespacing=1.6)

    fig.subplots_adjust(left=0.125, right=0.985, top=0.930, bottom=0.105)
    return fig


def main(argv):
    quais = list(range(1, 7))
    svg = True
    for arg in argv[1:]:
        if arg.startswith("--cenarios="):
            quais = [int(x) for x in arg.split("=", 1)[1].split(",")]
        elif arg == "--sem-svg":
            svg = False
        else:
            sys.stderr.write("Argumento desconhecido: %s\n" % arg)
            return 1

    os.makedirs(DEST, exist_ok=True)
    feitos = 0
    for n in quais:
        caminhos = {k: os.path.join(RES, k, "cenario%d.txt" % n)
                    for k, _, _, _, _ in NIVEIS}
        if not all(os.path.exists(p) for p in caminhos.values()):
            print("  cenário %d: faltam arquivos em results/ — pulado" % n)
            continue
        dados, passo = {}, 1
        for k, p in caminhos.items():
            cols, passo = decima(le(p))
            dados[k] = cols
        shas = {k: sha(p) for k, p in caminhos.items()}

        fig = desenha(n, dados, shas, passo)
        png = os.path.join(DEST, "cenario%d.png" % n)
        fig.savefig(png, dpi=150, facecolor=SUPERFICIE)
        if svg:
            fig.savefig(os.path.join(DEST, "cenario%d.svg" % n),
                        facecolor=SUPERFICIE)
        plt.close(fig)
        print("  cenário %d: %s (%d pontos traçados%s)"
              % (n, os.path.relpath(png, RAIZ), len(dados["C"][0]),
                 ", decimado 1:%d" % passo if passo > 1 else ""))
        feitos += 1
    print("\n%d gráfico(s) em %s" % (feitos, os.path.relpath(DEST, RAIZ)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
