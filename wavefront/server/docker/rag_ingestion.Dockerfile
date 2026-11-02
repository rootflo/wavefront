# Wolfi (Chainguard's glibc-based distro) instead of Debian slim: its packages
# carry no unpatched CVEs, whereas Debian ships glibc/zlib/util-linux issues it
# marks no-fix. Pinned by digest; bump with `docker pull` + rescan.
FROM cgr.dev/chainguard/wolfi-base@sha256:88a20e2d017bd20cdc0cb3910de603e7bea9512a6c351a8dd3c9df212ab03d73

# uv is bind-mounted only into the RUN steps that need it (ghcr.io/astral-sh/uv:0.12.24), so the
# image does not ship the uv binary and the Rust crates it bundles; the app
# runs straight from the venv.
# Keep uv/pip download caches out of the image layers; build the venv on the
# distro's python3.11 rather than a uv-downloaded interpreter (not UV_PYTHON:
# that would also point `uv pip` at the system interpreter instead of the venv)
ENV UV_NO_CACHE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/app/.venv \
    PATH=/app/.venv/bin:$PATH

# bash is for the startup script. The app runs from the uv venv, so drop
# ensurepip's bundled pip/setuptools wheels (they vendor urllib3, msgpack, etc.)
RUN apk upgrade --no-cache && \
    apk add --no-cache bash python-3.11 && \
    rm -rf /usr/lib/python3.11/ensurepip/_bundled

# Set working directory
WORKDIR /app

# Copy project files
COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./
COPY wavefront/server/background_jobs/rag_ingestion ./background_jobs/rag_ingestion/
COPY wavefront/server/packages/flo_cloud ./packages/flo_cloud/
COPY wavefront/server/packages/flo_utils ./packages/flo_utils/
COPY wavefront/server/packages/flo_lib ./packages/flo_lib/
COPY wavefront/server/packages/flo_stream ./packages/flo_stream/
COPY wavefront/server/modules/db_repo_module ./modules/db_repo_module/
COPY wavefront/server/modules/common_module ./modules/common_module/
COPY wavefront/server/scripts/rag_ingestion/startup-rag-ingestion.sh ./background_jobs/rag_ingestion/

# Install dependencies
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.24,source=/uv,target=/bin/uv uv sync --package rag-ingestion --frozen --no-dev

# uv.lock covers the whole workspace, but only this app's deps are in the venv;
# scanners (AWS Inspector) report every package in it, and nothing reads it at
# runtime.
RUN rm uv.lock

# Download the tiktoken encoding file
RUN mkdir -p /root/.cache/tiktoken
RUN /app/.venv/bin/python -c "import tiktoken; enc = tiktoken.encoding_for_model('gpt-4')"

WORKDIR /app/background_jobs/rag_ingestion

# Make startup script executable
RUN chmod +x startup-rag-ingestion.sh

# Create a non-root user with UID 1000 and ensure files are owned by that user
# This allows Kubernetes pods using securityContext.runAsUser: 1000 to work
RUN set -eux \
    && adduser -D -u 1000 -s /sbin/nologin appuser \
    && chown -R 1000:1000 /app /root/.cache/tiktoken

# Switch to the non-root user (UID 1000) so containers can run with securityContext 1000
USER 1000

# Set entrypoint to run startup script
CMD ["./startup-rag-ingestion.sh"]
