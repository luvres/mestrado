#!/usr/bin/env python3
"""
Extrai as curvas do simulador das Figuras 6.1-6.17 da dissertação de mestrado de
Marcos Antonio Gonçalves da Silva Filho (COPPE/UFRJ, 2023) e grava uma série
numérica por figura em reference/.

Os gráficos do PDF são VETORIAIS: as curvas estão no content stream como
polilinhas. O que este script recupera são os vértices dessas polilinhas — uma
versão já decimada da corrida original do autor, não a saída numérica dela.
Ver reference/README.md.

Pontos que não são óbvios e custaram para descobrir:

1. A série do simulador é a AZUL, rgb(26.7%, 44.7%, 76.9%). A laranja
   rgb(92.9%, 49.0%, 19.2%) é o sistema especialista. Confirmado pela geometria
   da legenda: o traço azul fica imediatamente à esquerda do rótulo "Simulação".

2. Os paths do SVG estão sob um transform (matrix) por gráfico; é preciso compor
   a pilha de transforms para chegar às coordenadas da página.

3. A calibração dos eixos tem que usar as LINHAS DE GRADE cinza
   rgb(85.1%, 85.1%, 85.1%), não o centro da caixa de texto dos rótulos: a caixa
   do pdftotext usa ascent/descent da fonte e introduz viés vertical de ~1 pt,
   que vira +0,8 % em eixos de potência e +34 L em eixos de volume de água.

4. Números soltos do corpo do texto ("Figura 6.1") contaminam a coluna de
   rótulos, daí o ajuste robusto (RANSAC) em vez de pegar o primeiro e o último.

Requer: poppler-utils (pdftocairo, pdftotext).
Uso: python3 scripts/extrai_curvas_dissertacao.py
"""

import itertools
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
AZUL = 'rgb(26.699829%, 44.699097%, 76.899719%)'   # série "Simulação"
CINZA = 'rgb(85.099792%, 85.099792%, 85.099792%)'  # linhas de grade

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(RAIZ, 'docs',
                   'MSc - UFRJ - SISTEMA ESPECIALISTA PARA O CONTROLE DE '
                   'REATIVIDADE DE REATORES NUCLEARES PWR.pdf')
SAIDA = os.path.join(RAIZ, 'reference')

# figura, cenário, grandeza, unidade, página do PDF, índice do gráfico na página
# (índice 0 = gráfico mais acima; ver ordena_por_posicao)
FIGURAS = [
    ('6.1',  1, 'Tmed',   'C',  45, 0), ('6.2',  1, 'DeltaI', '',   45, 1),
    ('6.3',  2, 'Tmed',   'C',  46, 0), ('6.4',  2, 'DeltaI', '',   47, 0),
    ('6.5',  2, 'Pot',    'pc', 47, 1), ('6.6',  3, 'Tmed',   'C',  48, 0),
    ('6.7',  3, 'DeltaI', '',   48, 1), ('6.8',  3, 'Pot',    'pc', 49, 0),
    ('6.9',  4, 'Tmed',   'C',  49, 1), ('6.10', 4, 'DeltaI', '',   50, 0),
    ('6.11', 4, 'Pot',    'pc', 50, 1), ('6.12', 4, 'Vagua',  'L',  50, 2),
    ('6.13', 5, 'Tmed',   'C',  51, 0), ('6.14', 5, 'DeltaI', '',   51, 1),
    ('6.15', 5, 'Pot',    'pc', 52, 0), ('6.16', 5, 'Vagua',  'L',  52, 1),
    ('6.17', 6, 'DeltaT', 'C',  53, 0),
]


# ---------------------------------------------------------------- SVG e paths

def _matriz(s):
    m = re.match(r'matrix\(([^)]*)\)', s or '')
    if not m:
        return (1, 0, 0, 1, 0, 0)
    return tuple(float(x) for x in re.split(r'[,\s]+', m.group(1).strip()))


def _compoe(A, B):
    a1, b1, c1, d1, e1, f1 = A
    a2, b2, c2, d2, e2, f2 = B
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _aplica(M, x, y):
    a, b, c, d, e, f = M
    return (a * x + c * y + e, b * x + d * y + f)


def _percorre(el, M, saida):
    t = el.get('transform')
    if t:
        M = _compoe(M, _matriz(t))
    if el.tag == NS + 'path':
        pts = [(float(x), float(y)) for _, x, y in
               re.findall(r'([ML])\s+(-?[\d.]+)\s+(-?[\d.]+)', el.get('d', ''))]
        if pts:
            cor = el.get('stroke') or el.get('fill')
            saida.append((cor, [_aplica(M, x, y) for x, y in pts]))
    for filho in el:
        _percorre(filho, M, saida)


def paths(svg):
    raiz = ET.parse(svg).getroot()
    saida = []
    for filho in raiz:
        if filho.tag != NS + 'defs':          # defs contém só os glifos
            _percorre(filho, (1, 0, 0, 1, 0, 0), saida)
    return saida


def curvas_azuis(svg):
    """Curvas de dados, ordenadas de cima para baixo na página.

    O filtro >2 pontos descarta as amostras de linha da legenda (2 pontos).
    A Fig. 6.5 e a 6.8 têm apenas 5 vértices — não elevar esse limite.
    """
    cs = [p for cor, p in paths(svg) if cor == AZUL and len(p) > 2]
    return sorted(cs, key=lambda c: min(p[1] for p in c))


def grade(svg):
    """Segmentos horizontais e verticais das linhas de grade."""
    H, V = [], []
    for cor, pts in paths(svg):
        if cor != CINZA:
            continue
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if abs(y0 - y1) < 0.05 and abs(x0 - x1) > 50:
                H.append((y0, min(x0, x1), max(x0, x1)))
            if abs(x0 - x1) < 0.05 and abs(y0 - y1) > 50:
                V.append((x0, min(y0, y1), max(y0, y1)))
    return H, V


