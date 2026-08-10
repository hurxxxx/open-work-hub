#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

dev_python_bin() {
  local python_bin="${ROOT_DIR}/apps/api/.venv/bin/python"
  if [[ -x "$python_bin" ]]; then
    printf '%s\n' "$python_bin"
  else
    command -v python3
  fi
}

dev_load_dotenv() {
  local env_file="${1:?env file is required}"
  [[ -f "$env_file" ]] || return 0

  local python_bin
  python_bin="$(dev_python_bin)"

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
    if key == "AI_DO_ENV_PROFILE" and key in os.environ:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
  )"
}

dev_export_ai_do_desktop_installer_defaults() {
  local python_bin
  python_bin="$(dev_python_bin)"

  eval "$(
    ROOT_DIR="$ROOT_DIR" "$python_bin" - <<'PY'
import json
import os
import pathlib
import shlex

root = pathlib.Path(os.environ["ROOT_DIR"])
manifest = json.loads(
    (root / "packages" / "contracts" / "ai-do-desktop-update-feed.manifest.json").read_text(
        encoding="utf-8"
    )
)
feed_path_prefix = manifest["feedPathPrefix"]
win_env_name = None
win_default_url = None

for platform in manifest["platformOrder"]:
    config = manifest["platforms"][platform]
    env_name = config["installerUrlEnv"]
    default_url = f'{feed_path_prefix}/{platform}/{config["installerStableCopy"]}'
    if not os.environ.get(env_name):
        print(f"export {env_name}={shlex.quote(default_url)}")
    if platform == "win":
        win_env_name = env_name
        win_default_url = default_url

fallback_url = os.environ.get(str(win_env_name)) if win_env_name else win_default_url
if not fallback_url:
    fallback_url = win_default_url
if fallback_url and not os.environ.get("VITE_AI_DO_DESKTOP_INSTALLER_URL"):
    print(f"export VITE_AI_DO_DESKTOP_INSTALLER_URL={shlex.quote(fallback_url)}")
PY
  )"
}

dev_lower() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

if [[ "${AI_DO_SKIP_DOTENV:-0}" != "1" ]]; then
  dev_load_dotenv "$ROOT_DIR/.env"
fi

export AI_DO_DEV_API_COUNT="${AI_DO_DEV_API_COUNT:-1}"
export AI_DO_DEV_API_HOST="${AI_DO_DEV_API_HOST:-0.0.0.0}"
export AI_DO_INFRA_CONTAINER_PREFIX="${AI_DO_INFRA_CONTAINER_PREFIX:-ai-do-dev}"
export AI_DO_INFRA_BIND_HOST="${AI_DO_INFRA_BIND_HOST:-0.0.0.0}"
export AI_DO_INFRA_NGINX_PORT="${AI_DO_INFRA_NGINX_PORT:-14200}"
export AI_DO_INFRA_REDIS_PORT="${AI_DO_INFRA_REDIS_PORT:-56380}"
export AI_DO_DEV_REDIS_URL="${AI_DO_DEV_REDIS_URL:-redis://127.0.0.1:${AI_DO_INFRA_REDIS_PORT}/0}"
export AI_DO_DEV_REDIS_RESULT_BACKEND="${AI_DO_DEV_REDIS_RESULT_BACKEND:-redis://127.0.0.1:${AI_DO_INFRA_REDIS_PORT}/1}"
export AI_DO_DEV_COLLAB_REDIS_URL="${AI_DO_DEV_COLLAB_REDIS_URL:-$AI_DO_DEV_REDIS_URL}"
export AI_DO_DEV_REALTIME_REDIS_URL="${AI_DO_DEV_REALTIME_REDIS_URL:-$AI_DO_DEV_REDIS_URL}"
export AI_DO_DEV_WORKER_BROKER_URL="${AI_DO_DEV_WORKER_BROKER_URL:-$AI_DO_DEV_REDIS_URL}"
export AI_DO_DEV_WORKER_RESULT_BACKEND="${AI_DO_DEV_WORKER_RESULT_BACKEND:-$AI_DO_DEV_REDIS_RESULT_BACKEND}"
export AI_DO_INFRA_MINIO_PORT="${AI_DO_INFRA_MINIO_PORT:-59010}"
export AI_DO_INFRA_MINIO_CONSOLE_PORT="${AI_DO_INFRA_MINIO_CONSOLE_PORT:-59011}"
export AI_DO_INFRA_OPENSEARCH_PORT="${AI_DO_INFRA_OPENSEARCH_PORT:-59210}"
export AI_DO_INFRA_OPENSEARCH_PERF_PORT="${AI_DO_INFRA_OPENSEARCH_PERF_PORT:-59610}"
export AI_DO_INFRA_QDRANT_PORT="${AI_DO_INFRA_QDRANT_PORT:-16333}"
export AI_DO_INFRA_QDRANT_GRPC_PORT="${AI_DO_INFRA_QDRANT_GRPC_PORT:-16334}"
export AI_DO_LIVEKIT_PORT="${AI_DO_LIVEKIT_PORT:-7880}"
export AI_DO_LIVEKIT_RTC_TCP_PORT="${AI_DO_LIVEKIT_RTC_TCP_PORT:-7881}"
export AI_DO_LIVEKIT_RTC_PORT_RANGE_START="${AI_DO_LIVEKIT_RTC_PORT_RANGE_START:-52000}"
export AI_DO_LIVEKIT_RTC_PORT_RANGE_END="${AI_DO_LIVEKIT_RTC_PORT_RANGE_END:-52100}"
export AI_DO_INFRA_USE_LOCAL_MINIO="${AI_DO_INFRA_USE_LOCAL_MINIO:-auto}"
export AI_DO_DEV_BASE_URL="${AI_DO_DEV_BASE_URL:-http://127.0.0.1:${AI_DO_INFRA_NGINX_PORT}}"
export AI_DO_DEV_RUNTIME_DIR="${AI_DO_DEV_RUNTIME_DIR:-$ROOT_DIR/.dev}"
export AI_DO_DEV_PID_DIR="${AI_DO_DEV_PID_DIR:-$AI_DO_DEV_RUNTIME_DIR/pids}"
export AI_DO_DEV_LOG_DIR="${AI_DO_DEV_LOG_DIR:-$AI_DO_DEV_RUNTIME_DIR/logs}"
export AI_DO_DEV_NGINX_CONF_TEMPLATE_PATH="${AI_DO_DEV_NGINX_CONF_TEMPLATE_PATH:-$ROOT_DIR/ops/dev/nginx.conf.template}"
export AI_DO_DEV_NGINX_CONF_PATH="${AI_DO_DEV_NGINX_CONF_PATH:-$AI_DO_DEV_RUNTIME_DIR/nginx.conf}"
export AI_DO_ENV_PROFILE="${AI_DO_ENV_PROFILE:-dev}"

