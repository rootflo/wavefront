#!/usr/bin/env bash
#
# Local development setup for wavefront.
#
# Steps:
#   1. Check prerequisites (python >= 3.11, uv, docker, openssl, node, pnpm)
#   2. Ask which apps to start (interactive checkbox: floconsole, floware,
#      web client, celery, RAG ingestion, inference, call processing), then
#      separately whether to replace existing .env files (off by default)
#   3. For each selected app, create its .env from the sample if missing
#      (or replace when that option is on) and ask any follow-ups
#      (Hugging Face token, mismatched secrets, …)
#   4. Start postgres, redis and localstack (server/docker-compose.yml), create
#      databases for selected apps, and create the S3 bucket, SQS queue and KMS
#      signing/encryption keys in localstack
#   5. Install python deps and start the selected python services / workers in
#      new terminal windows (health-check where applicable)
#   6. If selected, install client deps and start the web client (pnpm run dev)
#
# Usage: ./dev-start.sh
#
# Shared helpers may be sourced by ./dev-stop.sh; main only runs when executed
# directly (see the guard at the bottom of this file).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$ROOT_DIR/server"
FLOCONSOLE_DIR="$SERVER_DIR/apps/floconsole/floconsole"
FLOWARE_DIR="$SERVER_DIR/apps/floware/floware"
CELERY_DIR="$SERVER_DIR/background_jobs/celery_worker"
RAG_DIR="$SERVER_DIR/background_jobs/rag_ingestion"
INFERENCE_DIR="$SERVER_DIR/apps/inference_app/inference_app"
CALL_PROCESSING_DIR="$SERVER_DIR/apps/call_processing/call_processing"
CLIENT_DIR="$ROOT_DIR/client"

REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=11
REQUIRED_NODE_MAJOR=20

# ---------------------------------------------------------------------------
# Output helpers
# Style notes: clack/gum-inspired (◆ headings, │ rails, key pills, spinners).
# Respects NO_COLOR and non-TTY. Uses 256-color when available.
# ---------------------------------------------------------------------------

USE_COLOR=0
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]; then
  USE_COLOR=1
fi

if (( USE_COLOR )); then
  RESET=$'\033[0m'
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  # Ocean accent (wavefront) — soft cyan/teal like gum + homebrew freshness
  ACCENT=$'\033[38;5;45m'
  ACCENT_DIM=$'\033[38;5;37m'
  GREEN=$'\033[38;5;114m'
  YELLOW=$'\033[38;5;221m'
  RED=$'\033[38;5;203m'
  MUTED=$'\033[38;5;245m'
  WHITE=$'\033[38;5;255m'
  # Key pills: dark chip + bright label (huh / gum choose)
  KEY_BG=$'\033[48;5;238m'
  KEY_FG=$'\033[38;5;255m'
else
  RESET=''; BOLD=''; DIM=''; ACCENT=''; ACCENT_DIM=''
  GREEN=''; YELLOW=''; RED=''; MUTED=''; WHITE=''
  KEY_BG=''; KEY_FG=''
fi

# Pill for a keyboard shortcut: [ space ]
key() { printf '%s %s %s' "$KEY_BG$KEY_FG$BOLD" "$1" "$RESET"; }

# Dim action label after a key pill
key_action() { printf '%s%s%s' "$MUTED" "$1" "$RESET"; }

# Section heading — clack ◆  Title  with a muted rail underneath
step() {
  echo
  printf '  %s◆%s  %s%s%s\n' "$ACCENT$BOLD" "$RESET" "$BOLD$WHITE" "$*" "$RESET"
  printf '  %s│%s\n' "$MUTED" "$RESET"
}

ok() {
  printf '  %s│%s  %s●%s  %s\n' "$MUTED" "$RESET" "$GREEN" "$RESET" "$*"
}

warn() {
  printf '  %s│%s  %s▲%s  %s%s%s\n' "$MUTED" "$RESET" "$YELLOW" "$RESET" "$YELLOW" "$*" "$RESET"
}

fail() {
  printf '  %s│%s  %s✖%s  %s%s%s\n' "$MUTED" "$RESET" "$RED" "$RESET" "$RED" "$*" "$RESET"
}

