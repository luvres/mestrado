#!/usr/bin/env bash
# Verifica a MALHA FECHADA: os dois servicos, por HTTP, contra o porte fiel.
#
#   simulador.py                          um processo, 1482 linhas
#   vs
#   reactor-simulator:8008  (a fisica)  +  reactor-expert-system:8009  (as regras)
#
# O cliente (scripts/cliente_malha.py) nao decide nem calcula nada: ele abre a
# sessao, pede ciclos e concatena o campo `saida` de cada resposta. O que sai e
# a saida padrao do simulador remontada a partir de dois servicos.
#
# Criterio, o mesmo dos Passos 1, 2 e 4: byte a byte no arquivo de amostras E na
# saida padrao inteira (por SHA-256 — no cenario 6 ela passa de 400 MB).
#
# Uso: bash scripts/verifica_malha_fechada.sh [--completo]
#      --completo inclui o cenario 6 (ciclo inteiro; varios minutos).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG_R=localhost/reactor-simulator:latest
IMG_E=localhost/reactor-expert-system:latest
SUF=$$
REDE=malha-$SUF
NOME_R=reactor-malha-$SUF
NOME_E=expert-malha-$SUF
PORTA=18009
TMP="$(mktemp -d)"
COMPLETO=0
[ "${1:-}" = "--completo" ] && COMPLETO=1

limpa() {
  podman rm -f "$NOME_E" "$NOME_R" >/dev/null 2>&1
  podman network rm "$REDE" >/dev/null 2>&1
  rm -rf "$TMP"
}
trap limpa EXIT

echo "== construindo as duas imagens =="
podman build -q -t "$IMG_R" -f "$RAIZ/reactor/Dockerfile" "$RAIZ/reactor" >/dev/null || exit 1
podman build -q -t "$IMG_E" -f "$RAIZ/expert/Dockerfile" "$RAIZ/expert" >/dev/null || exit 1

echo "== subindo a malha =="
podman network create "$REDE" >/dev/null 2>&1
# O expert alcanca a planta pelo nome do conteiner na rede; por isso o alias.
podman run -d --name "$NOME_R" --network "$REDE" --network-alias reactor-simulator \
  --userns=keep-id -v "$TMP:/saida:z" -e SAIDA_DIR=/saida "$IMG_R" >/dev/null || exit 1
podman run -d --name "$NOME_E" --network "$REDE" -p "$PORTA:8009" "$IMG_E" >/dev/null || exit 1

for _ in $(seq 1 40); do
  podman exec "$NOME_E" curl -sf http://localhost:8009/health >/dev/null 2>&1 && break
  sleep 1
done
podman exec "$NOME_E" curl -sf http://localhost:8009/health >/dev/null 2>&1 \
  || { echo "FALHOU: expert nao respondeu"; podman logs "$NOME_E" | tail -20; exit 1; }
podman exec "$NOME_E" curl -sf http://reactor-simulator:8008/health >/dev/null 2>&1 \
  || { echo "FALHOU: o expert nao alcanca o reator"; exit 1; }

falhas=0

