FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .python-version ./

COPY modules/common_module /app/modules/common_module
COPY packages/flo_cloud /app/packages/flo_cloud
COPY apps/inference_app /app/apps/inference_app

RUN uv sync --package inference-app --frozen --no-dev

WORKDIR /app/apps/inference_app/inference_app

CMD ["uv", "run", "server.py"]
