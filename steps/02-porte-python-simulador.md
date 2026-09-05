# Passo 2 — Porte do simulador para Python

**Data:** 2026-09-05
**Entrada:** `V8_Reatividade_SimuladorIgor_linux.c` (saída validada do Passo 1)
**Saída:** `simulador.py` + `scripts/verifica_equivalencia_python.sh`

## Objetivo

Obter em Python o mesmo simulador, para que os passos seguintes da pesquisa possam
instrumentá-lo, acoplá-lo e variá-lo sem depender de recompilar C — **sem que isso
custe nada em fidelidade**. O critério de aceitação foi fixado antes de escrever a
primeira linha:

> Para a mesma linha de comando e a mesma entrada, `simulador.py` deve produzir o
> mesmo arquivo de amostras **byte a byte** e a mesma saída padrão **byte a byte**
> que o binário C.

O nome do arquivo é a única coisa que difere: o C grava em `Modelagem_Reator.txt` e o
Python em `Modelagem_Reator_py.txt`. Como os dois abrem em modo *append* com nome fixo,
nomes distintos são o que permite rodar os dois no mesmo diretório sem que uma corrida
acrescente na outra. O nome não aparece em lugar nenhum da saída padrão, então a
comparação byte a byte do stdout não é afetada.

Esse critério é mais forte do que "concordar dentro de uma tolerância", e a escolha é
deliberada: o Passo 1 mediu que o modelo decide diluir, borar e mover barra por
comparações de ponto flutuante (`DeltaT>=t1`, `DesvioDeltaI>2`, `Deltaro!=0`), de modo
que **±0,001 no último decimal desloca um evento de diluição e desfaz a fase de toda a
corrida seguinte** — dois builds do mesmo `.c` (SSE vs `-mfpmath=387`) correlacionam só
+0,40 entre si em 669.000 min. Num modelo assim, "quase igual" não é um resultado
estável: ou o porte é exato, ou a comparação com as figuras da dissertação teria de ser
refeita do zero para o Python.

## O que o porte é

`simulador.py` é uma **transcrição**, não uma reimplementação. Preserva os nomes das
funções e das variáveis, a ordem das declarações, a ordem das operações dentro de cada
expressão, os textos impressos e os comentários do original — inclusive os trechos
comentados pelo Igor e o `AlvoTref=298.5` do runback de 400 MW, que é aparente typo
preservado de propósito desde o Passo 1.

1354 linhas de C viraram 1482 de Python; a diferença é quase toda docstring e a camada
de emulação numérica descrita abaixo.

## O ponto central: emular a aritmética do C

Em C, quase todas as variáveis do simulador são `float` (32 bits) e só as do Xe/Iodo são
`double` (64 bits). Em Python só existe o `double`. Rodar o modelo inteiro em `double`
produziria um simulador **plausível e diferente** — exatamente o modo de falha que o
critério de aceitação existe para pegar.

Três semânticas do C foram reproduzidas explicitamente:

### 1. `float` de 32 bits, arredondado a cada operação

A classe `F` herda de `float` (para que comparações e `%`-formatação já promovam a
`double`, como o C faz) e sobrecarrega os operadores aritméticos seguindo as conversões
usuais do C89:

| expressão | resultado | por quê |
|---|---|---|
| `F op F` | `F` | `float op float` é calculado em `float` no SSE (`FLT_EVAL_METHOD=0`) |
| `F op int` | `F` | o `int` é convertido para `float` antes da operação |
| `F op double` | `double` | o `float` é promovido; não há arredondamento |

Assim `Ptopo=(2*Pot+DeltaI)/2` arredonda três vezes, como o C, enquanto
`AlvoDeltaI=(57.14-Pot)/28.57` é avaliado inteiro em `double` e só arredonda no
armazenamento — que é o que o C faz, porque `57.14` é um literal `double`.

### 2. A semântica de *armazenamento*, e não a atenção do transcritor

