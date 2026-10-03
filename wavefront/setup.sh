#!/usr/bin/env bash
#
# Local development setup for wavefront.
#
# Steps:
#   1. Check prerequisites (python >= 3.11, uv, docker, openssl, node, pnpm)
#   2. Create .env files from their samples: floconsole (.env.example),
#      floware and client (.env.sample)
#   3. Start postgres, redis and localstack (server/docker-compose.yml), create
#      the floconsole and floware databases using the credentials in each .env,
#      and create the S3 bucket, SQS queue and KMS signing/encryption keys in localstack
#   4. Install python deps and start floconsole and floware (python server.py)
#      in new terminal windows, then wait for their /v1/health endpoints
#      Optionally download the inference models and start the inference app,
#      and start the celery and RAG ingestion workers, the same way
#   5. Install client deps and start the web client (pnpm run dev) in a new
#      terminal window
#
# Usage: ./setup.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$ROOT_DIR/server"
FLOCONSOLE_DIR="$SERVER_DIR/apps/floconsole/floconsole"
FLOWARE_DIR="$SERVER_DIR/apps/floware/floware"
CELERY_DIR="$SERVER_DIR/background_jobs/celery_worker"
RAG_DIR="$SERVER_DIR/background_jobs/rag_ingestion"
INFERENCE_DIR="$SERVER_DIR/apps/inference_app/inference_app"
CLIENT_DIR="$ROOT_DIR/client"

REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=11
REQUIRED_NODE_MAJOR=20

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=''; GREEN=''; YELLOW=''; RED=''; CYAN=''; RESET=''
fi

step()  { echo; echo "${BOLD}==> $*${RESET}"; }
ok()    { echo "  ${GREEN}✓${RESET} $*"; }
warn()  { echo "  ${YELLOW}!${RESET} $*"; }
fail()  { echo "  ${RED}✗${RESET} $*"; }

print_banner() {
  echo "${CYAN}${BOLD}"
  cat <<'BANNER'
██╗    ██╗ █████╗ ██╗   ██╗███████╗███████╗██████╗  ██████╗ ███╗   ██╗████████╗
██║    ██║██╔══██╗██║   ██║██╔════╝██╔════╝██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝
██║ █╗ ██║███████║██║   ██║█████╗  █████╗  ██████╔╝██║   ██║██╔██╗ ██║   ██║
██║███╗██║██╔══██║╚██╗ ██╔╝██╔══╝  ██╔══╝  ██╔══██╗██║   ██║██║╚██╗██║   ██║
╚███╔███╔╝██║  ██║ ╚████╔╝ ███████╗██║     ██║  ██║╚██████╔╝██║ ╚████║   ██║
 ╚══╝╚══╝ ╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝
BANNER
  printf "%78s\n" "by Rootflo"
  echo "${RESET}  Local development setup"
}

# Ask a yes/no question. Returns 0 for yes. Default is no.
confirm() {
  local reply
  read -r -p "  $1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# ---------------------------------------------------------------------------
# Step 1: prerequisites
# ---------------------------------------------------------------------------

check_python() {
  local py=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      py="$candidate"
      break
    fi
  done

  if [[ -z "$py" ]]; then
    fail "python not found (need >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR})"
    return 1
  fi

  local version
  version="$("$py" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}")')"
  local major="${version%%.*}"
  local minor="${version#*.}"; minor="${minor%%.*}"

  if (( major > REQUIRED_PYTHON_MAJOR || (major == REQUIRED_PYTHON_MAJOR && minor >= REQUIRED_PYTHON_MINOR) )); then
    ok "python $version ($py)"
  else
    fail "python $version found, need >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}"
    return 1
  fi
}

check_uv() {
  if command -v uv >/dev/null 2>&1; then
    ok "$(uv --version)"
  else
    fail "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 1
  fi
}

check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "docker not found. Install Docker Desktop: https://docs.docker.com/get-docker/"
    return 1
  fi

  if ! docker info >/dev/null 2>&1; then
    fail "docker is installed but the daemon is not running. Start Docker and re-run."
    return 1
  fi
  ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)"

  if docker compose version >/dev/null 2>&1; then
    ok "$(docker compose version)"
  else
    fail "docker compose plugin not found"
    return 1
  fi
}

check_openssl() {
  if command -v openssl >/dev/null 2>&1; then
    ok "$(openssl version)"
  else
    fail "openssl not found (needed to generate PASSTHROUGH_SECRET)"
    return 1
  fi
}

