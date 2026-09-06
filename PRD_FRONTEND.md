# PRD — Frontend de demonstração

**Documento vivo.** Registra as ideias discutidas para o cliente de demonstração do
simulador. Vai sendo atualizado conforme as decisões amadurecem. O que está decidido está
marcado como tal; o resto é proposta ou pergunta em aberto.

Última atualização: 2026-09-06 (sétima revisão — os sete parâmetros de partida ficaram
visíveis e editáveis, e a tela passou a caber na janela sem rolagem).

---

## 1. Por que existe, e o que precisa provar

A tese afirma que o conhecimento de controle de um operador sênior, embutido num simulador
legado em C, foi extraído e passou a existir como **base de regras inspecionável, servida
separadamente da física** — e que a separação é exata: os dois serviços reproduzem o binário
original byte a byte, nos 6 cenários.

Uma tela que só desenhe curvas **não prova nada disso**. As curvas seriam idênticas se as
regras continuassem enterradas na física — é justamente o que a igualdade byte a byte diz.

Então a tela tem de mostrar a **fronteira**, não escondê-la: a planta de um lado, as 19
regras do outro, e o tráfego entre elas.

Este é o primeiro critério para aceitar ou rejeitar qualquer ideia. O segundo é o §2.

---

## 2. O alvo

**Uma interface simples, profissional e bonita**, para explorar uma corrida e entender as
decisões do controlador.

> **Revisão de 2026-09-06.** Este documento nasceu com outro alvo — *tela de projeção numa
> defesa*, com legibilidade a três metros e um tempo de fala de 3 a 5 minutos. Essa restrição
> foi **retirada**. O registro fica porque ela moldou decisões que continuam valendo por
> outros motivos, e porque saber que ela existiu explica por que a §4 já foi mais enxuta.

O que a restrição de projeção deixou, e por quê:

**Zero requisições externas** — mantido. Não é mais "a defesa pode falhar", é
reprodutibilidade: a mesma disciplina que fixa versões e roda tudo em contêiner. A página tem
de abrir daqui a cinco anos, com a rede desligada. Sem CDN, sem fonte remota.

**A falha tem de ser visível** — mantido, e é a lição mais cara do frontend anterior: erro do
expert era tratado como "sem ação", a simulação seguia com o controle desligado, e ninguém
percebia.

**A stack sem build** — mantida (§8).

O que caiu junto com a restrição: o corte agressivo de conteúdo (§4.5), o "um medidor por vez"
(§4.1) e o teto de densidade. Sem projeção, cabe mais na tela.

### 2.1 A pergunta que a tela responde

> *"No minuto 412 o controlador inseriu barra. Por quê? Porque esta regra testa se ΔT passou
> de 0,6 — e passou. Ela não está dentro do simulador: está num serviço separado, e o que
> está escrito aqui é o texto do programa do Igor, linha 1176."*

Isso não mudou, e continua sendo o que separa esta tela de um dashboard qualquer.

---

## 3. Estado das decisões

| Assunto | Situação |
|---|---|
| Alvo: interface simples, profissional e bonita | **decidido** (§2) |
| ~~Projeção numa defesa~~ | **retirado** pelo usuário em 2026-09-06 |
| Zero requisições externas | **decidido** (§2) — por reprodutibilidade |
| Falha de serviço visível | **decidido** (§2) |
| Stack: HTML + CSS + ES modules, sem build | **decidido** (§8) |
| O laço de controle **não** vai para o cliente | **decidido** (§6.1) |
| O frontend **não calcula nada** | **decidido** (§6.2) |
| Sem seletor de política de arbitragem | **decidido** (§6.3) |
| Fonte única dos 6 cenários | **resolvido** — `cenarios.json` |
| Onde a página é servida | **decidido** (§7.1) — montada no expert, em `/app` |
| Fundo claro ou escuro | **em aberto** — os dois existem, no botão ◐ |
| Tela inteira sem rolagem | **decidido** (§4.6) — `100dvh`, duas colunas |
| Faixa nos campos de partida | **decidido** (§7.6) — avisar, nunca travar |
| Quantos instrumentos, e de que forma | **decidido** (§4.1) — cinco painéis no tempo; os medidores de agulha foram descartados |
| As 5 curvas na tela | **resolvido** (§7.2) — voltaram, e são o próprio instrumento |
| Blocos de duração na faixa de disparos | **em aberto** (§7.3) — a v1 desenha tiques |
| Cenário 6 | **decidido** (§7.4) — fora da timeline, desabilitado no seletor |
| **A API não reporta os parâmetros da ação** | **em aberto** (§5.5) — muda a API; a lacuna já aparece na tela |
| Gramática das regiões: `&&` × `\|\|` | **decidido** (§4.1.1) — árvore, não lista |
| **Sobreposição com as curvas da dissertação** | **em aberto** (§7.5) |
| **Parâmetros de partida editáveis** | **decidido** (§7.6) — os 7 mais o horizonte, com avisos e 4 atalhos de borda |

---

## 3.1 Implementação

**Implementada em 2026-09-06, com autorização.** Serve em `http://localhost:8009/app/`, junto
com os serviços: `podman-compose up -d` sobe a demo inteira.

### O que existe

`static/`, nove arquivos, HTML + CSS + ES modules, sem build, sem npm, sem CDN:

| arquivo | papel |
|---|---|
| `index.html`, `style.css` | marcação e os dois temas |
| `app.js` | roda a corrida e liga o cursor a tudo; **não tem laço de controle** |
| `api.js` | as quatro chamadas; qualquer resposta não-2xx levanta e para a corrida |
| `tree.js` | lê a condição como **árvore** booleana e classifica cada termo; nunca avalia |
| `panels.js` | os cinco painéis no tempo, SVG à mão |
| `rule.js` | a condição com os valores substituídos, o consequente e o console |
| `band.js` | as 19 regras alinhadas no tempo |
| `params.js` | os sete valores de partida, os avisos e os atalhos de borda |
| `format.js` | vírgula na interface, ponto dentro da condição |

Nos serviços, a §7.1: `expert/main.py` ganhou um `StaticFiles` em `/app` (com guarda — sem a
montagem o serviço sobe igual, sem `/app`) e uma rota para `cenarios.json`; o
`docker-compose.yml` ganhou `./static:/api/static:ro` e `./cenarios.json:/api/cenarios.json:ro`.
Depois entraram mais duas mudanças em serviço, ambas pequenas e ambas por motivo apurado:

- **`no-cache` em `/app`** (`_AppEstatico` em `expert/main.py`). Sem cabeçalho de cache o
  navegador aplicava cache heurístico e continuava servindo o módulo antigo depois da edição —
  o que anula o motivo de `static/` entrar por montagem. Descoberto do pior jeito: eu media
  uma tela e o código em execução era outro. `no-cache` não proíbe guardar, obriga a
  revalidar, e o ETag resolve em 304. Vale só para `/app`.
- **`gt=0` em `tempodilute`** (`expert/models.py` e `reactor/models.py`), pelo motivo do §7.6.

Nenhuma rota da API foi tocada, e a suíte do expert continua em 46 passed / 41 skipped.

### Como foi verificado

- **Cenário 3**: 260 ciclos, e as contagens de disparo lidas na tela — `R1:23 R5:26 R7:2 R9:6
  R10:1 R13:3 R14:31 R18:4` — são idênticas a `results/API/cenario3-disparos.json`.
- **Cenário 5**: 92 ciclos, contagens idênticas a `cenario5-disparos.json`.
- **Falha visível**: com o `reactor-simulator` parado, o clique em Rodar produz barra vermelha
  com o 502 e o detalhe do expert, LED vermelho e corrida interrompida — não "sem ação".

### Achados

Os três primeiros vêm da tentativa não autorizada e revertida da manhã; todos foram aplicados:

- `formata(0.72)` devolvia `0,720` — casas decimais fixas deixam zero à toa;
- a linha da condição misturava separadores (`5,16>0.6`). A interface deve usar vírgula, mas
  **dentro da condição o separador tem de ser ponto**: os literais dela são texto do fonte C;
- os limiares de `DeltaI` não apareciam, porque o `DeltaI<0` de R11 e R12 vive no `quando` do
  efeito partido, não na condição da regra. Quem for extrair limiares precisa ler os dois. É
  por isso que há um painel de ΔI, separado do desvio (§4.1).

Os três seguintes são da primeira implementação:

- **duração de ação não se deduz do salto do relógio.** Ver §7.3 — a tentativa está registrada
  lá porque a ideia é atraente e errada;
- **montar um arquivo dentro de um diretório que já é bind-mount suja o repositório.**
  `- ./cenarios.json:/api/static/cenarios.json:ro` fez o podman criar um `static/cenarios.json`
  de 0 byte **no host**, porque o alvo não existia. `cenarios.json` passou a entrar em
  `/api/cenarios.json`, fora do diretório servido, e sai por uma rota explícita;
- **o `StaticFiles` não segue symlink para fora do diretório servido** — verificado: um
  `static/x.json -> ../cenarios.json` responde 404. Foi o que descartou a saída do symlink e
  obrigou à rota.

E estes são da troca dos medidores pelos painéis:

- **desenhar comparações como lista afirma conjunção.** Nove das dezenove condições têm `||`,
  e nelas a região pintada dizia algo falso. O conserto foi ler a árvore (§4.1.1). É o achado
  de maior alcance desta revisão, porque não era um defeito de estilo: a tela afirmava.
- **os dois eixos do tempo não estavam alinhados.** Os painéis reservam 52 unidades do SVG à
  esquerda para os rótulos do eixo Y; a faixa de disparos não reservava nada. Empilhar as duas
  coisas só faz sentido se o mesmo minuto cair na mesma coluna de pixels — agora ambas usam a
  mesma calha, exportada de `panels.js`, e o desvio medido entre o cursor da faixa e o ponto do
  painel é de 1 px, que é a largura do próprio cursor.
- **dois tropeços de navegador, registrados para não voltarem:** `calc()` não multiplica
  porcentagem por comprimento — a expressão inteira vira inválida e o elemento vai para a borda
  da tela; e `offsetParent` é `null` enquanto o elemento está `hidden`, então medir antes de
  mostrar devolve zero.

---

## 4. O que fica na tela

Três elementos, cada um grande o bastante para ler de longe.

```
┌──────────────────────────────────────────────────────────────┐
│  CENÁRIO 3 — runback manual para 150 MW          t = 412 min │
│                                                              │
│   ΔT   −1,67 ──┬─ −0,1 ── 0 ── 0,6 ─ 0,8 ─┬── +1,67          │
│                │           ▲ 0,72          │                 │
│                                                              │
│   R9  disparou →  barra −1                                   │
│   (ΔT>0.6) && (DΔI>=-2.2) && (P>(LI+11) || ΔT>1.5)           │
│   (0.72>0.6) && (-0.31>=-2.2) && (212>184 || …)   verdadeira │
│   V8_Reatividade_SimuladorIgor_linux.c:1176                  │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ R1  ·                    ·              ·                    │
│ R5  ││││││ ││   │││                                          │
│ R9  ││ ││││││ ││││││ │││││█││││ ││││ ││││││ │││ ││││ ││      │
│ R13 ││││││││││││││││││││││││││││││││││││││││││││││││││││      │
│     0        200       400   ▲    600       800      1440    │
└──────────────────────────────────────────────────────────────┘
```