O risco óbvio de uma transcrição manual é esquecer um arredondamento numa das ~150
atribuições. Por isso os três conjuntos `_FLOAT`, `_INT` e `_DOUBLE` da classe `Reator`
repetem o bloco de declarações do `.c`, e `__setattr__` aplica a conversão de tipo em
**toda** atribuição: arredondar para 32 bits num `float`, truncar para zero num `int`.
A garantia é estrutural — não depende de o transcritor ter lembrado.

### 3. Os casos degenerados

- **Divisão por zero.** O C devolve ±inf ou NaN; o Python levanta `ZeroDivisionError`.
  `_divide()` reproduz o IEEE. Não é hipotético: `CalculaDeltaI()` imprime
  `Pbase/PbaseAntes` sem guarda nenhuma.
- **`(int)` de inf/NaN.** É comportamento indefinido no C; no x86 dá `0x80000000`.
  `_para_int()` devolve esse valor em vez de levantar `OverflowError`. Também não é
  hipotético: com `Cboro` entre 2594,7 e 2601 tem-se `taxatemp==0`, e o laço principal
  calcula `valor=(t/taxatemp)` seguido de `aux=valor`. O sweep aleatório caiu nesse caso
  quatro vezes.

## Diferenças deliberadas em relação ao `.c`

Três, todas verificadas sem efeito numérico ou sobre os bytes de saída:

| `.c` | `simulador.py` | por quê |
|---|---|---|
| `float lambda` | `lambda_` | `lambda` é palavra reservada em Python |
| `printf("%c",177)` | `putc_raw(b'\xb1')` | o C emite **um** byte (o `▒` do codepage 437); `chr(177)` em UTF-8 seriam dois |
| `#ifdef WIN_ORIGINAL` | variável de ambiente `WIN_ORIGINAL=1` | macro de compilação não tem equivalente em Python; o efeito é o mesmo de `gcc -DWIN_ORIGINAL` |

Um detalhe encontrado ao transcrever: a linha do alarme de ΔI usa `%C` maiúsculo, que não
é padrão. A glibc trata `%C` como apelido de `%lc`, e com o argumento 37 imprime `%` — o
mesmo que `%c`. Confirmado empiricamente com um programa de duas linhas antes de escolher
`%c` no Python.

## Verificação

```fish
bash scripts/verifica_equivalencia_python.sh          # ~51 s (inclui o ciclo completo)
bash scripts/verifica_equivalencia_python.sh --rapido # ~5 s
```

O script compila as duas variantes do `.c`, roda cada caso nos dois portes e compara o
`Modelagem_Reator.txt` byte a byte e o SHA-256 da saída padrão inteira. Resultado:

| Caso | Amostras | Dados | stdout |
|---|---|---|---|
| Cenário 1 — operação normal, 1 dia | 1.072 | idênticos | idêntico |
| Cenário 2 — runback bomba de alimentação | 750 | idênticos | idêntico |
| Cenário 3 — runback manual 150 MW | 260 | idênticos | idêntico |
| Cenário 4 — rampa 32→650 MW a 1 MW/min | 328 | idênticos | idêntico |
| Cenário 5 — rampa 650→32 MW a 3 MW/min | 92 | idênticos | idêntico |
| **Cenário 6 — ciclo completo até `Cboro<8`** | **514.421** | **idênticos** | **idêntico (446 MB)** |
| Ramo `Pbase<0`, semântica do porte | 9 | idênticos | idêntico |
| Ramo `Pbase<0`, semântica `WIN_ORIGINAL` | 376 | idênticos | idêntico |
| Boração por limite de inserção (3 casos) | 111 / 528 / 424 | idênticos | idêntico |
| Erros de linha de comando (3 casos) | — | mesma mensagem e mesmo `rc` | — |

