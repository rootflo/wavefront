# Docker Setup Guide

This guide explains how to configure and run the RootFlo AI platform using Docker Compose.

> [!WARNING]
> 
> - This project is under active development and APIs may change without notice. Please checkout the [platform docs](https://wavefront.rootflo.ai) for the latest information.
> - The platform is not in the GA state, and there are unimplemented feature. Checkout [ROADMAP.md](../ROADMAP.md) for the list of features, and whats missing.

## Quick Start

1. **Generate JWT Keys**
   ```bash
   cd /path/to/wavefront/server
   ./scripts/generate-keys.sh
   ```
   Copy the output `PRIVATE_KEY` and `PUBLIC_KEY` values.

2. **Configure Environment Variables**

   Edit `docker-compose.yml` and replace all `<YOUR_...>` placeholders with your actual values.

3. **Start Services**
   ```bash
   docker-compose up -d
   ```

4. **Check Logs**
   ```bash
   docker-compose logs -f floware
   ```

## Setting Up Credential Files

Some services require credential files (JSON files for GCP, OAuth, etc.). Follow these steps:

1. **Create a credentials directory** (recommended):
   ```bash
   mkdir -p /path/to/wavefront/server/credentials
   ```

2. **Copy your credential files**:
   ```bash
   # Example for GCP
   cp ~/Downloads/service-account.json ./credentials/gcp-service-account.json

   # Example for Google OAuth
   cp ~/Downloads/client_secret.json ./credentials/google-oauth-client-secret.json

   # Example for Gmail Service Account
   cp ~/Downloads/gmail-service-account.json ./credentials/gmail-service-account.json
   ```

3. **Uncomment volume mounts in docker-compose.sample.yml**:
   - Find the `volumes:` section under the `floware` service
   - Uncomment the lines for the credentials you're using
   - Update the left side of the `:` with your actual file path

4. **Security**: Add `credentials/` to `.gitignore` to avoid committing secrets
   ```bash
   echo "credentials/" >> .gitignore
   ```

### Which Credentials Do I Need?

- **GCP Service Account** (`GOOGLE_APPLICATION_CREDENTIALS`):
  - Required if: `CLOUD_PROVIDER=gcp`
  - Used for: Cloud Storage, KMS, Pub/Sub
  - Environment variable: `GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcp-service-account.json`

- **Gmail Service Account** (`GMAIL_SERVICE_ACCOUNT_FILE`):
  - Required if: `EMAIL_PROVIDER=gmail` with service account auth
  - Used for: Sending emails via Gmail API
  - Environment variable: `GMAIL_SERVICE_ACCOUNT_FILE=/app/credentials/gmail-service-account.json`

**Note**: The container paths (right side of `:` in volume mounts) are fixed at `/app/credentials/`. Only change the host paths (left side) to match where you store your credential files.

## Services Overview

| Service | Port | Description |
|---------|------|-------------|
| **floware** | 8001 | Core AI middleware service |
| **floconsole** | 8002 | Management console service |
| **inference_app** | 8003 | Inference App service (Alpha) |
| **call_processing** | 8004 | Voice call processing service (Pipecat) |
| **postgres-floware** | 5432 | Floware database (with pgvector extension) |
| **postgres-console** | 5433 | Console database |
| **redis-floware** | 6379 | Floware cache |
| **redis-call-processing** | 6380 | Call processing service cache |

## Environment Variables Reference

### Floware Service

#### Required Variables

**Database**:

| Variable | Description |
|----------|-------------|
| `DB_USERNAME` | PostgreSQL username (default: `postgres`) |
| `DB_PASSWORD` | PostgreSQL password (default: `postgres`) |
| `DB_HOST` | Database host (default: `postgres-floware`) |
| `DB_PORT` | Database port (default: `5432`) |
| `DB_NAME` | Database name (default: `floware`) |

**Redis**:

| Variable | Description |
|----------|-------------|
| `REDIS_PROTOCOL` | Protocol (default: `redis`) |
| `REDIS_HOST` | Redis host (default: `redis-floware`) |
| `REDIS_PORT` | Redis port (default: `6379`) |

**Application Settings**:

| Variable | Description |
|----------|-------------|
| `APP_ENV` | Application environment (e.g., `dev`, `staging`, `production`) |
| `APP_NAME` | Application name (default: `floware`) |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins |
| `PASSTHROUGH_SECRET` | Secret for service-to-service authentication (when `APP_ENV` is local, dev, staging)|

**IMPORTANT**: `PASSTHROUGH_SECRET` must be the same in floware, floconsole, and call_processing services. This is used only in non-production environments (`APP_NAME` being local, dev, staging), for production, you should configure service mesh or API gateway to handle service-to-service authentication.

**JWT Authentication**:

| Variable | Description |
|----------|-------------|
| `PRIVATE_KEY` | Base64-encoded RSA private key (generate using `./scripts/generate-keys.sh`) |
| `PUBLIC_KEY` | Base64-encoded RSA public key (generate using `./scripts/generate-keys.sh`) |
| `TOKEN_EXPIRY` | Token expiration in seconds (default: `3600`) |
| `TEMPORARY_TOKEN_EXPIRY` | Temporary token expiration (default: `600`) |
| `ENABLE_CLOUD_KMS` | Enable cloud KMS for key management (`true` or `false`) |
| `CONSOLE_TOKEN_PREFIX` | Token prefix for console tokens (default: `fc_`) |
| `FLOWARE_JWT_ISSUER` | JWT issuer URL for floware |
| `FLOWARE_JWT_AUDIENCE` | JWT audience URL for floware |
| `FLOWARE_JWT_VALIDATION_ISSUER` | Comma-separated list of valid issuers |

**Initial User configuration**:

| Variable | Description |
|----------|-------------|
| `EMAIL` | User Email |
| `PASSWORD` | User Password |
| `FIRST_NAME` | User first name |
| `LAST_NAME` | User last name |

**Cloud Provider** (Choose one: `aws` or `gcp`):

| Variable | Description |
|----------|-------------|
| `CLOUD_PROVIDER` | Set to `aws` or `gcp` |

#### AWS Configuration (if CLOUD_PROVIDER=aws)

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key |
| `AWS_REGION` | AWS region (e.g., ap-south-1) |
| `AWS_KMS_ARN` | KMS key ARN for encryption |
| `AWS_QUEUE_URL` | SQS queue URL |
| `TRANSCRIPT_BUCKET_NAME` | Bucket for audio transcripts |
| `AUDIO_BUCKET_NAME` | Bucket for audio files |
| `AWS_GOLD_ASSET_BUCKET_NAME` | Bucket for gold/insights assets |
| `MODEL_STORAGE_BUCKET` | Bucket for ML models |
| `AGENT_YAML_BUCKET` | Bucket for agent YAML configs |
| `VOICE_AGENT_BUCKET` | Bucket for voice agent configs |
| `IMAGE_SEARCH_REFERENCE_IMAGES_BUCKET` | Bucket for reference images |
| `APPLICATION_BUCKET` | Bucket for API service applications |

#### GCP Configuration (if CLOUD_PROVIDER=gcp)

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_LOCATION` | GCP region (e.g., asia-south1) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON file |
| `GCP_KMS_KEY_RING` | KMS key ring name |
| `GCP_KMS_CRYPTO_KEY` | KMS crypto key name |
| `GCP_KMS_CRYPTO_KEY_VERSION` | KMS key version (usually 1) |
| `GCP_ASSET_STORAGE_BUCKET` | Bucket for assets |
| `WORKFLOW_WORKER_TOPIC` | Workflow Pub/Sub topic |
| `APPLICATION_BUCKET` | Bucket for API service applications |

#### Optional Configurations

**External Services**:

| Variable | Description |
|----------|-------------|
| `INFERENCE_SERVICE_URL` | URL for the inference service (default: `http://inference_app:8003`) |
| `EMBEDDING_SERVICE_URL` | URL for the embedding service |
| `CALL_PROCESSING_BASE_URL` | URL for call processing service (default: `http://call_processing:8004`) |
| `HERMES_URL` | URL for Hermes service |

<!-- **OAuth Integration**:

| Variable | Description |
|----------|-------------|
| `AZURE_CLIENT_ID` | Azure OAuth client ID |
| `AZURE_TENANT_ID` | Azure OAuth tenant ID |
| `AZURE_CLIENT_SECRET` | Azure OAuth client secret |
| `AZURE_SCOPES` | Azure OAuth scopes |
| `AZURE_REDIRECT_URI` | Azure OAuth redirect URI | -->

**Email Integration**:

| Variable | Description |
|----------|-------------|
| `EMAIL_PROVIDER` | `gmail` or `outlook` |
| `GMAIL_SERVICE_ACCOUNT_FILE` | Gmail service account JSON file path |
| `GMAIL_SENDER_EMAILID` | Gmail sender email address |
| `GMAIL_DELEGATE_USER` | Gmail delegate user |
| `OUTLOOK_CLIENT_ID` | Outlook OAuth client ID |
| `OUTLOOK_CLIENT_SECRET` | Outlook OAuth client secret |
| `OUTLOOK_TENANT_ID` | Outlook OAuth tenant ID |
| `OUTLOOK_SENDER_EMAILID` | Outlook sender email address |

<!-- **Analytics**:

| Variable | Description |
|----------|-------------|
| `SUPERSET_URL` | Superset URL |
| `SUPERSET_USERNAME` | Superset username |
| `SUPERSET_PASSWORD` | Superset password |
| `BQ_PROJECT_ID` | BigQuery project ID |
| `BQ_DATASET_ID` | BigQuery dataset ID |
| `REDSHIFT_DB` | Redshift database name |
| `REDSHIFT_USERNAME` | Redshift username |
| `REDSHIFT_PASSWORD` | Redshift password |
| `REDSHIFT_HOST` | Redshift host |
| `REDSHIFT_PORT` | Redshift port | -->

**Auth Security Settings**:

| Variable | Description |
|----------|-------------|
| `MAX_FAILED_ATTEMPTS` | Maximum failed login attempts before lockout (default: `3`) |
| `LOCKOUT_DURATION_HOURS` | Hours to lock account after max failed attempts (default: `24`) |
| `INACTIVE_DAYS_THRESHOLD` | Days of inactivity before account is disabled (default: `60`) |

<!-- **Feature Flags** (set to `true` or `false`):

| Variable | Description |
|----------|-------------|
| `AZURE_FLAG` | Enable Azure integration |
| `AZURE_OPENAI_FLAG` | Enable Azure OpenAI |
| `CELERY_FLAG` | Enable Celery for async tasks |
| `EMAIL_SYNC_FLAG` | Enable email synchronization |
| `GOOGLE_FLAG` | Enable Google integration |
| `INACTIVE_ACCOUNT_DISABLE_FLAG` | Enable automatic account disabling for inactive users |
| `SAML_FLAG` | Enable SAML authentication |
| `SLACK_FLAG` | Enable Slack integration |
| `SUPERSET_FLAG` | Enable Superset analytics |
| `VECTOR_DB_FLAG` | Enable vector database features | -->

### FloConsole Service

#### Required Variables

| Variable | Description |
|----------|-------------|
| `ALLOWED_ORIGINS` | Allowed origins (http://wavefront:3000) |
| `CONSOLE_DB_HOST` | Database host (default: `postgres-console`) |
| `CONSOLE_DB_PORT` | Database port (default: `5432`) |
| `CONSOLE_DB_USERNAME` | Database username (default: `postgres`) |
| `CONSOLE_DB_PASSWORD` | Database password (default: `postgres`) |
| `CONSOLE_DB_NAME` | Database name (default: `console`) |
| `CONSOLE_EMAIL` | Admin email address |
| `CONSOLE_PASSWORD` | Admin password |
| `CONSOLE_FIRST_NAME` | Admin first name |
| `CONSOLE_LAST_NAME` | Admin last name |
| `CONSOLE_JWT_ISSUER` | JWT issuer URL for console |
| `CONSOLE_JWT_AUDIENCE` | JWT audience URL for console |
| `CONSOLE_TOKEN_PREFIX` | Token prefix for console tokens (default: `fc_`) |
| `TOKEN_EXPIRY` | Token expiration in seconds (default: `3600`) |
| `TEMPORARY_TOKEN_EXPIRY` | Temporary token expiration (default: `600`) |
| `PRIVATE_KEY` | Base64-encoded RSA private key (can be different from floware) |
| `PUBLIC_KEY` | Base64-encoded RSA public key (can be different from floware) |
| `APP_ENV` | Application environment |
| `ENABLE_CLOUD_KMS` | Enable cloud KMS for key management (`true` or `false`) |
| `PASSTHROUGH_SECRET` | Secret for service-to-service authentication (**IMPORTANT**: Must be the same as floware and call_processing) |
| `DEFAULT_APP_NAME` | Name for the default app created automatically (e.g., `floware-dev`) |
| `DEFAULT_APP_PUBLIC_URL` | Public URL for the default app (e.g., `http://floware:8001`) |
| `DEFAULT_APP_PRIVATE_URL` | Private URL for the default app (e.g., `http://floware:8001`) |

### Call Processing Service

#### Required Variables

| Variable | Description |
|----------|-------------|
| `REDIS_HOST` | Redis host (default: `redis-call-processing`) |
| `REDIS_PORT` | Redis port (default: `6379`) |
| `REDIS_DB` | Redis database number (default: `0`) |
| `APP_ENV` | Application environment |
| `APP_NAME` | Application name (default: `call_processing`) |
| `APP_NAME_FLOWARE` | Floware app name reference (default: `floware`) |
| `FLOWARE_BASE_URL` | Floware URL (default: `http://floware:8001`) |
| `PASSTHROUGH_SECRET` | Secret for service-to-service authentication |
| `TOKEN_EXPIRY` | Token expiration in seconds (default: `3600`) |
| `TEMPORARY_TOKEN_EXPIRY` | Temporary token expiration (default: `600`) |
| `CALL_PROCESSING_TOKEN_PREFIX` | Token prefix (default: `fc_`) |
| `CALL_PROCESSING_JWT_ISSUER` | JWT issuer URL for call processing |

### Inference App Service (Optional)

Uncomment the `inference_app` service in `docker-compose.yml` to enable.

#### Required Variables

| Variable | Description |
|----------|-------------|
| `APP_ENV` | Application environment |
| `CLOUD_PROVIDER` | `aws` or `gcp` |
| `MODEL_STORAGE_BUCKET` | Bucket for ML models |

**If AWS**:

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_REGION` | AWS region (e.g., `ap-south-1`) |

**If GCP**:

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON file (default: `/app/credentials/gcp-service-account.json`) |

## Cloud Provider Setup

### AWS Setup

1. **Create IAM User**:
   ```bash
   aws iam create-user --user-name rootflo-backend
   ```

2. **Attach Policies**:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:GetObject",
           "s3:PutObject",
           "s3:DeleteObject",
           "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::your-bucket-name",
           "arn:aws:s3:::your-bucket-name/*"
         ]
       },
       {
         "Effect": "Allow",
         "Action": [
           "sqs:SendMessage",
           "sqs:ReceiveMessage",
           "sqs:DeleteMessage"
         ],
         "Resource": "arn:aws:sqs:*:*:your-queue"
       },
       {
         "Effect": "Allow",
         "Action": [
           "kms:Decrypt",
           "kms:Encrypt",
           "kms:GenerateDataKey"
         ],
         "Resource": "arn:aws:kms:*:*:key/*"
       }
     ]
   }
   ```

3. **Create Buckets**:
   ```bash
   aws s3 mb s3://your-transcript-bucket --region ap-south-1
   aws s3 mb s3://your-audio-bucket --region ap-south-1
   aws s3 mb s3://your-agent-yaml-bucket --region ap-south-1
   # ... create other buckets as needed
   ```

### GCP Setup

1. **Create Service Account**:
   ```bash
   gcloud iam service-accounts create rootflo-backend \
     --display-name="RootFlo Backend Service Account"
   ```

2. **Grant Roles**:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:rootflo-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/storage.objectAdmin"

   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:rootflo-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/pubsub.publisher"

   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:rootflo-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
   ```

3. **Create Service Account Key**:
   ```bash
   gcloud iam service-accounts keys create service-account.json \
     --iam-account=rootflo-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

4. **Create Buckets**:
   ```bash
   gsutil mb -l asia-south1 gs://your-gcp-assets-bucket
   gsutil mb -l asia-south1 gs://your-gcp-storage-bucket
   # ... create other buckets as needed
   ```

5. **Create Pub/Sub Topics**:
   ```bash
   gcloud pubsub topics create your-gold-topic
   gcloud pubsub topics create your-email-topic
   gcloud pubsub topics create your-workflow-topic
   ```

### LocalStack (Development Alternative)

For local development without cloud dependencies:

1. **Add LocalStack to docker-compose.yml**:
   ```yaml
   localstack:
     image: localstack/localstack:latest
     ports:
       - "4566:4566"
     environment:
       - SERVICES=s3,sqs,kms
       - DEBUG=1
     networks:
       - floware-network
   ```

2. **Configure Environment Variables**:
   ```yaml
   AWS_ACCESS_KEY_ID: test
   AWS_SECRET_ACCESS_KEY: test
   AWS_ENDPOINT_URL: http://localstack:4566
   ```

## Common Operations

### Start All Services
```bash
docker-compose up -d
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f floware
```

### Restart Service
```bash
docker-compose restart floware
```

### Stop All Services
```bash
docker-compose down
```

### Stop and Remove Volumes (Reset Everything)
```bash
docker-compose down -v
```

### Rebuild Service
```bash
docker-compose build floware
docker-compose up -d floware
```

### Run Database Migrations
Migrations run automatically on service startup. To run manually:
```bash
docker-compose exec floware uv run alembic upgrade head
```

### Access Database
```bash
# Floware database
docker-compose exec postgres-floware psql -U postgres -d floware

# Console database
docker-compose exec postgres-console psql -U postgres -d console
```

### Access Redis
```bash
# Floware Redis
docker-compose exec redis-floware redis-cli

# Call Processing Redis
docker-compose exec redis-call-processing redis-cli
```

## Troubleshooting

### Service Won't Start

1. **Check logs**:
   ```bash
   docker-compose logs floware
   ```

2. **Check environment variables**:
   ```bash
   docker-compose config
   ```

3. **Verify dependencies**:
   ```bash
   docker-compose ps
   ```

### Database Connection Issues

- Ensure database service is healthy: `docker-compose ps postgres-floware`
- Check database logs: `docker-compose logs postgres-floware`
- Verify credentials in docker-compose.yml match

### Redis Connection Issues

- Ensure Redis is running: `docker-compose ps redis-floware`
- Test connection: `docker-compose exec redis-floware redis-cli ping`

### Port Conflicts

If ports are already in use, modify the port mappings in docker-compose.yml:
```yaml
ports:
  - '8002:8001'  # Map to different external port
```

### Out of Memory

Increase Docker memory limit in Docker Desktop settings (recommended: 8GB minimum).

## Initial Setup

After starting all services, you need to configure floconsole to connect to floware:

### Option 1: Automatic App Creation (Recommended)

Configure the default app using environment variables in docker-compose.yml:

```yaml
DEFAULT_APP_NAME: floware-dev
DEFAULT_APP_PUBLIC_URL: http://floware:8001
DEFAULT_APP_PRIVATE_URL: http://floware:8001
```

When the FloConsole service starts, it will automatically create this app with `success` status if these environment variables are set.

**Why `http://floware:8001` and not `http://localhost:8001`?**
- Inside Docker containers, services communicate using Docker service names
- `localhost` inside a container refers to the container itself, not other containers
- Using `http://floware:8001` allows floconsole to properly proxy requests to the floware service

### Option 2: Manual App Creation

If you prefer to create the app manually or need additional apps:

1. **Access FloConsole**: Navigate to `http://localhost:8002`

2. **Login** with the credentials configured in docker-compose.yml:
   - Email: Value of `CONSOLE_EMAIL`
   - Password: Value of `CONSOLE_PASSWORD`

3. **Create New App**:
   - **Deployment Type**: Select `Manual`
   - **App Name**: Any name you prefer (e.g., `floware-dev`)
   - **Public URL**: `http://floware:8001` (**IMPORTANT**: Use Docker service name, not `localhost`)
   - **Private URL**: `http://floware:8001`

## Production Deployment Notes

This docker-compose setup is designed for **local development only**. For production:

1. Use Kubernetes or Docker Swarm for orchestration
2. Implement proper secrets management (Vault, AWS Secrets Manager, etc.)
3. Set up monitoring and logging (Prometheus, Grafana, ELK stack)
4. Configure auto-scaling based on load
5. Use managed databases (RDS, Cloud SQL) instead of containerized databases
6. Implement backup and disaster recovery procedures
7. Use CDN for static assets
8. Set up CI/CD pipelines for automated deployments

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review this documentation
- Check service health: `docker-compose ps`
