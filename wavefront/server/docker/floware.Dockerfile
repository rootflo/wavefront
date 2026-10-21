# Wolfi (Chainguard's glibc-based distro) instead of Debian slim: its packages
# carry no unpatched CVEs, whereas Debian ships glibc/zlib/libxml2/util-linux
# issues it marks no-fix. Pinned by digest; bump with `docker pull` + rescan.
FROM cgr.dev/chainguard/wolfi-base@sha256:81211e15a86ea1d5357f284482af45730c51de45eaf10ad9ce205d6bfc2df323

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
# MSSQL goes through mssql-python, which bundles Microsoft's ODBC driver; the
# driver needs libltdl, krb5 (GSSAPI) and glibc's iconv modules at runtime, and
# dlopens OpenSSL 1.x/3.x for TLS (Wolfi's default is OpenSSL 4, hence libssl3).
RUN apk upgrade --no-cache && \
    apk add --no-cache bash python-3.11 libltdl krb5-libs glibc-iconv libssl3 libcrypto3

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/modules/auth_module /app/modules/auth_module
COPY wavefront/server/modules/common_module /app/modules/common_module
COPY wavefront/server/modules/db_repo_module /app/modules/db_repo_module
COPY wavefront/server/modules/gold_module /app/modules/gold_module
COPY wavefront/server/modules/guardrails_module /app/modules/guardrails_module
COPY wavefront/server/modules/knowledge_base_module /app/modules/knowledge_base_module
COPY wavefront/server/modules/user_management_module /app/modules/user_management_module
COPY wavefront/server/modules/llm_inference_config_module /app/modules/llm_inference_config_module
COPY wavefront/server/modules/agents_module /app/modules/agents_module
COPY wavefront/server/modules/plugins_module/ /app/modules/plugins_module
COPY wavefront/server/modules/product_analysis_module /app/modules/product_analysis_module
COPY wavefront/server/modules/tools_module /app/modules/tools_module
COPY wavefront/server/modules/voice_agents_module /app/modules/voice_agents_module
COPY wavefront/server/modules/api_services_module /app/modules/api_services_module
COPY wavefront/server/modules/chatbots_module /app/modules/chatbots_module

COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY wavefront/server/packages/flo_utils /app/packages/flo_utils
COPY wavefront/server/packages/flo_lib /app/packages/flo_lib

COPY wavefront/server/plugins/datasource /app/plugins/datasource
COPY wavefront/server/plugins/authenticator /app/plugins/authenticator
COPY wavefront/server/plugins/mailer /app/plugins/mailer

COPY wavefront/server/apps/floware /app/apps/floware

COPY wavefront/server/scripts/floware-init.sh /app/scripts/floware-init.sh
RUN chmod +x /app/scripts/floware-init.sh

RUN --mount=from=ghcr.io/astral-sh/uv:0.12.24,source=/uv,target=/bin/uv uv sync --package floware --frozen --no-dev

# uv.lock covers the whole workspace, but only this app's deps are in the venv;
# scanners (AWS Inspector) report every package in it, and nothing reads it at
# runtime.
RUN rm uv.lock

# spaCy model for Presidio, which arrives with the flo-ai[guardrails] extra
# that guardrails_module depends on. The model is not a pip dependency of it,
# and Presidio downloads one on first use when absent -- which would put a
# multi-hundred-MB fetch inside the first guarded request.
#
# `pip` is installed on purpose: `spacy download` resolves the model version
# and then shells out to `python -m pip install`, and a uv-created venv has no
# pip, so the download fails without it.
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.24,source=/uv,target=/bin/uv uv pip install pip && \
    /app/.venv/bin/python -m spacy download en_core_web_lg && \
    uv pip uninstall pip

# Create a non-root user and change ownership of the /app directory
RUN adduser -D -u 1000 floware && \
    chown -R floware:floware /app

USER floware

ENTRYPOINT ["/app/scripts/floware-init.sh"]
