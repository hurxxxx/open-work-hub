#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AIDOO_ENV_PROFILE="${AIDOO_ENV_PROFILE:-vm}"
source "$ROOT_DIR/scripts/dev-env.sh"

COMMAND="${1:-status}"
API_PORT="${DOOWON_VM_API_PORT:-8000}"
WEB_PORT="${DOOWON_VM_WEB_PORT:-4200}"
PUBLIC_URL="${DOOWON_VM_PUBLIC_URL:-https://dwdcc.lumejs.com}"
API_INSTANCE_ID="${DOOWON_VM_API_INSTANCE_ID:-remote-api}"
RUNTIME_DIR="${DOOWON_VM_RUNTIME_DIR:-$ROOT_DIR/.dev}"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

listening_pid() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true
}

stop_group_for_pid() {
  local pid="${1:-}"
  local label="${2:-process}"
  [[ -n "$pid" ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0

  local pgid
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
  [[ -n "$pgid" ]] || return 0
  echo "[vm] stopping $label pid=$pid pgid=$pgid"
  kill -TERM -- "-$pgid" 2>/dev/null || true
  for _ in $(seq 1 40); do
    pgrep -g "$pgid" >/dev/null 2>&1 || return 0
    sleep 0.25
  done
  echo "[vm] force stopping $label pgid=$pgid"
  kill -KILL -- "-$pgid" 2>/dev/null || true
}

wait_for_url() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 60); do
    curl -fsS "$url" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "[vm] timed out waiting for $label" >&2
  return 1
}

start_api() {
  local existing
  existing="$(listening_pid "$API_PORT")"
  if [[ -n "$existing" ]]; then
    echo "[vm] api port $API_PORT already in use by pid $existing" >&2
    return 1
  fi

  : >"$LOG_DIR/api-$API_PORT.log"
  ROOT_DIR="$ROOT_DIR" API_PORT="$API_PORT" API_INSTANCE_ID="$API_INSTANCE_ID" setsid bash -lc '
    cd "$ROOT_DIR/apps/api"
    export DOOWON_API_AUTO_MIGRATE=1
    export DOOWON_API_INSTANCE_ID="$API_INSTANCE_ID"
    exec "$ROOT_DIR/apps/api/.venv/bin/python" -m uvicorn aidoo_api.main:app --app-dir src --host 127.0.0.1 --port "$API_PORT"
  ' >>"$LOG_DIR/api-$API_PORT.log" 2>&1 &
  echo "$!" >"$PID_DIR/api-$API_PORT.pid"
  echo "[vm] started api:$API_PORT pid=$(cat "$PID_DIR/api-$API_PORT.pid")"
  wait_for_url "http://127.0.0.1:$API_PORT/healthz" "api"
}

start_web() {
  local existing
  existing="$(listening_pid "$WEB_PORT")"
  if [[ -n "$existing" ]]; then
    local existing_cmd
    existing_cmd="$(ps -o args= -p "$existing" 2>/dev/null || true)"
    if [[ "$existing_cmd" == *"vite"* ]]; then
      echo "[vm] reusing web:$WEB_PORT pid=$existing"
      echo "$existing" >"$PID_DIR/web-$WEB_PORT.pid"
      wait_for_url "http://127.0.0.1:$WEB_PORT/" "web"
      return 0
    fi

    echo "[vm] web port $WEB_PORT already in use by pid $existing" >&2
    return 1
  fi

  : >"$LOG_DIR/web-$WEB_PORT.log"
  ROOT_DIR="$ROOT_DIR" setsid bash -lc '
    cd "$ROOT_DIR"
    export NX_DAEMON=false
    exec pnpm nx dev web
  ' >>"$LOG_DIR/web-$WEB_PORT.log" 2>&1 &
  echo "$!" >"$PID_DIR/web-$WEB_PORT.pid"
  echo "[vm] started web:$WEB_PORT pid=$(cat "$PID_DIR/web-$WEB_PORT.pid")"
  wait_for_url "http://127.0.0.1:$WEB_PORT/" "web"
}

stop_stack() {
  stop_group_for_pid "$(cat "$PID_DIR/web-$WEB_PORT.pid" 2>/dev/null || true)" "web"
  stop_group_for_pid "$(listening_pid "$WEB_PORT")" "web"
  stop_group_for_pid "$(cat "$PID_DIR/api-$API_PORT.pid" 2>/dev/null || true)" "api"
  stop_group_for_pid "$(listening_pid "$API_PORT")" "api"
  rm -f "$PID_DIR/web-$WEB_PORT.pid" "$PID_DIR/api-$API_PORT.pid"
}

start_stack() {
  start_api
  start_web
}

status_code() {
  curl -sS -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || printf '000'
}

status_stack() {
  echo "[vm] runtime"
  echo "  root: $ROOT_DIR"
  echo "  profile: $AIDOO_ENV_PROFILE"
  echo "  public_url: $PUBLIC_URL"
  echo
  echo "[vm] ports"
  echo "  api:$API_PORT pid=$(listening_pid "$API_PORT")"
  echo "  web:$WEB_PORT pid=$(listening_pid "$WEB_PORT")"
  echo
  echo "[vm] checks"
  echo "  api health: $(status_code "http://127.0.0.1:$API_PORT/healthz")"
  echo "  web shell: $(status_code "http://127.0.0.1:$WEB_PORT/")"
  echo "  collab route: $(status_code "${PUBLIC_URL%/}/api/v1/workspaces/hq/whiteboard/collab/items/probe/session")"
}

case "$COMMAND" in
  start)
    start_stack
    ;;
  stop)
    stop_stack
    ;;
  restart)
    stop_stack
    start_stack
    ;;
  deploy)
    (cd "$ROOT_DIR" && pnpm nx build web)
    stop_stack
    start_stack
    status_stack
    ;;
  status)
    status_stack
    ;;
  log|logs)
    tail -F "$LOG_DIR/api-$API_PORT.log" "$LOG_DIR/web-$WEB_PORT.log"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|deploy|status|log}" >&2
    exit 1
    ;;
esac