check_node() {
  if ! command -v node >/dev/null 2>&1; then
    fail "node not found (need >= $REQUIRED_NODE_MAJOR). Install: https://nodejs.org/"
    return 1
  fi
  local version major
  version="$(node -v)"; version="${version#v}"
  major="${version%%.*}"
  if (( major >= REQUIRED_NODE_MAJOR )); then
    ok "node $version"
  else
    fail "node $version found, need >= $REQUIRED_NODE_MAJOR"
    return 1
  fi
}

check_pnpm() {
  if command -v pnpm >/dev/null 2>&1; then
    ok "pnpm $(pnpm -v)"
  else
    fail "pnpm not found. Install: corepack enable (ships with node)"
    return 1
  fi
}

check_prerequisites() {
  step "Checking prerequisites"
  local failed=0
  check_python  || failed=1
  check_uv      || failed=1
  check_docker  || failed=1
  check_openssl || failed=1
  check_node    || failed=1
  check_pnpm    || failed=1

  if (( failed )); then
    echo
    fail "Missing prerequisites. Fix the above and re-run ./setup.sh"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Step 2: env files
# ---------------------------------------------------------------------------

# Set KEY=VALUE in an env file, replacing the existing line.
# Uses awk + ENVIRON so values containing / + = are safe.
set_env_value() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp)"
  KEY="$key" VALUE="$value" awk '
    BEGIN { found = 0 }
    index($0, ENVIRON["KEY"] "=") == 1 { print ENVIRON["KEY"] "=" ENVIRON["VALUE"]; found = 1; next }
    { print }
    END { if (!found) print ENVIRON["KEY"] "=" ENVIRON["VALUE"] }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

# Copy an example env file to .env, asking before replacing an existing one.
# Returns 0 when a fresh .env was written, 1 when the existing one was kept.
#   copy_env_file <example> <env_file>
copy_env_file() {
  local example="$1" env_file="$2"

  if [[ ! -f "$example" ]]; then
    fail "Missing ${example#"$ROOT_DIR"/}"
    exit 1
  fi

  if [[ -f "$env_file" ]]; then
    warn "${env_file#"$ROOT_DIR"/} already exists"
    if ! confirm "Replace it with a fresh copy from $(basename "$example")? (a backup will be kept)"; then
      ok "Keeping existing .env"
      return 1
    fi
    local backup
    backup="$env_file.backup.$(date +%Y%m%d%H%M%S)"
    cp "$env_file" "$backup"
    ok "Backed up to ${backup#"$ROOT_DIR"/}"
  fi

  cp "$example" "$env_file"
  ok "Created ${env_file#"$ROOT_DIR"/} from $(basename "$example")"
}

setup_floconsole_env() {
  step "Configuring floconsole environment"
  local env_file="$FLOCONSOLE_DIR/.env"

  copy_env_file "$FLOCONSOLE_DIR/.env.example" "$env_file" || return 0
  set_env_value "$env_file" PASSTHROUGH_SECRET "$(openssl rand -hex 32)"
  chmod 600 "$env_file"
  ok "Generated PASSTHROUGH_SECRET"
}

setup_floware_env() {
  step "Configuring floware environment"
  local env_file="$FLOWARE_DIR/.env"
  local console_secret
  console_secret="$(env_get "$FLOCONSOLE_DIR/.env" PASSTHROUGH_SECRET)"

  if copy_env_file "$FLOWARE_DIR/.env.sample" "$env_file"; then
    # floconsole proxies to floware with this secret, so they must match.
    set_env_value "$env_file" PASSTHROUGH_SECRET "$console_secret"
    chmod 600 "$env_file"
    ok "Copied PASSTHROUGH_SECRET from floconsole"
  elif [[ "$(env_get "$env_file" PASSTHROUGH_SECRET)" != "$console_secret" ]]; then
    warn "PASSTHROUGH_SECRET differs from floconsole's .env; floconsole cannot reach floware"
  fi
}

RUN_CELERY_WORKER=0

setup_celery_env() {
  step "Celery worker (async agent and workflow runs)"
  if ! confirm "Run the celery worker as well?"; then
    ok "Skipping celery worker"
    return
  fi
  RUN_CELERY_WORKER=1
  copy_env_file "$CELERY_DIR/celery_worker/.env.sample" "$CELERY_DIR/celery_worker/.env" || true
}

RUN_RAG_WORKER=0

