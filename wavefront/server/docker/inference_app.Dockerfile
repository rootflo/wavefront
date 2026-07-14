FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create user early so uv sync runs as appuser — avoids Python binary landing in /root/.local
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

COPY --chown=appuser:appuser wavefront/server/pyproject.toml wavefront/server/uv.lock wavefront/server/.python-version ./
COPY --chown=appuser:appuser wavefront/server/modules/common_module /app/modules/common_module
COPY --chown=appuser:appuser wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY --chown=appuser:appuser wavefront/server/apps/inference_app /app/apps/inference_app

USER appuser

RUN uv sync --package inference-app --frozen --no-dev

WORKDIR /app/apps/inference_app/inference_app

CMD ["uv", "run", "server.py"]