### 4.1 Os cinco instrumentos, no tempo, com as regiões das regras

A ideia central do desenho. Um gráfico genérico mostra `ΔT` subindo; um gráfico com as regiões
das regras mostra **por que** algo vai acontecer. E os limiares são dado: `GET /expert/regras`
devolve a condição de cada regra no texto literal do fonte C.

```
ΔT   5 ┤     ╭╮                                                    │
       │     ││   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  R9·B: ΔT>1.5   (contorno)
   2,5 ┤    ╭╯╰╮  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  R9: ΔT>0.6     (cheia)
     0 ┤────╯───╰──────────────────────────────────────────
       0        200       400       600       800      1440
```

**Cinco painéis** — ΔT, ΔI, desvio de ΔI, banco D e boro —, empilhados, dividindo o eixo do
tempo, com o cursor atravessando os cinco.

**Por que não são medidores de agulha.** Foram, na primeira versão, e o usuário rejeitou:
*"repare que ninguém entende nada. Pior que os gráficos em results/graficos/"*. Duas causas,
e a segunda é a que importa:

1. **Densidade sem hierarquia.** Dezessete limiares e trinta siglas de regra numa linha de
   900 px, em fonte de 8,5 px e três alturas alternadas. A régua do ΔT sozinha carregava todos
   os limiares de todas as regras, sempre, independentemente de fazerem sentido naquele
   minuto.
2. **O conteúdo de tese é temporal.** "Vê-se a barra sendo espremida contra o limite" é a
   barra *se aproximando* de `LimiteInsercao` ao longo do tempo. `LI` e `BD` não são marcas —
   **são curvas**. Uma agulha num instante não mostra aproximação, e na régua do banco D as
   duas simplesmente saíam de cena: `LI = 2,58·Pot − 85` fica em −27 a 23 % de potência.

Agora `LI` e `BD` são curvas ao lado da curva da barra, recortadas pelo painel — aparecem
quando chegam perto, que é quando importam. E vê-se `BD` caindo de 217 para 160 no cenário 3
enquanto a barra é empurrada atrás dele, que é o que explica os 31 disparos de R14.

**A gramática das regiões** (§4.1.1) é o que distingue isto de um gráfico com linhas de
referência.

#### 4.1.1 A condição é uma árvore, e o desenho tem de dizer isso

A primeira versão dos painéis pintava uma região por comparação e chamava todas de "termo da
conjunção". **Nove das dezenove condições têm `||`** — R1, R2, R3, R5, R7, R8, R9, R17, R18 —
e nelas a tela afirmava algo falso: pintava `PosicaoBarra>=222` como região a satisfazer com a
barra em 194 e a regra tendo disparado assim mesmo, por outro ramo do `ou`.

O desenho passou a ler a **árvore**, não a lista:

| | |
|---|---|
| região cheia | termo obrigatório — só `&&` até a raiz. A regra disparou, então ele vale, e a curva está dentro |
| contorno **A**, **B**, … | alternativas sob um `||`. Mesma letra vale junto; letras diferentes, basta uma |
| tracejado | a guarda do bloco — que também tem estrutura: a do bloco II é `DΔI>2 \|\| DΔI<-2` |

Em R9 saem dois obrigatórios — `ΔT>0.6` e `DesvioΔI>=-2.2` — mais o par `A: P>LI+11` /
`B: ΔT>1.5`, cada um no painel da grandeza que testa. Em R1, que é disjunção pura, **nada**
recebe região cheia.

Depois de achatar `&&` de `&&` e `||` de `||`, nenhuma das 19 passa de **dois níveis** — o
percurso é recursivo mesmo assim, porque nada na API promete que continuará assim.

**O que a tela não diz: qual ramo venceu.** Dizer exigiria comparar em `double` o que o expert
decidiu em float de 32 bits, e num caso de fronteira os dois discordariam — a tela mostraria
"falso" ao lado da regra acesa (§6.2). Quem sabe é o motor, no instante em que atua: é pedido
da mesma família do §5.5.

Nenhum limiar é escrito no cliente. `tree.js` lê as comparações do texto da condição, da
guarda e do `quando` dos efeitos — inclusive o `DeltaI<0` que R11 e R12 escondem no efeito
partido, e que é a razão de haver um painel de ΔI separado do desvio. Comparações contra outro
campo (`(LimiteInsercao+11)`, `(BD-3)`, `t1`, `t2`) viram **fronteiras móveis**: curvas, não
linhas. E termo cuja grandeza não tem painel — `VariacaoDeltaI`, de R1 e R2 — sai numa linha
abaixo dos painéis, em vez de sumir calado.

### 4.2 A regra explicada, com os valores substituídos

```
R9: (ΔT>0.6) && (DΔI>=-2.2) && (P>(LI+11) || ΔT>1.5)
    (0.72>0.6) && (-0.31>=-2.2) && (212>184 || 0.72>1.5)   → verdadeira
    fonte: V8_Reatividade_SimuladorIgor_linux.c:1176
```