O cenário 6 é a evidência forte: **514.421 amostras e 446 MB de saída padrão com o mesmo
SHA-256**, ao longo de 669.105 minutos simulados e ~465 dias de ciclo. É precisamente o
regime em que o Passo 1 mediu que o código não se reproduz nem entre duas compilações
de si mesmo — e o Python reproduz o build SSE exatamente.

Os dois casos do ramo `Pbase<0` cobrem a única divergência conhecida entre o porte e o
original do Igor: as duas semânticas dão 9 e 376 amostras (trajetórias completamente
diferentes), e o Python acompanha as duas. Ou seja, o porte Python é fiel ao C **e**
carrega a mesma divergência documentada, em vez de escolher um lado.

### Sweep aleatório

Além dos casos fixos, 24 conjuntos de condições iniciais sorteados (potência 32–650 MW,
boro 300–3000 ppm com concentração extra em torno de 2601 ppm, banco D 100–230, todos os
seis transientes, horizontes de 300 a 2000 min): **24/24 idênticos**, dados e stdout.
Semente `20260905`, no histórico desta sessão; não versionado por não acrescentar
cobertura sobre o que o script de verificação já fixa.

### Cobertura

Contando as marcas de execução no stdout agregado, todas as funções e todos os ramos de
decisão do modelo foram exercitados: `atualizadadosXe`/`Xeg`, diluição, boração,
movimentação de barra nos dois sentidos, compensação da queima, as quatro correções de
ΔI, as duas borações por limite de inserção, os dois alarmes e o fim de ciclo.

A única exceção é `VariacaodeCarga()`, o menu interativo: é **código morto nos dois
portes**, porque `kbhit()` é fixo em 0 desde o Passo 1. Foi transcrito assim mesmo,
para que os dois arquivos continuem linha a linha comparáveis.

## Desempenho

| | C | Python | razão |
|---|---|---|---|
| Cenário 1 (1440 min) | 0,02 s | 0,15 s | 7,5× |
| Cenário 6 (669.105 min) | 6,6 s | 42,6 s | 6,5× |

Um fator ~7 é bem menor do que o esperado para Python puro com uma classe numérica
embrulhando cada operação. A razão é que o laço principal avança `t` em saltos (cada
diluição consome `tempodilute` minutos de uma vez), então o ciclo completo são ~514 mil
iterações, não 669 mil × nada. O custo é dominado pelo `printf`: o cenário 6 escreve
446 MB na saída padrão.

## Limites deste passo

- A equivalência é verificada **nesta máquina, contra este build**. As duas
  implementações chamam a mesma `libm` da glibc para `pow()`, o que é justamente o que
  faz os dígitos baterem; num sistema com outra `libm` as duas mudariam juntas, mas isso
  não foi testado.
- O alvo é o build **SSE** (o `gcc` padrão em x86-64). O build `-mfpmath=387`, que o
  Passo 1 identificou como o mais próximo da corrida original em Windows, **não** é
  reproduzido — o Python não tem como emular os intermediários de 80 bits do x87. A
  consequência é a mesma já documentada: idêntico nos cenários 1–5, divergente na fase
  dos eventos no ciclo completo.
- `VariacaodeCarga()` não é testável (código morto nos dois portes).

## Fora de escopo

- Nenhuma melhoria, correção ou refatoração do modelo. A transcrição preserva os bugs do
  original — inclusive o `AlvoTref=298.5`, o `Ptopo`/`Pbase` trocados e a comparação
  `Nxeb-NxeAntes` que compara a concentração de base com a global.
- Nenhuma API, serviço, gráfico ou instrumentação sobre o `simulador.py`.
- Nenhuma comparação nova contra as figuras da dissertação: como a saída é byte a byte
  idêntica à do C, os resultados do Passo 1 valem sem refazer nada.

## Artefatos produzidos neste passo

| Caminho | Conteúdo |
|---|---|
| `simulador.py` | o porte em Python |
| `scripts/verifica_equivalencia_python.sh` | compila o C e confere a identidade byte a byte nos 13 casos |
