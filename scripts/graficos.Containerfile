# Imagem só para gerar os gráficos. Não é serviço: não expõe porta, não roda
# uvicorn. Existe porque o Python do host é "externally managed" (PEP 668) e
# não aceita `pip install`, e `python3 -m venv` falha sem ensurepip.
#
# Construção e uso ficam em scripts/gera_graficos.sh.
FROM python:3.14-slim
LABEL maintainer="Leonardo Loures <luvres@hotmail.com>"

ENV \
  DEBIAN_FRONTEND=noninteractive \
  PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  MPLBACKEND=Agg \
  MPLCONFIGDIR=/tmp/mpl

# Versão fixada: os gráficos da dissertação têm de ser regeráveis anos depois.
RUN pip install --no-cache-dir matplotlib

WORKDIR /repo