Se a demonstração inteira tivesse de caber num só elemento, seria este. O texto da condição
vem do expert (`condicao`), os valores vêm do `estado`, a procedência vem de `linha_c`.

### 4.3 A faixa de disparos, uma linha por regra

As 19 empilhadas, com uma marca onde cada uma disparou, e o cursor da timeline atravessando.
É a única visualização que mostra a base de regras *funcionando como base de regras* —
densidades diferentes, regras que nunca acendem, o padrão mudando durante o transiente. É a
tabela de `results/RESUMO.md`, alinhada no tempo.

**Blocos de duração, não tiques instantâneos** (proposta, **não implementada** — ver §7.3).
Uma diluição consome 22 minutos simulados (4 de injeção + 18 de homogeneização), uma boração
18, uma barra 2. Isso não é detalhe de renderização: é fato físico, e explica por que o
controlador não corrige instantaneamente. Com blocos, R1 acende e ocupa 22 minutos da linha,
durante os quais mais nada acontece.

A v1 desenha tiques. O que ela ganhou de graça foi outra coisa: o `title` de cada tique diz o
minuto do disparo e quanto tempo falta até a amostra seguinte.

### 4.4 A timeline é arrastável

É o que separa demonstração de instrumento. Arrastar o cursor para o minuto 412 e o
instrumento, a regra explicada e a faixa voltam àquele instante.

Sai de graça: cada resposta de `POST /expert/{sid}/ciclo` traz estado e regras disparadas, e o
cliente guarda o vetor — ~1.440 entradas nos cenários 1–5. O frontend anterior morreu
exatamente aqui, mas porque guardava 700 mil pontos tentando animar o cenário 6.

### 4.5 O que foi cortado na v1, e por quê

Os cortes abaixo foram feitos sob a restrição de projeção. Com ela retirada, os dois
primeiros voltam a ser candidatos — ver §7.1.

| Cortado | Motivo |
|---|---|
| As 5 curvas (Pot, Tmed, ΔI, Banco D, Boro) | já existem como figura impressa em `results/graficos/`, com mais resolução e sem depender do serviço no ar. A tela não deve competir com o que o papel faz melhor — o que ela tem de próprio é tempo, causalidade e interação |
| O console (`saida_b64`) | parede de texto ilegível em projetor. Fica acessível para o minuto selecionado, se alguém quiser abrir |
| O log de chamadas HTTP | ninguém lê log num projetor. Se a arquitetura precisar aparecer, um diagrama `expert:8009 ⇄ reactor:8008` que pulsa a cada chamada se lê de longe e diz o mesmo |
| Os medidores que não são o da vez | §4.1 |

Dos quatro cortes, **três foram desfeitos**. O console existe **recolhido**, num `<details>`,
mostrando os bytes daquele minuto. A arquitetura aparece como o par `expert:8009 ⇄
reactor:8008` no topo, com o LED pulsando em verde e virando vermelho quando a chamada falha —
o diagrama que a própria tabela sugeriu, em vez do log. E as cinco curvas voltaram inteiras
(§7.2), porque viraram o instrumento. Só o quarto corte não se aplica mais: não há "medidor da
vez", há cinco painéis simultâneos.

### 4.6 A tela inteira, sem rolagem

Pedido do usuário ao testar: *"o ideal é a tela toda visível compactada sem precisar rolar"*.

Duas colunas: à esquerda o que compartilha o eixo do tempo — os cinco painéis e a faixa de
disparos —, à direita a regra. Empilhar os três não cabia numa janela de 900 px, e o primeiro
a sofrer era o painel, que é o instrumento.

A altura de cada painel **não sai da proporção do `viewBox`**: o `app.js` mede a caixa e
converte para unidades, e a escala mapeia largura e altura exatamente. Com `viewBox` de altura
fixa e `width:100%`, cinco painéis viravam ~1090 px e a rolagem voltava. Verificado em
1920×1200 (painéis de 140 px), 1680×1050 (92 px) e 1366×768 (51 px), redimensionando.

Três armadilhas que isso expôs, registradas porque voltam:

- `align-items:center` no grid do painel impede a célula de esticar, e então `height:100%` no
  SVG não resolve — ele volta a mandar na própria altura;
- a conversão precisa da largura do **SVG**, não a do contêiner: a coluna do rótulo fica fora
  dele, e usar a errada deixa uma faixa vazia em cada painel;
- `calc()` não multiplica porcentagem por comprimento — a expressão inteira vira inválida e o
  elemento vai para a borda da tela. O cursor da faixa passou a ser posicionado por medição.

O que ficou fino: as 11 regras que não disparam num cenário ganham linha de 9 px em vez de 13,
e o consequente virou `<details>`, como o console. As duas coisas continuam na tela.
---

## 5. A API que sustenta tudo

### 5.1 Um endpoint move a demonstração inteira

`POST /expert/{sid}/ciclo` avança um minuto e devolve:

| campo | uso na tela |
|---|---|
| `estado` | as 30 grandezas → as curvas dos cinco painéis, as fronteiras móveis e os valores substituídos |
| `disparadas` | ids das regras que dispararam, na ordem → faixa de disparos e regra explicada |
| `saida_b64` | bytes impressos naquele minuto → console recolhido |
| `ciclos`, `termino`, `pode_continuar` | controle da corrida |

Complementares: `GET /expert/regras` (a base inteira, uma vez, na partida) e
`GET /expert/{sid}/disparos` (contagem acumulada).

**O navegador fala com um serviço só, o expert, na porta 8009.** Nunca com o reactor.

### 5.2 CORS não é impedimento — é uma escolha de onde servir

