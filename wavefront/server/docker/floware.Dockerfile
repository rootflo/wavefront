FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    unixodbc \
    unixodbc-dev \
    curl \
    gnupg2 \
    apt-transport-https \
    && rm -rf /var/lib/apt/lists/*

# Add Microsoft's ODBC driver repository and install msodbcsql
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft-archive-keyring.gpg && \
    echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" > /etc/apt/sources.list.d/microsoft-ubuntu-jammy-prod.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

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
COPY wavefront/server/modules/inference_module /app/modules/inference_module
COPY wavefront/server/modules/tools_module /app/modules/tools_module
COPY wavefront/server/modules/voice_agents_module /app/modules/voice_agents_module
COPY wavefront/server/modules/api_services_module /app/modules/api_services_module
COPY wavefront/server/modules/triggers_module /app/modules/triggers_module

COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY wavefront/server/packages/flo_utils /app/packages/flo_utils

COPY wavefront/server/plugins/datasource /app/plugins/datasource
COPY wavefront/server/plugins/authenticator /app/plugins/authenticator

COPY wavefront/server/apps/floware /app/apps/floware

COPY wavefront/server/scripts/floware-init.sh /app/scripts/floware-init.sh
RUN chmod +x /app/scripts/floware-init.sh

RUN uv sync --package floware --frozen --no-dev

# spaCy model for Presidio, which arrives with the flo-ai[guardrails] extra
# that guardrails_module depends on. The model is not a pip dependency of it,
# and Presidio downloads one on first use when absent -- which would put a
# multi-hundred-MB fetch inside the first guarded request.
#
# `pip` is installed on purpose: `spacy download` resolves the model version
# and then shells out to `python -m pip install`, and a uv-created venv has no
# pip, so the download fails without it.
RUN uv pip install pip && \
    /app/.venv/bin/python -m spacy download en_core_web_lg

# Bound how long any single regex may run. Presidio's default is 60s and it
# reads this at import time, so it can only be set from the environment.
#
# The default is dangerous here rather than merely slow: the adapter analyses in
# a two-thread pool, and a pattern that backtracks pins a thread for the whole
# timeout. The policy's own timeout fires on the awaiting coroutine but cannot
# cancel a running thread, so requests queue behind it and time out -- and
# since the PII provider defaults to FAIL_CLOSED, that is a namespace-wide
# outage. At 2s the pool recovers and the worst case is one pattern finding
# nothing on one request.
ENV REGEX_TIMEOUT_SECONDS=2

# Create a non-root user and change ownership of the /app directory
RUN useradd -m -u 1000 floware && \
    chown -R floware:floware /app

USER floware

ENTRYPOINT ["/app/scripts/floware-init.sh"]