setup_rag_env() {
  step "RAG ingestion worker (knowledge base documents)"
  if ! confirm "Run the RAG ingestion worker as well?"; then
    ok "Skipping RAG ingestion worker"
    return
  fi
  RUN_RAG_WORKER=1

  local env_file="$RAG_DIR/rag_ingestion/.env"
  local floware_secret
  floware_secret="$(env_get "$FLOWARE_DIR/.env" PASSTHROUGH_SECRET)"
  if copy_env_file "$RAG_DIR/rag_ingestion/.env.sample" "$env_file"; then
    # The worker calls floware back with this secret, so they must match.
    set_env_value "$env_file" PASSTHROUGH_SECRET "$floware_secret"
    chmod 600 "$env_file"
    ok "Copied PASSTHROUGH_SECRET from floware"
  elif [[ "$(env_get "$env_file" PASSTHROUGH_SECRET)" != "$floware_secret" ]]; then
    warn "PASSTHROUGH_SECRET differs from floware's .env; the worker cannot call floware"
    if confirm "Update it in ${env_file#"$ROOT_DIR"/} to match floware?"; then
      set_env_value "$env_file" PASSTHROUGH_SECRET "$floware_secret"
      ok "Synced PASSTHROUGH_SECRET from floware"
    else
      RUN_RAG_WORKER=0
      warn "Skipping RAG ingestion worker: it cannot run with a mismatched secret"
      return
    fi
  fi
}

RUN_INFERENCE_APP=0
INFERENCE_MODELS_DIR="$INFERENCE_DIR/scripts/.mcache"
# <env var>:<folder under .mcache>; must match MODELS in scripts/download_models.py
INFERENCE_MODELS=(
  "CLIP_VIT_BASE_PATCH32_MODEL_URI:clip-vit-base-patch32-hf"
  "DINOV3_VITL16_HF_MODEL_URI:dinov3-vitl16-hf"
  "BGE_M3_MODEL_URI:bge-m3-hf"
)

# True if any inference model folder is missing or empty.
inference_models_missing() {
  local entry dir
  for entry in "${INFERENCE_MODELS[@]}"; do
    dir="$INFERENCE_MODELS_DIR/${entry#*:}"
    # `ls` without -A: a failed download leaves only a hidden .cache/ behind
    [[ -d "$dir" && -n "$(ls "$dir" 2>/dev/null)" ]] || return 0
  done
  return 1
}

# Inference runs on CPU (CPU-only torch from the pytorch-cpu index) on Linux and
# Apple Silicon. Intel Macs have no PyTorch build at the supported version
# (>= 2.6), so torch isn't installed there and the inference app serves mock
# embeddings instead: same API and shapes, synthetic vectors, no models to
# download. Checks the hardware, not `uname -m`, which also says x86_64 under
# Rosetta.
INFERENCE_MOCK=0
is_intel_mac() {
  [[ "$OSTYPE" == darwin* ]] && [[ "$(sysctl -in hw.optional.arm64 2>/dev/null)" != 1 ]]
}

setup_inference_env() {
  step "Inference app (image embeddings, CLIP + DINOv3; text embeddings, BGE-M3)"
  local env_file="$INFERENCE_DIR/.env" entry var

  if is_intel_mac; then
    echo "  Intel Mac: PyTorch has no build here at the supported version (>= 2.6), so"
    echo "  the inference app runs in mock mode: the same API returning synthetic"
    echo "  embeddings, for integration testing. Search results won't be meaningful."
    echo "  Use Apple Silicon or Linux for real embeddings."
    if ! confirm "Run the inference app in mock mode?"; then
      ok "Skipping inference app"
      return
    fi
    RUN_INFERENCE_APP=1
    INFERENCE_MOCK=1
    copy_env_file "$INFERENCE_DIR/.env.sample" "$env_file" || true
    return
  fi

  echo "  All three models together need roughly 4-5 GB of free memory."
  if ! confirm "Run the inference app as well? (downloads several GB of models on first run)"; then
    ok "Skipping inference app"
    return
  fi
  RUN_INFERENCE_APP=1

  copy_env_file "$INFERENCE_DIR/.env.sample" "$env_file" || true
  # Point empty model URIs at the local download folders (machine-specific paths).
  for entry in "${INFERENCE_MODELS[@]}"; do
    var="${entry%%:*}"
    if [[ -z "$(env_get "$env_file" "$var")" ]]; then
      set_env_value "$env_file" "$var" "$INFERENCE_MODELS_DIR/${entry#*:}"
      ok "$var → scripts/.mcache/${entry#*:}"
    fi
  done

  # Ask for the token now so the download later runs unattended.
  if inference_models_missing && [[ -z "${HF_TOKEN:-}" ]]; then
    echo "  The models are downloaded from Hugging Face. DINOv3 is gated: accept its"
    echo "  license at https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m"
    echo "  and create a read token at https://huggingface.co/settings/tokens"
    read -r -s -p "  Hugging Face token (input hidden): " HF_TOKEN
    echo
    if [[ -z "$HF_TOKEN" ]]; then
      fail "A Hugging Face token is needed to download the models"
      exit 1
    fi
  fi
}

