# Resultados — 6 cenários × 3 níveis

Gerado por `scripts/gera_resultados.sh` em 2026-09-06 16:58.

Os três níveis simulam o mesmo modelo por caminhos diferentes:

| nível | o que é |
|---|---|
| `C` | `./simulador`, compilado de `V8_Reatividade_SimuladorIgor_linux.c` |
| `python` | `simulador.py`, o porte fiel do Passo 2 |
| `API` | `reactor:8008` (física) + `expert:8009` (as 19 regras), por HTTP |

Cada pasta tem, por cenário: `cenarioN.txt` (as amostras),
`cenarioN-comparacao.txt` (confronto com as curvas da dissertação) e, só na API,
`cenarioN-disparos.json` (quantas vezes cada uma das 19 regras disparou).

## Identidade entre os níveis

| cenário | descrição | amostras | C = python = API | SHA-256 |
|---|---|--:|---|---|
| 1 | operação normal, 1 dia | 1072 | **idênticos** | `26924432ba18bb96…` |
| 2 | runback da bomba de água de alimentação | 750 | **idênticos** | `ac155f5867c159aa…` |
| 3 | runback manual para 150 MW | 260 | **idênticos** | `e7f53b0a23d9a44f…` |
| 4 | rampa 32 → 650 MW a 1 MW/min | 328 | **idênticos** | `7737110bf65852dd…` |
| 5 | rampa 650 → 32 MW a 3 MW/min | 92 | **idênticos** | `d41a2160a4e4db83…` |
| 6 | ciclo completo até Cboro < 8 | 514421 | **idênticos** | `a1ebc8a0dbb92ffb…` |

## Regras exercitadas por cenário

Extraído de `API/cenarioN-disparos.json` — só a API sabe isso, porque só ela
separa as regras da física.

| cenário | regras que dispararam |
|---|---|
| 1 | `{"R13":77,"R9":74,"R1":3}` |
| 2 | `{"R13":3,"R9":7,"R10":1,"R18":2,"R14":18,"R5":4,"R1":24}` |
| 3 | `{"R13":3,"R9":6,"R10":1,"R18":4,"R7":2,"R14":31,"R5":26,"R1":23}` |
| 4 | `{"R13":83,"R9":38,"R5":25,"R1":9,"R3":6,"R18":3,"R4":2,"R7":1}` |
| 5 | `{"R13":4,"R9":8,"R10":3,"R14":68,"R18":1,"R1":50,"R2":25}` |
| 6 | `{"R13":77,"R9":74,"R1":5966,"R6":8,"R2":2,"R8":1285,"R16":1,"R19":1}` |

## Como regerar

```sh
gcc --std=gnu89 -Wall V8_Reatividade_SimuladorIgor_linux.c -o simulador -lm
podman-compose up -d
bash scripts/gera_resultados.sh          # --rapido pula o cenário 6
```
