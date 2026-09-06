# Passo 5 — O sistema especialista: as 19 regras como dado

**Objetivo:** dar às regras identificadas no Passo 3 uma existência própria, fora da planta.
O resultado é `expert/`, na porta 8009, que não tem modelo de reator nenhum: ele observa,
decide, e manda. A malha se fecha por HTTP entre os dois serviços.

**Critério de aceitação** — o mesmo dos Passos 1, 2 e 4:

> Os dois serviços, conversando por HTTP, têm de produzir **os mesmos bytes** que
> `simulador.py` — no arquivo de amostras e na saída padrão inteira — nos 6 cenários da
> dissertação e nas configurações de borda.

Verificado. §7 tem os comandos e o resultado.

---

## 1. Dois braços, e por que não um

O passo entrega **duas representações das mesmas 19 regras**:

| | Onde | O que é |
|---|---|---|
| **procedural** | `scripts/validate_c_vs_python.py` | os 19 blocos `if` transcritos do `.c`; é o instrumento que validou o Passo 4 |
| **declarativo** | `expert/regras.py` + `expert/motor.py` | 19 registros interpretados por um motor; é o que roda no serviço |

Elas existem para serem confrontadas. Uma sozinha só pode ser comparada com o fonte; duas
podem ser comparadas **entre si**, e a divergência então localiza o erro no que as distingue —
a representação das regras — em vez de deixar a dúvida entre regra, motor e planta.

Isso não é teoria. O primeiro confronto reprovou o braço declarativo, e §5 conta onde.

## 2. A base é dado, e o dado é o texto do C

Um antecedente como

```
(VariacaoDeltaI>=0 || DeltaT<-0.3) || (PosicaoBarra>=222 || DesvioDeltaI>-3)
```

não foi reescrito em Python. Ele está guardado **assim**, texto do fonte, e é compilado
(`expert/expressoes.py`). Duas consequências:

1. **Não há duas representações para divergir.** A regra não tem uma condição "no papel" e
   outra "no código". Tem uma só, que é ao mesmo tempo o que `GET /expert/regras` devolve e o
   que decide.
2. **A comparação com o `.c` é exata.** `tests/test_equivalencia_regras.py` extrai a condição
   da linha declarada em `Regra.linha_c` e canoniza os dois lados pela mesma AST. Espaços,
   quebras de linha e parênteses redundantes somem; a estrutura do operador fica. `((A))`
   bate com `(A)`; `A && B || C` **não** bate com `A && (B || C)`.

A tradução é mínima porque C e Python quase não diferem aqui: `||` vira `or`, `&&` vira
`and`, e só. A precedência relativa é a mesma nas duas linguagens, e nenhuma condição do
simulador encadeia comparações (`a < b < c`), que é o único ponto onde Python mudaria o
sentido.

A mesma ideia vale para os consequentes: a vazão da rampa é `(-a*DeltaT)+b`, o volume de boro
de R11 é `(LimiteInsercao-PosicaoBarra+11)*2`. Texto do fonte, avaliado sobre grandezas já
reembrulhadas no tipo C que `GET /reactor/tipos` declara — é o que faz a aritmética arredondar
a 32 bits nos mesmos pontos que o original.

## 3. Os quatro consequentes, e o partido

A Varredura 1 do Passo 3 encontrou um vocabulário de ações fechado, e a base o reflete: todo
consequente é `Diluir`, `Borar`, `MoverBarra` ou `Alarmar`. Os 19 registros somam **21
efeitos**, e a diferença é exatamente o que o §5.4 do Passo 3 previu:

| Efeito | Quantos | Regras |
|---|---|---|
| diluir | 3 | R1, R3, R5 |
| borar | 4 | R8, R10, R11, R12 |
| barra | 9 | R2, R4, R6, R7, R9, R13–R16 |
| alarme | **5** | R11, R12, R17, R18, R19 |

R11 e R12 têm **consequente partido**: o alarme sai com a condição externa, a boração só com
a condição externa **e** `DeltaI<0`. Na base isso é literal — a regra tem dois efeitos, e o
segundo tem `quando`. Contando *regras* que só sinalizam, voltam a ser as 3 do Passo 3
(R17, R18, R19).

## 4. O motor: a estratégia num lugar só

`regras.py` diz **o que** são as regras; `motor.py` diz **como** são aplicadas. Essa separação
é o ponto do passo: a estratégia de resolução de conflito que o §5.1 do Passo 3 exigiu que
fosse escolhida deliberadamente fica explícita e trocável, em vez de diluída em 19 blocos `if`.

O motor faz três coisas, e só:

1. **Prioridade = ordem.** Sem pontuação, especificidade ou recência. A ordem de leitura de
   `BASE` é a ordem de avaliação, e é a ordem do fonte.
2. **Disparo múltiplo.** Não para na primeira que casa. As 19 são testadas, todo ciclo.
3. **Estado relido a cada regra.** Depois de cada atuação, relê da planta — a regra seguinte
   tem de ver o que a anterior deixou. É por isso que a API do reator é de ação, e não de ciclo.

