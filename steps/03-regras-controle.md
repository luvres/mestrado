# Passo 3 — Identificação das regras de controle do simulador

**Objetivo:** extrair do fonte do simulador, de forma rastreável e reexecutável, o conjunto
de regras que constitui o controlador. Esse conjunto é a especificação do sistema
especialista: nenhuma decisão de controle existe fora dele.

**Critério de contagem** (declarado antes do resultado, porque o número depende dele):

> É uma regra todo bloco `if` que, no nível de decisão de `CompensacaoQueima`,
> `Corrige_DeltaI` ou do laço do `main`, provoca **ação sobre a planta** (diluição,
> boração, movimentação de barra) **ou** emite **sinalização** (alarme, fim de ciclo).

Sob esse critério são **19 regras**: 16 de atuação e 3 de sinalização.

Sob o critério mais estrito — só atuação — são **16**. Os dois números descrevem o mesmo
conjunto; a diferença são exatamente R17, R18 e R19, que não chamam função nenhuma.
Qualquer citação do número tem de vir acompanhada da frase de critério.

Fontes: `V8_Reatividade_SimuladorIgor_linux.c` e `simulador.py`. O mapa da §3 dá a linha da
regra nos **dois** portes. As 19 condições — mais os dois `if` internos de R11 e R12 — foram
conferidas uma a uma e são textualmente idênticas nos dois arquivos, como esperado do Passo 2,
que provou os portes idênticos byte a byte. As demais linhas citadas fora do mapa (chamadas,
fórmulas, guardas) referem-se ao `.c`.

---

## 1. O método

O instinto é abrir o código e caçar `if`. Não funciona: o fonte tem mais de 60 `if`, entre
laço, entrada de dados, impressão, seleção de vazão e alarme, e não há critério óbvio para
separá-los. O caminho que funciona é o inverso — **começar pela ação**, porque uma regra só
existe porque alguém faz alguma coisa, e a lista de coisas que se pode fazer num PWR é curta
e fechada.

O método tem quatro varreduras. Cada uma é um comando reexecutável.

### Varredura 1 — o vocabulário de ações

A hipótese vem da física, antes do código: num PWR só há três alavancas de reatividade —
tirar boro, pôr boro, mover barras. O código confirma ou refuta.

Procuram-se as funções que **escrevem no estado da planta**, não os `if`:

```sh
grep -n "^void Corrige" V8_Reatividade_SimuladorIgor_linux.c
```

Resultado: **sete** linhas. Seis são funções `Corrige<Grandeza><Ação>`, organizadas em
3 ações × 2 grandezas. A sétima é a armadilha descrita logo abaixo.

| Ação | Como aparece no código | Parâmetro | Custo em tempo |
|---|---|---|---|
| **diluir** (tirar boro) | `CorrigeTmedDiluicao()` + `CorrigeDeltaIDiluicao()` | `Vazao` (lpm) | `tempodilute` min |
| **borar** (pôr boro) | `CorrigeTmedBoracao()` + `CorrigeDeltaIBoracao()` | `VazaoBoro` (lpm), `Vboro` (L) | 2 min |
| **mexer nas barras** | `CorrigeTmedDeltaBarra()` + `CorrigeDeltaIDeltaBarra()` | `DeltaBarra` (± passos) | 2 min |
| **alarmar / encerrar** | `printf("…ALARME…")`, `strcpy(termino,"fim")` | — | 0 |

Armadilha de nomenclatura: `Corrige_DeltaI` (L788, com underscore) **não** é ação — é um
bloco de decisão. O underscore é a única coisa que a distingue das seis.

### Varredura 2 — os pontos de disparo

Cada ocorrência de uma ação é a âncora de exatamente uma regra. Localizá-las e verificar que
os pares são homogêneos (nunca um `Tmed` de diluição casado com um `DeltaI` de boração):