# ------------------------------------------------------------- rótulos e eixos

def rotulos(bbox):
    s = open(bbox).read()
    saida = []
    for a, b, c, d, w in re.findall(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" '
            r'yMax="([\d.]+)">([^<]*)</word>', s):
        if re.fullmatch(r'-?\d+([.,]\d+)?', w):
            saida.append((float(a), float(b), float(c), float(d),
                          float(w.replace(',', '.'))))
    return saida


def _ransac(cands):
    """Reta valor = a*pos + b com mais inliers. Imune a números do corpo do texto."""
    melhor = None
    for (p1, v1), (p2, v2) in itertools.combinations(cands, 2):
        if abs(p1 - p2) < 5 or v1 == v2:
            continue
        a = (v2 - v1) / (p2 - p1)
        b = v1 - a * p1
        tol = max(abs(v) for _, v in cands) * 0.02 + 1e-9
        inl = [c for c in cands if abs(a * c[0] + b - c[1]) < tol]
        if melhor is None or len(inl) > len(melhor[2]):
            melhor = (a, b, inl)
    return melhor


def _encaixa(p, linhas, tol=4.0):
    if not linhas:
        return None
    g = min(linhas, key=lambda g: abs(g - p))
    return g if abs(g - p) <= tol else None


def calibra(pts, W, H, V):
    """Converte os vértices de coordenadas de página para (tempo, valor)."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xlo, xhi, ylo, yhi = min(xs), max(xs), min(ys), max(ys)

    gy = sorted({round(h[0], 2) for h in H
                 if h[1] < xhi + 30 and h[2] > xlo - 30 and ylo - 90 < h[0] < yhi + 90})
    gx = sorted({round(v[0], 2) for v in V
                 if v[1] < yhi + 90 and v[2] > ylo - 90 and xlo - 60 < v[0] < xhi + 60})

    yc = []
    for w in W:
        if xlo - 70 < w[2] < xlo + 8 and ylo - 45 < (w[1] + w[3]) / 2 < yhi + 45:
            s = _encaixa((w[1] + w[3]) / 2, gy)
            if s is not None:
                yc.append((s, w[4]))

    # os rótulos do eixo X estão todos na mesma linha: agrupar por y antes
    linhas = {}
    for w in W:
        if yhi - 25 < (w[1] + w[3]) / 2 < yhi + 130 and xlo - 5 < (w[0] + w[2]) / 2 < xhi + 40:
            linhas.setdefault(round((w[1] + w[3]) / 2 / 3), []).append(w)
    ok = [r for r in linhas.values()
          if len(r) >= 3 and max(x[2] for x in r) - min(x[0] for x in r) > 80]
    linha = min(ok, key=lambda r: min((w[1] + w[3]) / 2 for w in r)) if ok else []

    xc = []
    for w in linha:
        s = _encaixa((w[0] + w[2]) / 2, gx)
        if s is not None:
            xc.append((s, w[4]))
    if len(xc) < 3:
        xc = [((w[0] + w[2]) / 2, w[4]) for w in linha]

    if len(yc) < 3 or len(xc) < 3:
        raise RuntimeError('rótulos de eixo insuficientes')
    ax, bx, _ = _ransac(xc)
    ay, by, _ = _ransac(yc)
    return [(ax * px + bx, ay * py + by) for px, py in pts]


# ----------------------------------------------------------------------- main

def main():
    if not os.path.exists(PDF):
        sys.exit(f'PDF não encontrado: {PDF}')
    os.makedirs(SAIDA, exist_ok=True)
    tmp = os.path.join(SAIDA, '.tmp')
    os.makedirs(tmp, exist_ok=True)

    paginas = sorted({f[4] for f in FIGURAS})
    for p in paginas:
        svg = f'{tmp}/p{p}.svg'
        bbox = f'{tmp}/p{p}.xml'
        if not os.path.exists(svg):
            subprocess.run(['pdftocairo', '-svg', '-f', str(p), '-l', str(p), PDF, svg],
                           check=True)
        if not os.path.exists(bbox):
            subprocess.run(['pdftotext', '-bbox', '-f', str(p), '-l', str(p), PDF, bbox],
                           check=True)

    cache = {}
    total = 0
    for fig, cen, grandeza, unidade, pg, idx in FIGURAS:
        if pg not in cache:
            svg = f'{tmp}/p{pg}.svg'
            cache[pg] = (curvas_azuis(svg), rotulos(f'{tmp}/p{pg}.xml'), *grade(svg))
        cs, W, H, V = cache[pg]
        serie = calibra(cs[idx], W, H, V)
        nome = f'marcos-fig-{fig}-c{cen}-{grandeza.lower()}.csv'
        with open(os.path.join(SAIDA, nome), 'w') as fh:
            fh.write(f'# Figura {fig} da dissertação de Marcos A. G. da Silva Filho '
                     f'(COPPE/UFRJ, 2023)\n')
            fh.write(f'# cenário {cen} — {grandeza}'
                     f'{" [" + unidade + "]" if unidade else ""}\n')
            fh.write('# série "Simulação"; vértices extraídos do gráfico vetorial, '
                     'NÃO a saída numérica original\n')
            fh.write('t_min,valor\n')
            for t, v in serie:
                fh.write(f'{t:.2f},{v:.4f}\n')
        total += len(serie)
        print(f'  {nome:42} {len(serie):>5} pontos')
    print(f'\n{len(FIGURAS)} séries, {total} pontos -> {SAIDA}/')


if __name__ == '__main__':
    main()