Um motor clássico — casa todas, dispara uma, recomeça — não reproduziria nada disso.

**A guarda é do bloco, não da regra.** No fonte, `if (DeltaT<-0.1) CompensacaoQueima()` (L1168)
e a primeira linha da função (L717) repetem a mesma guarda, e R1–R4 são então testadas em
sequência **sem reavaliá-la**. Isso importa: se R1 dilui e ΔT sobe acima de −0,1, R2, R3 e R4
ainda são avaliadas. Por isso `Bloco` tem guarda e `Regra` não.

## 5. O que os dois braços pegaram

**O confronto reprovou o declarativo na primeira execução**, e da forma mais informativa
possível: nas configurações que alcançam R11 e R12, as **amostras batiam** e o **stdout não**.
Decisões idênticas, texto diferente — o que localiza o erro no consequente, não no antecedente.

Era o bloco de despejo de estado (t, Z, Pot, Tmed, …). R17, R18 e R19 o imprimem depois do
cabeçalho; os alarmes de limite de inserção de R11 e R12 imprimem só a linha e seguem. Meu
`Alarmar` despejava sempre. `despejo` virou dado da regra.

Se o passo tivesse um braço só, isso teria aparecido como "diverge do `simulador.py`" e a
busca começaria do zero.

## 6. O bug do byte 177

`printf("%c",177)` no C escreve **um byte** — o `▒` do codepage 437 — e R18 imprime 37 deles,
R19 imprime 30. Não é UTF-8 válido.

O campo que transporta a saída era `saida: str` nos dois serviços, com uma ressalva escrita no
`reactor/`: *"sempre UTF-8, porque o único ponto do fonte que emite byte cru está do lado do
expert"*. Assim que o expert passou a existir, a ressalva cobrou: `PydanticSerializationError:
surrogates not allowed`, em **todo** cenário que aciona o alarme de temperatura — o que inclui
os três runbacks e as duas rampas.

O acoplamento estava num comentário, não no tipo. O campo virou `saida_b64` nos dois serviços,
carregando os bytes exatos em base64, e a invariante "carrega os bytes desta chamada" passou a
valer sem ressalva. O Passo 4 foi revalidado inteiro depois da mudança.

## 7. Como reproduzir

**Os dois braços, tudo em processo** (~7 s sem o cenário 6):

```sh
bash scripts/verifica_expert.sh --rapido
bash scripts/verifica_expert.sh            # inclui o ciclo até Cboro<8
```

Compara `simulador.py` × braço procedural × braço declarativo, todos dirigindo a mesma planta.

**A malha fechada, dois serviços por HTTP:**

```sh
bash scripts/verifica_malha_fechada.sh              # ~15 s
bash scripts/verifica_malha_fechada.sh --completo   # inclui o cenário 6
```

**Os serviços e as suítes:**

```sh
podman-compose up -d
podman exec reactor-simulator      python -m pytest /tests    # 40 testes
podman exec reactor-expert-system  python -m pytest /tests    # 46 testes
```

Os dois contêineres montam a **mesma** pasta `tests/`; `SERVICO` diz qual está executando e
cada módulo se pula sozinho quando não é a sua vez.

**Uma corrida à mão pela malha:**

```sh
echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' \
  | python3 scripts/cliente_malha.py --tmax=1440 --pedaco=500 > malha.out
