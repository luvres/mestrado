# Passo 4 — Separação da física: o reator como serviço

**Objetivo:** tirar do simulador tudo que decide, deixando só o que acontece, e pôr o que
sobrou atrás de uma API. O resultado é `reactor/`, que roda na porta 8008 e não tem uma
única linha de controle. O sistema especialista (`expert/`, porta 8009) é o Passo 5.

**Critério de aceitação** — o mesmo dos Passos 1 e 2, e por isso é comparável a eles:

> A planta separada, dirigida pelas 19 regras do Passo 3, tem de produzir **os mesmos
> bytes** que `simulador.py` — no arquivo de amostras **e** na saída padrão inteira —
> nos 6 cenários da dissertação e nas configurações de borda.

Foi verificado nos dois transportes: com as regras no mesmo processo e com a planta atrás
do HTTP. Nenhum byte mudou. §6 tem os comandos.

---

## 1. Onde cortar

O corte não é entre arquivos nem entre funções — é dentro de cada uma das 19 regras. Toda
regra tem a mesma anatomia, e ela se parte sempre no mesmo lugar:

| Parte da regra | Exemplo em R1 | Fica em |
|---|---|---|
| **antecedente** | `VΔI≥0 ∨ ΔT<−0,3 ∨ P≥222 ∨ DΔI>−3` | expert |
| **parametrização do consequente** | qual vazão: `v1`, `v2` ou `−a·ΔT+b` | expert |
| **texto que identifica a regra** | `"Iniciada a Diluicao na Vazao de %.0f lpm"` | expert |
| **efeito** | mistura do boro, 18 min de homogeneização, redistribuição topo/base | **reactor** |

As três primeiras linhas são a mesma decisão vista de ângulos diferentes; a quarta é a
planta. O §4 do Passo 3 já tinha classificado a seleção de vazão como "escolhe *quanto*
diluir, não *se* diluir" — aqui isso vira fronteira executável.

O teste da terceira linha é R1 contra R5: as duas mandam diluir, e o efeito na planta é
idêntico, mas uma imprime `Iniciada a Diluicao` e a outra `Iniciada a Correcao do Delta I
por Diluicao`. O texto identifica a regra, não o efeito — logo é do expert. Mesma coisa com
`Posicao Anterior/Atual do Banco D`, que aparece em nove regras diferentes.

Sobram **três alavancas**, que são exatamente as três que a Varredura 1 do Passo 3 achou:

```
POST /reactor/{sid}/acao   {"acao": {"tipo": "diluir", "vazao": 5.0047}}
                           {"acao": {"tipo": "borar", "vazao_boro": 12.0, "vboro": 24.0}}
                           {"acao": {"tipo": "barra", "passos": -2}}
```

## 2. Por que a API é de ação, e não de ciclo

Esta é a decisão que estrutura o resto, e ela foi imposta pelo §5.1 do Passo 3: as regras
**não são atômicas**. Os 19 blocos são testados em sequência fixa, vários disparam no mesmo
minuto, e cada um enxerga o estado que o anterior deixou — `CorrigeTmedDeltaBarra` já
reescreveu `Tmed` e `DeltaT` antes de o `if` seguinte ser avaliado.

Um endpoint que recebesse as decisões do minuto em bloco só funcionaria se o expert
soubesse prever esses estados intermediários — ou seja, se ele tivesse um modelo da planta
dentro de si. Isso desfaria a separação inteira.

Então o protocolo é: **uma atuação por chamada, estado relido a cada vez**.

```
POST /reactor/{sid}/passo   →  avança um minuto, devolve o estado
   avalia R1 → dispara → POST /acao → estado novo
   avalia R2 sobre o estado novo → não dispara
   avalia R3 sobre o mesmo estado → dispara → POST /acao → ...
```

O preço é o número de idas e voltas. Medido:

| Cenário | passos | diluir | borar | barra | total de chamadas |
|---|---|---|---|---|---|
| 1 — operação normal, 1 dia | 1072 | 3 | 0 | 151 | **1226** |
| 3 — runback manual 150 MW | 260 | 49 | 1 | 42 | **352** |

O cenário 1 inteiro leva ~1,8 s por HTTP. É o preço certo.

## 3. O que cada arquivo é

| Arquivo | Linhas | O que é |
|---|---|---|
| `reactor/f32.py` | 131 | O `float` de 32 bits do C. **Cópia literal** de `simulador.py`. |
| `reactor/saida.py` | 53 | Captura do que a planta imprime, por sessão (`ContextVar`). |
| `reactor/physics.py` | 1021 | A planta. **47% é cópia literal** de `simulador.py`. |
| `reactor/models.py` | 134 | Contratos pydantic da API. |
| `reactor/main.py` | 234 | As rotas. Não contém nenhuma conta. |
| `scripts/validate_c_vs_python.py` | 552 | O braço procedural: as 19 regras fora da planta. |