CORS é regra do navegador: uma página carregada de um endereço só lê a resposta de outro
endereço se o servidor de destino permitir por cabeçalho. "Endereço" é protocolo + host +
porta — `localhost:8000` e `localhost:8009` já são diferentes.

| como a página é aberta | o `fetch` para `:8009` |
|---|---|
| `file:///…/index.html` | bloqueado |
| servida por um estático em outra porta | bloqueado |
| servida **pelo próprio expert**, em `localhost:8009/app` | funciona — não é cross-origin |

Duas saídas, ambas de três linhas: montar `StaticFiles` no `expert/main.py`, ou habilitar
`CORSMiddleware`. **Escolhida a primeira** (§7.1): a página sai de `localhost:8009/app`, é
mesma origem, e não há uma linha de CORS no projeto.

### 5.3 A partida — e duas armadilhas

`POST /expert/initialize` aceita 15 campos, **todos com padrão**, então `{}` funciona. Duas
coisas mordem:

**O padrão de `tmax` é 700000.** `{}` não roda o cenário 1 — roda o ciclo completo, 514 mil
minutos. Mandar `tmax` explícito sempre, mesmo quando coincide.

**`reactor_url` é um endereço que o navegador não alcança.** O padrão,
`http://reactor-simulator:8008`, só resolve dentro da rede do podman. Mas o navegador não
precisa dele — quem chama o reactor é o expert. **A saída é omitir o campo.** O frontend
anterior errou aí, com o endereço interno fixo no `app.js`.

### 5.4 Os 6 cenários

Vêm de `cenarios.json`, a fonte única (criada em 2026-09-06). O frontend faz `fetch` dele, ou
usa `scripts/cenarios.py --json N` no momento de gerar a página. Corpo da requisição:

```js
1: {tmax:1440}
2: {tmax:1440, transiente:"runback-bap",  t_transiente:10}
3: {tmax:1440, transiente:"runback-150",  t_transiente:10}
4: {tmax:1440, transiente:"rampa", alvo:650, taxa:1, t_transiente:10,
    pot_turbina:32, posicao_barra:144}
5: {tmax:1440, transiente:"rampa", alvo:32,  taxa:3, t_transiente:10}
6: {}
```

O cenário 6 (514 mil ciclos) fica fora da timeline: no máximo um modo "rodar até o fim e
mostrar o resumo", sem cursor.

### 5.5 A API diz *qual* regra disparou, não *com quê*

**Achado de 2026-09-06.** `disparadas` é uma lista de ids: `["R9", "R13"]`. Só isso.

Mas quando R1 dispara, o expert **decidiu uma vazão** — escolheu entre `v1`, `v2` e a rampa
`(-a*DeltaT)+b` conforme a faixa de ΔT em que o desvio de temperatura caiu. Esse número é
decisão de controle, e não efeito de planta: o §4 do `steps/03-regras-controle.md` classifica
a seleção de vazão como *"escolhe quanto diluir, não se diluir"*, e é por isso que ela ficou
do lado do expert na hora de cortar a fronteira.

O que a tela consegue hoje, e o que não consegue:

| | |
|---|---|
| qual regra disparou | sim, via `disparadas` |
| a **fórmula** do consequente | sim, via `GET /expert/regras` — as três faixas de R1, a saturação de R8 |
| **qual faixa venceu** e **quanto saiu** | **não** — 5,0047 lpm ou 19,84 lpm é invisível |

Isso morde exatamente o argumento central da tela. A regra tem duas metades — o antecedente
(*se*) e a parametrização do consequente (*quanto*) —, e a segunda é a que fica sem mostrar.

Para resolver, `disparadas` teria de deixar de ser `list[str]` e virar algo como:

```json
[{"id": "R1", "acao": "diluir",
  "parametros": {"vazao": 5.0047, "faixa": "DeltaT >= t1"}}]
```

**É mudança de API, não de frontend** — mexe em `expert/models.py` e `expert/motor.py`, e o
motor já tem esses valores na mão no momento em que atua. Decidir se entra como requisito.

Enquanto não entra, a tela **mostra a lacuna em vez de escondê-la**: quando a regra tem
consequente parametrizado, o painel lista as fórmulas todas — as três faixas de R1, os dois
ramos de R9 — com os valores do estado já substituídos, e diz, embaixo, que qual delas venceu
a resposta do ciclo não informa. É o mesmo tratamento dado à duração da ação no §7.3.

---

## 6. Restrições duras

### 6.1 O laço de controle não vai para o cliente

`POST /expert/{sid}/ciclo` já percorre as 19 regras na ordem do fonte, relendo o estado a cada
atuação. Se o frontend reimplementar isso, vira mais uma cópia da lógica de decisão.

Não é hipótese: aconteceu no projeto anterior, onde o laço existia em cinco lugares. O
comentário que ficou no `app.js` depois da remoção diz o porquê — *"qualquer divergência faria
a demonstração da defesa mostrar uma coisa e o capítulo de resultados relatar outra"*.

### 6.2 O frontend não calcula nada

Nenhum `DesvioDeltaI = DeltaI − AlvoDeltaI` em JavaScript, nenhum limite de inserção
recalculado, nenhuma conversão de unidade. Tudo o que aparece vem do campo correspondente do
`estado` — as 30 grandezas já incluem `DeltaT`, `DesvioDeltaI`, `LimiteInsercao` e `BD`,
justamente para isso.

