FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/modules/common_module /app/modules/common_module

COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud

COPY wavefront/server/apps/floconsole /app/apps/floconsole

COPY wavefront/server/scripts/console-server-init.sh /app/scripts/console-server-init.sh
RUN chmod +x /app/scripts/console-server-init.sh

RUN uv sync --package floconsole --frozen --no-dev

# Add a new non-root user named 'appuser' with a home directory
RUN useradd -m appuser

# Give 'appuser' ownership of the /app directory and its contents
RUN chown -R appuser:appuser /app

# Switch to the non-root user for all subsequent instructions
USER appuser

ENTRYPOINT ["/app/scripts/console-server-init.sh"]
