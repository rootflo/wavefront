FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/modules/auth_module /app/modules/auth_module
COPY wavefront/server/modules/common_module /app/modules/common_module
COPY wavefront/server/modules/db_repo_module /app/modules/db_repo_module
COPY wavefront/server/modules/guardrails_module /app/modules/guardrails_module
COPY wavefront/server/modules/knowledge_base_module /app/modules/knowledge_base_module
COPY wavefront/server/modules/llm_inference_config_module /app/modules/llm_inference_config_module
COPY wavefront/server/modules/agents_module /app/modules/agents_module
COPY wavefront/server/modules/plugins_module /app/modules/plugins_module
COPY wavefront/server/modules/tools_module /app/modules/tools_module
COPY wavefront/server/modules/api_services_module /app/modules/api_services_module
COPY wavefront/server/modules/user_management_module /app/modules/user_management_module

COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY wavefront/server/packages/flo_utils /app/packages/flo_utils

COPY wavefront/server/plugins/datasource /app/plugins/datasource
COPY wavefront/server/plugins/authenticator /app/plugins/authenticator
COPY wavefront/server/plugins/mailer /app/plugins/mailer

COPY wavefront/server/background_jobs/celery_worker /app/background_jobs/celery_worker

RUN uv sync --package celery-worker --frozen --no-dev

# spaCy model for Presidio, and the regex bound Presidio reads at import time.
# The worker registers the PII adapter at startup just like floware does, so
# both apply here for the same reasons -- see floware.Dockerfile, which carries
# the full rationale. Without the model, the first guarded task pays a
# multi-hundred-MB download inside the task itself.
RUN uv pip install pip && \
    /app/.venv/bin/python -m spacy download en_core_web_lg

ENV REGEX_TIMEOUT_SECONDS=2

RUN useradd -m -u 1000 celery && \
    chown -R celery:celery /app

USER celery

WORKDIR /app/background_jobs/celery_worker

CMD ["uv", "run", "--frozen", "--no-sync", "celery", "-A", "celery_worker.celery_app", "worker", "--loglevel=info", "--pool=solo", "--without-mingle", "--without-gossip"]
