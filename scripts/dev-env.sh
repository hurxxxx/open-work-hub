#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

dev_load_dotenv() {
  local env_file="${1:?env file is required}"
  [[ -f "$env_file" ]] || return 0

  local python_bin="${ROOT_DIR}/apps/api/.venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    python_bin="$(command -v python3)"
  fi

  eval "$(
    DEV_ENV_FILE="$env_file" "$python_bin" - <<'PY'
import os
import pathlib
import shlex

path = pathlib.Path(os.environ["DEV_ENV_FILE"])
for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key == "AIDOO_ENV_PROFILE" and key in os.environ:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
  )"
}

dev_lower() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

dev_load_dotenv "$ROOT_DIR/.env"

export DOOWON_DEV_API_COUNT="${DOOWON_DEV_API_COUNT:-8}"
export DOOWON_DEV_NGINX_PORT="${DOOWON_DEV_NGINX_PORT:-4200}"
export DOOWON_DEV_POSTGRES_PORT="${DOOWON_DEV_POSTGRES_PORT:-55432}"
export DOOWON_DEV_REDIS_PORT="${DOOWON_DEV_REDIS_PORT:-56379}"
export DOOWON_DEV_REDIS_URL="${DOOWON_DEV_REDIS_URL:-redis://127.0.0.1:${DOOWON_DEV_REDIS_PORT}/0}"
export DOOWON_DEV_REDIS_RESULT_BACKEND="${DOOWON_DEV_REDIS_RESULT_BACKEND:-redis://127.0.0.1:${DOOWON_DEV_REDIS_PORT}/1}"
export DOOWON_DEV_COLLAB_REDIS_URL="${DOOWON_DEV_COLLAB_REDIS_URL:-$DOOWON_DEV_REDIS_URL}"
export DOOWON_DEV_WORKER_BROKER_URL="${DOOWON_DEV_WORKER_BROKER_URL:-$DOOWON_DEV_REDIS_URL}"
export DOOWON_DEV_WORKER_RESULT_BACKEND="${DOOWON_DEV_WORKER_RESULT_BACKEND:-$DOOWON_DEV_REDIS_RESULT_BACKEND}"
export DOOWON_DEV_MINIO_PORT="${DOOWON_DEV_MINIO_PORT:-59000}"
export DOOWON_DEV_MINIO_CONSOLE_PORT="${DOOWON_DEV_MINIO_CONSOLE_PORT:-59001}"
export DOOWON_DEV_USE_LOCAL_POSTGRES="${DOOWON_DEV_USE_LOCAL_POSTGRES:-auto}"
export DOOWON_DEV_USE_LOCAL_MINIO="${DOOWON_DEV_USE_LOCAL_MINIO:-auto}"
export DOOWON_DEV_BASE_URL="${DOOWON_DEV_BASE_URL:-http://127.0.0.1:${DOOWON_DEV_NGINX_PORT}}"
export DOOWON_DEV_RUNTIME_DIR="${DOOWON_DEV_RUNTIME_DIR:-$ROOT_DIR/.dev}"
export DOOWON_DEV_PID_DIR="${DOOWON_DEV_PID_DIR:-$DOOWON_DEV_RUNTIME_DIR/pids}"
export DOOWON_DEV_LOG_DIR="${DOOWON_DEV_LOG_DIR:-$DOOWON_DEV_RUNTIME_DIR/logs}"
export DOOWON_DEV_NGINX_CONF_TEMPLATE_PATH="${DOOWON_DEV_NGINX_CONF_TEMPLATE_PATH:-$ROOT_DIR/ops/dev/nginx.conf.template}"
export DOOWON_DEV_NGINX_CONF_PATH="${DOOWON_DEV_NGINX_CONF_PATH:-$DOOWON_DEV_RUNTIME_DIR/nginx.conf}"
export AIDOO_ENV_PROFILE="${AIDOO_ENV_PROFILE:-local}"

export DOOWON_POSTGRES_DSN="${DOOWON_POSTGRES_DSN:-postgresql+psycopg://aidoo_db:aidoo_db@127.0.0.1:${DOOWON_DEV_POSTGRES_PORT}/doowon_ai_portal}"
export DOOWON_REDIS_URL="$DOOWON_DEV_REDIS_URL"
export DOOWON_API_COLLAB_REDIS_URL="$DOOWON_DEV_COLLAB_REDIS_URL"
export DOOWON_WORKER_BROKER_URL="$DOOWON_DEV_WORKER_BROKER_URL"
export DOOWON_WORKER_RESULT_BACKEND="$DOOWON_DEV_WORKER_RESULT_BACKEND"
export DOOWON_MINIO_ENDPOINT="${DOOWON_MINIO_ENDPOINT:-http://127.0.0.1:${DOOWON_DEV_MINIO_PORT}}"
export DOOWON_MINIO_ACCESS_KEY="${DOOWON_MINIO_ACCESS_KEY:-minioadmin}"
export DOOWON_MINIO_SECRET_KEY="${DOOWON_MINIO_SECRET_KEY:-minioadmin}"
export DOOWON_MINIO_BUCKET="${DOOWON_MINIO_BUCKET:-aidoo-portal}"
export DOOWON_LLM_HEALTHCHECK_ON_STARTUP="${DOOWON_LLM_HEALTHCHECK_ON_STARTUP:-0}"
export DOOWON_LLM_REQUIRED="${DOOWON_LLM_REQUIRED:-0}"
export DOOWON_API_ALLOW_DEV_ADMIN_LOGIN="${DOOWON_API_ALLOW_DEV_ADMIN_LOGIN:-1}"
export DOOWON_IMAGE_API_KEY="${DOOWON_IMAGE_API_KEY:-${OPENAI_API_KEY:-}}"