export AI_DO_POSTGRES_DSN="${AI_DO_POSTGRES_DSN:-postgresql+psycopg://ai_do_dev:ai_do_dev@127.0.0.1:5432/ai_do_dev}"
export AI_DO_API_COLLAB_REDIS_URL="$AI_DO_DEV_COLLAB_REDIS_URL"
export AI_DO_API_REALTIME_REDIS_URL="$AI_DO_DEV_REALTIME_REDIS_URL"
export AI_DO_WORKER_BROKER_URL="$AI_DO_DEV_WORKER_BROKER_URL"
export AI_DO_WORKER_RESULT_BACKEND="$AI_DO_DEV_WORKER_RESULT_BACKEND"
export AI_DO_MINIO_ENDPOINT="${AI_DO_MINIO_ENDPOINT:-http://127.0.0.1:${AI_DO_INFRA_MINIO_PORT}}"
export AI_DO_MINIO_ACCESS_KEY="${AI_DO_MINIO_ACCESS_KEY:-ai_do_dev_minio}"
export AI_DO_MINIO_SECRET_KEY="${AI_DO_MINIO_SECRET_KEY:-ai_do_dev_minio}"
export AI_DO_MINIO_BUCKET="${AI_DO_MINIO_BUCKET:-ai-do-dev}"
export AI_DO_OPENSEARCH_URL="${AI_DO_OPENSEARCH_URL:-http://127.0.0.1:${AI_DO_INFRA_OPENSEARCH_PORT}}"
export AI_DO_OPENSEARCH_INDEX_PREFIX="${AI_DO_OPENSEARCH_INDEX_PREFIX:-ai-do-dev}"
export AI_DO_RAG_QDRANT_URL="${AI_DO_RAG_QDRANT_URL:-http://127.0.0.1:${AI_DO_INFRA_QDRANT_PORT}}"
export AI_DO_RAG_QDRANT_API_KEY="${AI_DO_RAG_QDRANT_API_KEY:-ai_do_dev_qdrant}"
export AI_DO_RAG_QDRANT_COLLECTION_PREFIX="${AI_DO_RAG_QDRANT_COLLECTION_PREFIX:-ai-do-dev-rag}"
export AI_DO_LIVEKIT_URL="${AI_DO_LIVEKIT_URL:-ws://127.0.0.1:${AI_DO_LIVEKIT_PORT}}"
export AI_DO_LIVEKIT_PUBLIC_URL="${AI_DO_LIVEKIT_PUBLIC_URL:-}"
export AI_DO_LIVEKIT_API_KEY="${AI_DO_LIVEKIT_API_KEY:-devkey}"
export AI_DO_LIVEKIT_API_SECRET="${AI_DO_LIVEKIT_API_SECRET:-devsecret-devsecret-devsecret-0001}"
export AI_DO_LLM_HEALTHCHECK_ON_STARTUP="${AI_DO_LLM_HEALTHCHECK_ON_STARTUP:-0}"
export AI_DO_LLM_REQUIRED="${AI_DO_LLM_REQUIRED:-0}"
export AI_DO_API_ALLOW_DEV_ADMIN_LOGIN="${AI_DO_API_ALLOW_DEV_ADMIN_LOGIN:-1}"
dev_export_ai_do_desktop_installer_defaults