```sh
grep -n "Corrige\(Tmed\|DeltaI\)\(Diluicao\|Boracao\|DeltaBarra\)();" \
     V8_Reatividade_SimuladorIgor_linux.c \
  | sed 's/.*Corrige\(Tmed\|DeltaI\)\(Diluicao\|Boracao\|DeltaBarra\)().*/\2/' \
  | paste - - | sort | uniq -c
```

Resultado: 32 chamadas, todas em pares adjacentes homogêneos — **16 âncoras**:
3 diluições, 4 borações, 9 movimentações de barra. Esse número é o teto de regras de atuação:
fora dessas 16 âncoras o programa não toca no reator.

### Varredura 3 — subir de cada âncora até a condição

De cada âncora sobe-se no código colhendo todo `if` atravessado. A regra pertence ao `if`
**mais interno** que a governa; os `if` externos entram como conjunção no antecedente.

Duas guardas de despacho, no `main`, entram em todas as regras dos blocos I e II:

| Guarda | Linha | Alcança |
|---|---|---|
| `DeltaT < -0.1` | 1168 | R1–R4 (chama `CompensacaoQueima`) |
| `DesvioDeltaI > 2 \|\| DesvioDeltaI < -2` | 1173 | R5–R8 (chama `Corrige_DeltaI`) |

A guarda `DeltaT < -0.1` está escrita **duas vezes** — na L1168 e de novo na L717, primeira
linha de `CompensacaoQueima`. É redundante: a segunda nunca é falsa quando a primeira passou.

### Varredura 4 — os blocos que sinalizam sem atuar

A varredura 2 não encontra as regras que não chamam função:

```sh
grep -n "ALARME\|FIM DO CICLO" V8_Reatividade_SimuladorIgor_linux.c
```

Cinco ocorrências. Duas delas (L1208 e L1226) pertencem a blocos que **também** boram, e já
estão entre as 16. As outras três só sinalizam — são R17, R18 e R19.

---

## 2. Grandezas observadas pelo controlador

Levantadas das condições das 19 regras. É tudo que o controlador enxerga — a interface de
entrada do futuro sistema especialista tem sete grandezas, mais `Cboro` só na R19.

| Símbolo | No código | Definição | Linha |
|---|---|---|---|
| ΔT | `DeltaT` | `Tmed − Tref` | 543, 622, 679, 957 |
| DΔI | `DesvioDeltaI` | `DeltaI − AlvoDeltaI` | 345, 406, 570, 649, 699 |
| VΔI | `VariacaoDeltaI` | `DeltaI − DeltaIantes` | 407 |
| ΔI | `DeltaI` | desequilíbrio axial de potência | `CalculaDeltaI` (341) |
| P | `PosicaoBarra` | passos do banco D | — |
| LI | `LimiteInsercao` | `2,58·Pot − 85` | 1054 |
| BD | `BD` | `0,73·Pot + 144` (banco de referência) | 1165 |
| — | `Cboro` | concentração de boro (ppm) | — |

Grandezas de apoio ao alvo e à vazão:

- `AlvoDeltaI` (L311): `Pot/100` se `Cboro≥1080`; `(57,14−Pot)/28,57` se `720≤Cboro<1080`;
  `(42,86−Pot)/28,57` se `Cboro<720`.
- `v1 = −0,05307·Cboro + 100,5307` (mínimo 5) — vazão mínima de diluição.
- `v2 = −0,24022·Cboro + 452,24022` (mínimo 10) — vazão máxima.
- `a = 2·v1`, `b = v1` — coeficientes da rampa `Vazao = −a·ΔT + b`.
- `t1`, `t2`, `tempodilute` — entradas do operador na partida
  (nos 6 cenários: `t1 = −0,3`, `t2 = −0,8`, `tempodilute = 4` min).

---

## 3. Mapa das 19 regras

