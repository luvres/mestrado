#!/usr/bin/env bash
# Gera os gráficos dos 6 cenários a partir de results/.
#
# Roda em contêiner porque o Python do host é "externally managed" (PEP 668):
# nem `pip install`, nem `python3 -m venv` (falta ensurepip). A imagem fixa
#
# Uso: bash scripts/gera_graficos.sh [--cenarios=1,2,3] [--sem-svg]

set -u
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGEM=localhost/reactor-graficos:latest

podman image exists "$IMAGEM" || {
  echo "== construindo a imagem de gráficos =="
  podman build -q -t "$IMAGEM" -f "$RAIZ/scripts/graficos.Containerfile" "$RAIZ" >/dev/null \
    || { echo "FALHOU: build"; exit 1; }
}

# --userns=keep-id: os PNGs saem em results/graficos/, que é do host.
podman run --rm --userns=keep-id -v "$RAIZ:/repo:z" -w /repo --pull=never "$IMAGEM" \
  python scripts/gera_graficos.py "$@"
