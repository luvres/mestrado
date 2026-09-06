#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compara_niveis.py — confronta os 3 niveis, cenario a cenario.

Le o que scripts/gera_resultados.sh deixou em results/{C,python,API}/ e escreve
results/COMPARACAO.md com, para cada cenario:

  1. os tres arquivos de amostras lado a lado (linhas, bytes, SHA-256) e o
     veredito de identidade byte a byte;
  2. o confronto com as curvas extraidas da dissertacao — que e o MESMO nos tres
     niveis, justamente porque os arquivos sao identicos;
  3. quais das 19 regras o cenario exercitou (so a API sabe disso).

A pergunta que este relatorio responde nao e "os numeros batem?", e sim "os tres
caminhos chegam ao mesmo lugar E esse lugar e o da dissertacao?". Sao duas
verificacoes independentes: a primeira e byte a byte entre implementacoes, a
segunda e por tolerancia contra uma fonte externa.

Uso: python3 scripts/compara_niveis.py
"""

import hashlib
import io
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(RAIZ, "results")
NIVEIS = ("C", "python", "API")

# Os cenários vêm de cenarios.json, a fonte única — não são redeclarados aqui.
# scripts/cenarios.py faz a tradução para as flags de linha de comando e para o
# corpo da API, para que a regra de tradução também exista num lugar só.
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
from cenarios import descricao, entrada, flags, json_parcial, numeros   # noqa: E402

DESCRICAO = {int(n): descricao(n) for n in numeros()}
COMANDO = {int(n): (flags(n) or "(sem flags)", json_parcial(n)) for n in numeros()}


def resumo(caminho):
    dados = open(caminho, "rb").read()
    amostras = sum(1 for l in dados.splitlines() if l[:1].isdigit())
    return {"bytes": len(dados), "amostras": amostras,
            "sha": hashlib.sha256(dados).hexdigest()}


def corpo_comparacao(caminho):
    """A saída do compara_corrida.py sem a primeira linha (que traz o caminho)."""
    linhas = io.open(caminho, encoding="utf-8").read().splitlines()
    return "\n".join(linhas[1:]).strip("\n")


def tabela_metricas(texto):
    """Converte a tabela de erros do compara_corrida.py em linhas Markdown.

    Só serve para os cenários 1-5; o 6 usa um formato agregado, e nesse caso
    devolve None para o relatório cair no bloco literal.
    """
    linhas = []
    for l in texto.splitlines():
        m = re.match(r"\s+(\w+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(.+?)\s*$", l)
        if m and m.group(1) not in ("grandeza",):
            linhas.append("| `%s` | %s | %s | %s | %s |"
                          % (m.group(1), m.group(2), m.group(3), m.group(4),
                             m.group(5).strip()))
    return linhas or None


def main():
    if not os.path.isdir(RES):
        sys.stderr.write("results/ não existe — rode scripts/gera_resultados.sh antes\n")
        return 1

    cenarios = sorted(
        n for n in DESCRICAO
        if all(os.path.exists(os.path.join(RES, k, "cenario%d.txt" % n)) for k in NIVEIS))
    if not cenarios:
        sys.stderr.write("nenhum cenário completo em results/\n")
        return 1

    saida = []
    w = saida.append
    w("# Comparação entre os 3 simuladores, cenário a cenário")
    w("")
    w("Gerado por `scripts/compara_niveis.py` a partir de `results/`.")
    w("")
    w("Os três níveis percorrem caminhos diferentes até o mesmo modelo:")
    w("")
    w("| nível | o que executa | onde as regras estão |")
    w("|---|---|---|")
    w("| `C` | `./simulador`, de `V8_Reatividade_SimuladorIgor_linux.c` | misturadas à física |")
    w("| `python` | `simulador.py`, o porte fiel do Passo 2 | misturadas à física |")
    w("| `API` | `reactor:8008` + `expert:8009`, por HTTP | **separadas**, no expert |")
    w("")
    w("São **duas verificações independentes** em cada cenário:")
    w("")
    w("1. **Entre os níveis** — byte a byte. É o critério forte: não basta chegar aos")
    w("   mesmos números, é preciso chegar pelo mesmo caminho.")
    w("2. **Contra a dissertação** — por tolerância, com as curvas extraídas dos PDFs.")
    w("   Como os arquivos dos três níveis são idênticos, este confronto dá")
    w("   necessariamente o mesmo resultado nos três — e por isso aparece uma vez só.")
    w("")

    # --- panorama ---
    w("## Panorama")
    w("")
    w("| cenário | descrição | amostras | C = python = API |")
    w("|---|---|--:|---|")
    todos_ok = True
    for n in cenarios:
        r = {k: resumo(os.path.join(RES, k, "cenario%d.txt" % n)) for k in NIVEIS}
        ok = r["C"]["sha"] == r["python"]["sha"] == r["API"]["sha"]
        todos_ok = todos_ok and ok
        w("| %d | %s | %s | %s |"
          % (n, DESCRICAO[n], r["C"]["amostras"],
             "**idênticos**" if ok else "**DIVERGEM**"))
    w("")

    # --- por cenario ---
    for n in cenarios:
        r = {k: resumo(os.path.join(RES, k, "cenario%d.txt" % n)) for k in NIVEIS}
        ok = r["C"]["sha"] == r["python"]["sha"] == r["API"]["sha"]
        flags_c, campos_api = COMANDO[n]

        w("---")
        w("")
        w("## Cenário %d — %s" % (n, DESCRICAO[n]))
        w("")
        w("Entrada do operador: `%s`" % entrada(n))
        w("")
        w("- C e Python: `%s`" % flags_c)
        w("- API: `%s`" % campos_api)
        w("")
        w("### 1. Os três níveis entre si")
        w("")
        w("| nível | amostras | bytes | SHA-256 |")
        w("|---|--:|--:|---|")
        for k in NIVEIS:
            w("| `%s` | %s | %s | `%s…` |"
              % (k, r[k]["amostras"], r[k]["bytes"], r[k]["sha"][:24]))
        w("")
        w("> %s" % ("**Idênticos byte a byte.**" if ok
                    else "**DIVERGEM — investigar.**"))
        w("")
        w("### 2. Contra as curvas da dissertação")
        w("")
        texto = corpo_comparacao(os.path.join(RES, "C", "cenario%d-comparacao.txt" % n))
        metricas = tabela_metricas(texto)
        if metricas:
            w("| grandeza | pontos | erro médio | erro máx | faixa da referência |")
            w("|---|--:|--:|--:|---|")
            saida.extend(metricas)
        else:
            w("O cenário 6 não admite comparação ponto a ponto — a trajetória minuto a")
            w("minuto não é reprodutível nem entre dois *builds* do mesmo fonte. O")
            w("critério aqui é por grandezas agregadas:")
            w("")
            w("```")
            w(texto)
            w("```")
        w("")

        disparos = os.path.join(RES, "API", "cenario%d-disparos.json" % n)
        if os.path.exists(disparos):
            d = json.load(open(disparos, encoding="utf-8"))
            ordenado = sorted(d.get("disparos", {}).items(),
                              key=lambda kv: int(kv[0][1:]))
            w("### 3. Regras exercitadas")
            w("")
            w("| regra | disparos |")
            w("|---|--:|")
            for rid, qtd in ordenado:
                w("| %s | %s |" % (rid, qtd))
            w("")
            nunca = d.get("nunca_dispararam", [])
            w("%d de 19 regras. Não alcançadas: %s"
              % (len(ordenado), ", ".join(nunca) if nunca else "nenhuma"))
            w("")

    # --- fechamento ---
    w("---")
    w("")
    w("## Leitura")
    w("")
    if todos_ok:
        w("Nos %d cenários, os três níveis produzem **exatamente os mesmos bytes**."
          % len(cenarios))
        w("")
        w("Isso é mais forte do que concordância numérica. O nível `API` tem as 19 regras")
        w("num serviço separado, decidindo sobre um estado que chega por JSON e voltando")
        w("por HTTP a cada atuação — e ainda assim a corrida é indistinguível da do")
        w("binário C. Se alguma regra tivesse ficado do lado errado da fronteira, ou se a")
        w("aritmética do expert arredondasse num ponto diferente, a divergência apareceria")
        w("aqui: o modelo decide por comparações de ponto flutuante, e ±0,001 desloca um")
        w("evento de diluição e desfaz a fase do resto da corrida.")
    else:
        w("**Há divergência entre os níveis.** Ver os cenários marcados no panorama.")
    w("")
    todas = set()
    for n in cenarios:
        p = os.path.join(RES, "API", "cenario%d-disparos.json" % n)
        if os.path.exists(p):
            todas |= set(json.load(open(p, encoding="utf-8")).get("disparos", {}))
    if todas:
        faltam = [r for r in ("R%d" % i for i in range(1, 20)) if r not in todas]
        w("Somados, os cenários exercitam **%d das 19 regras**.%s"
          % (len(todas),
             (" Nenhum deles alcança %s — essas exigem configurações de borda "
              "(ver `steps/05-servico-expert.md` §8)." % ", ".join(faltam))
             if faltam else ""))
        w("")

    destino = os.path.join(RES, "COMPARACAO.md")
    io.open(destino, "w", encoding="utf-8").write("\n".join(saida) + "\n")
    print("escrito: %s (%d cenários)" % (destino, len(cenarios)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