Além de ser mais uma cópia (a da aritmética, desta vez), há um motivo específico: a aritmética
do modelo é de **32 bits emulada**, e o JavaScript só tem `double`. Um `DesvioDeltaI`
calculado em JS divergiria do que a regra usou para decidir, e a tela mostraria uma condição
"falsa" ao lado da regra acesa. É o tipo de defeito que só aparece na defesa.

### 6.3 Sem seletor de política de arbitragem

O frontend anterior tinha *Single-best*, *Group-Seq*, *Sequential-All*. Elas existiam porque
aquela base carregava `Priority` e `confidence` — campos que **não existem em nenhuma fonte**
(nem no C, nem no Apêndice A, nem no B). Com pontuação inventada, é preciso decidir o que
fazer com ela, e cada resposta virou uma política. Das três, só a `Sequential-All` reproduzia
o simulador do Igor.

A nossa base não tem esses campos: cada regra carrega condição, consequente, linha de origem e
posição na ordem. **Não há com que arbitrar** — a estratégia não é escolha entre três, é a
única que os dados sustentam.

Existe uma pergunta de pesquisa legítima ali ("um motor clássico controla melhor?"), mas é
outra tese: exige critério de desempenho em vez de fidelidade byte a byte, e as curvas da
dissertação deixam de servir de referência.

---

## 7. Questões em aberto

### 7.1 Onde a página é servida — **decidido**

**Servida pelo próprio expert, em `/app`.** A demo fala com um serviço só, então mesma origem
resolve CORS de graça, e sobe tudo com `podman-compose up -d` — sem um segundo processo para
lembrar de ligar.

Custou o que se previa, mais uma linha: `StaticFiles` no `expert/main.py`, duas montagens na
compose, e uma rota para `cenarios.json`, que não pôde entrar por montagem dentro de
`static/` nem por symlink (§3.1). Foi mudança em serviço, autorizada, e a suíte do expert
continua passando.

O andaime que serviu para testar antes da decisão — um servidor estático com proxy para a
`:8009`, fora do repositório — não faz mais falta e não foi versionado.

### 7.2 As cinco curvas voltam?

Foram cortadas por falta de espaço numa projeção. Sem essa restrição, cabem — e para explorar
uma corrida elas ajudam. O contra-argumento continua de pé: as mesmas curvas já existem como
figura em `results/graficos/`, com mais resolução e sem depender do serviço no ar.

**Resolvido: as cinco voltaram, e são o próprio instrumento** (§4.1). O meio-termo — uma faixa
fina de contexto com a curva da grandeza selecionada — durou uma versão e foi absorvido: se
cada grandeza já é uma curva no tempo, não há o que pôr embaixo.

O contra-argumento caiu por conta própria. A tela não compete mais com a figura impressa
porque não desenha a mesma coisa: `results/graficos/` tem as curvas; a tela tem as curvas
**mais** as regiões das regras, as fronteiras móveis de `LI` e `BD`, o cursor e a faixa de
disparos alinhada no mesmo eixo. O que o papel faz melhor — resolução, independência do
serviço — continua sendo dele.

### 7.3 Tiques ou blocos de duração na faixa de disparos

A v1 desenha um tique por disparo. Blocos seriam mais fiéis: uma diluição consome 22 minutos
simulados (4 de injeção + 18 de homogeneização), uma boração 18, uma barra 2 — o §5.6 do
`steps/03-regras-controle.md` registra isso, e é o que explica os saltos no eixo do tempo.

Duas saídas foram consideradas na implementação, e nenhuma serviu:

- **escrever 22/18/2 no cliente** copia para o frontend um pedaço do modelo, que é o que o
  §6.2 proíbe;
- **medir pelo salto do relógio** — tentado, e **errado**. O intervalo até a amostra seguinte
  não é a duração da ação: em regime o simulador só volta a imprimir a cada ~47 minutos, e um
  movimento de barra de 2 minutos virava um bloco de 47.

Fica em aberto, e a saída limpa é a mesma do §5.5: a resposta do ciclo dizer quanto a ação
consumiu. O motor tem esse número na mão.

> **Nota de procedência.** Ao conferir isso o §5.6 do `steps/03-regras-controle.md` foi
> encontrado **errado** e corrigido: dizia "diluição avança `tempodilute` minutos; boração e
> movimentação de barra, 2 minutos cada". A homogeneização de 18 minutos não estava contada, e
> o laço do `main` avança 1 minuto por ciclo, que o texto negava. Os números deste PRD estavam
> certos; os do passo 3, não.

### 7.4 O cenário 6 — **fora, e visivelmente fora**

514 mil ciclos não cabem no vetor da timeline nem na paciência de quem espera. Fora da v1.

Na tela ele aparece no seletor, **desabilitado**, com o motivo escrito ao lado: o `tmax` dele é
nulo em `cenarios.json`, e é esse nulo que o desabilita — não uma lista de exceções no código.
Some sozinho se um dia ganhar horizonte.

Alternativa, ainda em aberto: um modo "rodar até o fim e mostrar o resumo", sem cursor.

### 7.5 Sobreposição com as curvas da dissertação

Há **17 CSVs** em `reference/`, extraídos das figuras 6.1 a 6.17 por
`scripts/extrai_curvas_dissertacao.py`. A tela poderia desenhar a corrida ao vivo sobre a
curva publicada, com o erro corrente ao lado.

O que isso acrescenta é uma afirmação **diferente e independente** da atual. Hoje a tela
provaria *"o controlador decide assim, e a decisão é este texto do fonte C"*. Com a
sobreposição, provaria também *"e o resultado bate com o que a dissertação reportou"*.