setup_client_env() {
  step "Configuring client environment"
  copy_env_file "$CLIENT_DIR/.env.sample" "$CLIENT_DIR/.env" || true
}

# ---------------------------------------------------------------------------
# Step 3: postgres, redis + localstack via docker compose
# ---------------------------------------------------------------------------

COMPOSE_FILE="$SERVER_DIR/docker-compose.yml"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

# Read KEY from an env file (last occurrence wins, surrounding quotes stripped).
env_get() {
  local file="$1" key="$2"
  KEY="$key" awk '
    index($0, ENVIRON["KEY"] "=") == 1 { v = substr($0, length(ENVIRON["KEY"]) + 2) }
    END {
      if (v ~ /^".*"$/ || v ~ /^\047.*\047$/) v = substr(v, 2, length(v) - 2)
      print v
    }
  ' "$file"
}

# Retry a command until it succeeds or the timeout (seconds) runs out.
wait_for() {
  local label="$1" timeout="$2"; shift 2
  local waited=0
  until "$@" </dev/null >/dev/null 2>&1; do
    if (( waited >= timeout )); then
      fail "$label not ready after ${timeout}s"
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  ok "$label is ready"
}

LOCALSTACK_URL="http://localhost:4566"
LOCALSTACK_REGION="us-east-1"
# S3 bucket names cannot contain '_'. Must match the .env samples.
S3_BUCKETS=(application-bucket)
RAG_INGESTION_QUEUE_NAME="rag-ingestion-queue"

# KMS keys use fixed IDs so the ARNs in the .env samples never change.
# LocalStack forgets keys on restart; the encryption key also gets fixed key
# material so values floware encrypted into postgres stay decryptable. Signing
# keys get fresh material, so existing JWTs stop verifying (log in again).
# LocalStack-only (dev) material, never used against real AWS.
KMS_CONSOLE_SIGN_KEY_ID="00000000-0000-0000-0000-00000000c519"
KMS_SIGN_KEY_ID="00000000-0000-0000-0000-00000000519e"
KMS_ENC_KEY_ID="00000000-0000-0000-0000-00000000e0c1"
KMS_ENC_KEY_MATERIAL="d2F2ZWZyb250LWxvY2Fsc3RhY2stZGV2LWtleS0wMDE="

awslocal() {
  compose exec -T localstack awslocal --region "$LOCALSTACK_REGION" "$@" </dev/null
}

is_localstack_ready() {
  local health
  health="$(curl -fsS --max-time 2 "$LOCALSTACK_URL/_localstack/health" 2>/dev/null)" || return 1
  local service
  for service in s3 sqs kms; do
    grep -Eq "\"$service\": *\"(available|running)\"" <<<"$health" || return 1
  done
}

start_services() {
  step "Starting postgres, redis and localstack (server/docker-compose.yml)"
  compose up -d postgres redis localstack </dev/null
  wait_for "postgres" 60 compose exec -T postgres pg_isready -U postgres
  wait_for "redis" 30 compose exec -T redis redis-cli ping
  wait_for "localstack" 90 is_localstack_ready
}

