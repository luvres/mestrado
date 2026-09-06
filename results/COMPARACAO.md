# Comparação entre os 3 simuladores, cenário a cenário

Gerado por `scripts/compara_niveis.py` a partir de `results/`.

Os três níveis percorrem caminhos diferentes até o mesmo modelo:

| nível | o que executa | onde as regras estão |
|---|---|---|
| `C` | `./simulador`, de `V8_Reatividade_SimuladorIgor_linux.c` | misturadas à física |
| `python` | `simulador.py`, o porte fiel do Passo 2 | misturadas à física |
| `API` | `reactor:8008` + `expert:8009`, por HTTP | **separadas**, no expert |

São **duas verificações independentes** em cada cenário:

1. **Entre os níveis** — byte a byte. É o critério forte: não basta chegar aos
   mesmos números, é preciso chegar pelo mesmo caminho.
2. **Contra a dissertação** — por tolerância, com as curvas extraídas dos PDFs.
   Como os arquivos dos três níveis são idênticos, este confronto dá
   necessariamente o mesmo resultado nos três — e por isso aparece uma vez só.

## Panorama

| cenário | descrição | amostras | C = python = API |
|---|---|--:|---|
| 1 | operação normal, 1 dia | 1072 | **idênticos** |
| 2 | runback da bomba de água de alimentação | 750 | **idênticos** |
| 3 | runback manual para 150 MW | 260 | **idênticos** |
| 4 | rampa 32 → 650 MW a 1 MW/min | 328 | **idênticos** |
| 5 | rampa 650 → 32 MW a 3 MW/min | 92 | **idênticos** |
| 6 | ciclo completo até Cboro < 8 | 514421 | **idênticos** |

---

## Cenário 1 — operação normal, 1 dia

Entrada do operador: `650 1800 210 4 -0.3 -0.8 0`

- C e Python: `--tmax=1440`
- API: `"pot_turbina":650, "cboro":1800, "posicao_barra":210, "tempodilute":4, "t1":-0.3, "t2":-0.8, "delta_i":0, "tmax":1440`

### 1. Os três níveis entre si

| nível | amostras | bytes | SHA-256 |
|---|--:|--:|---|
| `C` | 1072 | 87382 | `26924432ba18bb960abb5d3a…` |
| `python` | 1072 | 87382 | `26924432ba18bb960abb5d3a…` |
| `API` | 1072 | 87382 | `26924432ba18bb960abb5d3a…` |

> **Idênticos byte a byte.**

### 2. Contra as curvas da dissertação

| grandeza | pontos | erro médio | erro máx | faixa da referência |
|---|--:|--:|--:|---|
| `tmed` | 28 | 0.0441 | 0.1288 | 302.80..303.80 |
| `deltai` | 238 | 0.0013 | 0.0602 | 0.15..0.76 |

### 3. Regras exercitadas

| regra | disparos |
|---|--:|
| R1 | 3 |
| R9 | 74 |
| R13 | 77 |

3 de 19 regras. Não alcançadas: R2, R3, R4, R5, R6, R7, R8, R10, R11, R12, R14, R15, R16, R17, R18, R19

---

## Cenário 2 — runback da bomba de água de alimentação

Entrada do operador: `650 1800 210 4 -0.3 -0.8 0`

- C e Python: `--transiente=runback-bap --t-transiente=10 --tmax=1440`
- API: `"pot_turbina":650, "cboro":1800, "posicao_barra":210, "tempodilute":4, "t1":-0.3, "t2":-0.8, "delta_i":0, "tmax":1440, "transiente":"runback-bap", "t_transiente":10`

### 1. Os três níveis entre si

| nível | amostras | bytes | SHA-256 |
|---|--:|--:|---|
| `C` | 750 | 62716 | `ac155f5867c159aac54e74f8…` |
| `python` | 750 | 62716 | `ac155f5867c159aac54e74f8…` |
| `API` | 750 | 62716 | `ac155f5867c159aac54e74f8…` |

> **Idênticos byte a byte.**

### 2. Contra as curvas da dissertação

| grandeza | pontos | erro médio | erro máx | faixa da referência |
|---|--:|--:|--:|---|
| `tmed` | 76 | 0.0354 | 0.1419 | 296.08..303.80 |
| `deltai` | 46 | 0.0122 | 0.1221 | 0.01..3.79 |
| `pot` | 5 | 0.0812 | 0.1483 | 45.67..100.06 |

