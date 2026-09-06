#!/usr/bin/env bash
# Verifica que a SEPARACAO fisica/regras nao mudou nada.
#
# Compara duas execucoes:
#   A) simulador.py                      — o porte fiel, monolitico (Passo 2)
#   B) reactor/physics.py  +  scripts/validate_c_vs_python.py
#      (a planta, sem nenhuma regra) dirigida pelo braco procedural (as 19 regras)
#
# O criterio e o mesmo do Passo 2, byte a byte em dois artefatos independentes:
# o arquivo de amostras e a saida padrao inteira (por SHA-256 — no cenario 6 ela
# passa de 400 MB).
#
# Por que isso prova que a fronteira esta certa: se um `if` de decisao tivesse
# ficado dentro da planta, ele dispararia duas vezes (uma na planta, outra no
# braco) ou nenhuma; se um efeito tivesse vindo junto com uma regra, o estado
# divergiria no ciclo seguinte. Qualquer um dos dois desloca um evento de
# diluicao, e a comparacao acusa.
#
# A saida padrao e comparada nos DOIS caminhos do servico:
#   direto     — printf escreve no stdout, como no monolito
#   --capturar — printf escreve no buffer que a API devolve em cada resposta,
#                remontado no fim. E o caminho que o HTTP vai usar.
#
# Uso: bash scripts/verifica_fronteira_reactor.sh [--rapido]
#      --rapido pula o cenario 6 (ciclo completo).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RAPIDO=0
[ "${1:-}" = "--rapido" ] && RAPIDO=1

SAIDA_MONO="Modelagem_Reator_py.txt"
SAIDA_SEP="Modelagem_Reator_api.txt"

falhas=0
mkdir -p "$TMP/mono" "$TMP/sep" "$TMP/cap"

# compara <rotulo> <7 valores> <env> <flags...>
compara() {
  local rotulo=$1 entrada=$2 amb=$3; shift 3
  echo "$entrada" | tr ' ' '\n' > "$TMP/entrada.txt"

  ( cd "$TMP/mono" && rm -f "$SAIDA_MONO" \
    && env $amb python3 "$RAIZ/simulador.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )
  ( cd "$TMP/sep"  && rm -f "$SAIDA_SEP" \
    && env $amb python3 "$RAIZ/scripts/validate_c_vs_python.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )
  ( cd "$TMP/cap"  && rm -f "$SAIDA_SEP" \
    && env $amb python3 "$RAIZ/scripts/validate_c_vs_python.py" --capturar "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )

  local n dados stdout captura
  n=$(grep -c '^[0-9]' "$TMP/mono/$SAIDA_MONO" 2>/dev/null)
  if cmp -s "$TMP/mono/$SAIDA_MONO" "$TMP/sep/$SAIDA_SEP"; then
    dados="dados ok"
  else
    dados="DADOS DIVERGEM"; falhas=$((falhas+1))
    diff "$TMP/mono/$SAIDA_MONO" "$TMP/sep/$SAIDA_SEP" | head -6
  fi
  if cmp -s "$TMP/mono/sha.txt" "$TMP/sep/sha.txt"; then
    stdout="stdout ok"
  else
    stdout="STDOUT DIVERGE"; falhas=$((falhas+1))
    echo "   mono: $(cat "$TMP/mono/sha.txt")"
    echo "   sep : $(cat "$TMP/sep/sha.txt")"
  fi
  if cmp -s "$TMP/mono/sha.txt" "$TMP/cap/sha.txt"; then
    captura="captura ok"
  else
    captura="CAPTURA DIVERGE"; falhas=$((falhas+1))
  fi
  printf '  %-46s %8s amostras   %-15s %-15s %s\n' \
         "$rotulo" "$n" "$dados" "$stdout" "$captura"
}

PADRAO="650 1800 210 4 -0.3 -0.8 0"

echo "== os 6 cenarios da dissertacao (Tabelas 6.1 e 6.2) =="
compara "1 - operacao normal, 1 dia"      "$PADRAO"                    IGNORA=1 --tmax=1440
compara "2 - runback bomba alimentacao"   "$PADRAO"                    IGNORA=1 --transiente=runback-bap --t-transiente=10 --tmax=1440
compara "3 - runback manual 150 MW"       "$PADRAO"                    IGNORA=1 --transiente=runback-150 --t-transiente=10 --tmax=1440
compara "4 - rampa 32->650 MW a 1 MW/min" "32 1800 144 4 -0.3 -0.8 0"  IGNORA=1 --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440
compara "5 - rampa 650->32 MW a 3 MW/min" "$PADRAO"                    IGNORA=1 --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440
if [ "$RAPIDO" = 0 ]; then
  compara "6 - ciclo completo ate Cboro<8" "$PADRAO"                   IGNORA=1
else
  echo "  6 - ciclo completo                             (pulado por --rapido)"
fi

echo
echo "== ramo Pbase<0: as duas semanticas, que divergem entre si =="
compara "Pbase=0 (porte)"                 "32 1800 144 4 -0.3 -0.8 12" IGNORA=1       --tmax=400
compara "Ptopo=0 (WIN_ORIGINAL)"          "32 1800 144 4 -0.3 -0.8 12" WIN_ORIGINAL=1 --tmax=400

echo
echo "== boracao por limite de insercao (R11 e R12; nenhum cenario da dissertacao alcanca) =="
compara "banco D=178, DeltaI=-1 (normal)"      "650 1800 178 4 -0.3 -0.8 -1" IGNORA=1 --tmax=600
compara "banco D=170, DeltaI=-1 (normal+emg)"  "650 1800 170 4 -0.3 -0.8 -1" IGNORA=1 --tmax=600
compara "banco D=150, DeltaI=-4 (emergencia)"  "650 1800 150 4 -0.3 -0.8 -4" IGNORA=1 --tmax=600

echo
if [ "$falhas" = 0 ]; then
  echo "Fronteira confirmada: a separacao nao mudou nenhum byte."
  exit 0
fi
echo "FALHOU: $falhas divergencia(s)."
exit 1
