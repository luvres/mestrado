#!/usr/bin/env bash
# Verifica que a planta ATRAS DO HTTP produz os mesmos bytes que o monolito.
#
# verifica_fronteira_reactor.sh ja provou que o corte fisica/regras nao mudou
# nada quando os dois lados estao no mesmo processo. Este script fecha a outra
# metade: o mesmo braco procedural, as mesmas 19 regras, mas conversando com
# reactor/main.py por HTTP — uma chamada por atuacao, o estado relido a cada vez,
# e a saida padrao remontada a partir do campo `saida` de cada resposta.
#
# Se algo de essencial estivesse ficando no processo (um estado global, uma
# ordem de impressao, um arredondamento feito do lado errado da fronteira), e
# aqui que apareceria.
#
# O cliente tambem roda em conteiner: um auxiliar entra na rede do servico e
# executa o braco procedural de la. O motivo e reprodutibilidade — o cliente usa
# o mesmo Python e as mesmas versoes fixadas em reactor/requirements.txt que o
# servico, e o teste nao depende de nada instalado no host.
#
# Do host tambem funciona, e e util para depurar:
#     python3 scripts/validate_c_vs_python.py --api=http://localhost:8008 --tmax=1440
#
# Uso: bash scripts/verifica_api_reactor.sh [--completo]
#      --completo inclui o cenario 6 (ciclo inteiro, ~500 mil minutos; alguns
#      minutos de relogio e mais de um milhao de requisicoes).

set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Nome QUALIFICADO. Sem o "localhost/", podman trata o nome como nao
# qualificado e, se por algum motivo a tag local nao estiver la, tenta puxar
# do docker.io — que responde "access denied" e o teste falha parecendo
# divergencia de resultado. Melhor falhar dizendo que falta a imagem.
IMAGEM=localhost/reactor-simulator:latest
NOME=reactor-verifica-$$
TMP="$(mktemp -d)"
COMPLETO=0
[ "${1:-}" = "--completo" ] && COMPLETO=1

limpa() { podman rm -f "$NOME" >/dev/null 2>&1; rm -rf "$TMP"; }
trap limpa EXIT

echo "== construindo a imagem =="
podman build -q -t "$IMAGEM" -f "$RAIZ/reactor/Dockerfile" "$RAIZ/reactor" >/dev/null \
  || { echo "FALHOU: build da imagem"; exit 1; }
podman image exists "$IMAGEM" \
  || { echo "FALHOU: imagem $IMAGEM nao esta no armazenamento local"; exit 1; }

echo "== subindo o servico =="
# keep-id: sem ele o uid do conteiner cai num subuid e nao escreve no diretorio
# montado do host (mesmo motivo do userns_mode no docker-compose.yml).
podman run -d --name "$NOME" --userns=keep-id -v "$TMP:/saida:z" \
  -e SAIDA_DIR=/saida "$IMAGEM" >/dev/null \
  || { echo "FALHOU: nao subiu o conteiner"; exit 1; }
for _ in $(seq 1 30); do
  podman exec "$NOME" curl -sf http://localhost:8008/health >/dev/null 2>&1 && break
  sleep 1
done
podman exec "$NOME" curl -sf http://localhost:8008/health >/dev/null 2>&1 \
  || { echo "FALHOU: /health nao respondeu"; podman logs "$NOME" | tail -20; exit 1; }

falhas=0

