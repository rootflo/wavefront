FROM python:3.11-slim-buster

# Copy UV from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project files
COPY wavefront/server/pyproject.toml wavefront/server/uv.lock ./
COPY wavefront/server/background_jobs/rag_ingestion ./background_jobs/rag_ingestion/
COPY wavefront/server/packages/flo_cloud ./packages/flo_cloud/
COPY wavefront/server/packages/flo_utils ./packages/flo_utils/
COPY wavefront/server/modules/db_repo_module ./modules/db_repo_module/
COPY wavefront/server/modules/common_module ./modules/common_module/
COPY wavefront/server/scripts/rag_ingestion/startup-rag-ingestion.sh ./background_jobs/rag_ingestion/

# Install dependencies
RUN uv sync --package rag-ingestion --frozen --no-dev

# Download the tiktoken encoding file and NLTK data
RUN mkdir -p /root/.cache/tiktoken
RUN uv run python3 -c "import tiktoken; enc = tiktoken.encoding_for_model('gpt-4')"
RUN uv run python3 -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"

WORKDIR /app/background_jobs/rag_ingestion

# Make startup script executable
RUN chmod +x startup-rag-ingestion.sh

# Set entrypoint to run startup script
CMD ["./startup-rag-ingestion.sh"] 