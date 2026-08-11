#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(basename "$ROOT_DIR")" == "prod" && "${OPEN_WORK_HUB_ALLOW_PROD_CHECKOUT_DEV_COMMANDS:-0}" != "1" ]]; then
  echo "Refusing to manage development infra from the production checkout." >&2
  exit 1
fi
source "$ROOT_DIR/scripts/dev-env.sh"
COMMAND="${1:-up}"
MODE="${2:-}"

if [[ -n "$MODE" && "$MODE" != "--minimal" ]]; then
  echo "Unknown option: $MODE" >&2
  echo "Usage: $0 {up|down|logs|ps|start|stop|status} [--minimal]" >&2
  exit 2
fi

cd "$ROOT_DIR"
COMPOSE_FILE="$(dev_compose_file)"
COMPOSE_ENV_FILE="$(dev_compose_env_file)"

compose() {
  dev_docker compose --env-file "$COMPOSE_ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

case "$COMMAND" in
  up|start)
    if [[ "$MODE" == "--minimal" ]]; then
      compose up -d --wait postgres redis
      exit 0
    fi

    dev_render_nginx_conf
    services=(redis opensearch qdrant bento nginx)
    if dev_use_local_postgres; then
      services=(postgres "${services[@]}")
    fi
    if dev_use_local_minio; then
      services=(minio "${services[@]}")
    fi
    if [[ "$(printf '%s' "${OPEN_WORK_HUB_API_VIDEO_CHAT_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')" != "false" ]]; then
      services+=(livekit)
    fi
    compose up -d "${services[@]}"
    ;;
  down|stop)
    if [[ "$MODE" == "--minimal" ]]; then
      compose stop postgres redis
    else
      compose down
    fi
    ;;
  logs)
    if [[ "$MODE" == "--minimal" ]]; then
      compose logs -f postgres redis
    else
      compose logs -f
    fi
    ;;
  ps|status)
    if [[ "$MODE" == "--minimal" ]]; then
      compose ps postgres redis
    else
      compose ps
    fi
    ;;
  *)
    echo "Usage: $0 {up|down|logs|ps|start|stop|status} [--minimal]" >&2
    exit 1
    ;;
esac
