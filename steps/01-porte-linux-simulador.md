# Passo 1 — Porte do simulador de reatividade para Linux

**Data:** 2026-09-05
**Entrada:** `V8_Reatividade_SimuladorIgor.txt` (fonte primária, código do Igor para Windows)
**Saída:** `V8_Reatividade_SimuladorIgor_linux.c` + binário `simulador`

## Objetivo

Obter uma versão do simulador de controle de reatividade que:

1. **compile e execute no Linux**, já que o original depende de `conio.h`, exclusivo do DOS/Windows;
2. **rode em lote, sem interação**, aceitando os parâmetros dos cenários por linha de comando
   em vez de exigir que um operador responda perguntas e aperte teclas durante a simulação;
3. **preserve o modelo físico intacto** — nenhuma equação, coeficiente ou regra de decisão
   pode mudar, sob pena de invalidar a comparação com a dissertação.

O simulador é a implementação descrita na Seção 4 da monografia
*Controle Automático de Reatividade e Simulador para Testes* (funções `CompensaQueima`,
`Corrige_DeltaI`, inserção de reatividade negativa embutida no `main`). Na dissertação de
mestrado ele aparece como a curva **"Simulação"** das Figuras 6.1–6.16, servindo de
referência ao sistema especialista.

## O que foi alterado, por categoria

### A. Portabilidade

| Original | Porte | Efeito |
|---|---|---|
| `#include<conio.h>` | removido; `<unistd.h>` acrescentado | — |
| `getch()` | macro para `getchar()`; chamadas de pausa comentadas | o programa não para nos alarmes |
| `kbhit()` | `#define kbhit() 0` | **desabilita a entrada interativa** (ver seção C) |
| `system("color 1F")` | `system_color()`, função vazia | cosmético |
| `\xf8\C` (codepage 437), `%c` com 177 | `°C` em UTF-8 | cosmético |

### B. Correções de C do original

Todas são *undefined behavior* que funcionava por acidente de layout de memória:

| Original | Porte | Justificativa |
|---|---|---|
| `char TipoVariacao[1]`, `Runback[1]`, `funcaocarga[1]` | `[16]` | `scanf("%s")` de `"r"` grava 2 bytes num array de 1 |
| `scanf("%s", &TipoVariacao)` | `scanf("%15s", TipoVariacao)` | limita a escrita; `&array` e `array` têm o mesmo endereço |
| `termino[10]="inicio"` | `strcpy(termino,"inicio")` | o original atribui um ponteiro ao índice 10, fora do array; `termino` ficava `""` |
| `fopen(...,"aw")` | `"a"` | `"aw"` não é modo válido |
| `float AlvoDeltaI;` duas vezes | uma vez | definições tentativas |
| chamadas sem protótipo | protótipos de `atualizadadosXe/Xeg` | evita declaração implícita |
| `fflush(stdin)` em `GravaDados()` | removido | UB no Linux |
| `if (Pbase<0) { Ptopo=0; }` | `Pbase=0` | **única com efeito numérico** — ver "Divergência conhecida" |

### C. Automação em lote

Este é o motivo pelo qual o passo não terminou na simples compilação.

No original, o transiente de carga entra pelo teclado: o operador digita `v` durante a
execução, o `kbhit()` dispara `VariacaodeCarga()` e ele responde a uma sequência de perguntas.
Com `kbhit()` fixado em 0, esse caminho vira código morto — e **os cenários 2 a 5 da
Tabela 6.1 tornam-se impossíveis de reproduzir**, pois todos sairiam iguais ao cenário 1.

Restaurar um `kbhit()` real (termios + `select`) não resolveria: a Tabela 6.1 exige o
transiente em **t = 10 min de simulação**, e o laço executa milhares de iterações por segundo.
O instante não seria controlável nem repetível.

Solução adotada — parâmetros de linha de comando:

```
--transiente=<runback-bap|runback-circ|runback-400|runback-300|runback-150|rampa>
--alvo=<MW>            (só para rampa)
--taxa=<MW/min>        (só para rampa)
--t-transiente=<min>   (default 10)
--tmax=<min>           (default 700000)
```

Restrições que garantem que isso não é uma mudança de comportamento:

- as flags apenas **encaminham** para `AplicaRunback()` / `AplicaRampa()`, os mesmos helpers
  que o menu interativo passou a chamar — com as mesmas guardas de potência
  (`PotTurbina>301`, `>401`, `>150`);
