#!/usr/bin/env bash
# Os 6 cenarios da dissertacao, nos TRES niveis, comparados entre si.
#
#   C      binario de V8_Reatividade_SimuladorIgor_linux.c   (o original portado)
#   PY     simulador.py                                      (o porte fiel, Passo 2)
#   MALHA  reactor:8008 + expert:8009 por HTTP               (Passos 4 e 5)
#
# Por que este script existe alem dos outros: verifica_equivalencia_python.sh
# compara C com PY, e verifica_malha_fechada.sh compara PY com MALHA. Encadear os
# dois prova C == MALHA por transitividade — mas transitividade nao e medicao, e
# a pergunta "o sistema em servico reproduz o simulador original?" merece ser
# respondida com uma comparacao direta.
#
# Criterio: byte a byte no arquivo de amostras E na saida padrao inteira.
# Os tres gravam em nomes DIFERENTES de proposito (os tres abrem em append), o
# que permite as tres corridas conviverem no mesmo diretorio.
#
# Uso: bash scripts/verifica_seis_cenarios.sh [--rapido]
#      --rapido pula o cenario 6 (ciclo completo; ~15 min pela malha).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG_R=localhost/reactor-simulator:latest
IMG_E=localhost/reactor-expert-system:latest
SUF=$$
REDE=seis-$SUF
NOME_R=reactor-seis-$SUF
NOME_E=expert-seis-$SUF
PORTA=18109
TMP="$(mktemp -d)"
RAPIDO=0
[ "${1:-}" = "--rapido" ] && RAPIDO=1

limpa() {
  podman rm -f "$NOME_E" "$NOME_R" >/dev/null 2>&1
  podman network rm "$REDE" >/dev/null 2>&1
  rm -rf "$TMP"
}
trap limpa EXIT

echo "== compilando o porte C =="
gcc --std=gnu89 -Wall "$RAIZ/V8_Reatividade_SimuladorIgor_linux.c" -o "$TMP/simulador" -lm \
  || { echo "FALHOU: nao compilou"; exit 1; }

echo "== construindo as duas imagens =="
podman build -q -t "$IMG_R" -f "$RAIZ/reactor/Dockerfile" "$RAIZ/reactor" >/dev/null || exit 1
podman build -q -t "$IMG_E" -f "$RAIZ/expert/Dockerfile" "$RAIZ/expert" >/dev/null || exit 1

echo "== subindo a malha =="
podman network create "$REDE" >/dev/null 2>&1
podman run -d --name "$NOME_R" --network "$REDE" --network-alias reactor-simulator \
  --userns=keep-id -v "$TMP:/saida:z" -e SAIDA_DIR=/saida "$IMG_R" >/dev/null || exit 1
podman run -d --name "$NOME_E" --network "$REDE" -p "$PORTA:8009" "$IMG_E" >/dev/null || exit 1
for _ in $(seq 1 40); do
  podman exec "$NOME_E" curl -sf http://localhost:8009/health >/dev/null 2>&1 && break
  sleep 1
done
podman exec "$NOME_E" curl -sf http://reactor-simulator:8008/health >/dev/null 2>&1 \
  || { echo "FALHOU: a malha nao subiu"; podman logs "$NOME_E" | tail -20; exit 1; }

falhas=0
printf '\n  %-38s %9s  %-22s %s\n' "cenario" "amostras" "amostras C=PY=MALHA" "stdout C=PY=MALHA"
printf '  %s\n' "----------------------------------------------------------------------------------------"

# compara <rotulo> <7 valores> <flags...>
compara() {
  local rotulo=$1 entrada=$2; shift 2
  echo "$entrada" | tr ' ' '\n' > "$TMP/entrada.txt"

  ( cd "$TMP" && rm -f Modelagem_Reator.txt \
    && "$TMP/simulador" "$@" < entrada.txt | sha256sum > sha_c.txt )
  ( cd "$TMP" && rm -f Modelagem_Reator_py.txt \
    && python3 "$RAIZ/simulador.py" "$@" < entrada.txt | sha256sum > sha_py.txt )

  rm -f "$TMP/Modelagem_Reator_malha.txt"
  python3 "$RAIZ/scripts/cliente_malha.py" --expert="http://localhost:$PORTA" \
      --reactor=http://reactor-simulator:8008 --arquivo=Modelagem_Reator_malha.txt \
      --pedaco=20000 "$@" < "$TMP/entrada.txt" 2>"$TMP/cliente.err" \
    | sha256sum > "$TMP/sha_malha.txt"
  local rc=${PIPESTATUS[0]}
  if [ "$rc" != 0 ]; then
    echo "   >> o cliente da malha falhou (rc=$rc); a corrida esta incompleta:"
    tail -5 "$TMP/cliente.err" | sed 's/^/      /'
  fi

  local n dados stdout
  n=$(grep -c '^[0-9]' "$TMP/Modelagem_Reator.txt" 2>/dev/null)
  if cmp -s "$TMP/Modelagem_Reator.txt" "$TMP/Modelagem_Reator_py.txt" \
     && cmp -s "$TMP/Modelagem_Reator.txt" "$TMP/Modelagem_Reator_malha.txt"; then
    dados="identicas"
  else
    dados="DIVERGEM"; falhas=$((falhas+1))
    cmp -s "$TMP/Modelagem_Reator.txt" "$TMP/Modelagem_Reator_py.txt" \
      || echo "      C != PY"
    cmp -s "$TMP/Modelagem_Reator.txt" "$TMP/Modelagem_Reator_malha.txt" \
      || { echo "      C != MALHA"; diff "$TMP/Modelagem_Reator.txt" \
             "$TMP/Modelagem_Reator_malha.txt" | head -4 | sed 's/^/      /'; }
  fi
  if cmp -s "$TMP/sha_c.txt" "$TMP/sha_py.txt" && cmp -s "$TMP/sha_c.txt" "$TMP/sha_malha.txt"; then
    stdout="identico  $(cut -c1-16 < "$TMP/sha_c.txt")"
  else
    stdout="DIVERGE"; falhas=$((falhas+1))
    echo "      C    : $(cat "$TMP/sha_c.txt")"
    echo "      PY   : $(cat "$TMP/sha_py.txt")"
    echo "      MALHA: $(cat "$TMP/sha_malha.txt")"
  fi
  printf '  %-38s %9s  %-22s %s\n' "$rotulo" "$n" "$dados" "$stdout"
}

PADRAO="650 1800 210 4 -0.3 -0.8 0"

compara "1 - operacao normal, 1 dia"      "$PADRAO"                    --tmax=1440
compara "2 - runback bomba alimentacao"   "$PADRAO"                    --transiente=runback-bap --t-transiente=10 --tmax=1440
compara "3 - runback manual 150 MW"       "$PADRAO"                    --transiente=runback-150 --t-transiente=10 --tmax=1440
compara "4 - rampa 32->650 MW a 1 MW/min" "32 1800 144 4 -0.3 -0.8 0"  --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440
compara "5 - rampa 650->32 MW a 3 MW/min" "$PADRAO"                    --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440
if [ "$RAPIDO" = 0 ]; then
  compara "6 - ciclo completo ate Cboro<8" "$PADRAO"
else
  printf '  %-38s %9s  %s\n' "6 - ciclo completo" "-" "(pulado por --rapido)"
fi

echo
if [ "$falhas" = 0 ]; then
  echo "Os 6 cenarios: C, simulador.py e a malha (reactor+expert) produzem os mesmos bytes."
  exit 0
fi
echo "FALHOU: $falhas divergencia(s)."
exit 1