# Create a service's database (and optional extension) using the DB settings
# in its .env, checking the credentials actually work against docker postgres.
#   setup_database <label> <env_file> <var_prefix> [extension]
setup_database() {
  local label="$1" env_file="$2" prefix="$3" extension="${4:-}"
  step "Preparing $label database"
  local user password host port db
  user="$(env_get "$env_file" "${prefix}USERNAME")"
  password="$(env_get "$env_file" "${prefix}PASSWORD")"
  host="$(env_get "$env_file" "${prefix}HOST")"
  port="$(env_get "$env_file" "${prefix}PORT")"
  db="$(env_get "$env_file" "${prefix}NAME")"

  if [[ "$host" != "localhost" && "$host" != "127.0.0.1" ]]; then
    warn "${prefix}HOST=$host is not local; skipping docker database setup"
    return
  fi

  # The .env port must be the one docker publishes postgres on.
  local published
  published="$(compose port postgres 5432 2>/dev/null | awk -F: '{print $NF}')"
  if [[ "$published" != "$port" ]]; then
    fail "${prefix}PORT=$port but postgres is published on port ${published:-<none>}"
    exit 1
  fi

  # Connect via the container's network hostname: the image trusts localhost
  # connections, but requires a password on the network (as from the host).
  if ! compose exec -T -e PGPASSWORD="$password" postgres \
      psql -h postgres -U "$user" -d postgres -tAc 'SELECT 1' </dev/null >/dev/null 2>&1; then
    fail "Cannot log in to postgres as '$user' with the password from ${env_file#"$ROOT_DIR"/}"
    fail "docker-compose.yml sets POSTGRES_USER/POSTGRES_PASSWORD; make .env match it"
    exit 1
  fi
  ok "Logged in as '$user' using .env credentials"

  compose exec -T -e PGPASSWORD="$password" postgres \
    psql -h postgres -U "$user" -d postgres -v ON_ERROR_STOP=1 -q -v db="$db" >/dev/null <<'SQL'
SELECT format('CREATE DATABASE %I', :'db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db')\gexec
SQL
  ok "Database '$db' exists"

  if [[ -n "$extension" ]]; then
    compose exec -T -e PGPASSWORD="$password" postgres \
      psql -h postgres -U "$user" -d "$db" -v ON_ERROR_STOP=1 -q \
      -c "CREATE EXTENSION IF NOT EXISTS \"$extension\"" </dev/null >/dev/null
    ok "Extension '$extension' enabled"
  fi
  ok "Connect with: postgresql://$user:<password>@$host:$port/$db"
}

setup_localstack_resources() {
  # Required: floconsole and floware sign JWTs with these KMS keys.
  step "Creating AWS resources in LocalStack"

  local bucket
  for bucket in "${S3_BUCKETS[@]}"; do
    if awslocal s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
      ok "S3 bucket '$bucket' exists"
    else
      awslocal s3api create-bucket --bucket "$bucket" >/dev/null
      ok "Created S3 bucket '$bucket'"
    fi
  done

  # create-queue is idempotent and returns the existing queue's URL.
  local queue_url
  queue_url="$(awslocal sqs create-queue --queue-name "$RAG_INGESTION_QUEUE_NAME" \
    --query QueueUrl --output text | tr -d '\r')"
  awslocal sqs get-queue-attributes --queue-url "$queue_url" --attribute-names QueueArn >/dev/null
  ok "SQS queue '$RAG_INGESTION_QUEUE_NAME' is ready: $queue_url"


  ensure_kms_key "$KMS_ENC_KEY_ID" "encryption" --key-usage ENCRYPT_DECRYPT \
    --tags "TagKey=_custom_id_,TagValue=$KMS_ENC_KEY_ID" \
    "TagKey=_custom_key_material_,TagValue=$KMS_ENC_KEY_MATERIAL"
  ensure_kms_key "$KMS_SIGN_KEY_ID" "floware signing" --key-usage SIGN_VERIFY --key-spec RSA_2048 \
    --tags "TagKey=_custom_id_,TagValue=$KMS_SIGN_KEY_ID"
  ensure_kms_key "$KMS_CONSOLE_SIGN_KEY_ID" "floconsole signing" --key-usage SIGN_VERIFY --key-spec RSA_2048 \
    --tags "TagKey=_custom_id_,TagValue=$KMS_CONSOLE_SIGN_KEY_ID"
}

#   ensure_kms_key <key_id> <label> <create-key args...>
ensure_kms_key() {
  local key_id="$1" label="$2"; shift 2
  if awslocal kms describe-key --key-id "$key_id" >/dev/null 2>&1; then
    ok "KMS $label key exists: $key_id"
  else
    awslocal kms create-key "$@" >/dev/null
    ok "Created KMS $label key: $key_id"
  fi
}

# ---------------------------------------------------------------------------
# Step 4: python deps + floconsole and floware servers
# ---------------------------------------------------------------------------