# compara <rotulo> <7 valores> <env> <flags...>
compara() {
  local rotulo=$1 entrada=$2 amb=$3; shift 3
  echo "$entrada" | tr ' ' '\n' > "$TMP/entrada.txt"

  # A) monolito, no host
  ( cd "$TMP" && rm -f Modelagem_Reator_py.txt \
    && env $amb python3 "$RAIZ/simulador.py" "$@" < "$TMP/entrada.txt" | sha256sum > sha_mono.txt )

  # B) braco procedural falando com o servico por HTTP
  rm -f "$TMP/Modelagem_Reator_http.txt"
  podman run --rm --network "container:$NOME" --userns=keep-id \
    -v "$RAIZ:/repo:ro" -v "$TMP:/saida:z" \
    -e DIR_MODULOS=/api -e "$amb" -w /saida --pull=never "$IMAGEM" \
    sh -c "python /repo/scripts/validate_c_vs_python.py --api=http://localhost:8008 \
             --arquivo=Modelagem_Reator_http.txt $* < /saida/entrada.txt | sha256sum > /saida/sha_http.txt"

  local n dados stdout
  n=$(grep -c '^[0-9]' "$TMP/Modelagem_Reator_py.txt" 2>/dev/null)
  if cmp -s "$TMP/Modelagem_Reator_py.txt" "$TMP/Modelagem_Reator_http.txt"; then
    dados="dados ok"
  else
    dados="DADOS DIVERGEM"; falhas=$((falhas+1))
    diff "$TMP/Modelagem_Reator_py.txt" "$TMP/Modelagem_Reator_http.txt" | head -6
  fi
  if cmp -s "$TMP/sha_mono.txt" "$TMP/sha_http.txt"; then
    stdout="stdout ok"
  else
    stdout="STDOUT DIVERGE"; falhas=$((falhas+1))
    echo "   mono: $(cat "$TMP/sha_mono.txt")"
    echo "   http: $(cat "$TMP/sha_http.txt")"
  fi
  printf '  %-46s %8s amostras   %-15s %s\n' "$rotulo" "$n" "$dados" "$stdout"
}

PADRAO="650 1800 210 4 -0.3 -0.8 0"

echo
echo "== os cenarios da dissertacao, agora por HTTP =="
compara "1 - operacao normal, 1 dia"      "$PADRAO"                    IGNORA=1 --tmax=1440
compara "2 - runback bomba alimentacao"   "$PADRAO"                    IGNORA=1 --transiente=runback-bap --t-transiente=10 --tmax=1440
compara "3 - runback manual 150 MW"       "$PADRAO"                    IGNORA=1 --transiente=runback-150 --t-transiente=10 --tmax=1440
compara "4 - rampa 32->650 MW a 1 MW/min" "32 1800 144 4 -0.3 -0.8 0"  IGNORA=1 --transiente=rampa --alvo=650 --taxa=1 --t-transiente=10 --tmax=1440
compara "5 - rampa 650->32 MW a 3 MW/min" "$PADRAO"                    IGNORA=1 --transiente=rampa --alvo=32 --taxa=3 --t-transiente=10 --tmax=1440
if [ "$COMPLETO" = 1 ]; then
  compara "6 - ciclo completo ate Cboro<8" "$PADRAO"                   IGNORA=1
else
  echo "  6 - ciclo completo                             (pulado; use --completo)"
fi

echo
echo "== ramo Pbase<0 e boracao por limite de insercao =="
compara "Pbase=0 (porte)"                      "32 1800 144 4 -0.3 -0.8 12"  IGNORA=1       --tmax=400
compara "Ptopo=0 (WIN_ORIGINAL)"               "32 1800 144 4 -0.3 -0.8 12"  WIN_ORIGINAL=1 --tmax=400
compara "banco D=178, DeltaI=-1 (so R11)"       "650 1800 178 4 -0.3 -0.8 -1" IGNORA=1       --tmax=600
compara "banco D=170, DeltaI=-1 (R11 e R12)"   "650 1800 170 4 -0.3 -0.8 -1" IGNORA=1       --tmax=600
compara "banco D=150, DeltaI=-4 (emergencia)"  "650 1800 150 4 -0.3 -0.8 -4" IGNORA=1       --tmax=600

echo
if [ "$falhas" = 0 ]; then
  echo "API confirmada: a planta atras do HTTP nao mudou nenhum byte."
  exit 0
fi
echo "FALHOU: $falhas divergencia(s)."
exit 1
