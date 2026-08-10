#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  echo "Usage: $0 {prod|dev} {up|down|start|stop|restart|ps|logs|pull} [compose args...]" >&2
}

require_matching_checkout() {
  local environment="${1:?environment is required}"
  local checkout_name
  checkout_name="$(basename "$ROOT_DIR")"
  case "$environment" in
    prod)
      if [[ "$checkout_name" != "prod" && "${OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS:-0}" != "1" ]]; then
        echo "Refusing to manage production infra from non-prod checkout: $ROOT_DIR" >&2
        exit 1
      fi
      ;;
    dev)
      if [[ "$checkout_name" == "prod" && "${OPEN_ALM_ALLOW_PROD_CHECKOUT_DEV_COMMANDS:-0}" != "1" ]]; then
        echo "Refusing to manage development infra from production checkout: $ROOT_DIR" >&2
        exit 1
      fi
      ;;
  esac
}

ENVIRONMENT="${1:-}"
COMMAND="${2:-}"
if [[ -z "$ENVIRONMENT" || -z "$COMMAND" ]]; then
  usage
  exit 2
fi
shift 2

case "$ENVIRONMENT" in
  prod)
    require_matching_checkout prod
    COMPOSE_FILE="$ROOT_DIR/ops/compose/open-alm-prod.infra.yml"
    ;;
  dev)
    require_matching_checkout dev
    COMPOSE_FILE="$ROOT_DIR/ops/compose/open-alm-dev.infra.yml"
    ;;
  *)
    usage
    exit 2
    ;;
esac

compose() {
  docker compose --env-file "$ROOT_DIR/.env" -f "$COMPOSE_FILE" "$@"
}

cd "$ROOT_DIR"

case "$COMMAND" in
  up)
    compose up -d --remove-orphans "$@"
    ;;
  down)
    compose down "$@"
    ;;
  start)
    compose start "$@"
    ;;
  stop)
    compose stop "$@"
    ;;
  restart)
    compose up -d --remove-orphans "$@"
    ;;
  ps|status)
    compose ps "$@"
    ;;
  logs|log)
    compose logs -f "$@"
    ;;
  pull)
    compose pull "$@"
    ;;
  *)
    usage
    exit 2
    ;;
esac
