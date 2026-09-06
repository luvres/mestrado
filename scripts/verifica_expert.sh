#!/usr/bin/env bash
# Verifica os DOIS bracos do sistema especialista contra o porte fiel.
#
#   A) simulador.py                    o monolito, provado identico ao C (Passo 2)
#   B) scripts/validate_c_vs_python.py o braco PROCEDURAL: 19 blocos `if` transcritos
#   C) scripts/validate_expert.py      o braco DECLARATIVO: expert/regras.py + motor.py
#
# Os tres dirigem a MESMA planta (reactor/physics.py). Se a base de regras disser
# exatamente o que o fonte diz, e se o motor aplicar a estrategia de resolucao de
# conflito certa (prioridade = ordem, disparo multiplo, estado relido a cada
# regra), as tres corridas produzem os mesmos bytes.
#
# O que cada divergencia significaria:
#   B != A  a transcricao procedural errou um `if`
#   C != A  a base declarativa ou o motor erraram
#   C != B  os dois bracos discordam entre si — o caso mais informativo, porque
#           localiza o erro no que os distingue: a representacao das regras
#
# Criterio: byte a byte no arquivo de amostras E na saida padrao inteira.
#
# Uso: bash scripts/verifica_expert.sh [--rapido]
#      --rapido pula o cenario 6 (ciclo completo).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RAPIDO=0
[ "${1:-}" = "--rapido" ] && RAPIDO=1

falhas=0
mkdir -p "$TMP/a" "$TMP/b" "$TMP/c" "$TMP/cap"

# compara <rotulo> <7 valores> <env> <flags...>
compara() {
  local rotulo=$1 entrada=$2 amb=$3; shift 3
  echo "$entrada" | tr ' ' '\n' > "$TMP/entrada.txt"

  ( cd "$TMP/a" && rm -f Modelagem_Reator_py.txt \
    && env $amb python3 "$RAIZ/simulador.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )
  ( cd "$TMP/b" && rm -f Modelagem_Reator_api.txt \
    && env $amb python3 "$RAIZ/scripts/validate_c_vs_python.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )
  ( cd "$TMP/c" && rm -f Modelagem_Reator_expert.txt \
    && env $amb python3 "$RAIZ/scripts/validate_expert.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )
  ( cd "$TMP/cap" && rm -f Modelagem_Reator_expert.txt \
    && env $amb python3 "$RAIZ/scripts/validate_expert.py" --capturar "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )

  local n proc decl cap
  n=$(grep -c '^[0-9]' "$TMP/a/Modelagem_Reator_py.txt" 2>/dev/null)

  if cmp -s "$TMP/a/Modelagem_Reator_py.txt" "$TMP/b/Modelagem_Reator_api.txt" \
     && cmp -s "$TMP/a/sha.txt" "$TMP/b/sha.txt"; then
    proc="procedural ok"
  else
    proc="PROCEDURAL DIVERGE"; falhas=$((falhas+1))
  fi

  if cmp -s "$TMP/a/Modelagem_Reator_py.txt" "$TMP/c/Modelagem_Reator_expert.txt"; then
    if cmp -s "$TMP/a/sha.txt" "$TMP/c/sha.txt"; then
      decl="declarativo ok"
    else
      decl="DECL: STDOUT"; falhas=$((falhas+1))
      echo "   mono: $(cat "$TMP/a/sha.txt")"
      echo "   decl: $(cat "$TMP/c/sha.txt")"
    fi
  else
    decl="DECL: DADOS"; falhas=$((falhas+1))
    diff "$TMP/a/Modelagem_Reator_py.txt" "$TMP/c/Modelagem_Reator_expert.txt" | head -6
  fi

  if cmp -s "$TMP/a/sha.txt" "$TMP/cap/sha.txt"; then cap="captura ok"
  else cap="CAPTURA DIVERGE"; falhas=$((falhas+1)); fi

  printf '  %-44s %8s amostras   %-20s %-16s %s\n' "$rotulo" "$n" "$proc" "$decl" "$cap"
}

PADRAO="650 1800 210 4 -0.3 -0.8 0"

echo "== os cenarios da dissertacao =="
compara "1 - operacao normal, 1 dia"      "$PADRAO"                    IGNORA=1 --tmax=1440
compara "2 - runback bomba alimentacao"   "$PADRAO"                    IGNORA=1 --transiente=runback-bap --t-transiente=10 --tmax=1440
compara "3 - runback manual 150 MW"       "$PADRAO"                    IGNORA=1 --transiente=runback-150 --t-transiente=10 --tmax=1440
compara "4 - rampa 32->650 MW a 1 MW/min" "32 1800 144 4 -0.3 -0.8 0"  IGNORA=1 --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440
compara "5 - rampa 650->32 MW a 3 MW/min" "$PADRAO"                    IGNORA=1 --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440
if [ "$RAPIDO" = 0 ]; then
  compara "6 - ciclo completo (R19)"      "$PADRAO"                    IGNORA=1
else
  echo "  6 - ciclo completo                           (pulado por --rapido)"
fi

echo
echo "== bordas: ramo Pbase<0, alarmes e boracao por limite de insercao =="
compara "Pbase=0 (porte)"                      "32 1800 144 4 -0.3 -0.8 12"  IGNORA=1       --tmax=400
compara "Ptopo=0 (WIN_ORIGINAL)"               "32 1800 144 4 -0.3 -0.8 12"  WIN_ORIGINAL=1 --tmax=400
compara "banco D=178, DeltaI=-1 (R11)"         "650 1800 178 4 -0.3 -0.8 -1" IGNORA=1       --tmax=600
compara "banco D=170, DeltaI=-1 (R11 e R12)"   "650 1800 170 4 -0.3 -0.8 -1" IGNORA=1       --tmax=600
compara "banco D=150, DeltaI=-4 (R12 emerg.)"  "650 1800 150 4 -0.3 -0.8 -4" IGNORA=1       --tmax=600

echo
if [ "$falhas" = 0 ]; then
  echo "Os dois bracos concordam com o porte fiel, byte a byte."
  exit 0
fi
echo "FALHOU: $falhas divergencia(s)."
exit 1
