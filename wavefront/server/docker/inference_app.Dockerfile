FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock wavefront/server/.python-version ./

COPY wavefront/server/modules/common_module /app/modules/common_module
COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY wavefront/server/apps/inference_app /app/apps/inference_app

RUN uv sync --package inference-app --frozen --no-dev

WORKDIR /app/apps/inference_app/inference_app

# Create a non-root user 'appuser' with a home directory
RUN useradd -m appuser

# Change ownership of the /app directory to 'appuser' to ensure permission
RUN chown -R appuser:appuser /app

# Ensure subsequent actions run as 'appuser'
USER appuser

CMD ["uv", "run", "server.py"]