# compara <rotulo> <7 valores> <env-do-monolito> <flags-do-cliente...>
compara() {
  local rotulo=$1 entrada=$2 amb=$3; shift 3
  echo "$entrada" | tr ' ' '\n' > "$TMP/entrada.txt"

  ( cd "$TMP" && rm -f Modelagem_Reator_py.txt \
    && env $amb python3 "$RAIZ/simulador.py" $MONO_FLAGS < "$TMP/entrada.txt" | sha256sum > sha_mono.txt )

  rm -f "$TMP/Modelagem_Reator_malha.txt"
  # O stderr do cliente NAO vai para /dev/null. Uma corrida interrompida no meio
  # (o servico caiu, a imagem foi reconstruida por baixo, a rede sumiu) produz
  # saida parcial, que sem isto aparece como "DADOS DIVERGEM" e faz procurar um
  # erro de modelagem onde ha um problema de infraestrutura.
  python3 "$RAIZ/scripts/cliente_malha.py" --expert="http://localhost:$PORTA" \
      --reactor=http://reactor-simulator:8008 --arquivo=Modelagem_Reator_malha.txt \
      --pedaco=20000 "$@" < "$TMP/entrada.txt" 2>"$TMP/cliente.err" \
    | sha256sum > "$TMP/sha_malha.txt"
  local rc=${PIPESTATUS[0]}
  if [ "$rc" != 0 ]; then
    echo "   >> o cliente da malha falhou (rc=$rc), a corrida esta incompleta:"
    tail -5 "$TMP/cliente.err" | sed 's/^/      /'
  fi

  local n dados stdout
  n=$(grep -c '^[0-9]' "$TMP/Modelagem_Reator_py.txt" 2>/dev/null)
  if cmp -s "$TMP/Modelagem_Reator_py.txt" "$TMP/Modelagem_Reator_malha.txt"; then
    dados="dados ok"
  else
    dados="DADOS DIVERGEM"; falhas=$((falhas+1))
    diff "$TMP/Modelagem_Reator_py.txt" "$TMP/Modelagem_Reator_malha.txt" | head -6
  fi
  if cmp -s "$TMP/sha_mono.txt" "$TMP/sha_malha.txt"; then
    stdout="stdout ok"
  else
    stdout="STDOUT DIVERGE"; falhas=$((falhas+1))
    echo "   mono : $(cat "$TMP/sha_mono.txt")"
    echo "   malha: $(cat "$TMP/sha_malha.txt")"
  fi
  printf '  %-44s %8s amostras   %-15s %s\n' "$rotulo" "$n" "$dados" "$stdout"
}

PADRAO="650 1800 210 4 -0.3 -0.8 0"

echo
echo "== os cenarios da dissertacao, pelos dois servicos =="
MONO_FLAGS="--tmax=1440"
compara "1 - operacao normal, 1 dia" "$PADRAO" IGNORA=1 --tmax=1440

MONO_FLAGS="--transiente=runback-bap --t-transiente=10 --tmax=1440"
compara "2 - runback bomba alimentacao" "$PADRAO" IGNORA=1 --transiente=runback-bap --t-transiente=10 --tmax=1440

MONO_FLAGS="--transiente=runback-150 --t-transiente=10 --tmax=1440"
compara "3 - runback manual 150 MW" "$PADRAO" IGNORA=1 --transiente=runback-150 --t-transiente=10 --tmax=1440

MONO_FLAGS="--transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440"
compara "4 - rampa 32->650 MW a 1 MW/min" "32 1800 144 4 -0.3 -0.8 0" IGNORA=1 \
        --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440

MONO_FLAGS="--transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440"
compara "5 - rampa 650->32 MW a 3 MW/min" "$PADRAO" IGNORA=1 \
        --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440

if [ "$COMPLETO" = 1 ]; then
  MONO_FLAGS=""
  compara "6 - ciclo completo (R19 dispara)" "$PADRAO" IGNORA=1
else
  echo "  6 - ciclo completo                           (pulado; use --completo)"
fi

echo
echo "== bordas: alarmes e boracao por limite de insercao (R11, R12) =="
MONO_FLAGS="--tmax=400"
compara "Pbase=0 (porte)" "32 1800 144 4 -0.3 -0.8 12" IGNORA=1 --tmax=400
MONO_FLAGS="--tmax=600"
compara "banco D=178, DeltaI=-1 (R11)"        "650 1800 178 4 -0.3 -0.8 -1" IGNORA=1 --tmax=600
compara "banco D=170, DeltaI=-1 (R11 e R12)"  "650 1800 170 4 -0.3 -0.8 -1" IGNORA=1 --tmax=600
compara "banco D=150, DeltaI=-4 (R12 emerg.)" "650 1800 150 4 -0.3 -0.8 -4" IGNORA=1 --tmax=600

echo
if [ "$falhas" = 0 ]; then
  echo "Malha fechada confirmada: dois servicos, nenhum byte diferente."
  exit 0
fi
echo "FALHOU: $falhas divergencia(s)."
exit 1
