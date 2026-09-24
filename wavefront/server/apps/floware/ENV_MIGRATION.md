# Environment variable migration (floware / flo_cloud config cleanup)

Old names continue to work only where apps still read them as aliases
(e.g. celery `WORKFLOW_WORKER_TOPIC` → `WORKFLOW_QUEUE`). Prefer the new names.

## Cloud identity

| Old | New |
| --- | --- |
| `CLOUD_PROVIDER` | `CLOUD_PROVIDER` (unchanged; ini key is now `[cloud] provider`) |
| `AWS_REGION` / `GCP_LOCATION` (split) | `CLOUD_REGION`, `CLOUD_LOCATION` |
| `GCP_PROJECT_ID` | `CLOUD_PROJECT_ID` (`[triggers_gmail] pubsub_project_id` also uses this) |

## Storage buckets

| Old | New |
| --- | --- |
| `ASSET_STORAGE_BUCKET` / `MODEL_STORAGE_BUCKET` / `AGENT_YAML_BUCKET` / `AGENTIC_EXECUTIONS_BUCKET` / `VOICE_AGENT_BUCKET` / `APPLICATION_BUCKET` / `AWS_GOLD_ASSET_BUCKET_NAME` | `APPLICATION_BUCKET` → `[storage] application_bucket` (single shared bucket) |
| `CONFIG_FILE_NAME` | `CONFIG_FILE_NAME` → `[storage] config_file_name` |

Removed (were never consumed): `TRANSCRIPT_BUCKET_NAME`, `AUDIO_BUCKET_NAME`,
`GCP_STORAGE_BUCKET_NAME`, `GCP_SERVICE_ACCOUNT_JSON`.

## Queues

| Old | New |
| --- | --- |
| `GCP_RAG_TOPIC_ID` / `AWS_RAG_QUEUE_URL` / `AZURE_STORAGE_QUEUE_NAME` (rag) | `RAG_QUEUE` |
| `GCP_PUBSUB_SUBSCRIPTION_ID` (rag consumer) | `RAG_QUEUE_SUBSCRIPTION` |
| `WORKFLOW_WORKER_TOPIC` / `GCP_PUBSUB_TOPIC_ID` (workflow) | `WORKFLOW_QUEUE` |
| (workflow consumer subscription) | `WORKFLOW_QUEUE_SUBSCRIPTION` |
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
| `AZURE_KEY_VAULT_URL` | `AZURE_KEY_VAULT_URL` → `[azure] key_vault_url` |

## JWT / Redis / runtime URLs (now via app config, not direct env reads)

| Old env read site | Config key |
| --- | --- |
| `FLOWARE_JWT_VALIDATION_ISSUER` | `[jwt_token] validation_issuer` |
| `CONSOLE_TOKEN_PREFIX` | `[jwt_token] console_token_prefix` |
| `FLOWARE_JWT_AUDIENCE` | `[jwt_token] audience` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PROTOCOL` / `REDIS_PASSWORD` / `REDIS_DB` | `[redis] host/port/protocol/password/db` |
| `FLOWARE_BASE_URL` | `[env_config] base_url` (wired via `common_module.runtime_settings`) |
| `PASSTHROUGH_SECRET` | `[env_config] passthrough_secret` (also `[app_config]` in workflow/rag) |
| `ALLOWED_ORIGINS` | `[web] allowed_origins` |
| `FLOWARE_WORKER_COUNT` | `[env_config] worker_count` |
| `UVICORN_LOG_LEVEL` | `[env_config] uvicorn_log_level` |
| `CALL_PROCESSING_BASE_URL` | `[voice_agents] call_processing_base_url` (floware) / `[env_config] call_processing_base_url` (call_processing) |
| `FLOWARE_SERVICE_URL` | `[floware] service_url` / `[app_config] floware_service_url` → runtime `floware_base_url` |
| `APP_ENV` | `[env_config] app_env` |

## Removed dead config sections / keys

`[redshift]`, `[google]`, `[slack]`, `[bigquery]`, `[scheduler]`, `[usage_metric]`,
`[openai]`, `[leads]`, `[image_search]`, `[insights]`, `[extractor]`,
`[azure_openai]`, and unused azure embeddings / scopes / redirect keys.