> **Sobre os números de linha.** Valem para o estado do repositório no commit em que este
> documento foi escrito. O Passo 4 vai reorganizar o `simulador.py` e deslocar as linhas do
> `.py`. A âncora estável de cada regra é o **texto da condição**, não o número — se a linha
> não bater, procure pela condição.

### Bloco I — `CompensacaoQueima` · guarda `ΔT < −0,1`

| # | `if` no `.c` | `if` no `.py` | Condição | Ação | Chamadas no `.c` |
|---|---|---|---|---|---|
| R1 | 720 | 857 | (VΔI≥0 **ou** ΔT<−0,3) **ou** (P≥222 **ou** DΔI>−3) | diluir | 745-746 |
| R2 | 748 | 885 | DΔI<0 **e** (VΔI≤0 **ou** ΔT<−0,3) **e** P<222 | barra **+1** | 754-755 |
| R3 | 757 | 896 | ΔT<−0,8 **e** (DΔI≥0 **ou** P≥222) | diluir a `v2` | 770-771 |
| R4 | 773 | 911 | ΔT<−0,8 **e** DΔI<4 **e** P<222 | barra **+2** | 779-780 |

Vazão de R1, escolhida por faixa de ΔT (L722, 727, 732): `v1` se ΔT≥t1; `v2` se ΔT≤t2;
`−a·ΔT+b` se t2<ΔT<t1.

### Bloco II — `Corrige_DeltaI` · guarda `|DΔI| > 2`

| # | `if` no `.c` | `if` no `.py` | Condição | Ação | Chamadas no `.c` |
|---|---|---|---|---|---|
| R5 | 789 | 925 | (DΔI≥0 **e** ΔT≤0,4) **ou** (DΔI>4,5 **e** ΔT<2) | diluir com vazão **dobrada** | 813-814 |
| R6 | 816 | 952 | DΔI<0 **e** ΔT<0,8 **e** P<222 | barra **+1** | 823-824 |
| R7 | 826 | 962 | ΔT>−0,6 **e** DΔI>4,5 **e** (P>LI+11 **ou** DΔI>5) | barra **−1** | 833-834 |
| R8 | 838 | 973 | (DΔI<−4 **e** P≥222 **e** ΔT>−1) **ou** (DΔI<−10 **e** ΔT>−3) | borar | 850-851 |

Boração de R8: `VazaoBoro = −DΔI·6`, saturada em 20 lpm (L843); `Vboro = VazaoBoro·2`.

### Bloco III — laço do `main` · sem guarda

| # | `if` no `.c` | `if` no `.py` | Condição | Ação | Chamadas no `.c` |
|---|---|---|---|---|---|
| R9 | 1176 | 1299 | ΔT>0,6 **e** DΔI≥−2,2 **e** (P>LI+11 **ou** ΔT>1,5) | barra **−1** se ΔT<1, senão **−2** | 1189-1190 |
| R10 | 1193 | 1314 | ΔT>0,8 **e** DΔI<0 | borar | 1202-1203 |
| R11 | 1206 ∧ 1210 | 1326 ∧ 1330 | LI < P ≤ LI+10 **e** ΔI<0 | alarme *limite baixo* + borar | 1219-1220 |
| R12 | 1224 ∧ 1228 | 1342 ∧ 1346 | P ≤ LI **e** ΔI<0 | alarme *muito baixo* + borar (emergência) | 1236-1237 |
| R13 | 1241 | 1357 | P<BD−3 **e** DΔI<4,2 **e** ΔT<0,8 | barra **+1** | 1247-1248 |
| R14 | 1250 | 1367 | P>BD+10 **e** DΔI≥−3 **e** ΔT>−0,4 | barra **−1** | 1256-1257 |
| R15 | 1259 | 1377 | P<LI+11 **e** DΔI<4 **e** ΔT<0,5 | barra **+1** | 1265-1266 |
| R16 | 1268 | 1387 | P>220 **e** DΔI≥−1,5 **e** ΔT>−0,25 | barra **−1** | 1274-1275 |
| R17 | 1284 | 1404 | \|DΔI\| > 5 | alarme *ΔI fora da banda alvo* | 1286 |
| R18 | 1306 | 1425 | \|ΔT\| > 1,67 | alarme *desvio de temperatura 1,67 °C* | 1308 |
| R19 | 1327 | 1448 | Cboro < 8 | *fim do ciclo*, `termino="fim"` | 1329, 1343 |