info() {
  printf '  %s│%s  %s%s%s\n' "$MUTED" "$RESET" "$MUTED" "$*" "$RESET"
}

hint() {
  printf '  %s│%s  %s%s%s\n' "$MUTED" "$RESET" "$DIM$MUTED" "$*" "$RESET"
}

# Clear current terminal line (for spinner / in-place redraws).
clear_line() { printf '\r\033[2K'; }

# Braille spinner frames (charm / clack)
SPIN_FRAMES=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
SPIN_I=0

spin() {
  if (( ! USE_COLOR )) || [[ ! -t 1 ]]; then
    return
  fi
  clear_line
  printf '  %s│%s  %s%s%s  %s%s%s' \
    "$MUTED" "$RESET" "$ACCENT" "${SPIN_FRAMES[SPIN_I]}" "$RESET" "$MUTED" "$*" "$RESET"
  SPIN_I=$(( (SPIN_I + 1) % ${#SPIN_FRAMES[@]} ))
}

spin_done() {
  # Always return 0 so callers under set -e are not aborted when color/TTY
  # checks fail (a failing `(( USE_COLOR ))` / `[[ -t 1 ]]` in a trailing
  # `&&` chain would otherwise become this function's exit status).
  if (( USE_COLOR )) && [[ -t 1 ]]; then
    clear_line
  fi
}

# Sleep that tolerates missing fractional support.
sleep_ms() {
  local ms="$1"
  if sleep "$(awk "BEGIN { printf \"%.3f\", $ms/1000 }")" 2>/dev/null; then
    return
  fi
  sleep 1
}

print_banner() {
  local -a lines=(
    '██╗    ██╗ █████╗ ██╗   ██╗███████╗███████╗██████╗  ██████╗ ███╗   ██╗████████╗'
    '██║    ██║██╔══██╗██║   ██║██╔════╝██╔════╝██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝'
    '██║ █╗ ██║███████║██║   ██║█████╗  █████╗  ██████╔╝██║   ██║██╔██╗ ██║   ██║   '
    '██║███╗██║██╔══██║╚██╗ ██╔╝██╔══╝  ██╔══╝  ██╔══██╗██║   ██║██║╚██╗██║   ██║   '
    '╚███╔███╔╝██║  ██║ ╚████╔╝ ███████╗██║     ██║  ██║╚██████╔╝██║ ╚████║   ██║   '
    ' ╚══╝╚══╝ ╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   '
  )
  # Gradient through cyan → teal → blue (256-color indices)
  local -a grad=(45 44 43 80 39 33)
  local i
  echo
  for (( i = 0; i < ${#lines[@]}; i++ )); do
    if (( USE_COLOR )); then
      printf '  %s%s%s\n' $'\033[38;5;'"${grad[i]}"m "$BOLD${lines[i]}" "$RESET"
    else
      printf '  %s\n' "${lines[i]}"
    fi
    (( USE_COLOR )) && sleep_ms 35
  done
  printf '  %s%s%*s%s\n' "$MUTED" "$DIM" 74 "by Rootflo" "$RESET"
  printf '  %s%sLocal development setup%s\n' "$ACCENT_DIM" "$DIM" "$RESET"
  printf '  %s────────────────────────────────────────────────────────%s\n' "$MUTED" "$RESET"
}

# Ask a yes/no question. Returns 0 for yes. Default is no.
confirm() {
  local reply
  printf '  %s│%s  %s?%s %s %s[y/N]%s ' \
    "$MUTED" "$RESET" "$ACCENT" "$RESET" "$1" "$MUTED" "$RESET"
  read -r reply
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# Interactive multi-select checkbox menu (bash 3.2-safe; no namerefs).
# Reads/writes the global CHECKBOX_SELECTED array (0/1 flags). Labels are the
# remaining arguments. Requires a TTY; otherwise leaves CHECKBOX_SELECTED as-is.
CHECKBOX_SELECTED=()
checkbox_select() {
  local -a _cs_labels=("$@")
  local n=${#_cs_labels[@]} i=0 key cursor=0
  local hint_lines=2

  if (( n == 0 )); then
    return
  fi
  if (( ${#CHECKBOX_SELECTED[@]} != n )); then
    fail "checkbox_select: CHECKBOX_SELECTED (${#CHECKBOX_SELECTED[@]}) != labels ($n)"
    exit 1
  fi

  if [[ ! -t 0 || ! -t 1 ]]; then
    warn "No interactive terminal; using the default selection"
    return
  fi

  # Hide cursor; restore on EXIT (normal return or abort). INT must exit so
  # Ctrl-C does not get swallowed by `read ... || true` and leave the menu loop
  # running — exit 130, EXIT trap shows the cursor.
  printf '\033[?25l'
  trap 'printf "\033[?25h"' EXIT
  trap 'exit 130' INT

  _cs_draw_hints() {
    printf '  %s│%s  ' "$MUTED" "$RESET"
    key "↑/↓"; printf ' '; key_action "move"; printf '  '
    key "space"; printf ' '; key_action "toggle"; printf '  '
    key "a"; printf ' '; key_action "all"; printf '  '
    key "n"; printf ' '; key_action "none"; printf '  '
    key "enter"; printf ' '; key_action "confirm"
    echo
    printf '  %s│%s\n' "$MUTED" "$RESET"
  }

  _cs_draw() {
    local j mark name desc full
    for (( j = 0; j < n; j++ )); do
      if (( CHECKBOX_SELECTED[j] )); then
        mark="${GREEN}●${RESET}"
      else
        mark="${MUTED}○${RESET}"
      fi
      # Split "name   description" on 2+ spaces when present (bash 3.2-safe).
      full="${_cs_labels[j]}"
      name="$full"
      desc=""
      if [[ "$full" == *"  "* ]]; then
        name="${full%%  *}"
        desc="${full#*  }"
        while [[ "$desc" == ' '* ]]; do desc="${desc# }"; done
      fi
      if (( j == cursor )); then
        printf '  %s│%s %s❯%s %s %s%s%s' \
          "$MUTED" "$RESET" "$ACCENT$BOLD" "$RESET" "$mark" "$BOLD$WHITE" "$name" "$RESET"
        [[ -n "$desc" ]] && printf '  %s%s%s' "$MUTED" "$desc" "$RESET"
        echo
      else
        printf '  %s│%s   %s %s%s%s' \
          "$MUTED" "$RESET" "$mark" "$WHITE" "$name" "$RESET"
        [[ -n "$desc" ]] && printf '  %s%s%s' "$DIM$MUTED" "$desc" "$RESET"
        echo
      fi
    done
  }

  _cs_draw_hints
  _cs_draw

  # Read raw keypresses (arrows are ESC [ A/B).
  while true; do
    IFS= read -r -s -n1 key || true
    case "$key" in
      '') # enter
        break
        ;;
      ' ')
        CHECKBOX_SELECTED[cursor]=$(( 1 - CHECKBOX_SELECTED[cursor] ))
        ;;
      a|A)
        for (( i = 0; i < n; i++ )); do CHECKBOX_SELECTED[i]=1; done
        ;;
      n|N)
        for (( i = 0; i < n; i++ )); do CHECKBOX_SELECTED[i]=0; done
        ;;
      $'\x1b')
        IFS= read -r -s -n1 key || true
        if [[ "$key" == '[' ]]; then
          IFS= read -r -s -n1 key || true
          case "$key" in
            A) if (( cursor > 0 )); then (( cursor-- )) || true; fi ;;
            B) if (( cursor < n - 1 )); then (( cursor++ )) || true; fi ;;
          esac
        fi
        ;;
      k|K) if (( cursor > 0 )); then (( cursor-- )) || true; fi ;;
      j|J) if (( cursor < n - 1 )); then (( cursor++ )) || true; fi ;;
      *) continue ;;
    esac
    # Redraw hints + items in place.
    printf '\033[%dA' "$(( n + hint_lines ))"
    _cs_draw_hints
    _cs_draw
  done

  printf '\033[?25h'
  trap - EXIT INT
  printf '  %s│%s\n' "$MUTED" "$RESET"
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
    fail "Missing prerequisites. Fix the above and re-run ./dev-start.sh"
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

# Copy an example env file to .env.
# If .env already exists: keep it unless REPLACE_ENVS=1 (then backup and replace).
# Returns 0 when a fresh .env was written, 1 when the existing one was kept.
#   copy_env_file <example> <env_file>
copy_env_file() {
  local example="$1" env_file="$2"

  if [[ ! -f "$example" ]]; then
    fail "Missing ${example#"$ROOT_DIR"/}"
    exit 1
  fi

  if [[ -f "$env_file" ]]; then
    if (( ! REPLACE_ENVS )); then
      ok "Keeping existing ${env_file#"$ROOT_DIR"/}"
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

# Which apps to start. Selected up front via checkbox_select; env/setup
# follow-ups for each selected app run afterwards.
RUN_FLOCONSOLE=0
RUN_FLOWARE=0
RUN_CELERY_WORKER=0
RUN_RAG_WORKER=0
RUN_INFERENCE_APP=0
RUN_CALL_PROCESSING=0
RUN_CLIENT=0
REPLACE_ENVS=0

select_apps() {
  step "Select apps to start"
  local -a labels=(
    "floconsole          API + auth console (port 8002)"
    "floware             App runtime API (port 8001)"
    "web client          Vite frontend (port 5173)"
    "celery worker       Async agent and workflow runs"
    "RAG ingestion       Knowledge base document worker"
    "inference app       Image/text embeddings (CLIP, DINOv3, BGE-M3)"
    "call processing     Voice call processing (port 8004)"
  )
  # Defaults: core stack on; optional workers/inference/call processing off.
  CHECKBOX_SELECTED=(1 1 1 0 0 0 0)

  checkbox_select "${labels[@]}"

  RUN_FLOCONSOLE=${CHECKBOX_SELECTED[0]}
  RUN_FLOWARE=${CHECKBOX_SELECTED[1]}
  RUN_CLIENT=${CHECKBOX_SELECTED[2]}
  RUN_CELERY_WORKER=${CHECKBOX_SELECTED[3]}
  RUN_RAG_WORKER=${CHECKBOX_SELECTED[4]}
  RUN_INFERENCE_APP=${CHECKBOX_SELECTED[5]}
  RUN_CALL_PROCESSING=${CHECKBOX_SELECTED[6]}

  if (( ! RUN_FLOCONSOLE && ! RUN_FLOWARE && ! RUN_CELERY_WORKER && ! RUN_RAG_WORKER && ! RUN_INFERENCE_APP && ! RUN_CALL_PROCESSING && ! RUN_CLIENT )); then
    fail "No apps selected. Re-run ./dev-start.sh and pick at least one."
    exit 1
  fi

  # Soft dependency hints (do not auto-enable; just warn).
  if (( RUN_FLOWARE && ! RUN_FLOCONSOLE )); then
    warn "floware is usually paired with floconsole (PASSTHROUGH_SECRET / proxying)"
  fi
  if (( RUN_RAG_WORKER && ! RUN_FLOWARE )); then
    warn "RAG ingestion calls floware; floware should be running (and its .env present)"
  fi
  if (( RUN_CALL_PROCESSING && ! RUN_FLOWARE )); then
    warn "call processing calls floware; floware should be running (and its .env present)"
  fi
  if (( RUN_CLIENT && ! RUN_FLOCONSOLE )); then
    warn "web client talks to floconsole; floconsole should be running"
  fi

  local -a chosen=()
  (( RUN_FLOCONSOLE )) && chosen+=("floconsole")
  (( RUN_FLOWARE )) && chosen+=("floware")
  (( RUN_CLIENT )) && chosen+=("client")
  (( RUN_CELERY_WORKER )) && chosen+=("celery")
  (( RUN_RAG_WORKER )) && chosen+=("rag")
  (( RUN_INFERENCE_APP )) && chosen+=("inference")
  (( RUN_CALL_PROCESSING )) && chosen+=("call-processing")
  ok "Will start: ${chosen[*]}"

  # Separate from app selection — opt-in, always defaults off.
  step "Env options"
  hint "Existing .env files are kept unless you opt in below."
  CHECKBOX_SELECTED=(0)
  checkbox_select "replace .env files   Recreate from samples (backs up existing)"
  REPLACE_ENVS=${CHECKBOX_SELECTED[0]}
  if (( REPLACE_ENVS )); then
    ok "Will replace existing .env files from samples (with backups)"
  else
    ok "Will keep existing .env files"
  fi
}

# True if any python server / worker was selected (needs .venv + docker services).
needs_python_stack() {
  (( RUN_FLOCONSOLE || RUN_FLOWARE || RUN_CELERY_WORKER || RUN_RAG_WORKER || RUN_INFERENCE_APP || RUN_CALL_PROCESSING ))
}

setup_floconsole_env() {
  (( RUN_FLOCONSOLE )) || return 0
  step "Configuring floconsole environment"
  local env_file="$FLOCONSOLE_DIR/.env"

  copy_env_file "$FLOCONSOLE_DIR/.env.example" "$env_file" || return 0
  set_env_value "$env_file" PASSTHROUGH_SECRET "$(openssl rand -hex 32)"
  chmod 600 "$env_file"
  ok "Generated PASSTHROUGH_SECRET"
}

setup_floware_env() {
  (( RUN_FLOWARE )) || return 0
  step "Configuring floware environment"
  local env_file="$FLOWARE_DIR/.env"
  local console_secret=""

  if [[ -f "$FLOCONSOLE_DIR/.env" ]]; then
    console_secret="$(env_get "$FLOCONSOLE_DIR/.env" PASSTHROUGH_SECRET)"
  fi

  if copy_env_file "$FLOWARE_DIR/.env.sample" "$env_file"; then
    if [[ -n "$console_secret" ]]; then
      # floconsole proxies to floware with this secret, so they must match.
      set_env_value "$env_file" PASSTHROUGH_SECRET "$console_secret"
      chmod 600 "$env_file"
      ok "Copied PASSTHROUGH_SECRET from floconsole"
    else
      chmod 600 "$env_file"
      warn "floconsole .env not found; left PASSTHROUGH_SECRET from the sample"
    fi
  elif [[ -n "$console_secret" && "$(env_get "$env_file" PASSTHROUGH_SECRET)" != "$console_secret" ]]; then
    warn "PASSTHROUGH_SECRET differs from floconsole's .env; floconsole cannot reach floware"
  fi
}

setup_celery_env() {
  (( RUN_CELERY_WORKER )) || return 0
  step "Configuring celery worker environment"
  copy_env_file "$CELERY_DIR/celery_worker/.env.sample" "$CELERY_DIR/celery_worker/.env" || true
}

setup_rag_env() {
  (( RUN_RAG_WORKER )) || return 0
  step "Configuring RAG ingestion worker environment"

  local env_file="$RAG_DIR/rag_ingestion/.env"
  local floware_secret=""
  if [[ -f "$FLOWARE_DIR/.env" ]]; then
    floware_secret="$(env_get "$FLOWARE_DIR/.env" PASSTHROUGH_SECRET)"
  fi

  if copy_env_file "$RAG_DIR/rag_ingestion/.env.sample" "$env_file"; then
    if [[ -n "$floware_secret" ]]; then
      # The worker calls floware back with this secret, so they must match.
      set_env_value "$env_file" PASSTHROUGH_SECRET "$floware_secret"
      chmod 600 "$env_file"
      ok "Copied PASSTHROUGH_SECRET from floware"
    else
      chmod 600 "$env_file"
      warn "floware .env not found; left PASSTHROUGH_SECRET from the sample"
    fi
  elif [[ -n "$floware_secret" && "$(env_get "$env_file" PASSTHROUGH_SECRET)" != "$floware_secret" ]]; then
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
  (( RUN_INFERENCE_APP )) || return 0
  step "Configuring inference app environment"
  local env_file="$INFERENCE_DIR/.env" entry var

  if is_intel_mac; then
    hint "Intel Mac: PyTorch has no build here at the supported version (>= 2.6), so"
    hint "the inference app runs in mock mode: the same API returning synthetic"
    hint "embeddings, for integration testing. Search results won't be meaningful."
    hint "Use Apple Silicon or Linux for real embeddings."
    INFERENCE_MOCK=1
    copy_env_file "$INFERENCE_DIR/.env.sample" "$env_file" || true
    return
  fi

  hint "All three models together need roughly 4-5 GB of free memory."
  hint "First run downloads several GB of models from Hugging Face."

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
    hint "The models are downloaded from Hugging Face. DINOv3 is gated: accept its"
    hint "license at https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m"
    hint "and create a read token at https://huggingface.co/settings/tokens"
    printf '  %s│%s  %sHugging Face token%s %s(input hidden)%s: ' \
      "$MUTED" "$RESET" "$BOLD$WHITE" "$RESET" "$MUTED" "$RESET"
    read -r -s HF_TOKEN
    echo
    if [[ -z "$HF_TOKEN" ]]; then
      fail "A Hugging Face token is needed to download the models"
      exit 1
    fi
  fi
}

setup_call_processing_env() {
  (( RUN_CALL_PROCESSING )) || return 0
  step "Configuring call processing environment"

  local env_file="$CALL_PROCESSING_DIR/.env"
  local floware_secret=""
  if [[ -f "$FLOWARE_DIR/.env" ]]; then
    floware_secret="$(env_get "$FLOWARE_DIR/.env" PASSTHROUGH_SECRET)"
  fi

  if copy_env_file "$CALL_PROCESSING_DIR/.env.sample" "$env_file"; then
    if [[ -n "$floware_secret" ]]; then
      # Calls floware with this secret, so they must match.
      set_env_value "$env_file" PASSTHROUGH_SECRET "$floware_secret"
      chmod 600 "$env_file"
      ok "Copied PASSTHROUGH_SECRET from floware"
    else
      chmod 600 "$env_file"
      warn "floware .env not found; left PASSTHROUGH_SECRET from the sample"
    fi
  elif [[ -n "$floware_secret" && "$(env_get "$env_file" PASSTHROUGH_SECRET)" != "$floware_secret" ]]; then
    warn "PASSTHROUGH_SECRET differs from floware's .env; call processing cannot call floware"
    if confirm "Update it in ${env_file#"$ROOT_DIR"/} to match floware?"; then
      set_env_value "$env_file" PASSTHROUGH_SECRET "$floware_secret"
      ok "Synced PASSTHROUGH_SECRET from floware"
    else
      RUN_CALL_PROCESSING=0
      warn "Skipping call processing: it cannot run with a mismatched secret"
      return
    fi
  fi

  # Point floware at this service when both are selected.
  if (( RUN_FLOWARE )) && [[ -f "$FLOWARE_DIR/.env" ]]; then
    if [[ -z "$(env_get "$FLOWARE_DIR/.env" CALL_PROCESSING_BASE_URL)" ]]; then
      set_env_value "$FLOWARE_DIR/.env" CALL_PROCESSING_BASE_URL "http://localhost:8004"
      ok "Set floware CALL_PROCESSING_BASE_URL=http://localhost:8004"
    fi
  fi
}

setup_client_env() {
  (( RUN_CLIENT )) || return 0
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
# Shows a braille spinner while waiting when stdout is a color TTY.
wait_for() {
  local label="$1" timeout="$2"; shift 2
  local waited=0 tick
  until "$@" </dev/null >/dev/null 2>&1; do
    if (( waited >= timeout )); then
      spin_done
      fail "$label not ready after ${timeout}s"
      return 1
    fi
    # Spin for ~2s (20 × 100ms), re-checking the condition each tick when possible.
    for tick in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      spin "waiting for ${label}…  ${waited}s / ${timeout}s"
      sleep_ms 100
      if "$@" </dev/null >/dev/null 2>&1; then
        spin_done
        ok "$label is ready"
        return 0
      fi
    done
    waited=$((waited + 2))
  done
  spin_done
  ok "$label is ready"
}

LOCALSTACK_URL="http://localhost:4566"
LOCALSTACK_REGION="us-east-1"
# S3 bucket names cannot contain '_'. Must match APPLICATION_BUCKET in the .env samples.
S3_BUCKETS=(application-bucket)
RAG_INGESTION_QUEUE_NAME="rag-ingestion-queue"

# KMS keys use fixed IDs so the KMS_*_KEY ARNs in the .env samples never change.
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
  needs_python_stack || return 0
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
  needs_python_stack || return 0
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

# Warn when an .env points at a LocalStack resource dev-start.sh did not create
# (e.g. an older .env that predates a renamed variable).
#   check_env_resource <env_file> <var> <expected suffix> <label>
check_env_resource() {
  local env_file="$1" var="$2" suffix="$3" label="$4" value
  [[ -f "$env_file" ]] || return 0
  value="$(env_get "$env_file" "$var")"
  if [[ -z "$value" ]]; then
    warn "$var is not set in ${env_file#"$ROOT_DIR"/} ($label)"
  elif [[ "$value" != *"$suffix" ]]; then
    warn "$var in ${env_file#"$ROOT_DIR"/} does not point at the $label dev-start.sh created ($suffix)"
  fi
}

check_localstack_env() {
  needs_python_stack || return 0
  step "Checking .env files against the LocalStack resources"
  local floware_env="$FLOWARE_DIR/.env"
  local bucket="${S3_BUCKETS[0]}"

  if (( RUN_FLOCONSOLE )); then
    check_env_resource "$FLOCONSOLE_DIR/.env" KMS_SIGNING_KEY "$KMS_CONSOLE_SIGN_KEY_ID" "floconsole signing key"
  fi
  if (( RUN_FLOWARE )); then
    check_env_resource "$floware_env" KMS_SIGNING_KEY "$KMS_SIGN_KEY_ID" "floware signing key"
    check_env_resource "$floware_env" KMS_ENCRYPTION_KEY "$KMS_ENC_KEY_ID" "encryption key"
    check_env_resource "$floware_env" APPLICATION_BUCKET "$bucket" "S3 bucket"
    check_env_resource "$floware_env" RAG_QUEUE "/$RAG_INGESTION_QUEUE_NAME" "SQS queue"
  fi
  if (( RUN_CELERY_WORKER )); then
    check_env_resource "$CELERY_DIR/celery_worker/.env" APPLICATION_BUCKET "$bucket" "S3 bucket"
  fi
  if (( RUN_RAG_WORKER )); then
    check_env_resource "$RAG_DIR/rag_ingestion/.env" RAG_QUEUE "/$RAG_INGESTION_QUEUE_NAME" "SQS queue"
  fi
  ok "Checked"
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
CALL_PROCESSING_PORT=8004
CALL_PROCESSING_HEALTH_URL="http://localhost:$CALL_PROCESSING_PORT/health"

install_python_deps() {
  needs_python_stack || return 0
  step "Setting up python environment (server/.venv)"
  local venv="$SERVER_DIR/.venv"

  if [[ -d "$venv" ]]; then
    ok "Found existing server/.venv"
  else
    warn "server/.venv does not exist"
    if ! confirm "Create server/.venv and install dependencies?"; then
      fail "The python services need server/.venv to run. Re-run ./dev-start.sh when ready."
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
  (( RUN_FLOCONSOLE )) || return 0
  start_python_service floconsole "$FLOCONSOLE_DIR" "$FLOCONSOLE_PORT" "$FLOCONSOLE_HEALTH_URL"
  ok "Seed login: $(env_get "$FLOCONSOLE_DIR/.env" CONSOLE_EMAIL)"
}

start_floware() {
  (( RUN_FLOWARE )) || return 0
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

start_call_processing() {
  (( RUN_CALL_PROCESSING )) || return 0
  start_python_service call-processing "$CALL_PROCESSING_DIR" "$CALL_PROCESSING_PORT" "$CALL_PROCESSING_HEALTH_URL"
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
  (( RUN_CLIENT )) || return 0
  step "Installing client dependencies (pnpm)"

  if [[ ! -d "$CLIENT_DIR/node_modules" ]]; then
    warn "client/node_modules does not exist"
    if ! confirm "Install client dependencies with pnpm?"; then
      fail "The client needs its dependencies to run. Re-run ./dev-start.sh when ready."
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
  (( RUN_CLIENT )) || return 0
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
  local console_env="$FLOCONSOLE_DIR/.env" step_n=1
  echo
  printf '  %s└%s  %s✔ wavefront is running locally%s\n' \
    "$MUTED" "$RESET" "$GREEN$BOLD" "$RESET"
  echo
  _svc_line() {
    printf '     %s%-12s%s %s%s%s\n' "$MUTED" "$1" "$RESET" "$ACCENT" "$2" "$RESET"
  }
  (( RUN_CLIENT )) && _svc_line "web client" "$CLIENT_URL"
  (( RUN_FLOCONSOLE )) && _svc_line "floconsole" "http://localhost:$FLOCONSOLE_PORT"
  (( RUN_FLOWARE )) && _svc_line "floware" "http://localhost:$FLOWARE_PORT"
  if (( RUN_INFERENCE_APP )); then
    if (( INFERENCE_MOCK )); then
      _svc_line "inference" "http://localhost:$INFERENCE_PORT  (mock embeddings)"
    else
      _svc_line "inference" "http://localhost:$INFERENCE_PORT"
    fi
  fi
  (( RUN_CALL_PROCESSING )) && _svc_line "call-proc" "http://localhost:$CALL_PROCESSING_PORT"
  (( RUN_CELERY_WORKER )) && _svc_line "celery" "worker on redis://localhost:6379/0"
  (( RUN_RAG_WORKER )) && _svc_line "rag" "worker on the rag-ingestion-queue (LocalStack SQS)"
  echo
  printf '  %s◆%s  %sNext steps%s\n' "$ACCENT$BOLD" "$RESET" "$BOLD$WHITE" "$RESET"
  printf '  %s│%s\n' "$MUTED" "$RESET"
  if (( RUN_CLIENT && RUN_FLOCONSOLE )); then
    printf '  %s│%s  %s%d.%s Open floconsole in the browser: %s%s%s\n' \
      "$MUTED" "$RESET" "$ACCENT$BOLD" "$step_n" "$RESET" "$ACCENT" "$CLIENT_URL" "$RESET"
    hint "Log in as $(env_get "$console_env" CONSOLE_EMAIL) / $(env_get "$console_env" CONSOLE_PASSWORD)"
    printf '  %s│%s\n' "$MUTED" "$RESET"
    step_n=$((step_n + 1))
  fi
  if (( RUN_FLOCONSOLE && RUN_FLOWARE )); then
    printf '  %s│%s  %s%d.%s Add floware as a new app: %sApps → Create new app%s\n' \
      "$MUTED" "$RESET" "$ACCENT$BOLD" "$step_n" "$RESET" "$BOLD" "$RESET"
    hint "App Name         localhost"
    hint "Deployment Type  Manual"
    hint "Public URL       http://localhost:$FLOWARE_PORT"
    hint "Private URL      http://localhost:$FLOWARE_PORT"
    hint "With VITE_APP_ENV=local in client/.env, tick \"Create local app for development\"."
    printf '  %s│%s\n' "$MUTED" "$RESET"
    step_n=$((step_n + 1))
  fi
  printf '  %s│%s  %s%d.%s Enjoy developing locally! 🌊\n' \
    "$MUTED" "$RESET" "$ACCENT$BOLD" "$step_n" "$RESET"
  printf '  %s│%s\n' "$MUTED" "$RESET"
  hint "Each service runs in its own terminal window; close a window to stop it."
  hint "Re-run ./dev-start.sh any time; running services are left as they are."
  hint "Stop local apps with ./dev-stop.sh"
  printf '  %s└%s\n' "$MUTED" "$RESET"
  echo
}

# ---------------------------------------------------------------------------

main() {
  print_banner
  check_prerequisites
  # Pick apps first; env and follow-up prompts for each selection come after.
  select_apps
  setup_floconsole_env
  setup_floware_env
  setup_celery_env
  setup_rag_env
  setup_inference_env
  setup_call_processing_env
  setup_client_env
  start_services
  if (( RUN_FLOCONSOLE )); then
    setup_database floconsole "$FLOCONSOLE_DIR/.env" CONSOLE_DB_
  fi
  if (( RUN_FLOWARE )); then
    setup_database floware "$FLOWARE_DIR/.env" DB_ vector
  fi
  setup_localstack_resources
  check_localstack_env
  install_python_deps
  start_floconsole
  start_floware
  start_call_processing
  download_inference_models
  start_inference_app
  start_celery_worker
  start_rag_worker
  install_client_deps
  start_client
  print_next_steps
}

# Only run setup main when executed directly (not when sourced by dev-stop.sh).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
