FROM python:3.14-slim
LABEL maintainer="Leonardo Loures <luvres@hotmail.com>"

# DIR_MODULOS e SERVICO sao lidas por tests/conftest.py: dizem que os
# modulos sob teste sao os que estao servindo a API, e qual dos dois
# servicos e este. PYTHONDONTWRITEBYTECODE evita __pycache__ e
# PYTEST_ADDOPTS tira o cache do pytest da montagem read-only de
# /tests — sem isso o comando simples emite aviso de escrita negada.
ENV \
  DEBIAN_FRONTEND=noninteractive \
  PYTHONUNBUFFERED=1 \
  UVICORN_CMD="uvicorn main:app --host 0.0.0.0 --port 8009 --workers 1 --proxy-headers" \
  DIR_MODULOS=/api \
  SERVICO=expert \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_ADDOPTS="-o cache_dir=/tmp/.pytest_cache"

WORKDIR /api

COPY *.py .
COPY requirements.txt /tmp/requirements.txt

RUN \
  apt-get update && apt-get install --yes --no-install-recommends \
      curl \
  && apt-get clean && rm -rf /var/lib/apt/lists/* \
  \
  && pip install --no-cache-dir -r /tmp/requirements.txt \
  \
  && useradd -m -u 1000 expert && chown -R expert:expert /api

USER expert

CMD ["bash", "-c", "$UVICORN_CMD"] 