FLOCONSOLE_PORT=8002
FLOCONSOLE_HEALTH_URL="http://localhost:$FLOCONSOLE_PORT/floconsole/v1/health"
FLOWARE_PORT=8001
FLOWARE_HEALTH_URL="http://localhost:$FLOWARE_PORT/floware/v1/health"
INFERENCE_PORT=8003
INFERENCE_HEALTH_URL="http://localhost:$INFERENCE_PORT/inference/v1/health"

install_python_deps() {
  step "Setting up python environment (server/.venv)"
  local venv="$SERVER_DIR/.venv"

  if [[ -d "$venv" ]]; then
    ok "Found existing server/.venv"
  else
    warn "server/.venv does not exist"
    if ! confirm "Create server/.venv and install dependencies?"; then
      fail "The python services need server/.venv to run. Re-run ./setup.sh when ready."
      exit 1
    fi
    # uv picks the interpreter from server/.python-version.
    (cd "$SERVER_DIR" && uv venv)
    ok "Created server/.venv"
  fi

  # Installs every workspace member so later services share one environment.
  (cd "$SERVER_DIR" && uv sync --all-packages --frozen)
  ok "Dependencies installed into server/.venv"
}

# Run a command in a new terminal window so it keeps running after setup exits.
# Falls back to a background process with a log file when no terminal can be opened.
# With TEE_LOG=1 the window's output is also copied to .setup-logs/<title>.log,
# for services whose readiness can only be seen in their output.
#   [TEE_LOG=1] open_in_terminal <title> <dir> <command...>
open_in_terminal() {
  local title="$1" dir="$2"; shift 2
  local launcher log_file
  launcher="$(mktemp "${TMPDIR:-/tmp}/wavefront-${title}.XXXXXX")"
  log_file="$ROOT_DIR/.setup-logs/$title.log"
  mkdir -p "$(dirname "$log_file")"
  : > "$log_file"

  {
    echo '#!/usr/bin/env bash'
    printf 'printf "\\033]0;%%s\\007" %q\n' "$title"
    printf 'cd %q || exit 1\n' "$dir"
    [[ "${TEE_LOG:-0}" == 1 ]] && printf 'exec > >(tee -a %q) 2>&1\n' "$log_file"
    printf '%q ' "$@"; echo
  } > "$launcher"
  chmod +x "$launcher"

  if [[ "$OSTYPE" == darwin* ]]; then
    local app="Terminal"
    [[ "${TERM_PROGRAM:-}" == "iTerm.app" ]] && app="iTerm"
    if [[ "$app" == "iTerm" ]]; then
      osascript -e "tell application \"iTerm\" to create window with default profile command \"$launcher\"" >/dev/null
    else
      osascript -e "tell application \"Terminal\" to do script \"$launcher\"" >/dev/null
    fi
    ok "Started $title in a new $app window"
  elif command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="$title" -- bash -c "$launcher; exec bash"
    ok "Started $title in a new gnome-terminal window"
  elif command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -e bash -c "$launcher; exec bash" &
    ok "Started $title in a new terminal window"
  else
    nohup "$launcher" >> "$log_file" 2>&1 &
    ok "Started $title in the background (pid $!), logs: ${log_file#"$ROOT_DIR"/}"
  fi
}

# True if any socket is bound to the local port, in any state. Checking only
# LISTEN misses a dead server whose parent still holds the port (state CLOSED),
# which makes the next bind fail with "Address already in use".
port_in_use() {
  lsof -nP -iTCP:"$1" -Fn 2>/dev/null | grep -Eq "^n[^-]*:$1(->|$)"
}

# Show the processes holding a port.
show_port_owner() {
  local pid
  for pid in $(lsof -nP -tiTCP:"$1" 2>/dev/null | sort -u); do
    if lsof -nP -a -p "$pid" -iTCP:"$1" -Fn 2>/dev/null | grep -Eq "^n[^-]*:$1(->|$)"; then
      ps -o pid=,command= -p "$pid" | cut -c1-160 | sed 's/^/    /'
    fi
  done
}