- a injeção ocorre **no ponto exato do laço onde estava o `if (kbhit())`**, depois de
  `CalculaDeltaI()` e `GravaDados()`, de modo que a ordem das operações é a mesma que se o
  operador tivesse digitado `v` naquela iteração;
- o caminho interativo permanece no código, intacto;
- sem nenhuma flag, o comportamento é o anterior.

Equivalência com o que o operador digitaria no Windows:

| Flags | Teclado no original |
|---|---|
| `--transiente=runback-bap` | `v` → `r` → `s` |
| `--transiente=runback-150` | `v` → `r` → `n` → `n` → `150` |
| `--transiente=rampa --alvo=650 --taxa=1` | `v` → `l` → `650` → `1` |
| `--transiente=rampa --alvo=32 --taxa=3` | `v` → `l` → `32` → `3` |

`--t-transiente` e `--tmax` não têm equivalente no original: o instante do transiente não era
especificável, e o programa nunca terminava (ao atingir `Cboro<8` ele imprimia "FIM DO CICLO",
chamava `getch()` e seguia o laço). O porte encerra ali, e `--tmax` acrescenta um limite de
horizonte por cima — necessário porque os cenários 1–5 da dissertação são de 1 dia, enquanto
o ciclo completo leva ~465 dias e gera ~45 MB de dados.

## Verificação da fidelidade

Três evidências independentes, todas executadas:

**1. Refactor conferido linha a linha.** `AplicaRampa()` tem exatamente as mesmas 13 linhas do
bloco original, na mesma ordem (as duas a mais são as atribuições dos parâmetros, que
substituem os `scanf`). Os 5 pares `(Tref, AlvoTref)` dos runbacks são idênticos e na mesma
ordem — `(296.92, 296.92)`, `(298.65, 298.65)`, `(298.65, 298.5)`, `(296.92, 296.92)`,
`(294.31, 294.31)` — inclusive o `298.5` do runback de 400 MW, que é aparente typo do original
e foi **preservado de propósito**.

**2. O original compilado e comparado diretamente.** Esta é a evidência mais forte. O
`V8_Reatividade_SimuladorIgor.txt` é compilado **sem nenhuma alteração** — apenas com um shim
mínimo para o `<conio.h>`, que não existe no Linux — e a saída é comparada com a do porte:

| Cenário | Amostras | Resultado |
|---|---|---|
| 1 (1440 min) | 1.072 | **idênticas byte a byte** |
| 6 (ciclo completo, 669.105 min) | 514.421 | **idênticas byte a byte** |

Como os dois binários saem do mesmo gcc com as mesmas flags, isso isola a pergunta "o porte é
fiel ao original?" da pergunta "a aritmética do compilador muda o resultado?" — e responde a
primeira sem margem. Reproduzível com:

```fish
bash scripts/verifica_equivalencia_original.sh
```

Um detalhe encontrado ao rodar o original: ele **não termina**. Depois de `Cboro < 8` ele
imprime "FIM DO CICLO", chama `getch()` e segue o laço; deixado correndo, chegou a
t = 3.210.470 min com `Cboro = 0` e `Tmed = −202,4 °C` — sem sentido físico. É exatamente o
defeito que o porte corrige com `strcpy(termino,"fim")`.

**2b. Semântica do original reconstruída.** O `.c` também traz a divergência do `Pbase`/`Ptopo`
sob `#ifdef WIN_ORIGINAL`; compilando as duas variantes, os seis cenários saem idênticos —
confirmando que aquele ramo é inalcançável no envelope deles.

**3. Aritmética de ponto flutuante.** O original provavelmente foi compilado com MinGW 32-bit,
que usa x87 (intermediários de 80 bits), contra SSE no gcc x86-64. Compilando com
`-mfpmath=387`: diferenças apenas no último decimal de ΔI (±0,001) em poucas linhas; Tmed,
potência, posição de barra, boro e volume iguais; **valores finais idênticos nos 5 cenários**.

Esse resultado vale para o horizonte de 1440 min. **Não** vale para o ciclo completo: em
669.000 min os dois builds divergem na fase dos eventos de diluição — ver "Cenário 6" na seção
de resultados, onde isso é medido e explicado.

Compilação limpa com `gcc --std=gnu89 -Wall`, sem avisos.

## Como usar

### Compilação

Este é o comando que gera o binário `simulador` a partir do fonte portado:

```fish
gcc --std=gnu89 -Wall V8_Reatividade_SimuladorIgor_linux.c -o simulador -lm
```

- `--std=gnu89` — o código é C89 com extensões GNU (declarações após statements, comentários
  `//`); sem isso o gcc usa um padrão mais novo e passa a recusar construções do original.
