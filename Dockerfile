FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG TORCH_VERSION=2.13.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN sed '/^torch$/d' requirements.txt > /tmp/requirements.txt \
    && pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt \
    && pip install --index-url "$TORCH_INDEX_URL" "torch==$TORCH_VERSION"

COPY api ./api
COPY data ./data
COPY model ./model
COPY portfolio ./portfolio

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8089", "--workers", "1"]
