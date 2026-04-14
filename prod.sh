#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/scripts/prod-like-env.sh"

COMMAND="${1:-status}"
TARGET="${2:-all}"

prodlike_api_pid_file() {
  local index="${1:?instance index is required}"
  printf '%s/api-%s.pid\n' "$DOOWON_PRODLIKE_PID_DIR" "$index"
}

prodlike_api_log_file() {
  local index="${1:?instance index is required}"
  printf '%s/api-%s.log\n' "$DOOWON_PRODLIKE_LOG_DIR" "$index"
}

is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

listening_pid_for_port() {
  local port="${1:?port is required}"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true
}

wait_for_url() {
  local url="${1:?url is required}"
  local label="${2:-$url}"
  local attempts="${3:-60}"
  local delay_seconds="${4:-1}"
  local attempt

  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay_seconds"
  done

  echo "[prod-like] timed out waiting for ${label}" >&2
  return 1
}

api_health_payload() {
  local port="${1:?port is required}"
  curl -fsS "http://127.0.0.1:${port}/healthz"
}

api_instance_id_from_health() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)["instance_id"])'
}

start_api_instance() {
  local index="${1:?instance index is required}"
  local port
  port="$(prodlike_api_port "$index")"
  local pid_file
  pid_file="$(prodlike_api_pid_file "$index")"
  local log_file
  log_file="$(prodlike_api_log_file "$index")"
  local expected_id
  expected_id="$(prodlike_api_name "$index")"

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(tr -d ' \n' <"$pid_file")"
    if is_pid_running "$existing_pid"; then
      echo "[prod-like] api-${index} already running on pid ${existing_pid}"
      return 0
    fi
    rm -f "$pid_file"
  fi

  local port_pid
  port_pid="$(listening_pid_for_port "$port")"
  if [[ -n "$port_pid" ]]; then
    echo "[prod-like] port ${port} is already in use by pid ${port_pid}" >&2
    return 1
  fi

  : >"$log_file"
  local pid
  pid="$(
    PRODLIKE_API_LOG="$log_file" \
    PRODLIKE_API_INDEX="$index" \
    PRODLIKE_API_INSTANCE_ID="$expected_id" \
    ROOT_DIR="$ROOT_DIR" \
    python3 - <<'PY'
import os
import subprocess

log_path = os.environ["PRODLIKE_API_LOG"]
root_dir = os.environ["ROOT_DIR"]
index = os.environ["PRODLIKE_API_INDEX"]
instance_id = os.environ["PRODLIKE_API_INSTANCE_ID"]

with open(log_path, "ab", buffering=0) as log_file:
    proc = subprocess.Popen(
        ["bash", os.path.join(root_dir, "scripts/prod-like-api.sh"), index, instance_id],
        cwd=root_dir,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

print(proc.pid)
PY
  )"
  echo "$pid" >"$pid_file"
  echo "[prod-like] started api-${index} on port ${port} (pid ${pid})"
}

wait_for_api_instance() {
  local index="${1:?instance index is required}"
  local port
  port="$(prodlike_api_port "$index")"
  local expected_id
  expected_id="$(prodlike_api_name "$index")"

  wait_for_url "http://127.0.0.1:${port}/healthz" "api-${index} healthz"

  local actual_id
  actual_id="$(api_health_payload "$port" | api_instance_id_from_health)"
  if [[ "$actual_id" != "$expected_id" ]]; then
    echo "[prod-like] api-${index} responded with unexpected instance id ${actual_id}" >&2
    return 1
  fi
}

stop_api_instance() {
  local index="${1:?instance index is required}"
  local pid_file
  pid_file="$(prodlike_api_pid_file "$index")"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  local pid
  pid="$(tr -d ' \n' <"$pid_file")"
  if ! is_pid_running "$pid"; then
    rm -f "$pid_file"
    return 0
  fi

  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! is_pid_running "$pid"; then
      rm -f "$pid_file"
      echo "[prod-like] stopped api-${index} (pid ${pid})"
      return 0
    fi
    sleep 0.5
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "[prod-like] force-stopped api-${index} (pid ${pid})"
}

build_web() {
  echo "[prod-like] building web"
  (cd "$ROOT_DIR" && pnpm nx build web)
}

start_infra() {
  echo "[prod-like] starting docker infra"
  (cd "$ROOT_DIR" && bash ./scripts/prod-like-infra.sh up)
  if prodlike_use_local_minio; then
    wait_for_url "http://127.0.0.1:${DOOWON_PRODLIKE_MINIO_PORT}/minio/health/live" "minio health"
  fi
}

start_stack() {
  prodlike_ensure_runtime_dirs
  build_web
  start_infra
  wait_for_url "$DOOWON_PRODLIKE_BASE_URL/" "nginx static shell"

  start_api_instance 1
  wait_for_api_instance 1

  echo "[prod-like] seeding dev login accounts"
  (cd "$ROOT_DIR" && bash ./scripts/prod-like-seed-dev-login.sh)

  for instance in $(seq 2 "$DOOWON_PRODLIKE_API_COUNT"); do
    start_api_instance "$instance"
  done
  for instance in $(seq 2 "$DOOWON_PRODLIKE_API_COUNT"); do
    wait_for_api_instance "$instance"
  done

  echo "[prod-like] running smoke"
  (cd "$ROOT_DIR" && bash ./scripts/prod-like-smoke.sh)
}

stop_stack() {
  for instance in $(seq "$DOOWON_PRODLIKE_API_COUNT" -1 1); do
    stop_api_instance "$instance"
  done
  echo "[prod-like] stopping docker infra"
  (cd "$ROOT_DIR" && bash ./scripts/prod-like-infra.sh down)
}