is_healthy() {
  curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

# Start `python server.py` for a service in its own terminal and wait for health.
#   start_python_service <name> <dir> <port> <health_url> [timeout_seconds]
start_python_service() {
  local name="$1" dir="$2" port="$3" health_url="$4" timeout="${5:-180}"
  step "Starting $name"

  if is_healthy "$health_url"; then
    ok "$name is already running on port $port"
    return
  fi

  if port_in_use "$port"; then
    fail "Port $port is in use by something that is not a healthy $name:"
    show_port_owner "$port"
    exit 1
  fi

  open_in_terminal "$name" "$dir" uv run --no-sync python server.py

  # First start runs the alembic migrations, so give it a moment.
  if ! wait_for "$name ($health_url)" "$timeout" is_healthy "$health_url"; then
    fail "Check the $name terminal window for errors"
    exit 1
  fi
}

start_floconsole() {
  start_python_service floconsole "$FLOCONSOLE_DIR" "$FLOCONSOLE_PORT" "$FLOCONSOLE_HEALTH_URL"
  ok "Seed login: $(env_get "$FLOCONSOLE_DIR/.env" CONSOLE_EMAIL)"
}

start_floware() {
  start_python_service floware "$FLOWARE_DIR" "$FLOWARE_PORT" "$FLOWARE_HEALTH_URL"
  ok "Seed login: $(env_get "$FLOWARE_DIR/.env" EMAIL)"
}

download_inference_models() {
  (( RUN_INFERENCE_APP )) || return 0
  step "Downloading inference models (scripts/download_models.py)"
  if (( INFERENCE_MOCK )); then
    ok "Mock mode: no models to download"
    return
  fi

  if ! inference_models_missing; then
    ok "Models already downloaded to ${INFERENCE_MODELS_DIR#"$ROOT_DIR"/}"
    return
  fi

  # Token goes through the environment, not argv, so it stays out of `ps`.
  (cd "$INFERENCE_DIR/scripts" && HF_TOKEN="${HF_TOKEN:-}" uv run --no-sync python download_models.py)
  if inference_models_missing; then
    fail "Model download did not complete; check the output above"
    exit 1
  fi
  ok "Models downloaded to ${INFERENCE_MODELS_DIR#"$ROOT_DIR"/}"
}

start_inference_app() {
  (( RUN_INFERENCE_APP )) || return 0
  # Loading CLIP + DINOv3 into memory at startup takes a while (BGE-M3 loads in
  # the background after the app is up). Mock mode starts in seconds.
  start_python_service inference "$INFERENCE_DIR" "$INFERENCE_PORT" "$INFERENCE_HEALTH_URL" 300
}

# Same flags as docker/celery_worker.Dockerfile.
CELERY_CMD=(uv run --no-sync celery -A celery_worker.celery_app worker
  --loglevel=info --pool=solo --without-mingle --without-gossip)
CELERY_LOG="$ROOT_DIR/.setup-logs/celery-worker.log"

is_celery_running() {
  pgrep -f "celery -A celery_worker.celery_app worker" >/dev/null 2>&1
}

# Remote control is disabled in celery_app.py (no `inspect ping`), so readiness
# is celery's "celery@<host> ready." line in the worker's output.
is_celery_ready() {
  grep -q ' ready\.' "$CELERY_LOG" 2>/dev/null
}

start_celery_worker() {
  (( RUN_CELERY_WORKER )) || return 0
  step "Starting celery worker"

  if is_celery_running; then
    ok "celery worker is already running"
    return
  fi

  TEE_LOG=1 open_in_terminal celery-worker "$CELERY_DIR" "${CELERY_CMD[@]}"

  if ! wait_for "celery worker" 120 is_celery_ready; then
    fail "Check the celery-worker terminal window (or ${CELERY_LOG#"$ROOT_DIR"/}) for errors"
    exit 1
  fi
}

# Same command as docker/rag_ingestion.Dockerfile (startup-rag-ingestion.sh).
RAG_CMD=(uv run --no-sync python rag_ingestion/main.py)
RAG_LOG="$ROOT_DIR/.setup-logs/rag-ingestion.log"

is_rag_running() {
  pgrep -f "python rag_ingestion/main.py" >/dev/null 2>&1
}

start_rag_worker() {
  (( RUN_RAG_WORKER )) || return 0
  step "Starting RAG ingestion worker"

  if is_rag_running; then
    ok "RAG ingestion worker is already running"
    return
  fi

  TEE_LOG=1 open_in_terminal rag-ingestion "$RAG_DIR" "${RAG_CMD[@]}"

  # The worker only polls the queue and logs nothing on startup, so treat it as
  # up once it has survived startup (config and import errors exit quickly).
  local waited=0
  until (( waited >= 15 )); do
    sleep 3
    waited=$((waited + 3))
    if (( waited >= 6 )) && ! is_rag_running; then
      fail "RAG ingestion worker exited; check the rag-ingestion window (or ${RAG_LOG#"$ROOT_DIR"/})"
      exit 1
    fi
  done
  ok "RAG ingestion worker is running (polling rag-ingestion-queue)"
}

# ---------------------------------------------------------------------------
# Step 5: web client (vite dev server)
# ---------------------------------------------------------------------------

CLIENT_PORT=5173
CLIENT_URL="http://localhost:$CLIENT_PORT"

install_client_deps() {
  step "Installing client dependencies (pnpm)"

  if [[ ! -d "$CLIENT_DIR/node_modules" ]]; then
    warn "client/node_modules does not exist"
    if ! confirm "Install client dependencies with pnpm?"; then
      fail "The client needs its dependencies to run. Re-run ./setup.sh when ready."
      exit 1
    fi
  fi

  (cd "$CLIENT_DIR" && pnpm install --frozen-lockfile)
  ok "Client dependencies installed"
}

# The dev server serves index.html, so match its title to be sure it is ours.
is_client_up() {
  curl -fsS --max-time 2 "$CLIENT_URL" 2>/dev/null | grep -q '<title>Rootflo Console</title>'
}

start_client() {
  step "Starting web client"

  if is_client_up; then
    ok "Client is already running at $CLIENT_URL"
    return
  fi

  # vite silently moves to the next port when 5173 is taken, so refuse instead.
  if port_in_use "$CLIENT_PORT"; then
    fail "Port $CLIENT_PORT is in use by something that is not the client:"
    show_port_owner "$CLIENT_PORT"
    exit 1
  fi

  open_in_terminal client "$CLIENT_DIR" pnpm run dev

  if wait_for "client ($CLIENT_URL)" 60 is_client_up; then
    ok "Open $CLIENT_URL"
  else
    fail "Check the client terminal window for errors"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Done: next steps
# ---------------------------------------------------------------------------

print_next_steps() {
  local console_env="$FLOCONSOLE_DIR/.env"
  echo
  echo "${GREEN}${BOLD}  ✓ wavefront is running locally${RESET}"
  echo
  echo "    web client   $CLIENT_URL"
  echo "    floconsole   http://localhost:$FLOCONSOLE_PORT"
  echo "    floware      http://localhost:$FLOWARE_PORT"
  if (( RUN_INFERENCE_APP )); then
    if (( INFERENCE_MOCK )); then
      echo "    inference    http://localhost:$INFERENCE_PORT  (mock embeddings)"
    else
      echo "    inference    http://localhost:$INFERENCE_PORT"
    fi
  fi
  (( RUN_CELERY_WORKER )) && echo "    celery       worker on redis://localhost:6379/0"
  (( RUN_RAG_WORKER )) && echo "    rag          worker on the rag-ingestion-queue (LocalStack SQS)"
  echo
  echo "${BOLD}  Next steps${RESET}"
  echo
  echo "  1. Open floconsole in the browser: $CLIENT_URL"
  echo "     Log in as $(env_get "$console_env" CONSOLE_EMAIL) / $(env_get "$console_env" CONSOLE_PASSWORD)"
  echo
  echo "  2. Add floware as a new app: Apps → Create new app"
  echo "       App Name         localhost"
  echo "       Deployment Type  Manual"
  echo "       Public URL       http://localhost:$FLOWARE_PORT"
  echo "       Private URL      http://localhost:$FLOWARE_PORT"
  echo "     (With VITE_APP_ENV=local in client/.env, tick \"Create local app for"
  echo "     development\" to fill these in.)"
  echo
  echo "  3. Enjoy developing locally! 🌊"
  echo
  echo "  Each service runs in its own terminal window; close a window to stop it."
  echo "  Re-run ./setup.sh any time; running services are left as they are."
  echo
}

# ---------------------------------------------------------------------------

main() {
  print_banner
  check_prerequisites
  setup_floconsole_env
  setup_floware_env
  setup_celery_env
  setup_rag_env
  setup_inference_env
  setup_client_env
  start_services
  setup_database floconsole "$FLOCONSOLE_DIR/.env" CONSOLE_DB_
  setup_database floware "$FLOWARE_DIR/.env" DB_ vector
  setup_localstack_resources
  install_python_deps
  start_floconsole
  start_floware
  download_inference_models
  start_inference_app
  start_celery_worker
  start_rag_worker
  install_client_deps
  start_client
  print_next_steps
}

main "$@"