dev_docker() {
  case "$AIDOO_ENV_PROFILE" in
    local|"")
      docker "$@"
      ;;
    vm)
      if docker info >/dev/null 2>&1; then
        docker "$@"
      elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
        sudo -n docker "$@"
      else
        docker "$@"
      fi
      ;;
    prod|production)
      echo "[dev] AIDOO_ENV_PROFILE=$AIDOO_ENV_PROFILE is not supported for dev docker commands" >&2
      return 1
      ;;
    *)
      echo "[dev] invalid AIDOO_ENV_PROFILE: $AIDOO_ENV_PROFILE (expected local, vm, prod)" >&2
      return 1
      ;;
  esac
}

dev_docker_available() {
  dev_docker info >/dev/null 2>&1
}

dev_compose_file() {
  case "$AIDOO_ENV_PROFILE" in
    vm)
      printf '%s/compose.dev.host.yml\n' "$ROOT_DIR"
      ;;
    *)
      printf '%s/compose.dev.yml\n' "$ROOT_DIR"
      ;;
  esac
}

dev_api_port() {
  local index="${1:?instance index is required}"
  printf '%s\n' "$((8000 + index))"
}

dev_api_name() {
  local index="${1:?instance index is required}"
  printf 'dev-api-%s\n' "$index"
}

dev_ensure_runtime_dirs() {
  mkdir -p "$DOOWON_DEV_RUNTIME_DIR" "$DOOWON_DEV_PID_DIR" "$DOOWON_DEV_LOG_DIR"
}

dev_detect_api_upstream_host() {
  dev_docker run --rm --add-host=dev-host:host-gateway nginx:1.27-alpine \
    sh -lc "grep -m1 -E '^[0-9]+(\\.[0-9]+){3}[[:space:]]+dev-host([[:space:]]|\$)' /etc/hosts | awk '{print \$1}'"
}

dev_render_nginx_conf() {
  dev_ensure_runtime_dirs
  local upstream_host
  local listen_port
  if [[ "$AIDOO_ENV_PROFILE" == "vm" ]]; then
    upstream_host="127.0.0.1"
    listen_port="$DOOWON_DEV_NGINX_PORT"
  else
    upstream_host="$(dev_detect_api_upstream_host)"
    listen_port="80"
    if [[ -z "$upstream_host" ]]; then
      echo "[dev] failed to detect Docker host gateway IPv4 for nginx upstream" >&2
      return 1
    fi
  fi

  DEV_NGINX_TEMPLATE="$DOOWON_DEV_NGINX_CONF_TEMPLATE_PATH" \
  DEV_NGINX_OUTPUT="$DOOWON_DEV_NGINX_CONF_PATH" \
  DEV_API_UPSTREAM_HOST="$upstream_host" \
  DEV_NGINX_LISTEN_PORT="$listen_port" \
  python3 - <<'PY'
import os
from pathlib import Path

template = Path(os.environ["DEV_NGINX_TEMPLATE"]).read_text(encoding="utf-8")
rendered = (
    template
    .replace("__DOOWON_DEV_API_UPSTREAM_HOST__", os.environ["DEV_API_UPSTREAM_HOST"])
    .replace("__DOOWON_DEV_NGINX_LISTEN_PORT__", os.environ["DEV_NGINX_LISTEN_PORT"])
)
Path(os.environ["DEV_NGINX_OUTPUT"]).write_text(rendered, encoding="utf-8")
PY
}

dev_use_local_postgres() {
  case "$(dev_lower "$DOOWON_DEV_USE_LOCAL_POSTGRES")" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if [[ "$DOOWON_POSTGRES_DSN" == *"@127.0.0.1:${DOOWON_DEV_POSTGRES_PORT}/"* ]] || \
         [[ "$DOOWON_POSTGRES_DSN" == *"@localhost:${DOOWON_DEV_POSTGRES_PORT}/"* ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[dev] invalid DOOWON_DEV_USE_LOCAL_POSTGRES: $DOOWON_DEV_USE_LOCAL_POSTGRES" >&2
      return 1
      ;;
  esac
}

dev_use_local_minio() {
  case "$(dev_lower "$DOOWON_DEV_USE_LOCAL_MINIO")" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if [[ "$DOOWON_MINIO_ENDPOINT" == *"127.0.0.1:${DOOWON_DEV_MINIO_PORT}"* ]] || \
         [[ "$DOOWON_MINIO_ENDPOINT" == *"localhost:${DOOWON_DEV_MINIO_PORT}"* ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[dev] invalid DOOWON_DEV_USE_LOCAL_MINIO: $DOOWON_DEV_USE_LOCAL_MINIO" >&2
      return 1
      ;;
  esac
}