**As partes copiadas são cópia mesmo.** Em `f32.py` e `physics.py` os trechos herdados estão
entre marcadores `# --- inicio/fim do bloco copiado`, e `tests/test_genealogia.py` procura
cada bloco, **verbatim**, dentro de `simulador.py`. Não por número de linha — por texto,
para a prova sobreviver a qualquer deslocamento. Editar a cópia em vez do original quebra a
suíte.

O que **não** foi copiado, e por quê:

- `VariacaodeCarga()` e o bloco `kbhit()` do laço: código morto nos dois portes (`kbhit()`
  é fixo em 0, Passo 3 §4), e um serviço HTTP não tem teclado. Os dois caminhos que eles
  alimentavam — runback e rampa — entram por `AplicaTransienteAuto()`, que veio.
- `termino`: é R19 quem declara fim de ciclo. A planta só informa `t` e `tmax`;
  `pode_continuar()` é metade da condição do laço, e a outra metade é de quem controla.
- `sys.exit(1)` do `GravaDados`: virou exceção. Um serviço não morre porque uma sessão não
  conseguiu abrir arquivo.
- `WIN_ORIGINAL`, que era macro de compilação e depois variável de ambiente: agora é campo
  por sessão, porque duas sessões podem querer semânticas diferentes no mesmo processo.

## 4. O contrato de saída, e por que ele existe

Toda resposta traz o campo `saida_b64`: os **bytes** que aquela chamada imprimiu, em base64.
Decodificados e concatenados na ordem das chamadas, reproduzem byte a byte a saída padrão do
simulador monolítico.

Isso não é conveniência de log. É o que torna a separação **falsificável**. Comparar só o
arquivo de amostras provaria que se chegou aos mesmos números; comparar a saída padrão
inteira prova que se chegou por dentro do mesmo caminho — as mesmas diluições, na mesma
ordem, com as mesmas vazões, intercaladas com as mesmas movimentações de barra. Uma regra
que tivesse ficado do lado errado passaria no primeiro teste e falharia no segundo.

**Por que base64, e não texto.** A saída do simulador é um fluxo de *bytes*, não uma string:
`printf("%c",177)` no C escreve UM byte — o `▒` do codepage 437 — que não é UTF-8 válido, e
nenhum campo string de JSON o transporta sem perda. Esta planta em particular nunca emite
esse byte (quem emite são R18 e R19, do lado do expert), mas o campo tem o mesmo contrato nos
dois serviços, para que "carrega os bytes exatos desta chamada" valha sem ressalva.

Este campo era `saida: str` até o Passo 5, e a ressalva "sempre UTF-8 porque o byte cru está
do outro lado" parecia bastar. Não bastava: assim que o expert passou a emitir esses bytes, a
serialização quebrou com `PydanticSerializationError: surrogates not allowed` em todo cenário
que aciona o alarme de temperatura. O acoplamento estava num comentário, não no tipo.

## 5. `/reactor/tipos` — a fidelidade não sobrevive ao JSON sozinha

O expert não só lê números: ele faz contas com eles. `Vazao = −a·ΔT + b` e
`VazaoBoro = −DΔI·6` são contas do lado do controle, e no C elas arredondam a 32 bits a cada
operação. O JSON entrega `double`. Sem saber o tipo C de cada grandeza, o cliente calcularia
com precisão a mais, e o Passo 1 já registrou o que ±0,001 faz: desloca um evento de
diluição e desfaz a fase do resto da corrida.

Por isso `GET /reactor/tipos` devolve, para cada uma das 30 grandezas observadas, se ela é
`float` (32 bits), `int` ou `double`. O cliente reembrulha e as contas voltam a arredondar
nos mesmos pontos. É o que `Observacao` faz em `validate_c_vs_python.py` — e é a razão de as
19 regras funcionarem sem uma linha de diferença entre o modo em processo e o modo HTTP.

A observação tem **30 grandezas**: as 8 que aparecem nas condições das regras (Passo 3 §2),
as 8 de apoio ao alvo e à seleção de vazão, e 14 de relógio, potência e horizonte.
`GET /reactor/{sid}/interno` expõe as **104** variáveis globais do `.c` — não para o
controle, e sim para a validação poder comparar variável a variável.

## 6. Como reproduzir

**Fronteira, com tudo no mesmo processo** (~4 s sem o cenário 6):