dev_docker() {
  case "$AI_DO_ENV_PROFILE" in
    local|dev|"")
      if docker info >/dev/null 2>&1; then
        docker "$@"
      elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
        sudo -n docker "$@"
      else
        docker "$@"
      fi
      ;;
    prod|production)
      echo "[dev] AI_DO_ENV_PROFILE=$AI_DO_ENV_PROFILE is not supported for dev docker commands" >&2
      return 1
      ;;
    *)
      echo "[dev] invalid AI_DO_ENV_PROFILE: $AI_DO_ENV_PROFILE (expected local, dev, prod)" >&2
      return 1
      ;;
  esac
}

dev_docker_available() {
  dev_docker info >/dev/null 2>&1
}

dev_compose_file() {
  case "$AI_DO_ENV_PROFILE" in
    local|dev|"")
      printf '%s/ops/compose/ai-do-dev.infra.yml\n' "$ROOT_DIR"
      ;;
    prod|production)
      echo "[dev] AI_DO_ENV_PROFILE=$AI_DO_ENV_PROFILE is not supported for dev compose commands" >&2
      return 1
      ;;
    *)
      echo "[dev] invalid AI_DO_ENV_PROFILE: $AI_DO_ENV_PROFILE (expected local, dev, prod)" >&2
      return 1
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
  mkdir -p "$AI_DO_DEV_RUNTIME_DIR" "$AI_DO_DEV_PID_DIR" "$AI_DO_DEV_LOG_DIR"
}

dev_detect_api_upstream_host() {
  dev_docker run --rm --add-host=dev-host:host-gateway nginx:1.27-alpine \
    sh -lc "grep -m1 -E '^[0-9]+(\\.[0-9]+){3}[[:space:]]+dev-host([[:space:]]|\$)' /etc/hosts | awk '{print \$1}'"
}

dev_render_nginx_conf() {
  dev_ensure_runtime_dirs
  local upstream_host
  local listen_port
  upstream_host="$(dev_detect_api_upstream_host)"
  listen_port="80"
  if [[ -z "$upstream_host" ]]; then
    echo "[dev] failed to detect Docker host gateway IPv4 for nginx upstream" >&2
    return 1
  fi

  DEV_NGINX_TEMPLATE="$AI_DO_DEV_NGINX_CONF_TEMPLATE_PATH" \
  DEV_NGINX_OUTPUT="$AI_DO_DEV_NGINX_CONF_PATH" \
  DEV_API_UPSTREAM_HOST="$upstream_host" \
  DEV_NGINX_LISTEN_PORT="$listen_port" \
  python3 - <<'PY'
import os
from pathlib import Path

template = Path(os.environ["DEV_NGINX_TEMPLATE"]).read_text(encoding="utf-8")
rendered = (
    template
    .replace("__AI_DO_DEV_API_UPSTREAM_HOST__", os.environ["DEV_API_UPSTREAM_HOST"])
    .replace("__AI_DO_DEV_NGINX_LISTEN_PORT__", os.environ["DEV_NGINX_LISTEN_PORT"])
)
Path(os.environ["DEV_NGINX_OUTPUT"]).write_text(rendered, encoding="utf-8")
PY
}

dev_use_local_minio() {
  case "$(dev_lower "$AI_DO_INFRA_USE_LOCAL_MINIO")" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if [[ "$AI_DO_MINIO_ENDPOINT" == *"127.0.0.1:${AI_DO_INFRA_MINIO_PORT}"* ]] || \
         [[ "$AI_DO_MINIO_ENDPOINT" == *"localhost:${AI_DO_INFRA_MINIO_PORT}"* ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[dev] invalid AI_DO_INFRA_USE_LOCAL_MINIO: $AI_DO_INFRA_USE_LOCAL_MINIO" >&2
      return 1
      ;;
  esac
}