### 3. Regras exercitadas

| regra | disparos |
|---|--:|
| R1 | 24 |
| R5 | 4 |
| R9 | 7 |
| R10 | 1 |
| R13 | 3 |
| R14 | 18 |
| R18 | 2 |

7 de 19 regras. Não alcançadas: R2, R3, R4, R6, R7, R8, R11, R12, R15, R16, R17, R19

---

## Cenário 3 — runback manual para 150 MW

Entrada do operador: `650 1800 210 4 -0.3 -0.8 0`

- C e Python: `--transiente=runback-150 --t-transiente=10 --tmax=1440`
- API: `"pot_turbina":650, "cboro":1800, "posicao_barra":210, "tempodilute":4, "t1":-0.3, "t2":-0.8, "delta_i":0, "tmax":1440, "transiente":"runback-150", "t_transiente":10`

### 1. Os três níveis entre si

| nível | amostras | bytes | SHA-256 |
|---|--:|--:|---|
| `C` | 260 | 21841 | `e7f53b0a23d9a44f2dd72ff7…` |
| `python` | 260 | 21841 | `e7f53b0a23d9a44f2dd72ff7…` |
| `API` | 260 | 21841 | `e7f53b0a23d9a44f2dd72ff7…` |

> **Idênticos byte a byte.**

### 2. Contra as curvas da dissertação

| grandeza | pontos | erro médio | erro máx | faixa da referência |
|---|--:|--:|--:|---|
| `tmed` | 49 | 0.0225 | 0.1333 | 293.61..303.80 |
| `deltai` | 48 | 0.0121 | 0.0526 | -0.02..4.97 |
| `pot` | 5 | 0.5932 | 1.8976 | 23.05..100.06 |

### 3. Regras exercitadas

| regra | disparos |
|---|--:|
| R1 | 23 |
| R5 | 26 |
| R7 | 2 |
| R9 | 6 |
| R10 | 1 |
| R13 | 3 |
| R14 | 31 |
| R18 | 4 |

8 de 19 regras. Não alcançadas: R2, R3, R4, R6, R8, R11, R12, R15, R16, R17, R19

---

## Cenário 4 — rampa 32 → 650 MW a 1 MW/min

Entrada do operador: `32 1800 144 4 -0.3 -0.8 0`

- C e Python: `--transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440`
- API: `"pot_turbina":32, "cboro":1800, "posicao_barra":144, "tempodilute":4, "t1":-0.3, "t2":-0.8, "delta_i":0, "tmax":1440, "transiente":"rampa", "t_transiente":10, "alvo":650, "taxa":1`

### 1. Os três níveis entre si

| nível | amostras | bytes | SHA-256 |
|---|--:|--:|---|
| `C` | 328 | 26899 | `7737110bf65852ddda1969e4…` |
| `python` | 328 | 26899 | `7737110bf65852ddda1969e4…` |
| `API` | 328 | 26899 | `7737110bf65852ddda1969e4…` |

> **Idênticos byte a byte.**

### 2. Contra as curvas da dissertação

| grandeza | pontos | erro médio | erro máx | faixa da referência |
|---|--:|--:|--:|---|
| `deltai` | 306 | 0.0109 | 0.0324 | -0.02..5.50 |
| `pot` | 137 | 0.1182 | 0.2459 | 5.15..100.06 |
| `vagua` | 29 | 8.5360 | 19.0899 | -16.07..3104.05 |
| `tmed` | 138 | 0.0324 | 0.1838 | 292.24..303.49 |

### 3. Regras exercitadas

| regra | disparos |
|---|--:|
| R1 | 9 |
| R3 | 6 |
| R4 | 2 |
| R5 | 25 |
| R7 | 1 |
| R9 | 38 |
| R13 | 83 |
| R18 | 3 |

8 de 19 regras. Não alcançadas: R2, R6, R8, R10, R11, R12, R14, R15, R16, R17, R19

---

## Cenário 5 — rampa 650 → 32 MW a 3 MW/min

Entrada do operador: `650 1800 210 4 -0.3 -0.8 0`

