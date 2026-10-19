FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/modules/common_module /app/modules/common_module
COPY wavefront/server/packages/flo_lib /app/packages/flo_lib

COPY wavefront/server/apps/call_processing /app/apps/call_processing

RUN uv sync --package call_processing --frozen --no-dev

WORKDIR /app/apps/call_processing/call_processing

RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin appuser \
    && chown -R 1000:1000 /app

USER 1000

CMD ["uv", "run", "--frozen", "--no-sync", "server.py"]
