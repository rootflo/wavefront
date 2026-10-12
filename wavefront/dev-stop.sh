#!/usr/bin/env bash
#
# Stop local wavefront services started by ./dev-start.sh.
#
# Shows a checkbox of apps (pre-checked when they look like they're running),
# then SIGTERM / SIGKILL the matching processes. Optionally stops the docker
# compose stack (postgres, redis, localstack).
#
# Usage: ./dev-stop.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-start.sh
source "$ROOT_DIR/dev-start.sh"

# Listeners on a TCP port (one pid per line).
pids_on_port() {
  lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

# True if compose service container is running.
compose_service_up() {
  local name="$1" state
  state="$(compose ps --status running --services 2>/dev/null | grep -x "$name" || true)"
  [[ -n "$state" ]]
}

# Kill PIDs with TERM, then KILL if they linger.
kill_pids() {
  local label="$1"; shift
  local pids=("$@") pid still=()

  if (( ${#pids[@]} == 0 )); then
    ok "$label not running"
    return 0
  fi

  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done

  local waited=0
  while (( waited < 5 )); do
    still=()
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        still+=("$pid")
      fi
    done
    (( ${#still[@]} == 0 )) && break
    sleep_ms 200
    waited=$((waited + 1))
  done

  if (( ${#still[@]} > 0 )); then
    for pid in "${still[@]}"; do
      kill -9 "$pid" 2>/dev/null || true
    done
    ok "Stopped $label (forced)"
  else
    ok "Stopped $label"
  fi
}

kill_port() {
  local label="$1" port="$2"
  local -a pids=()
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] && pids+=("$line")
  done < <(pids_on_port "$port")
  if (( ${#pids[@]} == 0 )); then
    ok "$label not running (port $port)"
    return 0
  fi
  kill_pids "$label (port $port)" "${pids[@]}"
}

kill_pgrep() {
  local label="$1" pattern="$2"
  local -a pids=()
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] && pids+=("$line")
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
  if (( ${#pids[@]} == 0 )); then
    ok "$label not running"
    return 0
  fi
  kill_pids "$label" "${pids[@]}"
}

stop_docker_stack() {
  step "Stopping docker services"
  if ! command -v docker >/dev/null 2>&1; then
    warn "docker not found; skipped"
    return 0
  fi
  if ! docker info >/dev/null 2>&1; then
    warn "docker daemon not running; skipped"
    return 0
  fi
  if [[ ! -f "$COMPOSE_FILE" ]]; then
    warn "Missing ${COMPOSE_FILE#"$ROOT_DIR"/}; skipped"
    return 0
  fi
  compose stop postgres redis localstack </dev/null
  ok "Stopped postgres, redis and localstack"
}

main_stop() {
  print_banner

  step "Select services to stop"
  hint "Pre-checked items look like they are currently running."

  local -a labels=(
    "floconsole          API + auth console (port 8002)"
    "floware             App runtime API (port 8001)"
    "web client          Vite frontend (port 5173)"
    "celery worker       Async agent and workflow runs"
    "RAG ingestion       Knowledge base document worker"
    "inference app       Image/text embeddings (port 8003)"
    "call processing     Voice call processing (port 8004)"
    "docker stack        postgres, redis, localstack"
  )

  # Default: check whatever appears to be up.
  local d_floconsole=0 d_floware=0 d_client=0 d_celery=0 d_rag=0 d_inference=0 d_call=0 d_docker=0
  [[ -n "$(pids_on_port "$FLOCONSOLE_PORT")" ]] && d_floconsole=1
  [[ -n "$(pids_on_port "$FLOWARE_PORT")" ]] && d_floware=1
  [[ -n "$(pids_on_port "$CLIENT_PORT")" ]] && d_client=1
  pgrep -f "celery -A celery_worker.celery_app worker" >/dev/null 2>&1 && d_celery=1
  pgrep -f "python rag_ingestion/main.py" >/dev/null 2>&1 && d_rag=1
  [[ -n "$(pids_on_port "$INFERENCE_PORT")" ]] && d_inference=1
  [[ -n "$(pids_on_port "$CALL_PROCESSING_PORT")" ]] && d_call=1
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if compose_service_up postgres || compose_service_up redis || compose_service_up localstack; then
      d_docker=1
    fi
  fi

  CHECKBOX_SELECTED=("$d_floconsole" "$d_floware" "$d_client" "$d_celery" "$d_rag" "$d_inference" "$d_call" "$d_docker")
  checkbox_select "${labels[@]}"

  local stop_floconsole=${CHECKBOX_SELECTED[0]}
  local stop_floware=${CHECKBOX_SELECTED[1]}
  local stop_client=${CHECKBOX_SELECTED[2]}
  local stop_celery=${CHECKBOX_SELECTED[3]}
  local stop_rag=${CHECKBOX_SELECTED[4]}
  local stop_inference=${CHECKBOX_SELECTED[5]}
  local stop_call=${CHECKBOX_SELECTED[6]}
  local stop_docker=${CHECKBOX_SELECTED[7]}

  if (( ! stop_floconsole && ! stop_floware && ! stop_client && ! stop_celery && ! stop_rag && ! stop_inference && ! stop_call && ! stop_docker )); then
    warn "Nothing selected — exiting"
    exit 0
  fi

  step "Stopping services"
  (( stop_client )) && kill_port "web client" "$CLIENT_PORT"
  (( stop_floconsole )) && kill_port "floconsole" "$FLOCONSOLE_PORT"
  (( stop_floware )) && kill_port "floware" "$FLOWARE_PORT"
  (( stop_inference )) && kill_port "inference" "$INFERENCE_PORT"
  (( stop_call )) && kill_port "call processing" "$CALL_PROCESSING_PORT"
  (( stop_celery )) && kill_pgrep "celery worker" "celery -A celery_worker.celery_app worker"
  (( stop_rag )) && kill_pgrep "RAG ingestion" "python rag_ingestion/main.py"
  (( stop_docker )) && stop_docker_stack

  echo
  printf '  %s└%s  %s✔ done%s\n' "$MUTED" "$RESET" "$GREEN$BOLD" "$RESET"
  hint "Terminal windows may still be open; you can close them manually."
  hint "Start again with ./dev-start.sh"
  printf '  %s└%s\n' "$MUTED" "$RESET"
  echo
}

main_stop "$@"
