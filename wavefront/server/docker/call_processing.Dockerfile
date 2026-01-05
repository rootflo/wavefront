FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/apps/call_processing /app/apps/call_processing

RUN uv sync --package call_processing --frozen --no-dev

WORKDIR /app/apps/call_processing/call_processing

CMD ["uv", "run", "server.py"]
