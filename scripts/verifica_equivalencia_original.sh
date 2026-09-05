#!/usr/bin/env bash
# Verifica que o porte Linux produz saída IDÊNTICA ao código original do Igor.
#
# Compila o V8_Reatividade_SimuladorIgor.txt SEM NENHUMA ALTERAÇÃO — apenas com um
# shim mínimo para o <conio.h>, que não existe no Linux — e compara a saída com a
# do porte, no cenário 1 (1 dia) e no cenário 6 (ciclo completo).
#
# Isto isola a questão "o porte é fiel ao original?" da questão "a aritmética do
# compilador muda o resultado?": os dois binários são gerados pelo mesmo gcc, com
# as mesmas flags. Para a segunda, ver a verificação 3 em
# steps/01-porte-linux-simulador.md.
#
# O cenário 6 leva alguns minutos: o original não termina (ao atingir Cboro<8 ele
# imprime "FIM DO CICLO", chama getch() e segue o laço), então é interrompido ao
# alcançar o t final e a saída é truncada ali.
#
# Uso: bash scripts/verifica_equivalencia_original.sh

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
limpa() { pkill -9 -f "$TMP/original" 2>/dev/null; rm -rf "$TMP"; }
trap limpa EXIT

echo "== preparando =="
mkdir -p "$TMP/shim" "$TMP/exec_orig" "$TMP/exec_porte"

# O original inclui <conio.h> (getch/kbhit), exclusivo do DOS/Windows.
# kbhit()=0 reproduz "nenhuma tecla pressionada", que é a condição dos cenários
# 1 e 6 — não têm transiente, então o caminho interativo nunca é exercido.
cat > "$TMP/shim/conio.h" <<'EOF'
#ifndef CONIO_SHIM_H
#define CONIO_SHIM_H
#include <stdio.h>
static int getch(void) { return getchar(); }
static int kbhit(void) { return 0; }
#endif
EOF

cp "$RAIZ/V8_Reatividade_SimuladorIgor.txt" "$TMP/original.c"
printf '650\n1800\n210\n4\n-0.3\n-0.8\n0\n' > "$TMP/entrada.txt"

# gcc >= 14 promove a erro violações que o original contém e que fazem parte do
# que está sendo testado; aqui elas voltam a ser apenas avisos.
gcc --std=gnu89 -I"$TMP/shim" \
    -Wno-error=int-conversion -Wno-error=implicit-function-declaration \
    -Wno-error=incompatible-pointer-types -Wno-error=format \
    "$TMP/original.c" -o "$TMP/original" -lm 2>/dev/null \
  || { echo "FALHOU: não compilou o original"; exit 1; }

gcc --std=gnu89 -Wall "$RAIZ/V8_Reatividade_SimuladorIgor_linux.c" \
    -o "$TMP/porte" -lm \
  || { echo "FALHOU: não compilou o porte"; exit 1; }

# Roda o original até t>=$1 e escreve as amostras com t<=$1 na saída padrão.
# O 'exec' é essencial: sem ele $! seria o PID do subshell, e matá-lo deixaria o
# simulador órfão continuando a escrever no mesmo arquivo.
roda_original() {
  local fim=$1 pid
  rm -f "$TMP/exec_orig/Modelagem_Reator.txt"
  ( cd "$TMP/exec_orig" && exec "$TMP/original" < "$TMP/entrada.txt" >/dev/null 2>&1 ) &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if awk -v f="$fim" '$1 ~ /^[0-9]+$/ && $1+0>=f {ok=1} END{exit !ok}' \
         "$TMP/exec_orig/Modelagem_Reator.txt" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null; break
    fi
    sleep 1
  done
  wait "$pid" 2>/dev/null
  awk -v f="$fim" '$1 ~ /^[0-9]+$/ && $1+0<=f' "$TMP/exec_orig/Modelagem_Reator.txt"
}

compara() {
  local nome=$1 fim=$2; shift 2
  echo
  echo "== $nome =="
  roda_original "$fim" > "$TMP/a.txt"
  ( cd "$TMP/exec_porte" && rm -f Modelagem_Reator.txt \
    && "$TMP/porte" "$@" < "$TMP/entrada.txt" >/dev/null )
  awk -v f="$fim" '$1 ~ /^[0-9]+$/ && $1+0<=f' \
      "$TMP/exec_porte/Modelagem_Reator.txt" > "$TMP/b.txt"
  echo "   original: $(wc -l < "$TMP/a.txt") amostras"
  echo "   porte   : $(wc -l < "$TMP/b.txt") amostras"
  if [ -s "$TMP/a.txt" ] && diff -q "$TMP/a.txt" "$TMP/b.txt" >/dev/null; then
    echo "   IDÊNTICOS byte a byte  ✓"
  else
    echo "   DIVERGEM:"; diff "$TMP/a.txt" "$TMP/b.txt" | head -6
    exit 1
  fi
}

compara "Cenário 1 — 1 dia (1440 min)"             1440   --tmax=1440
compara "Cenário 6 — ciclo completo (669.105 min)" 669105
echo
echo "Equivalência confirmada."