- `-Wall` — compila **sem nenhum aviso**, o que é a checagem mínima de que as correções da
  categoria B eliminaram o *undefined behavior* do original.
- `-lm` — obrigatório: o modelo usa `pow()` intensamente nas equações do Xe e do Iodo.

### Execução

Os 7 valores lidos por `scanf`, nesta ordem: **turbina (MW), boro (ppm), banco D (passos),
tempo de diluição (min), ΔT vazão mínima (°C), ΔT vazão máxima (°C), ΔI inicial**.

`GravaDados()` abre `Modelagem_Reator.txt` com nome fixo e em modo *append* — apagar o arquivo
antes de cada corrida, ou rodar em diretório próprio.

Os seis cenários da dissertação (Tabelas 6.1 e 6.2):

```fish
# Cenário 1
rm -f Modelagem_Reator.txt; echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador --tmax=1440 > /dev/null
# Cenário 2
rm -f Modelagem_Reator.txt; echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador --transiente=runback-bap --t-transiente=10 --tmax=1440 > /dev/null
# Cenário 3
rm -f Modelagem_Reator.txt; echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador --transiente=runback-150 --t-transiente=10 --tmax=1440 > /dev/null
# Cenário 4
rm -f Modelagem_Reator.txt; echo "32 1800 144 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440 > /dev/null
# Cenário 5
rm -f Modelagem_Reator.txt; echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440 > /dev/null
# Cenário 6
rm -f Modelagem_Reator.txt; echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' | ./simulador > /dev/null
```

O que cada um representa, e o que esperar da saída:

| # | Transiente | Turbina / banco D iniciais | Horizonte | Amostras |
|---|---|---|---|---|
| 1 | nenhum — 1 dia de operação normal | 650 MW / 210 | 1440 min | 1072 |
| 2 | desarme da bomba de água de alimentação principal (→300 MW) em t=10 | 650 MW / 210 | 1440 min | 750 |
| 3 | runback manual para 150 MW em t=10 | 650 MW / 210 | 1440 min | 260 |
| 4 | elevação lenta 32→650 MW a 1 MW/min em t=10 | **32 MW / 144** | 1440 min | 328 |
| 5 | redução lenta 650→32 MW a 3 MW/min em t=10 | 650 MW / 210 | 1440 min | 92 |
| 6 | nenhum — ciclo completo até `Cboro < 8` | 650 MW / 210 | ~669.000 min | ~514.000 |

Dois pontos de atenção:

- o **cenário 4 é o único** com condições iniciais diferentes (turbina em 32 MW e banco D em
  144 passos, contra 650 MW e 210 nos demais);
- no **cenário 6** o `> /dev/null` não é opcional: sem `--tmax` o laço vai até o fim do ciclo
  (~465 dias simulados) e o despejo verboso passa de **446 MB**, com um
  `Modelagem_Reator.txt` de ~45 MB.

Para reproduzir a semântica literal do original, o mesmo comando com `-DWIN_ORIGINAL`:

```fish
gcc --std=gnu89 -Wall -DWIN_ORIGINAL V8_Reatividade_SimuladorIgor_linux.c -o simulador_win -lm
```

## Resultados — conferência com as dissertações

As duas fontes primárias têm papéis distintos, e a conferência contra cada uma é de natureza
diferente:

- **Igor Bottrel Baptista**, *Controle Automático de Reatividade e Simulador para Testes* —
  documenta o simulador em si. A correspondência é **estrutural**: as funções descritas na
  Seção 4 (`CompensaQueima`, `Corrige_DeltaI`, inserção de reatividade negativa embutida no
  `main`) correspondem uma a uma ao código portado.
- **Marcos Antonio Gonçalves da Silva Filho**, *Sistema Especialista para o Controle de
  Reatividade de Reatores Nucleares PWR* (COPPE/UFRJ, julho 2023) — usa este simulador como
  referência validada, e registra os resultados dos cenários nas Figuras 6.1–6.18. A
  conferência contra ela é **numérica**.

As curvas das figuras de Marcos são vetoriais e foram extraídas do content stream do PDF, com
os eixos calibrados pelas linhas de grade. A série comparada é a rotulada **"Simulação"** (azul),
identificada pela posição do símbolo da legenda; a laranja é o sistema especialista.

### Cenários 1 a 5 — concordância ponto a ponto

Todas as 16 figuras foram comparadas amostra a amostra com as corridas:

