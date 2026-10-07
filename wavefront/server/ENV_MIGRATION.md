# Environment variable migration (floware / flo_cloud config cleanup)

Old names continue to work only where apps still read them as aliases.
Prefer the new names.

## Cloud identity

| Old | New |
| --- | --- |
| `CLOUD_PROVIDER` | `CLOUD_PROVIDER` (unchanged; ini key is `[cloud] platform`) |
| `AWS_REGION` / `GCP_LOCATION` (split) | `CLOUD_REGION`, `CLOUD_LOCATION` |
| `GCP_PROJECT_ID` | `CLOUD_PROJECT_ID` |

Azure service-principal env vars (`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` /
`AZURE_CLIENT_SECRET`) are no longer read by apps. Workloads authenticate via
the attached identity (`DefaultAzureCredential`); flo_cloud still accepts
optional explicit credentials for local/tests.

## Storage buckets

| Old | New |
| --- | --- |
| `ASSET_STORAGE_BUCKET` / `MODEL_STORAGE_BUCKET` / `AGENT_YAML_BUCKET` / `AGENTIC_EXECUTIONS_BUCKET` / `VOICE_AGENT_BUCKET` / `APPLICATION_BUCKET` / `AWS_GOLD_ASSET_BUCKET_NAME` | `APPLICATION_BUCKET` → `[storage] application_bucket` (single shared bucket) |
| `CONFIG_FILE_NAME` | `CONFIG_FILE_NAME` → `[storage] config_file_name` |
| `AZURE_STORAGE_ACCOUNT_URL` | `STORAGE_ACCOUNT_URL` → `[storage] account_url` |

Removed (were never consumed): `TRANSCRIPT_BUCKET_NAME`, `AUDIO_BUCKET_NAME`,
`GCP_STORAGE_BUCKET_NAME`, `GCP_SERVICE_ACCOUNT_JSON`.

## Queues

| Old | New |
| --- | --- |
| `GCP_RAG_TOPIC_ID` / `AWS_RAG_QUEUE_URL` / `AZURE_STORAGE_QUEUE_NAME` (rag) | `RAG_QUEUE` |
| `GCP_PUBSUB_SUBSCRIPTION_ID` (rag consumer) | `RAG_QUEUE_SUBSCRIPTION` |
| `GCP_GOLD_TOPIC_ID` / `AWS_QUEUE_URL` / gold azure queue name | `GOLD_QUEUE` |
| `QUEUE_URL` (flo_cloud SQS module-level; never matched `AWS_QUEUE_URL`) | removed — use `QueueSettings.target` |

## KMS

| Old | New |
| --- | --- |
| `GCP_KMS_KEY_RING` | `KMS_KEY_RING` (shared by signing + encryption) |
| `GCP_KMS_CRYPTO_KEY` / `AWS_KMS_ARN` / `AZURE_KEY_VAULT_KEY_NAME` | `KMS_SIGNING_KEY` |
| `GCP_KMS_CRYPTO_KEY_VERSION` / `AZURE_KEY_VAULT_KEY_VERSION` | `KMS_SIGNING_KEY_VERSION` |
| `GCP_KMS_ENC_CRYPTO_KEY` / `AWS_KMS_ENC_ARN` / `AZURE_KEY_VAULT_ENC_KEY_NAME` | `KMS_ENCRYPTION_KEY` |
| `AZURE_KEY_VAULT_ENC_KEY_VERSION` | `KMS_ENCRYPTION_KEY_VERSION` |
| `AZURE_KEY_VAULT_URL` | `KMS_KEY_VAULT_URL` → `[kms_signing]` / `[kms_encryption] key_vault_url` |

## JWT / Redis / runtime URLs (now via app config, not direct env reads)

| Old env read site | Config key |
| --- | --- |
| `FLOWARE_JWT_VALIDATION_ISSUER` | `[jwt_token] validation_issuer` |
| `CONSOLE_TOKEN_PREFIX` | `[jwt_token] console_token_prefix` |
| `FLOWARE_JWT_AUDIENCE` | `[jwt_token] audience` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PROTOCOL` / `REDIS_PASSWORD` / `REDIS_DB` | `[redis] host/port/protocol/password/db` |
| `REDIS_POOL_SIZE` / `REDIS_POOL_TIMEOUT` | `[redis] pool_size` / `pool_timeout` |
| `FLOWARE_BASE_URL` | `[env_config] base_url` (wired via `common_module.runtime_settings`) |
| `PASSTHROUGH_SECRET` | `[env_config] passthrough_secret` |
| `ALLOWED_ORIGINS` | `[web] allowed_origins` |
| `FLOWARE_WORKER_COUNT` | `[env_config] worker_count` |
| `UVICORN_LOG_LEVEL` | `[env_config] uvicorn_log_level` |
| `CALL_PROCESSING_BASE_URL` | `[voice_agents] call_processing_base_url` (floware) / `[env_config] call_processing_base_url` (call_processing) |
| `FLOWARE_SERVICE_URL` | renamed to `FLOWARE_BASE_URL` → `[env_config] base_url` (rag_ingestion, same as floware/celery) |
| `APP_ENV` | `[env_config] app_env` |
| `APP_ENV=test` (pgvector model columns) | pytest: `db_repo_module.embedding_column_mode.enable_pgvector_test_standins()` in `flo_testing` plugin |
| `HMAC_AUTH_ROUTES` | `[auth] hmac_routes` (comma-separated; passed to `RequireAuthMiddleware`) |
| `MTLS_ALLOWED_NAMESPACES` | `[auth] mtls_allowed_namespaces` (comma-separated; passed to `RequireAuthMiddleware`) |
| `CELERY_BROKER_URL` | `[celery] broker_url` (floware + celery worker) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_SERVICE_NAME` / `APP_VERSION` / `HOSTNAME` | `[telemetry] otlp_endpoint`, `service_name`, `app_version`, `instance_id` |
| `LOG_LEVEL` | `[env_config] log_level` (floware, call_processing) |
| `ASYNC_AGENTIC_EXEC_*` / `KB_INDEX_STATUS_*` stream tuning | `[streams]` keys in floware `config.ini` |
| `GUARDRAILS_ENABLED` / `GUARDRAILS_*` / `AZURE_CONTENT_SAFETY_*` | `[guardrails]` in floware / celery `config.ini` (`enabled` gates container load) |
| `*_FLAG` feature toggles | `[feature_flags]` in floware `config.ini` |
| `PRODUCT_ANALYTICS_EXCLUDED_EMAILS` | `[product_analysis] excluded_emails` |
| `EXOTEL_APP_ID` | `[voice_agents] exotel_app_id` |
| `AZURE_OPENAI_API_VERSION` | `[model] azure_openai_api_version` |
| `SCHEDULER_WORKER_ID` | `[scheduler] worker_id` (defaults to hostname when empty) |
| Call-processing pipecat / eval env vars | `[pipecat]` / `[call_eval]` in call_processing `config.ini` |
| `REDIS_*` / `CLOUD_PROVIDER` (call_processing cache) | `[redis]` / `[cloud]` in call_processing `config.ini` |

## Removed dead config sections / keys

`[redshift]`, `[google]`, `[slack]`, `[bigquery]`, `[scheduler]`, `[usage_metric]`,
`[openai]`, `[leads]`, `[image_search]`, `[insights]`, `[extractor]`,
`[azure_openai]`, and unused azure embeddings / scopes / redirect keys.
