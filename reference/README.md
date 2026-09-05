# Séries de referência — dissertação de Marcos A. G. da Silva Filho

17 séries numéricas (9031 pontos) extraídas das **Figuras 6.1 a 6.17** de:

> Marcos Antonio Gonçalves da Silva Filho. *Sistema Especialista para o Controle de
> Reatividade de Reatores Nucleares PWR.* Dissertação de Mestrado, PEN/COPPE,
> Universidade Federal do Rio de Janeiro, julho de 2023.
> (`docs/MSc - UFRJ - SISTEMA ESPECIALISTA ... PWR.pdf`)

São a **curva do simulador** — a série rotulada "Simulação" nos gráficos, que corresponde ao
programa deste projeto. A outra série de cada figura ("Sistema Especialista") é a saída do
outro programa e **não** foi extraída.

## O que estes arquivos são — e o que não são

**Não são a saída numérica das corridas do Marcos.** Essa não existe no documento.

São os **vértices das polilinhas** que o Excel/Word gravou no PDF ao desenhar cada gráfico —
uma versão já decimada da corrida original, mais o erro residual da calibração dos eixos.
A Figura 6.1, por exemplo, guarda 29 vértices para 1440 min, enquanto uma corrida do cenário 1
produz 1072 amostras.

Consequências práticas:

- servem para **conferir** uma corrida do simulador e obter um número de desvio;
- **não** servem para citar "o valor obtido por Marcos" em texto. Para isso, cite as
  afirmações da própria dissertação (ex.: "o pico atinge aproximadamente 4" para o ΔI do
  cenário 2);
- o primeiro ponto de cada série pode cair em t ligeiramente negativo (ex.: −0,3 min). É o
  resíduo da calibração, não um dado. Ignorar ou tratar como t=0.

## Formato

Uma linha de cabeçalho comentada com a procedência, depois `t_min,valor`:

```
# Figura 6.1 da dissertação de Marcos A. G. da Silva Filho (COPPE/UFRJ, 2023)
# cenário 1 — Tmed [C]
# série "Simulação"; vértices extraídos do gráfico vetorial, NÃO a saída numérica original
t_min,valor
-0.30,303.0007
2.70,303.3008
...
```

Nome do arquivo: `marcos-fig-<figura>-c<cenário>-<grandeza>.csv`.

| Grandeza | Unidade | Coluna correspondente em `Modelagem_Reator.txt` |
|---|---|---|
| `tmed` | °C | `Tmed` |
| `deltai` | — | `Delta I` |
| `pot` | % da potência nominal | `Pot Rx` |
| `vagua` | L | `Volume de Água` |
| `deltat` | °C | `Tmed − Tref`, com `Tref = 0,113·Pot + 291,7` |

## Cobertura

| Cenário | Figuras |
|---|---|
| 1 | 6.1 (Tmed), 6.2 (ΔI) |
| 2 | 6.3 (Tmed), 6.4 (ΔI), 6.5 (potência) |
| 3 | 6.6 (Tmed), 6.7 (ΔI), 6.8 (potência) |
| 4 | 6.9 (Tmed), 6.10 (ΔI), 6.11 (potência), 6.12 (volume de água) |
| 5 | 6.13 (Tmed), 6.14 (ΔI), 6.15 (potência), 6.16 (volume de água) |
| 6 | 6.17 (ΔT, ciclo completo) |

A **Figura 6.18** não está aqui: é o ΔT do ciclo completo produzido pelo *sistema especialista*,
não pelo simulador.

## Como foram gerados

```fish
python3 scripts/extrai_curvas_dissertacao.py
```

Requer `poppler-utils` (`pdftocairo`, `pdftotext`). O script regrava os 17 CSVs a partir do PDF
em `docs/`; os SVGs intermediários ficam em `reference/.tmp/`.

Três detalhes do método que não são óbvios e estão documentados no script:

1. os gráficos são **vetoriais**, não bitmap — as curvas estão no content stream do PDF;
2. a série do simulador é a **azul** `rgb(26.7%, 44.7%, 76.9%)`, identificada pela posição do
   símbolo da legenda à esquerda do rótulo "Simulação";
3. a calibração dos eixos usa as **linhas de grade** cinza, não o centro da caixa de texto dos
   rótulos — a caixa do `pdftotext` introduz viés vertical de ~1 pt, que vira +0,8 % em eixos
   de potência e +34 L em eixos de volume de água.

## Como conferir uma corrida contra elas

```fish
rm -f Modelagem_Reator.txt
echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador --tmax=1440 > /dev/null
python3 scripts/compara_corrida.py Modelagem_Reator.txt 1
```

Para os cenários 1–5 a saída é uma tabela de erro ponto a ponto. Para o cenário 6 são as
grandezas agregadas — a trajetória minuto a minuto não é reprodutível nem entre dois builds do
mesmo fonte, e o motivo está em `steps/01-porte-linux-simulador.md`.

## Resultados de referência

Os desvios obtidos na validação do passo 1 estão em `steps/01-porte-linux-simulador.md`.
Resumo: Tmed 0,02–0,04 °C médio; ΔI 0,001–0,012; potência 0,08–0,59 %; volume de água 2–8,5 L.