Borações do bloco III: R10 `VazaoBoro = ΔT·10`, `Vboro = VazaoBoro·4`;
R11 `VazaoBoro = (LI−P+11)·2`, `Vboro = VazaoBoro·2`;
R12 `VazaoBoro = (LI+1−P)·5`, `Vboro = VazaoBoro·2`.

### Fechamento da conta

| Ação | Regras | Total |
|---|---|---|
| diluir | R1, R3, R5 | 3 |
| borar | R8, R10, R11, R12 | 4 |
| mexer nas barras | R2, R4, R6, R7, R9, R13, R14, R15, R16 | 9 |
| alarmar / encerrar | R17, R18, R19 | 3 |
| | | **19** |

As 16 primeiras batem com as 16 âncoras da varredura 2; as 3 últimas, com a varredura 4.

---

## 4. O que ficou de fora, e por quê

| `if` | Linhas | Por que não é regra |
|---|---|---|
| guardas de despacho | 717, 1168, 1173 | não agem; entram como conjunção no antecedente de R1–R8 |
| seleção de vazão | 722, 727, 732, 790, 795, 800 | escolhem *quanto* diluir, não *se* diluir — parametrizam o consequente de R1 e R5 |
| saturação de vazão de boro | 843 | idem, no consequente de R8 |
| magnitude da barra em R9 | 1179 | escolhe −1 ou −2 dentro da mesma decisão de mover (ver §5) |
| `DeltaI<0` dos limites | 1210, 1228 | não existe fora do alarme que o contém; já contado como conjunção em R11 e R12 |
| entrada de dados, laço de potência, transiente | 871–1143 | inicialização e cenário, não controle em malha |
| `VariacaodeCarga` | 223–310 | código morto nos dois portes: `kbhit()` é fixo em 0 |

---

## 5. Observações estruturais que condicionam a modelagem do SE

Achados verificados no fonte. Nenhum é bug a corrigir — corrigi-los invalidaria a validação
dos Passos 1 e 2. São restrições que o sistema especialista terá de reproduzir.

1. **As regras não são exclusivas nem atômicas.** Os 19 blocos são testados em sequência
   fixa, e vários podem disparar no mesmo minuto; cada um enxerga o estado que o anterior
   deixou (`CorrigeTmedDeltaBarra` já reescreveu `Tmed` e `DeltaT` antes de o próximo `if`
   ser avaliado). Um motor de inferência clássico — casa todas, dispara **uma**, recomeça —
   não reproduz isso. A estratégia de resolução de conflito tem de ser escolhida
   deliberadamente: prioridade = ordem do fonte, disparo múltiplo por ciclo.

2. **Pares de regras redundantes na mesma ação.** R13 e R15 fazem ambas barra +1 com
   condições que se sobrepõem; R14 e R16, barra −1. Estruturalmente nada impede que as duas
   de um par sejam verdadeiras no mesmo minuto, resultando em 2 passos. Se isso ocorre nos
   cenários da dissertação é medição, ainda não feita.

3. **R6 acumula onde as outras atribuem.** L822 é `DeltaBarra = DeltaBarra + 1`; todas as
   demais fazem atribuição direta. Só não muda o resultado porque `CorrigeTmedDeltaBarra`
   zera `DeltaBarra` na L674 depois de consumi-lo.

