#!/usr/bin/env bash
# Roda os 6 cenarios nos 3 niveis e guarda tudo em results/{C,python,API}/.
#
#   C       ./simulador                          (binario do porte, gcc)
#   python  simulador.py                         (porte fiel, Passo 2)
#   API     reactor:8008 + expert:8009 por HTTP  (Passos 4 e 5)
#
# Para cada cenario e cada nivel guarda DOIS arquivos:
#   cenarioN.txt              as amostras (o "Modelagem_Reator.txt" daquela corrida)
#   cenarioN-comparacao.txt   a saida de scripts/compara_corrida.py contra as
#                             curvas extraidas da dissertacao
#
# E no fim escreve results/RESUMO.md com a contagem de amostras, o SHA-256 de
# cada arquivo e a verificacao de que os tres niveis produziram os MESMOS bytes.
#
# Pre-requisitos:
#   gcc --std=gnu89 -Wall V8_Reatividade_SimuladorIgor_linux.c -o simulador -lm
#   podman-compose up -d
#
# Uso: bash scripts/gera_resultados.sh [--rapido]
#      --rapido pula o cenario 6 (ciclo completo: ~50 s em C, ~45 s em Python,
#      ~12 min pela API, e ~45 MB de amostras por nivel).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ" || exit 1
DEST="$RAIZ/results"
EXPERT=${EXPERT:-http://localhost:8009}
REATOR_INTERNO=${REATOR_INTERNO:-http://reactor-simulator:8008}
RAPIDO=0
[ "${1:-}" = "--rapido" ] && RAPIDO=1

mkdir -p "$DEST/C" "$DEST/python" "$DEST/API"

# --- os 6 cenarios ---------------------------------------------------------
# Os valores NAO ficam aqui. cenarios.json e a fonte unica, e scripts/cenarios.py
# traduz para as tres sintaxes que este script precisa: os 7 valores do stdin, as
# flags de linha de comando, e o corpo da API. Antes isto era um `case` com os
# numeros repetidos, e havia outras copias em compara_niveis.py e script.txt.
CEN=(python3 "$RAIZ/scripts/cenarios.py")

cenario() {          # cenario <n> -> define ENTRADA, FLAGS, JSON, DESCRICAO
  ENTRADA=$("${CEN[@]}" --entrada "$1")   || exit 1
  FLAGS=$("${CEN[@]}"   --flags "$1")     || exit 1
  JSON=$("${CEN[@]}"    --json "$1")      || exit 1
  DESCRICAO=$("${CEN[@]}" --descricao "$1") || exit 1
}

ULTIMO=6
[ "$RAPIDO" = 1 ] && ULTIMO=5

falhas=0

for n in $(seq 1 $ULTIMO); do
  cenario $n
  printf '\n== cenario %d — %s ==\n' "$n" "$DESCRICAO"
  echo "$ENTRADA" | tr ' ' '\n' > /tmp/entrada_cenario.$$

  # ---------------- C ----------------
  rm -f Modelagem_Reator.txt
  ./simulador $FLAGS < /tmp/entrada_cenario.$$ > /dev/null
  mv Modelagem_Reator.txt "$DEST/C/cenario$n.txt"
  python3 scripts/compara_corrida.py "$DEST/C/cenario$n.txt" $n \
    > "$DEST/C/cenario$n-comparacao.txt" 2>&1
  printf '  %-8s %8s amostras\n' "C" "$(grep -c '^[0-9]' "$DEST/C/cenario$n.txt")"

  # ---------------- Python ----------------
  rm -f Modelagem_Reator_py.txt
  python3 simulador.py $FLAGS < /tmp/entrada_cenario.$$ > /dev/null
  mv Modelagem_Reator_py.txt "$DEST/python/cenario$n.txt"
  python3 scripts/compara_corrida.py "$DEST/python/cenario$n.txt" $n \
    > "$DEST/python/cenario$n-comparacao.txt" 2>&1
  printf '  %-8s %8s amostras\n' "python" "$(grep -c '^[0-9]' "$DEST/python/cenario$n.txt")"

  # ---------------- API ----------------
  # Quem grava as amostras e o conteiner do reactor, em /runs (= ./runs do
  # host). Por isso a corrida escreve la e o arquivo e movido depois.
  rm -f "runs/Modelagem_Reator_res$n.txt"
  SID=$(curl -s -X POST "$EXPERT/expert/initialize" \
        -H 'Content-Type: application/json' \
        -d "{\"reactor_url\":\"$REATOR_INTERNO\", $JSON,
             \"arquivo\":\"Modelagem_Reator_res$n.txt\"}" | jq -r .sessao)
  if [ -z "$SID" ] || [ "$SID" = "null" ]; then
    echo "  API      FALHOU: nao abriu sessao (os servicos estao no ar?)"
    falhas=$((falhas+1)); continue
  fi
  # O servico limita cada resposta; repete-se enquanto houver corrida.
  while [ "$(curl -s -X POST "$EXPERT/expert/$SID/executar" \
               -H 'Content-Type: application/json' -d '{}' | jq -r .pode_continuar)" = "true" ]; do
    :
  done
  curl -s "$EXPERT/expert/$SID/disparos" | jq -c '{ciclos, disparos, nunca_dispararam}' \
    > "$DEST/API/cenario$n-disparos.json"
  curl -s -X DELETE "$EXPERT/expert/$SID" > /dev/null
  mv "runs/Modelagem_Reator_res$n.txt" "$DEST/API/cenario$n.txt"
  python3 scripts/compara_corrida.py "$DEST/API/cenario$n.txt" $n \
    > "$DEST/API/cenario$n-comparacao.txt" 2>&1
  printf '  %-8s %8s amostras\n' "API" "$(grep -c '^[0-9]' "$DEST/API/cenario$n.txt")"

  # ---------------- os tres batem? ----------------
  if cmp -s "$DEST/C/cenario$n.txt" "$DEST/python/cenario$n.txt" \
     && cmp -s "$DEST/C/cenario$n.txt" "$DEST/API/cenario$n.txt"; then
    echo "  -> C = python = API, byte a byte"
  else
    echo "  -> DIVERGEM"; falhas=$((falhas+1))
  fi
done
rm -f /tmp/entrada_cenario.$$

# --- RESUMO.md ---------------------------------------------------------------
{
  echo "# Resultados — 6 cenários × 3 níveis"
  echo
  echo "Gerado por \`scripts/gera_resultados.sh\` em $(date '+%Y-%m-%d %H:%M')."
  echo
  echo "Os três níveis simulam o mesmo modelo por caminhos diferentes:"
  echo
  echo '| nível | o que é |'
  echo '|---|---|'
  echo '| `C` | `./simulador`, compilado de `V8_Reatividade_SimuladorIgor_linux.c` |'
  echo '| `python` | `simulador.py`, o porte fiel do Passo 2 |'
  echo '| `API` | `reactor:8008` (física) + `expert:8009` (as 19 regras), por HTTP |'
  echo
  echo "Cada pasta tem, por cenário: \`cenarioN.txt\` (as amostras),"
  echo "\`cenarioN-comparacao.txt\` (confronto com as curvas da dissertação) e, só na API,"
  echo "\`cenarioN-disparos.json\` (quantas vezes cada uma das 19 regras disparou)."
  echo
  echo '## Identidade entre os níveis'
  echo
  echo '| cenário | descrição | amostras | C = python = API | SHA-256 |'
  echo '|---|---|--:|---|---|'
  for n in $(seq 1 $ULTIMO); do
    a="$DEST/C/cenario$n.txt"
    [ -f "$a" ] || continue
    amostras=$(grep -c '^[0-9]' "$a")
    sha=$(sha256sum "$a" | cut -c1-16)
    if cmp -s "$a" "$DEST/python/cenario$n.txt" && cmp -s "$a" "$DEST/API/cenario$n.txt"; then
      veredito='**idênticos**'
    else
      veredito='DIVERGEM'
    fi
    echo "| $n | $("${CEN[@]}" --descricao $n) | $amostras | $veredito | \`$sha…\` |"
  done
  echo
  echo '## Regras exercitadas por cenário'
  echo
  echo 'Extraído de `API/cenarioN-disparos.json` — só a API sabe isso, porque só ela'
  echo 'separa as regras da física.'
  echo
  echo '| cenário | regras que dispararam |'
  echo '|---|---|'
  for n in $(seq 1 $ULTIMO); do
    d="$DEST/API/cenario$n-disparos.json"
    [ -f "$d" ] || continue
    echo "| $n | \`$(jq -c '.disparos' "$d")\` |"
  done
  echo
  echo '## Como regerar'
  echo
  echo '```sh'
  echo 'gcc --std=gnu89 -Wall V8_Reatividade_SimuladorIgor_linux.c -o simulador -lm'
  echo 'podman-compose up -d'
  echo 'bash scripts/gera_resultados.sh          # --rapido pula o cenário 6'
  echo '```'
} > "$DEST/RESUMO.md"

echo
if [ "$falhas" = 0 ]; then
  echo "Pronto. $ULTIMO cenarios x 3 niveis em results/, e results/RESUMO.md."
  exit 0
fi
echo "FALHOU: $falhas problema(s)."
exit 1
