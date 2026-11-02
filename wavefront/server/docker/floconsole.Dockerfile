# Wolfi (Chainguard's glibc-based distro) instead of Debian slim: its packages
# carry no unpatched CVEs, whereas Debian ships glibc/zlib/util-linux issues it
# marks no-fix. Pinned by digest; bump with `docker pull` + rescan.
FROM cgr.dev/chainguard/wolfi-base@sha256:88a20e2d017bd20cdc0cb3910de603e7bea9512a6c351a8dd3c9df212ab03d73

WORKDIR /app

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

# Every locked dependency ships a wheel (psycopg/psycopg2 -binary bundle libpq),
# so no compiler, headers or libpq are needed; bash is for the init script.
RUN apk upgrade --no-cache && \
    apk add --no-cache bash python-3.11

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/modules/common_module /app/modules/common_module

COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY wavefront/server/packages/flo_lib /app/packages/flo_lib

COPY wavefront/server/apps/floconsole /app/apps/floconsole

COPY wavefront/server/scripts/console-server-init.sh /app/scripts/console-server-init.sh
RUN chmod +x /app/scripts/console-server-init.sh

RUN --mount=from=ghcr.io/astral-sh/uv:0.12.24,source=/uv,target=/bin/uv uv sync --package floconsole --frozen --no-dev

# uv.lock covers the whole workspace, but only this app's deps are in the venv;
# scanners (AWS Inspector) report every package in it, and nothing reads it at
# runtime.
RUN rm uv.lock

RUN adduser -D -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to the non-root user for all subsequent instructions
USER appuser

ENTRYPOINT ["/app/scripts/console-server-init.sh"]