status_stack() {
  local failures=0

  echo "[prod-like] runtime"
  echo "  root: $ROOT_DIR"
  echo "  base_url: $DOOWON_PRODLIKE_BASE_URL"
  echo "  api_count: $DOOWON_PRODLIKE_API_COUNT"
  echo "  runtime_dir: $DOOWON_PRODLIKE_RUNTIME_DIR"

  echo
  echo "[prod-like] web build"
  if [[ -f "$ROOT_DIR/dist/apps/web/index.html" ]]; then
    echo "  dist/apps/web/index.html present"
  else
    echo "  dist/apps/web/index.html missing"
    failures=$((failures + 1))
  fi

  echo
  echo "[prod-like] docker compose"
  (cd "$ROOT_DIR" && docker compose -f compose.prod-like.yml ps) || failures=$((failures + 1))

  echo
  echo "[prod-like] nginx"
  if curl -fsSI "$DOOWON_PRODLIKE_BASE_URL/" >/dev/null 2>&1; then
    echo "  reachable: $DOOWON_PRODLIKE_BASE_URL/"
  else
    echo "  unreachable: $DOOWON_PRODLIKE_BASE_URL/"
    failures=$((failures + 1))
  fi

  echo
  echo "[prod-like] api instances"
  for instance in $(seq 1 "$DOOWON_PRODLIKE_API_COUNT"); do
    local port
    port="$(prodlike_api_port "$instance")"
    local pid_file
    pid_file="$(prodlike_api_pid_file "$instance")"
    local pid_display="missing"
    if [[ -f "$pid_file" ]]; then
      pid_display="$(tr -d ' \n' <"$pid_file")"
      if ! is_pid_running "$pid_display"; then
        pid_display="${pid_display} (stale)"
      fi
    fi

    local health
    if health="$(api_health_payload "$port" 2>/dev/null)"; then
      local instance_id
      instance_id="$(printf '%s' "$health" | api_instance_id_from_health)"
      echo "  api-${instance}: port=${port} pid=${pid_display} health=ok instance_id=${instance_id}"
    else
      echo "  api-${instance}: port=${port} pid=${pid_display} health=down"
      failures=$((failures + 1))
    fi
  done

  echo
  echo "[prod-like] nginx upstream sample"
  local sample_ids
  if sample_ids="$(
    for _ in $(seq 1 16); do
      curl -fsS -D - -o /dev/null "$DOOWON_PRODLIKE_BASE_URL/api/v1/auth/bootstrap-status" \
        | tr -d '\r' \
        | awk -F': ' 'tolower($1)=="x-doowon-instance-id"{print $2}'
    done | sort -u
  )"; then
    if [[ -n "$sample_ids" ]]; then
      printf '  seen instance ids:\n%s\n' "$(printf '%s\n' "$sample_ids" | sed 's/^/    - /')"
    else
      echo "  no proxied instance ids observed"
      failures=$((failures + 1))
    fi
  else
    echo "  failed to query proxied bootstrap-status"
    failures=$((failures + 1))
  fi

  return "$failures"
}

logs_stack() {
  prodlike_ensure_runtime_dirs
  case "$TARGET" in
    all)
      local infra_pid=""
      local api_pid=""
      trap '[[ -n "$infra_pid" ]] && kill "$infra_pid" 2>/dev/null || true; [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
      (
        cd "$ROOT_DIR"
        docker compose -f compose.prod-like.yml logs -f postgres redis minio nginx
      ) &
      infra_pid=$!
      local api_logs=()
      for instance in $(seq 1 "$DOOWON_PRODLIKE_API_COUNT"); do
        local log_file
        log_file="$(prodlike_api_log_file "$instance")"
        touch "$log_file"
        api_logs+=("$log_file")
      done
      tail -F "${api_logs[@]}" &
      api_pid=$!
      wait "$infra_pid" || true
      wait "$api_pid" || true
      ;;
    api-[1-9]|api-10)
      local api_index="${TARGET#api-}"
      local api_log
      api_log="$(prodlike_api_log_file "$api_index")"
      touch "$api_log"
      tail -F "$api_log"
      ;;
    nginx|postgres|redis|minio)
      (
        cd "$ROOT_DIR"
        docker compose -f compose.prod-like.yml logs -f "$TARGET"
      )
      ;;
    *)
      echo "Usage: $0 log [all|api-1..api-8|nginx|postgres|redis|minio]" >&2
      return 1
      ;;
  esac
}

usage() {
  cat <<EOF
Usage: $0 {start|stop|status|log|restart|smoke}

Commands:
  start    Build web, start docker infra, start host api x${DOOWON_PRODLIKE_API_COUNT}, seed dev login, run smoke.
  stop     Stop host api processes and docker infra.
  status   Show web/dist, docker compose, nginx, and api x${DOOWON_PRODLIKE_API_COUNT} status.
  log      Tail logs. Optional target: all|api-1..api-${DOOWON_PRODLIKE_API_COUNT}|nginx|postgres|redis|minio
  restart  Stop then start.
  smoke    Run prod-like smoke checks against the current stack.
EOF
}

case "$COMMAND" in
  start)
    start_stack
    ;;
  stop)
    stop_stack
    ;;
  status)
    status_stack
    ;;
  log)
    logs_stack
    ;;
  restart)
    stop_stack
    start_stack
    ;;
  smoke)
    (cd "$ROOT_DIR" && bash ./scripts/prod-like-smoke.sh)
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