| Fig | Cen | Grandeza | pts | erro médio | erro máx |
|---|---|---|---|---|---|
| 6.1 | 1 | Tmed | 28 | 0,044 °C | 0,129 °C |
| 6.2 | 1 | ΔI | 238 | 0,0013 | 0,060 |
| 6.3 | 2 | Tmed | 76 | 0,035 °C | 0,142 °C |
| 6.4 | 2 | ΔI | 46 | 0,012 | 0,122 |
| 6.5 | 2 | Potência | 5 | 0,081 % | 0,148 % |
| 6.6 | 3 | Tmed | 49 | 0,023 °C | 0,134 °C |
| 6.7 | 3 | ΔI | 48 | 0,012 | 0,052 |
| 6.8 | 3 | Potência | 5 | 0,590 % | 1,880 % |
| 6.9 | 4 | Tmed | 138 | 0,032 °C | 0,184 °C |
| 6.10 | 4 | ΔI | 306 | 0,011 | 0,033 |
| 6.11 | 4 | Potência | 137 | 0,118 % | 0,247 % |
| 6.12 | 4 | V. água | 29 | 8,5 L | 19,1 L |
| 6.13 | 5 | Tmed | 81 | 0,043 °C | 0,070 °C |
| 6.14 | 5 | ΔI | 90 | 0,008 | 0,025 |
| 6.15 | 5 | Potência | 39 | 0,101 % | 0,229 % |
| 6.16 | 5 | V. água | 52 | 2,0 L | 4,1 L |

Os erros médios de Tmed (0,02–0,04 °C) estão no piso de quantização: `GravaDados()` imprime
Tmed com **uma casa decimal**, então ±0,05 °C é o limite inferior alcançável. Os volumes de
água divergem menos de 0,7 % em faixas de 1900–3100 L.

O único valor acima de 1 % é o máximo da Figura 6.8, e vem de **um** vértice: a curva de
potência do cenário 3 tem apenas 5 vértices, e o do fim do platô está em t=10,5 enquanto na
corrida a descida já começou. Os outros quatro batem dentro de 0,4 %.

As afirmações numéricas do texto de Marcos também se confirmam: o pico de ΔI "aproximadamente 4"
no cenário 2 (medido: 3,785) e "quase 5" no cenário 3 (medido: 4,972), maior que o do cenário 2;
e no cenário 5 o reator chega a ~5 % em ~205 min contados do transiente, contra os 206 min
teóricos citados.

### Cenário 6 — o limite de reprodutibilidade do modelo

A referência é a **Figura 6.17** (ΔT do SRR pelo simulador, ciclo completo). Aqui a comparação
ponto a ponto dá correlação de apenas **+0,24**, e isso exige explicação, já que o cenário 6 tem
as mesmas condições iniciais do cenário 1 e nenhum transiente — ele é o cenário 1 continuado
(verificado: os primeiros 1440 min do c6 são **byte a byte idênticos** ao c1).

A explicação foi obtida compilando o **mesmo arquivo-fonte** de duas formas e rodando o ciclo
completo em cada uma: `-mfpmath=387` (x87, 80 bits nos intermediários, como o MinGW 32-bit que
provavelmente gerou o binário original no Windows) e SSE (padrão do gcc x86-64).

| | Fim do ciclo (`Cboro < 8`) | Amostras | Correlação com a Fig. 6.17 |
|---|---|---|---|
| build SSE | 669.105 min | 514.421 | +0,24 |
| build x87 | **668.453 min** | 513.461 | +0,20 |
| Figura 6.17 (último vértice) | **668.429 min** | 7649 | — |

Os dois resultados decisivos:

1. **Os dois builds do mesmo fonte correlacionam apenas +0,40 entre si**, com diferença média
   de 0,067 °C e máxima de 0,400 °C — apesar de serem idênticos nos primeiros 1440 min. Ou seja,
   a trajetória minuto a minuto ao longo de 465 dias simulados **não é reprodutível nem entre
   duas compilações do código idêntico**. A correlação de +0,24 com a figura está na mesma
   ordem do +0,40 que o código atinge consigo mesmo.
2. **O build x87 acerta a duração do ciclo em 24 min de 668.429** — 0,004 % — contra 676 min
   (0,101 %) do build SSE. Isso indica que a corrida de Marcos usou aritmética x87, coerente
   com um binário Windows, e que o porte reproduz a grandeza integral do ciclo.

