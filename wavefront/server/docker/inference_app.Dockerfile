# CPU-only: torch comes from the pytorch-cpu index (see pyproject.toml), so
# no CUDA base image. Wolfi (Chainguard's glibc-based distro) instead of
# Ubuntu: its packages carry no unpatched CVEs. Pinned by digest; bump with
# `docker pull` + rescan.
FROM cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43

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

# Every locked dependency ships a wheel (psycopg2-binary bundles libpq), so no
# compiler or headers are needed; opencv-python needs libGL and GLib at runtime.
# The app runs from the venv, so drop ensurepip's bundled pip/setuptools wheels.
RUN apk upgrade --no-cache && \
    apk add --no-cache python-3.11 mesa-gl glib && \
    rm -rf /usr/lib/python3.11/ensurepip/_bundled

# Create user early so uv sync runs as appuser
RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /app

COPY --chown=appuser:appuser wavefront/server/pyproject.toml wavefront/server/uv.lock wavefront/server/.python-version ./
COPY --chown=appuser:appuser wavefront/server/modules/common_module /app/modules/common_module
COPY --chown=appuser:appuser wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY --chown=appuser:appuser wavefront/server/packages/flo_lib /app/packages/flo_lib
COPY --chown=appuser:appuser wavefront/server/apps/inference_app /app/apps/inference_app

USER appuser

RUN --mount=from=ghcr.io/astral-sh/uv:0.12.24,source=/uv,target=/bin/uv uv sync --package inference-app --frozen --no-dev

# uv.lock covers the whole workspace, but only this app's deps are in the venv;
# scanners (AWS Inspector) report every package in it, and nothing reads it at
# runtime.
RUN rm uv.lock

WORKDIR /app/apps/inference_app/inference_app

CMD ["python", "server.py"]
