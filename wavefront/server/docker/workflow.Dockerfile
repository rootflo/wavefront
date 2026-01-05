FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.6 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./

COPY wavefront/server/background_jobs/workflow_job /app/background_jobs/workflow_job
COPY wavefront/server/packages/flo_cloud /app/packages/flo_cloud
COPY wavefront/server/packages/flo_utils /app/packages/flo_utils

COPY wavefront/server/modules/api_services_module /app/modules/api_services_module
COPY wavefront/server/modules/auth_module /app/modules/auth_module
COPY wavefront/server/modules/agents_module /app/modules/agents_module
COPY wavefront/server/modules/common_module /app/modules/common_module
COPY wavefront/server/modules/db_repo_module /app/modules/db_repo_module
COPY wavefront/server/modules/knowledge_base_module /app/modules/knowledge_base_module
COPY wavefront/server/modules/plugins_module /app/modules/plugins_module
COPY wavefront/server/modules/tools_module /app/modules/tools_module
COPY wavefront/server/modules/user_management_module /app/modules/user_management_module

COPY wavefront/server/plugins/datasource /app/plugins/datasource
COPY wavefront/server/plugins/authenticator /app/plugins/authenticator

# Install dependencies (without dependecy resolution and no dev dependencies)
RUN uv sync --package workflow_job --frozen --no-dev

# change WORKDIR
WORKDIR /app/background_jobs/workflow_job/workflow_job

CMD ["uv", "run", "main.py"]