O mecanismo é conhecido: o modelo decide diluir/borar/mover barra por comparações de ponto
flutuante (`DeltaT>=t1`, `DesvioDeltaI>2`, `Deltaro!=0`). Uma diferença de ±0,001 no último
decimal inverte uma dessas comparações, desloca um evento de diluição em alguns minutos, e a
fase dos ciclos seguintes diverge em definitivo. Em 1440 min (cenários 1–5) isso não tem tempo
de se manifestar — x87 e SSE dão valores finais idênticos ali. Em 669.000 min, manifesta-se.

O que é reprodutível, e concorda:

| | Figura 6.17 | SSE | x87 |
|---|---|---|---|
| ΔT mínimo / máximo | −0,516 / +0,821 °C | −0,500 / +0,800 | −0,500 / +0,800 |
| ΔT médio | −0,104 °C | −0,079 | −0,075 |
| desvio-padrão | 0,109 °C | 0,098 | 0,099 |
| amplitude do dente-de-serra (mediana) | 0,253 °C | 0,200 °C | — |
| envelope por janela de 100.000 min | — | dentro de ±0,045 °C | — |

Resta um viés de **~0,025 °C** na média de ΔT, presente nos dois builds. É pequeno demais para
ser comportamento e grande demais para ser só ruído de leitura da figura; fica registrado como
não explicado.

**Conclusão:** o cenário 6 não diverge no modelo. Diverge na fase dos eventos individuais de
diluição, num regime em que o próprio código não se reproduz entre compiladores. Todas as
grandezas agregadas — duração do ciclo, envelope, amplitude, distribuição — concordam.

## Divergência conhecida

`if (Pbase<0)` zera `Pbase` no porte e zerava `Ptopo` no original — aparente troca de variável.
É uma **mudança real de comportamento**, não uma equivalência: com `Pot=4,92 %` e ΔI inicial 12
(`Pbase = −1,08`) as duas versões divergem por completo (ΔI ~9,8 contra ~0,03 em t=261).

Ela não afeta os cenários 1–6 porque o ramo é inalcançável ali: o mínimo de `Pot − ΔI/2` nas
corridas é 4,92, e disparar exigiria ΔI > 2·Pot.

## Limites deste passo

- **O original nunca foi executado no Windows** — não há máquina Windows disponível. Ele foi
  compilado e executado **no Linux, sem alteração**, e a saída é idêntica à do porte (verificação
  2). O que resta sem teste é o comportamento sob o *toolchain* Windows, em dois pontos:
  - **layout de memória**, de que depende o argumento de que os `char[1]` do original
    "funcionavam por acaso". Atenuante: esses arrays só são escritos dentro de
    `VariacaodeCarga()`, alcançável apenas pelo ramo do `kbhit()`. Nos cenários 1 e 6 não há
    transiente, então **nem no Windows** eles seriam escritos;
  - **aritmética**, coberta separadamente pelo teste x87 vs SSE.
- O indício de que era um compilador 32-bit (e portanto `int` do mesmo tamanho que aqui) é o
  `system("color 1F")`, comando do cmd do Windows NT. Se fosse Turbo C/DOS com `int` de 16 bits,
  `tXe*60` (que chega a 259.200) estouraria e as equações do Xe divergiriam.
- A coluna `Pot Turbina` da saída **atrasa**: só é atualizada quando `Pot` converge para
  `PotAlvo` ou durante rampa ativa. Para plotar potência da turbina, usar `6,5 × Pot Rx`.
  É comportamento do original, não do porte.

## Fora de escopo

- A **metodologia** de extração das curvas vetoriais do PDF (identificação da série pela
  legenda, calibração pelas linhas de grade, tratamento do viés de ~1 pt na leitura do centro
  dos rótulos de texto) fica documentada no passo seguinte, junto com os scripts. Aqui constam
  apenas os resultados.
- A Figura 6.18 (ΔT do ciclo completo **pelo sistema especialista**) não foi comparada: ela é a
  saída do outro programa, não deste simulador.

## Artefatos produzidos neste passo

| Caminho | Conteúdo |
|---|---|
| `V8_Reatividade_SimuladorIgor_linux.c` | o porte |
| `scripts/extrai_curvas_dissertacao.py` | extrai as 17 séries das Figuras 6.1–6.17 do PDF |
| `scripts/compara_corrida.py` | compara um `Modelagem_Reator.txt` com a referência |
| `scripts/verifica_equivalencia_original.sh` | compila o `.txt` original sem alterações e confere que a saída é idêntica |
| `reference/*.csv` | as 17 séries de referência (9031 pontos) |
| `reference/README.md` | procedência, formato e limitações dessas séries |

As corridas de referência não são versionadas: são regeradas em segundos pelos comandos da
seção "Execução", e conferidas com `scripts/compara_corrida.py`.
