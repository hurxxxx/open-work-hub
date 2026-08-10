#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(basename "$ROOT_DIR")" == "prod" && "${OPEN_ALM_ALLOW_PROD_CHECKOUT_DEV_COMMANDS:-0}" != "1" ]]; then
  echo "Refusing to manage development infra from the production checkout." >&2
  exit 1
fi
source "$ROOT_DIR/scripts/dev-env.sh"
COMMAND="${1:-up}"

cd "$ROOT_DIR"
COMPOSE_FILE="$(dev_compose_file)"

case "$COMMAND" in
  up|start)
    dev_render_nginx_conf
    services=(redis opensearch qdrant nginx)
    if [[ "$(printf '%s' "${OPEN_ALM_API_VIDEO_CHAT_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')" != "false" ]]; then
      services+=(livekit)
    fi
    if dev_use_local_minio; then
      services=(minio "${services[@]}")
    fi
    dev_docker compose --env-file "$ROOT_DIR/.env" -f "$COMPOSE_FILE" up -d "${services[@]}"
    ;;
  down|stop)
    dev_docker compose --env-file "$ROOT_DIR/.env" -f "$COMPOSE_FILE" down
    ;;
  logs)
    dev_docker compose --env-file "$ROOT_DIR/.env" -f "$COMPOSE_FILE" logs -f
    ;;
  ps|status)
    dev_docker compose --env-file "$ROOT_DIR/.env" -f "$COMPOSE_FILE" ps
    ;;
  *)
    echo "Usage: $0 {up|down|logs|ps|start|stop|status}" >&2
    exit 1
    ;;
esac