Contra: reacende a discussão das cinco curvas (§7.2), e o `scripts/compara_corrida.py` já faz
esse confronto em texto, com mais rigor. Talvez baste um selo por cenário — *"erro máx tmed
0,13 °C"* — em vez de sobrepor curva nenhuma.

Vale só para os 6 cenários: uma corrida com parâmetros arbitrários (§7.6) não tem referência.

### 7.6 Parâmetros de partida editáveis — **feito**

R11, R12, R15 e R17 não acendem em nenhum dos 6 cenários — só em configurações de borda. Os
**sete valores de partida mais o horizonte** ficaram editáveis: uma linha compacta sob o
cabeçalho mostra os sete sempre, na ordem dos prompts do simulador, e o ⚙ abre o editor.

O horizonte entrou junto porque as bordas usam 600 e 400, não 1440. `transiente`, `alvo` e
`taxa` continuam vindo do cenário.

**Os quatro atalhos de borda não foram inventados.** Os valores são os de
`scripts/verifica_expert.sh:94-98` e as contagens esperadas são a tabela do §8 de
`steps/05-servico-expert.md` — o que permite algo que a §7.5 dizia impossível numa corrida
arbitrária: **conferir**. Rodando `D=170, ΔI=−1` a tela mostra `R11 527 · R12 1 · R15 2`,
idêntico ao §8, e o selo diz "confere com o §8". Fora das bordas o selo diz **sem
referência**, que é honesto.

**A pergunta que esta seção deixava aberta — "achado ou artefato?" — tem resposta para um dos
casos.** A configuração que alcança R17 (32 MW, D=144, ΔI=12) cai sobre a única divergência
conhecida entre o porte e o original: o ramo `if (Pbase<0)` zera `Pbase` no porte e zerava
`Ptopo` no original, e com `Pot=4,92 %` as duas versões divergem por completo
(`steps/01-porte-linux-simulador.md:319-326`). É **artefato conhecido**, e o atalho diz isso
antes de rodar.

**Faixa: avisar, nunca travar.** Nem a API nem o C impõem faixa a esses campos — a de "32 a
650 MW" é texto do prompt. O formulário faz o mesmo: aceita qualquer número, e anota o que
muda no modelo com a linha do fonte (boro acima de 1894 satura `v1`; barra abaixo de 100 muda
o peso de 6,5 para 20 pcm/passo; ΔI > 2·Pot leva ao ramo divergente; `t2 ≥ t1` esvazia o ramo
do meio da rampa de vazão).

**Uma exceção, e não é faixa:** `tempodilute` ganhou `gt=0` nos dois serviços, pelo mesmo
motivo que `tmax` já tinha — os dois movem o relógio, e um relógio que não avança faz a
corrida nunca terminar. Nenhum dos outros cinco ganhou restrição: um `ge`/`le` inventado
viraria contrato que o artefato original não tem, que é o erro do `Priority`/`confidence` da
§6.3.

### 7.8 Teto de amostras no cliente

Com o horizonte editável, um `tmax` de 700000 pede 514 mil chamadas — exatamente a morte do
frontend anterior que a §9 registra. O laço de `roda()` não tinha teto nenhum.

Agora para em **20 mil amostras** e **diz que parou**, com o minuto alcançado. Medido: `tmax`
700000 parou em t=57098 sem travar a página — mas levou 142 segundos, o que revelou o defeito
seguinte: não havia como interromper. O botão Rodar vira **■ Parar** durante a corrida, e o
selo passa a dizer "interrompida", avisando que as contagens estão incompletas.

### 7.7 Acúmulo de arquivos

Cada sessão aberta pela tela grava `runs/Modelagem_Reator_<id>.txt`. Apertar "Rodar" vinte
vezes deixa vinte arquivos. Não é problema de correção, mas é o mesmo acúmulo já discutido.

O que a implementação já faz: **encerra a sessão** (`DELETE /expert/{sid}`) ao fim de cada
corrida, inclusive depois de erro, porque o serviço guarda no máximo 32 e vinte cliques
esgotariam o registro. O arquivo em `runs/` continua lá — encerrar a sessão não o apaga, e
apagá-lo seria decisão do serviço, não da tela.

---

## 8. Stack

**HTML + CSS custom properties + ES modules. Sem build, sem npm, sem CDN.**

Decorre do §2.3 (zero requisições externas), mas há também o argumento de coerência: a
disciplina desta tese é reprodutibilidade — versões fixadas, contêineres, uma linha de `gcc`
documentada, aceitação byte a byte. Um toolchain npm traz centenas de transitivas e um passo
de build; daqui a três anos `npm install` pode não resolver.

Sobre Tailwind há evidência empírica no próprio projeto: o frontend anterior carregava
`cdn.tailwindcss.com` e **nenhuma das 53 classes do HTML era utility do Tailwind** — eram
todas nomes semânticos próprios, definidos à mão em 484 linhas de CSS. Eram ~400 KB de
compilador JIT no navegador para não fazer nada.

Do TypeScript dá para aproveitar só a parte boa: o FastAPI publica `/openapi.json`, e há
checagem de tipos com JSDoc + `tsc --noEmit`, sem bundler.

Gráficos: SVG à mão. A geometria dos painéis já existe em `scripts/gera_graficos.py`, e um
`polyline` com `viewBox` é ~40 linhas. Zero dependência, escala nítido em projetor.

---

## 9. O que o frontend anterior ensinou

