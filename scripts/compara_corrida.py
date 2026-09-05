#!/usr/bin/env python3
"""
Compara um Modelagem_Reator.txt produzido pelo simulador com as séries de
referência extraídas da dissertação do Marcos (reference/*.csv).

Uso:
    python3 scripts/compara_corrida.py <Modelagem_Reator.txt> <cenário 1..6>

Exemplo:
    rm -f Modelagem_Reator.txt
    echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\\n' | ./simulador --tmax=1440 > /dev/null
    python3 scripts/compara_corrida.py Modelagem_Reator.txt 1

Sobre o critério de comparação
------------------------------
Para os cenários 1 a 5 (horizonte de 1440 min) a comparação ponto a ponto é
válida e os desvios ficam no piso de quantização do arquivo de saída — Tmed é
impresso com UMA casa decimal, então ±0,05 °C é o limite alcançável.

Para o cenário 6 (ciclo completo, ~669.000 min) a comparação ponto a ponto NÃO
é o critério adequado: a trajetória minuto a minuto não é reprodutível nem entre
dois builds do mesmo fonte (SSE vs -mfpmath=387 correlacionam só +0,40 entre si,
apesar de idênticos nos primeiros 1440 min). O modelo decide por comparações de
ponto flutuante e ±0,001 desloca um evento de diluição, desfasando o resto.
Por isso, para o cenário 6 este script reporta as grandezas agregadas.
"""

import bisect
import csv
import glob
import os
import statistics as st
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(RAIZ, 'reference')

# colunas de Modelagem_Reator.txt:
# 0=t 1=Pot 2=PotTurbina 3=Tmed 4=DeltaI 5=Cboro 6=BancoD 7=VaguaTemp
COLUNA = {'tmed': 3, 'deltai': 4, 'pot': 1, 'vagua': 7}


def carrega_corrida(caminho, grandeza):
    S = []
    for linha in open(caminho):
        f = linha.split()
        if len(f) == 8 and f[0].isdigit():
            t = float(f[0])
            if grandeza == 'deltat':
                # ΔT = Tmed − Tref, com Tref = 0,113·Pot + 291,7
                # (válido sem transiente de carga, que é o caso do cenário 6)
                v = float(f[3]) - (0.113 * float(f[1]) + 291.7)
            else:
                v = float(f[COLUNA[grandeza]])
            S.append((t, v))
    if not S:
        sys.exit(f'nenhuma amostra lida de {caminho}')
    return S


def carrega_ref(caminho):
    S = []
    with open(caminho) as fh:
        for linha in fh:
            if linha.startswith('#') or linha.startswith('t_min'):
                continue
            t, v = linha.split(',')
            S.append((float(t), float(v)))
    return S


def amostrador(S):
    T = [p[0] for p in S]
    V = [p[1] for p in S]

    def f(t):
        i = bisect.bisect_left(T, t)
        if i <= 0:
            return V[0]
        if i >= len(T):
            return V[-1]
        t0, t1, v0, v1 = T[i - 1], T[i], V[i - 1], V[i]
        return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return f, T[-1]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    corrida, cen = sys.argv[1], sys.argv[2]
    arquivos = sorted(glob.glob(os.path.join(REF, f'marcos-fig-*-c{cen}-*.csv')))
    if not arquivos:
        sys.exit(f'sem referência para o cenário {cen} em {REF}/')

    print(f'corrida: {corrida}   cenário: {cen}\n')
    if cen == '6':
        print('cenário 6 — comparação por grandezas agregadas (ver docstring)\n')
        for a in arquivos:
            grandeza = os.path.basename(a).rsplit('-', 1)[1][:-4]
            R = carrega_corrida(corrida, grandeza)
            F = carrega_ref(a)
            fr, fim = amostrador(R)
            amostras = [(t, v, fr(t)) for t, v in F if 0 <= t <= fim]
            ref = [p[1] for p in amostras]
            run = [p[2] for p in amostras]
            print(f'  {grandeza}:')
            print(f'    {"":14}{"referência":>12}{"corrida":>12}')
            print(f'    {"mínimo":14}{min(ref):>12.3f}{min(run):>12.3f}')
            print(f'    {"máximo":14}{max(ref):>12.3f}{max(run):>12.3f}')
            print(f'    {"média":14}{st.mean(ref):>12.4f}{st.mean(run):>12.4f}')
            print(f'    {"desvio-padrão":14}{st.pstdev(ref):>12.4f}{st.pstdev(run):>12.4f}')
            print(f'    fim do ciclo: referência t={F[-1][0]:.0f}   corrida t={fim:.0f}'
                  f'   ({100*abs(fim-F[-1][0])/F[-1][0]:.3f} %)')
        return

    print(f'  {"grandeza":<10}{"n":>6}{"erro médio":>13}{"erro máx":>11}   faixa da referência')
    print('  ' + '-' * 66)
    for a in arquivos:
        grandeza = os.path.basename(a).rsplit('-', 1)[1][:-4]
        R = carrega_corrida(corrida, grandeza)
        F = carrega_ref(a)
        fr, fim = amostrador(R)
        e, vs = [], []
        for t, v in F:
            if 0 <= t <= fim:
                e.append(abs(fr(t) - v))
                vs.append(v)
        if not e:
            continue
        print(f'  {grandeza:<10}{len(e):>6}{sum(e)/len(e):>13.4f}{max(e):>11.4f}'
              f'   {min(vs):8.2f}..{max(vs):<8.2f}')


if __name__ == '__main__':
    main()
