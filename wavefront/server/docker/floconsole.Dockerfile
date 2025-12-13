FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.7.15 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

COPY modules/common_module /app/modules/common_module

COPY packages/flo_cloud /app/packages/flo_cloud

COPY apps/floconsole /app/apps/floconsole

RUN uv sync --package floconsole --frozen --no-dev

WORKDIR /app/apps/floconsole/floconsole

CMD ["uv", "run", "server.py"]