Prior art em `~/1uvr3z/Mestrado/mestrado_old/static/` — 1.385 linhas (HTML 192, JS 709,
CSS 484), vanilla, sem build. O PRD dele dizia literalmente *"Sem framework, sem build, sem
node_modules"*.

| Lição | O que fazer diferente |
|---|---|
| Tailwind CDN carregado e 100% inutilizado | não carregar (§2.3) |
| `Plotly.newPlot()` redesenhando tudo a cada quadro, arrays sem limite (700 mil pontos/série no cenário 6) | cenário 6 fora da timeline; ~1.440 pontos guardados |
| O laço de controle no browser, quinta cópia | §6.1 |
| Erro do expert tratado como "sem ação" — a simulação seguia com o controle desligado, sem aviso | §2.4 |
| Grupo da regra inferido por *substring* do texto de raciocínio; 7 regras caíam no grupo errado ou sumiam | usar o campo `bloco` que a API já devolve |
| Política fixada na criação da sessão, mas o seletor sugeria troca ao vivo | não aplicável (§6.3) |

Também existem três capturas de tela em `mestrado_old/docs/figuras/` mostrando a interface
funcionando — nenhum documento do repositório as referencia.

---

## 10. Histórico deste documento

- **2026-09-06, sétima revisão** — os **sete parâmetros de partida** ficaram visíveis e
  editáveis (§7.6), com quatro atalhos de borda tirados de `scripts/verifica_expert.sh` e as
  contagens esperadas do §8 de `steps/05` — o que permitiu conferir uma corrida de borda regra
  por regra (`R11 527 · R12 1 · R15 2`, idêntico ao documento). A tela passou a caber na
  janela **sem rolagem** (§4.6), em duas colunas. Entraram o teto de amostras e o botão Parar
  (§7.8), e duas mudanças em serviço: `no-cache` em `/app` e `gt=0` em `tempodilute` (§3.1).
  Ao preparar isso, dois erros foram corrigidos no `steps/05-servico-expert.md` §8: a prosa
  dizia "12 das 19 regras" quando a própria tabela dá 15, e omitia **R15** da lista de
  inalcançáveis. Ficam em aberto §5.5, §7.3, §7.5 e o fundo claro/escuro.
- **2026-09-06, sexta revisão** — o usuário rejeitou os medidores de agulha (*"ninguém entende
  nada. Pior que os gráficos em results/graficos/"*), e eles foram substituídos por **cinco
  painéis no tempo** (§4.1). Isso resolveu a §7.2 pelo lado oposto ao da revisão anterior: as
  cinco curvas voltaram inteiras, e são o próprio instrumento. Entrou a §4.1.1, a gramática de
  regiões que lê a condição como árvore — resposta a um achado que vale além do desenho: a
  versão anterior pintava as comparações como lista e, nas nove regras que têm `||`, afirmava
  algo falso. Ficaram registrados o desalinhamento dos dois eixos do tempo e dois tropeços de
  navegador (§3.1). Continuam em aberto §5.5, §7.3, §7.5, §7.6 e o fundo claro/escuro.
- **2026-09-06, quinta revisão** — **a tela foi implementada, com autorização**, e está
  servida pelo próprio expert em `/app`. Isso fechou quatro decisões: onde servir (§7.1),
  cinco medidores simultâneos (§4.1), o meio-termo da curva de contexto (§7.2) e o cenário 6
  desabilitado pelo próprio `cenarios.json` (§7.4). A §3.1 deixou de dizer "nada implementado"
  e passou a registrar o que existe, como foi verificado — contagens de disparo idênticas às
  de `results/API/` nos cenários 3 e 5, e a falha visível testada com o reactor parado — e
  três achados novos: duração de ação não se deduz do salto do relógio (§7.3), montar arquivo
  dentro de bind-mount suja o repositório, e `StaticFiles` não segue symlink para fora. Ficam
  em aberto §5.5, §7.3, §7.5, §7.6 e o fundo claro/escuro.
- **2026-09-06, primeira versão** — stack, conteúdo da tela e armadilhas da API.
- **2026-09-06, quarta revisão** — a implementação não autorizada foi revertida e a tabela de
  decisões deixou de marcar itens como "implementado". Entraram três assuntos novos: o achado
  de que a API não reporta os parâmetros da ação (§5.5), a sobreposição com as curvas da
  dissertação (§7.5), e os parâmetros de partida editáveis (§7.6), que substituem a ideia de um
  cenário de borda codificado.
- **2026-09-06, terceira revisão** — o alvo *projeção numa defesa* foi **retirado** pelo
  usuário; a §2 foi reescrita e as decisões que dependiam dela foram reclassificadas (zero-rede
  e falha-visível sobreviveram por outros motivos; o corte de conteúdo e o "um medidor por vez"
  caíram). A primeira versão foi implementada — §3.1 registra o que existe, e três decisões que
  estavam em aberto foram tomadas durante a implementação: onde servir, claro/escuro, e quatro
  medidores simultâneos.
- **2026-09-06, segunda revisão** — o alvo passou a ser explicitamente *projeção numa defesa*
  (§2). Isso fechou cinco decisões (rodar-e-interrogar, zero rede, falha visível, stack, e o
  corte das curvas/console/log) e reorganizou a §4 em torno de três elementos grandes em vez de
  um painel denso. Entrou a restrição §6.2 (o frontend não calcula nada). O CORS foi
  reclassificado de "problema" para "escolha de onde servir" (§5.2) — eu tinha exagerado o tom.
  A fonte única dos cenários saiu de "em aberto" para "resolvido": `cenarios.json` existe.
