#!/usr/bin/env bash
# Verifica que simulador.py produz saída IDÊNTICA ao porte em C.
#
# O critério é byte a byte, em DOIS artefatos independentes:
#   - Modelagem_Reator.txt (as amostras do modelo);
#   - a saída padrão inteira, que no cenário 6 tem 446 MB (comparada por SHA-256).
#
# Isso é possível porque simulador.py emula a semântica de armazenamento do C:
# `float` de 32 bits arredondado a cada operação, `double` nas variáveis do Xe,
# e conversão float->int truncando para zero. Uma aritmética só em `double`
# NÃO passaria neste teste — o modelo decide por comparações de ponto flutuante,
# e ±0,001 desloca um evento de diluição (ver steps/01-porte-linux-simulador.md).
#
# Cobertura: os 6 cenários da dissertação, as duas variantes do ramo Pbase<0
# (padrão e WIN_ORIGINAL), os dois ramos de boração por limite de inserção — que
# nenhum dos 6 cenários alcança — e os caminhos de erro da linha de comando.
# O único trecho não exercitado é VariacaodeCarga(), código morto nos dois portes
# porque kbhit() é fixo em 0.
#
# Uso: bash scripts/verifica_equivalencia_python.sh [--rapido]
#      --rapido pula o cenário 6 (ciclo completo, ~50 s).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RAPIDO=0
[ "${1:-}" = "--rapido" ] && RAPIDO=1

# Os dois portes gravam com nomes fixos e DIFERENTES, de propósito: assim as duas
# corridas podem conviver no mesmo diretório sem uma acrescentar na outra (ambos
# abrem em modo append).
SAIDA_C="Modelagem_Reator.txt"
SAIDA_PY="Modelagem_Reator_py.txt"

falhas=0

echo "== compilando =="
gcc --std=gnu89 -Wall "$RAIZ/V8_Reatividade_SimuladorIgor_linux.c" -o "$TMP/simulador" -lm \
  || { echo "FALHOU: não compilou o porte C"; exit 1; }
gcc --std=gnu89 -Wall -DWIN_ORIGINAL "$RAIZ/V8_Reatividade_SimuladorIgor_linux.c" \
    -o "$TMP/simulador_win" -lm \
  || { echo "FALHOU: não compilou a variante WIN_ORIGINAL"; exit 1; }
mkdir -p "$TMP/c" "$TMP/py"

# compara <rótulo> <entrada scanf, 7 valores> <binário C> <env> <flags...>
compara() {
  local rotulo=$1 entrada=$2 bin=$3 amb=$4; shift 4
  echo "$entrada" | tr ' ' '\n' > "$TMP/entrada.txt"

  ( cd "$TMP/c"  && rm -f "$SAIDA_C" \
    && env $amb "$bin" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )
  ( cd "$TMP/py" && rm -f "$SAIDA_PY" \
    && env $amb python3 "$RAIZ/simulador.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha.txt )

  local n dados stdout
  n=$(grep -c '^[0-9]' "$TMP/c/$SAIDA_C" 2>/dev/null)
  if cmp -s "$TMP/c/$SAIDA_C" "$TMP/py/$SAIDA_PY"; then
    dados="dados ok"
  else
    dados="DADOS DIVERGEM"; falhas=$((falhas+1))
    diff "$TMP/c/$SAIDA_C" "$TMP/py/$SAIDA_PY" | head -6
  fi
  if cmp -s "$TMP/c/sha.txt" "$TMP/py/sha.txt"; then
    stdout="stdout ok"
  else
    stdout="STDOUT DIVERGE"; falhas=$((falhas+1))
    echo "   C : $(cat "$TMP/c/sha.txt")"
    echo "   PY: $(cat "$TMP/py/sha.txt")"
  fi
  printf '  %-46s %8s amostras   %-15s %s\n' "$rotulo" "$n" "$dados" "$stdout"
}

PADRAO="650 1800 210 4 -0.3 -0.8 0"

echo
echo "== os 6 cenários da dissertação (Tabelas 6.1 e 6.2) =="
compara "1 - operacao normal, 1 dia"      "$PADRAO"                    "$TMP/simulador" IGNORA=1 --tmax=1440
compara "2 - runback bomba alimentacao"   "$PADRAO"                    "$TMP/simulador" IGNORA=1 --transiente=runback-bap --t-transiente=10 --tmax=1440
compara "3 - runback manual 150 MW"       "$PADRAO"                    "$TMP/simulador" IGNORA=1 --transiente=runback-150 --t-transiente=10 --tmax=1440
compara "4 - rampa 32->650 MW a 1 MW/min" "32 1800 144 4 -0.3 -0.8 0"  "$TMP/simulador" IGNORA=1 --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440
compara "5 - rampa 650->32 MW a 3 MW/min" "$PADRAO"                    "$TMP/simulador" IGNORA=1 --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440
if [ "$RAPIDO" = 0 ]; then
  compara "6 - ciclo completo ate Cboro<8" "$PADRAO"                   "$TMP/simulador" IGNORA=1
else
  echo "  6 - ciclo completo                             (pulado por --rapido)"
fi

echo
echo "== ramo Pbase<0: as duas semânticas, que divergem entre si =="
compara "Pbase=0 (porte)"                 "32 1800 144 4 -0.3 -0.8 12" "$TMP/simulador"     IGNORA=1         --tmax=400
compara "Ptopo=0 (WIN_ORIGINAL)"          "32 1800 144 4 -0.3 -0.8 12" "$TMP/simulador_win" WIN_ORIGINAL=1   --tmax=400

echo
echo "== boração por limite de inserção (nenhum cenário da dissertação alcança) =="
compara "banco D=178, DeltaI=-1 (normal)"      "650 1800 178 4 -0.3 -0.8 -1" "$TMP/simulador" IGNORA=1 --tmax=600
compara "banco D=170, DeltaI=-1 (normal+emg)"  "650 1800 170 4 -0.3 -0.8 -1" "$TMP/simulador" IGNORA=1 --tmax=600
compara "banco D=150, DeltaI=-4 (emergencia)"  "650 1800 150 4 -0.3 -0.8 -4" "$TMP/simulador" IGNORA=1 --tmax=600

echo
echo "== caminhos de erro da linha de comando =="
for arg in "--transiente=nada" "--foo" "--transiente=rampa --alvo=650"; do
  c=$("$TMP/simulador"          $arg </dev/null 2>&1 >/dev/null; echo "rc=$?")
  p=$(python3 "$RAIZ/simulador.py" $arg </dev/null 2>&1 >/dev/null; echo "rc=$?")
  if [ "$c" = "$p" ]; then
    printf '  %-32s ok   %s\n' "$arg" "$(echo $c)"
  else
    printf '  %-32s DIVERGE\n     C : %s\n     PY: %s\n' "$arg" "$(echo $c)" "$(echo $p)"
    falhas=$((falhas+1))
  fi
done

echo
if [ "$falhas" = 0 ]; then
  echo "Equivalência confirmada: nenhuma divergência."
  exit 0
fi
echo "FALHOU: $falhas divergência(s)."
exit 1