4. **R11 e R12 têm consequente partido.** O alarme sai com a condição externa; a boração só
   com a condição externa **e** `ΔI<0`. São, a rigor, dois consequentes com antecedentes
   distintos sob o mesmo cabeçalho.

5. **A rampa de vazão de diluição é descontínua nos extremos.** Com `a=2·v1` e `b=v1`, a
   rampa vale `v1·(1−2·ΔT)`, que **não** encontra `v1` em `t1` nem `v2` em `t2`. Com
   `Cboro=1800` (v1=5,00; v2=19,84; t1=−0,3; t2=−0,8): em ΔT=−0,30 o ramo do `if` dá 5,00 e
   a rampa daria 8,01; em ΔT=−0,80 o ramo dá 19,84 e a rampa daria 13,01. Saltos nas duas
   pontas. O SE tem de reproduzir o comportamento por faixas, não interpolar.

6. **As ações consomem tempo simulado, e o custo não está num lugar só.** Cada iteração do
   laço do `main` avança 1 minuto (L1028). Sobre isso, cada ação acrescenta o seu custo, e
   nos dois casos de acerto químico ele vem em **duas parcelas**: o tempo de injeção, na
   regra, mais o tempo de homogeneização, dentro da função de correção
   (`for (i=thom; i>0; i--) { … t=t+1; }`, com `thom = 18` fixo em L950).

   | ação | onde o tempo é somado | total |
   |---|---|---|
   | diluição | `t += tempodilute` na regra (L738, 763, 806) **+** laço de `CorrigeTmedDiluicao` (L538–546) | `tempodilute + 18` = **22** min |
   | boração | só o laço de `CorrigeTmedBoracao` (L617–625) — não há incremento na regra | **18** min |
   | movimentação de barra | `t += 2` em `CorrigeTmedDeltaBarra` (L682) | **2** min |

   Medido na API sobre os cenários 1 e 3: ciclo sem ação salta 1 minuto; com uma barra, 3;
   com uma diluição, 23; com barra e boração, 21 — isto é, 1 do laço mais 2, 22 e 18. Duas
   ações do mesmo tipo no mesmo minuto somam duas vezes (dois movimentos de barra dão 5).

   A consequência: **quantos ciclos cabem num dia depende de quanto o controlador atua.** Um
   minuto parado custa um ciclo; uma diluição cobre 22 minutos num ciclo só. Por isso o mesmo
   dia de operação (`tmax = 1440`) sai em 1072 ciclos no cenário 1, com 154 disparos, e em 92
   no cenário 5, com 159 — medido em `results/API/cenario*-disparos.json`.

   E a homogeneização é **modelo de planta**: quem a executa é a função de correção, não a
   regra. O controlador não escolhe essa duração nem a enxerga — a resposta do ciclo já vem
   com o relógio adiantado.

7. **O peso da barra depende da posição.** `Deltaro = 6,5·DeltaBarra` se P≥100, senão
   `20·DeltaBarra` (L668–673). É modelo de planta, não controlador — o SE não decide isso.

---

## 6. Como reproduzir

As quatro varreduras da §1 são os comandos que geram este documento. Rodando-as no fonte
atual devem sair, nesta ordem: 7 linhas na varredura 1, das quais 6 são funções de ação e a
sétima é `Corrige_DeltaI`; 32 chamadas em 16 pares homogêneos
(4 boração, 9 barra, 3 diluição); as duas guardas de despacho; 5 ocorrências de alarme,
das quais 3 sem atuação.

## 7. Fora do escopo deste passo

- Não foi medido quantas vezes cada regra dispara, nem quais disparam juntas. Sem isso não se
  sabe quais das 19 são exercitadas pelos cenários da dissertação e quais são inalcançáveis.
- Não foi decidido se R9 é uma regra ou duas (−1 e −2 como consequentes distintos).
- Não foi feita nenhuma fusão de regras redundantes (§5.2).
- Não foi separado o controlador do modelo de planta em `simulador.py`.