```

O cliente não decide nem calcula nada: abre a sessão, pede ciclos e concatena `saida_b64`.

### Resultado — os dois braços, em processo

| Configuração | amostras | procedural | declarativo |
|---|---|---|---|
| 1 — operação normal, 1 dia | 1072 | ok | ok |
| 2 — runback bomba de alimentação | 750 | ok | ok |
| 3 — runback manual 150 MW | 260 | ok | ok |
| 4 — rampa 32→650 MW a 1 MW/min | 328 | ok | ok |
| 5 — rampa 650→32 MW a 3 MW/min | 92 | ok | ok |
| 6 — ciclo completo até Cboro<8 | 514421 | ok | ok |
| ramo Pbase<0 / Ptopo<0 (WIN_ORIGINAL) | 9 / 376 | ok | ok |
| banco D=178 / 170 / 150 (R11, R12) | 111 / 528 / 424 | ok | ok |

### Resultado — a malha fechada, dois serviços

| Configuração | amostras | dados | stdout |
|---|---|---|---|
| 1 a 5 — os cenários com transiente | 1072 / 750 / 260 / 328 / 92 | ok | ok |
| 6 — ciclo completo até Cboro<8 | 514421 | ok | ok |
| ramo Pbase<0 | 9 | ok | ok |
| banco D=178 / 170 / 150 (R11, R12) | 111 / 528 / 424 | ok | ok |

O cenário 6 pela malha são **467.771.168 bytes** de saída padrão remontados a partir de duas
APIs, com o mesmo SHA-256 do monolito, e um arquivo de amostras de 45,7 MB idêntico. São
514.421 ciclos e cerca de 522 mil idas e voltas HTTP.

**Uma armadilha de método, registrada porque me custou tempo.** A primeira execução completa
truncou no meio e apareceu como `DADOS DIVERGEM`. Não era: eu tinha reconstruído as imagens
enquanto a corrida rodava, e o cliente morreu com o `stderr` indo para `/dev/null`. Uma corrida
interrompida é indistinguível de uma divergência quando se joga o erro fora. O script agora
mostra o `stderr` do cliente e diz `>> o cliente da malha falhou (rc=N), a corrida está
incompleta` — o mesmo cenário, rodado sem interferência, bate byte a byte.

## 8. Quantas vezes cada regra dispara

Pendência aberta desde o §7 do Passo 3: *"não foi medido quantas vezes cada regra dispara, nem
quais disparam juntas. Sem isso não se sabe quais das 19 são exercitadas pelos cenários da
dissertação e quais são inalcançáveis."* O motor conta, e `GET /expert/{sid}/disparos` devolve.

| Cenário | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | R14 | R15 | R16 | R17 | R18 | R19 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 normal, 1 dia | 3 | · | · | · | · | · | · | · | 74 | · | · | · | 77 | · | · | · | · | · | · |
| 2 runback BAP | 24 | · | · | · | 4 | · | · | · | 7 | 1 | · | · | 3 | 18 | · | · | · | 2 | · |
| 3 runback 150 MW | 23 | · | · | · | 26 | · | 2 | · | 6 | 1 | · | · | 3 | 31 | · | · | · | 4 | · |
| 4 rampa 32→650 | 9 | · | 6 | 2 | 25 | · | 1 | · | 38 | · | · | · | 83 | · | · | · | · | 3 | · |
| 5 rampa 650→32 | 50 | 25 | · | · | · | · | · | · | 8 | 3 | · | · | 4 | 68 | · | · | · | 1 | · |
| 6 ciclo completo | 5966 | 2 | · | · | · | 8 | · | 1285 | 74 | · | · | · | 77 | · | · | 1 | · | · | 1 |
| D=178, ΔI=−1 | · | · | · | · | · | 1 | · | · | 106 | 1 | 3 | · | 111 | · | 1 | · | · | · | · |
| D=170, ΔI=−1 | · | · | · | · | · | 1 | · | · | · | 1 | 527 | 1 | 6 | · | 2 | · | · | · | · |
| D=150, ΔI=−4 | 3 | 1 | 1 | 2 | 1 | 1 | · | · | · | · | · | 424 | 7 | · | 4 | · | · | 2 | · |
| D=144, ΔI=12 | 8 | · | · | · | 9 | · | 9 | · | · | · | · | · | · | · | · | · | 9 | · | · |

Três leituras que a tabela permite:

- **Os 6 cenários da dissertação exercitam 15 das 19 regras.** R2, R3, R4, R6, R7, R8, R16 e
  R19 só aparecem no ciclo completo ou na rampa; **R11, R12, R15 e R17 nenhum deles alcança**
  — só as configurações de borda, construídas para isso.

  > **Correção.** Este parágrafo dizia "12 das 19" e listava três inalcançáveis, omitindo
  > **R15**. Os dois números saem da própria tabela acima: a união das colunas não vazias nas
  > seis primeiras linhas dá 15 regras, e R15 está com `·` nas seis. A conferência
  > independente é o campo `nunca_dispararam` de `results/API/cenario*-disparos.json`: a
  > interseção dos seis arquivos é exatamente **{R11, R12, R15, R17}**. R15 não teve
  > configuração feita para ela — sai de carona nas três corridas de banco próximo ao limite
  > de inserção, o que é coerente com a condição dela (`P<LI+11`).
- **Nenhuma das 19 é inalcançável.** Todas disparam em alguma configuração da bateria.
- **R14 dispara mais que R13 nos transientes e menos na operação normal**, e R15/R16 quase não
  aparecem — o que dá material para discutir as redundâncias do §5.2 do Passo 3 (R13/R15 fazem
  ambas barra +1; R14/R16, barra −1) com medida, e não só com estrutura.

## 9. O que ficou de fora

- **As redundâncias do §5.2 continuam intactas.** Reproduzi-las é obrigação; fundi-las seria
  mudar o controlador. A tabela do §8 é o insumo para essa discussão, não a decisão.
- **R9 continua sendo uma regra, não duas.** A escolha entre −1 e −2 está modelada como faixa
  dentro do mesmo consequente, como no fonte. Se a dissertação quiser contá-las separadamente,
  a base suporta — mas isso muda o número 19, e o Passo 3 fixou o critério de contagem.
- **O motor não tem estratégia alternativa.** Ele implementa a do simulador. Trocá-la (para
  disparo único, ou prioridade por especificidade) é uma linha em `Motor.ciclo`, mas seria
  outro controlador, e teria de ser validado contra outra coisa que não o `simulador.py`.
- **Não há interface de operação.** A malha é fechada por `scripts/cliente_malha.py`, que é um
  cliente de validação, não um painel.
