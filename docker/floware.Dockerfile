FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

COPY modules/auth_module /app/modules/auth_module
COPY modules/common_module /app/modules/common_module
COPY modules/db_repo_module /app/modules/db_repo_module
COPY modules/gold_module /app/modules/gold_module
COPY modules/insights_module /app/modules/insights_module
COPY modules/knowledge_base_module /app/modules/knowledge_base_module
COPY modules/user_management_module /app/modules/user_management_module
COPY modules/llm_inference_config_module /app/modules/llm_inference_config_module
COPY modules/agents_module /app/modules/agents_module
COPY modules/plugins_module/ /app/modules/plugins_module
COPY modules/product_analysis_module /app/modules/product_analysis_module
COPY modules/inference_module /app/modules/inference_module
COPY modules/image_search_module /app/modules/image_search_module
COPY modules/tools_module /app/modules/tools_module
COPY modules/voice_agents_module /app/modules/voice_agents_module
COPY modules/api_services_module /app/modules/api_services_module

COPY packages/flo_cloud /app/packages/flo_cloud
COPY packages/flo_utils /app/packages/flo_utils

COPY plugins/datasource /app/plugins/datasource
COPY plugins/authenticator /app/plugins/authenticator

COPY apps/floware /app/apps/floware

RUN uv sync --package floware --frozen --no-dev

WORKDIR /app/apps/floware/floware

CMD ["uv", "run", "server.py"]