- C e Python: `--transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440`
- API: `"pot_turbina":650, "cboro":1800, "posicao_barra":210, "tempodilute":4, "t1":-0.3, "t2":-0.8, "delta_i":0, "tmax":1440, "transiente":"rampa", "t_transiente":10, "alvo":32, "taxa":3`

### 1. Os três níveis entre si

| nível | amostras | bytes | SHA-256 |
|---|--:|--:|---|
| `C` | 92 | 7510 | `d41a2160a4e4db83fb9035e4…` |
| `python` | 92 | 7510 | `d41a2160a4e4db83fb9035e4…` |
| `API` | 92 | 7510 | `d41a2160a4e4db83fb9035e4…` |

> **Idênticos byte a byte.**

### 2. Contra as curvas da dissertação

| grandeza | pontos | erro médio | erro máx | faixa da referência |
|---|--:|--:|--:|---|
| `tmed` | 81 | 0.0429 | 0.0699 | 291.54..303.80 |
| `deltai` | 90 | 0.0077 | 0.0255 | -0.55..1.06 |
| `pot` | 39 | 0.1005 | 0.2286 | 5.04..100.05 |
| `vagua` | 52 | 2.0240 | 4.0821 | 4.08..1879.65 |

### 3. Regras exercitadas

| regra | disparos |
|---|--:|
| R1 | 50 |
| R2 | 25 |
| R9 | 8 |
| R10 | 3 |
| R13 | 4 |
| R14 | 68 |
| R18 | 1 |

7 de 19 regras. Não alcançadas: R3, R4, R5, R6, R7, R8, R11, R12, R15, R16, R17, R19

---

## Cenário 6 — ciclo completo até Cboro < 8

Entrada do operador: `650 1800 210 4 -0.3 -0.8 0`

- C e Python: `(sem flags)`
- API: `"pot_turbina":650, "cboro":1800, "posicao_barra":210, "tempodilute":4, "t1":-0.3, "t2":-0.8, "delta_i":0`

### 1. Os três níveis entre si

| nível | amostras | bytes | SHA-256 |
|---|--:|--:|---|
| `C` | 514421 | 45750807 | `a1ebc8a0dbb92ffb6df849f1…` |
| `python` | 514421 | 45750807 | `a1ebc8a0dbb92ffb6df849f1…` |
| `API` | 514421 | 45750807 | `a1ebc8a0dbb92ffb6df849f1…` |

> **Idênticos byte a byte.**

### 2. Contra as curvas da dissertação

O cenário 6 não admite comparação ponto a ponto — a trajetória minuto a
minuto não é reprodutível nem entre dois *builds* do mesmo fonte. O
critério aqui é por grandezas agregadas:

```
cenário 6 — comparação por grandezas agregadas (ver docstring)

  deltat:
                    referência     corrida
    mínimo              -0.516      -0.492
    máximo               0.821       0.800
    média              -0.1041     -0.0817
    desvio-padrão       0.1094      0.0908
    fim do ciclo: referência t=668429   corrida t=669105   (0.101 %)
```

### 3. Regras exercitadas

| regra | disparos |
|---|--:|
| R1 | 5966 |
| R2 | 2 |
| R6 | 8 |
| R8 | 1285 |
| R9 | 74 |
| R13 | 77 |
| R16 | 1 |
| R19 | 1 |

8 de 19 regras. Não alcançadas: R3, R4, R5, R7, R10, R11, R12, R14, R15, R17, R18

---

## Leitura

Nos 6 cenários, os três níveis produzem **exatamente os mesmos bytes**.

Isso é mais forte do que concordância numérica. O nível `API` tem as 19 regras
num serviço separado, decidindo sobre um estado que chega por JSON e voltando
por HTTP a cada atuação — e ainda assim a corrida é indistinguível da do
binário C. Se alguma regra tivesse ficado do lado errado da fronteira, ou se a
aritmética do expert arredondasse num ponto diferente, a divergência apareceria
aqui: o modelo decide por comparações de ponto flutuante, e ±0,001 desloca um
evento de diluição e desfaz a fase do resto da corrida.

Somados, os cenários exercitam **15 das 19 regras**. Nenhum deles alcança R11, R12, R15, R17 — essas exigem configurações de borda (ver `steps/05-servico-expert.md` §8).