```sh
bash scripts/verifica_fronteira_reactor.sh --rapido   # 6 cenários menos o ciclo completo
bash scripts/verifica_fronteira_reactor.sh            # inclui o ciclo até Cboro<8
```

Compara `simulador.py` com `reactor/physics.py` + o braço procedural, em três colunas: o
arquivo de amostras, a saída padrão (SHA-256 — no cenário 6 ela passa de 400 MB) e a mesma
saída passando pelo buffer de captura que a API usa.

**API, com a planta atrás do HTTP** (~25 s sem o cenário 6):

```sh
bash scripts/verifica_api_reactor.sh              # constrói a imagem, sobe, compara
bash scripts/verifica_api_reactor.sh --completo   # inclui o ciclo completo
```

O cliente também roda em contêiner, na rede do serviço. O motivo é reprodutibilidade: ele usa
o mesmo Python e as mesmas versões fixadas de `reactor/requirements.txt` que o serviço, e o
teste não depende de nada instalado no host. Do host também funciona — é como se depura uma
corrida à mão (o comando está logo abaixo).

**O serviço e a suíte:**

```sh
podman-compose up -d reactor-simulator
podman exec reactor-simulator python -m pytest /tests     # 39 testes
podman exec reactor-simulator curl -s localhost:8008/health
```

A suíte entra por montagem read-only e roda **dentro** da imagem, contra os módulos que
estão servindo a API — com a versão de Python da imagem e as versões fixadas em
`reactor/requirements.txt`. Testar uma cópia no host provaria que a cópia funciona.

**Uma corrida à mão, por HTTP:**

```sh
echo "650 1800 210 4 -0.3 -0.8 0" | tr ' ' '\n' \
  | python3 scripts/validate_c_vs_python.py --api=http://localhost:8008 --tmax=1440 \
  > /dev/null
```

### Resultado

| Configuração | amostras | dados | stdout |
|---|---|---|---|
| 1 — operação normal, 1 dia | 1072 | ok | ok |
| 2 — runback bomba de alimentação | 750 | ok | ok |
| 3 — runback manual 150 MW | 260 | ok | ok |
| 4 — rampa 32→650 MW a 1 MW/min | 328 | ok | ok |
| 5 — rampa 650→32 MW a 3 MW/min | 92 | ok | ok |
| 6 — ciclo completo até Cboro<8 | 514421 | ok | ok |
| ramo Pbase<0 (porte) | 9 | ok | ok |
| ramo Ptopo<0 (WIN_ORIGINAL) | 376 | ok | ok |
| banco D=178, ΔI=−1 (R11) | 111 | ok | ok |
| banco D=170, ΔI=−1 (R11+R12) | 528 | ok | ok |
| banco D=150, ΔI=−4 (R12 emergência) | 424 | ok | ok |

Idênticas nos dois transportes.

## 7. Uma ressalva registrada

`diluir()` fixa `tempo = t` no instante da atuação. No fonte, `tempo = t` é atribuído dentro
de cada um dos três ramos de seleção de vazão (L722, 727, 732), que são exaustivos para
qualquer `t1 > t2` — e `t1 > t2` vale nos 6 cenários e em toda a bateria. Se algum dia
alguém rodar com `t1 ≤ t2`, os três ramos podem ser todos falsos, e aí o fonte usaria o
`tempo` da diluição anterior enquanto a planta usa o atual. É a única equivalência do passo
que vale sob hipótese, e não incondicionalmente.

## 8. Uma armadilha de infraestrutura

No podman *rootless*, o uid 1000 de dentro do contêiner cai num subuid do host e **não**
consegue escrever num diretório do usuário. Como o serviço grava as amostras em `/runs`,
que é `./runs` montado do host, sem `userns_mode: "keep-id"` o `POST /reactor/initialize`
responde 500. Está no `docker-compose.yml`, comentado.

## 9. Fora do escopo deste passo

- O `expert/` não foi escrito. `scripts/validate_c_vs_python.py` **não é** o sistema
  especialista: é a transcrição procedural que serve de instrumento de verificação aqui e
  de referência no Passo 5, quando a base de regras declarativa for conferida contra ela.
- Não foi decidido nada sobre as redundâncias que o Passo 3 §5.2 apontou (R13/R15 e
  R14/R16). Reproduzi-las é obrigação; fundi-las seria mudar o controlador.
- Não foi medido quantas vezes cada regra dispara nos cenários — continua pendente desde o
  Passo 3 §7. A instrumentação ficou mais fácil agora: basta contar as chamadas a `/acao`.
- A malha ainda é fechada por um script, e não por um serviço. `POST /expert/initialize`,
  que recebe a URL do reator, é do Passo 5.
