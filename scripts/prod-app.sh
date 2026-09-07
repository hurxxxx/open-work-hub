#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/ops/compose/open-work-hub-prod.app.yml"
ENV_FILE="$ROOT_DIR/.env"
COMPOSE_PROJECT_NAME="open-work-hub-prod-app"
IMAGE_REPOSITORY="open-work-hub-app"
CURRENT_IMAGE="$IMAGE_REPOSITORY:prod"
PREVIOUS_IMAGE="$IMAGE_REPOSITORY:prod-previous"

usage() {
  echo "Usage: $0 {build|deploy|migrate|rollback|smoke|status|up}" >&2
}

require_prod_checkout() {
  if [[ "$(basename "$ROOT_DIR")" != "prod" ]]; then
    echo "Refusing to manage the production app outside the prod checkout: $ROOT_DIR" >&2
    exit 1
  fi
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Production runtime env file is missing: $ENV_FILE" >&2
    exit 1
  fi
}

require_release_source() {
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "Refusing to deploy from a dirty production checkout." >&2
    exit 1
  fi
  local head_revision main_revision
  head_revision="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  main_revision="$(git -C "$ROOT_DIR" rev-parse origin/main)"
  if [[ "$head_revision" != "$main_revision" ]]; then
    echo "Refusing to deploy a production checkout that does not match origin/main." >&2
    exit 1
  fi
}

validate_environment() {
  node "$ROOT_DIR/scripts/prod-app-config.mjs" "$ENV_FILE"
}

require_terminal_broker_port_available() {
  local port expected_container expected_running expected_binding
  port="$(
    node "$ROOT_DIR/scripts/prod-app-config.mjs" \
      "$ENV_FILE" \
      --print-hermes-terminal-broker-port
  )"
  expected_container="open-work-hub-prod-hermes-terminal-broker"

  if ! command -v ss >/dev/null 2>&1; then
    echo "Production port preflight requires the ss command." >&2
    return 1
  fi
  if ! ss -H -ltn "sport = :$port" | grep -q .; then
    return 0
  fi

  expected_running="$(
    docker inspect --format '{{.State.Running}}' "$expected_container" 2>/dev/null || true
  )"
  expected_binding="$(
    docker inspect \
      --format '{{range (index .NetworkSettings.Ports "18765/tcp")}}{{printf "%s:%s" .HostIp .HostPort}}{{end}}' \
      "$expected_container" 2>/dev/null || true
  )"
  if [[ "$expected_running" == "true" && "$expected_binding" == "127.0.0.1:$port" ]]; then
    return 0
  fi

  echo \
    "Production Hermes Terminal broker port 127.0.0.1:$port is already in use by another listener; refusing before build or migration." \
    >&2
  return 1
}

compose() {
  docker compose \
    --project-name "$COMPOSE_PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    "$@"
}

image_revision() {
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "${1:?image is required}"
}

build_release_image() {
  local revision short_revision image bento_server_url
  node "$ROOT_DIR/scripts/docker-storage.mjs" check >&2 || return 1
  revision="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  short_revision="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD)"
  image="$IMAGE_REPOSITORY:$short_revision"
  bento_server_url="$(
    node "$ROOT_DIR/scripts/prod-app-config.mjs" \
      "$ENV_FILE" \
      --print-bento-server-url
  )"
  docker build \
    --file "$ROOT_DIR/ops/app/Dockerfile" \
    --target runtime \
    --build-arg "OPEN_WORK_HUB_BENTO_SERVER_URL=$bento_server_url" \
    --build-arg "OPEN_WORK_HUB_BUILD_REVISION=$revision" \
    --tag "$image" \
    "$ROOT_DIR" >&2 || return 1
  verify_release_image "$image" "$revision" || return 1
  printf '%s\n' "$image"
}

verify_release_image() {
  local image="${1:?image is required}"
  local expected_revision="${2:?revision is required}"
  if [[ "$(image_revision "$image")" != "$expected_revision" ]]; then
    echo "Built image revision does not match the release source." >&2
    return 1
  fi
  docker run --rm --entrypoint /bin/sh "$image" -ec '
    test "$(id -u)" = 10001
    test -x apps/api/.venv/bin/uvicorn
    test -x apps/worker/.venv/bin/celery
    test -f dist/apps/web/index.html
    test -f scripts/blocknote-collab-codec.mjs
    node --version >/dev/null
    node scripts/blocknote-collab-codec.mjs encode </dev/null >/dev/null
    apps/api/.venv/bin/python -c "import open_work_hub_api"
    OPEN_WORK_HUB_POSTGRES_DSN=sqlite:///migration-config-smoke.db \
      apps/api/.venv/bin/python -c \
      "from alembic.script import ScriptDirectory; from open_work_hub_api.core.db import _alembic_config; assert ScriptDirectory.from_config(_alembic_config()).get_current_head()"
    apps/api/.venv/bin/python -c "import opf, torch"
    apps/worker/.venv/bin/python -c "import open_work_hub_worker"
  '
}

promote_image() {
  local image="${1:?image is required}"
  if docker image inspect "$CURRENT_IMAGE" >/dev/null 2>&1; then
    docker tag "$CURRENT_IMAGE" "$PREVIOUS_IMAGE"
  fi
  docker tag "$image" "$CURRENT_IMAGE"
}

run_migrations() {
  compose run --rm migrate
}

start_runtime() {
  compose up \
    --detach \
    --force-recreate \
    --remove-orphans \
    --wait \
    --wait-timeout 600 \
    hermes-bootstrap hermes-gateway hermes-dashboard \
    hermes-terminal-egress hermes-terminal-broker \
    privacy-filter api worker beat
}

run_smoke() {
  local revision
  revision="$(image_revision "$CURRENT_IMAGE")"
  OPEN_WORK_HUB_EXPECTED_REVISION="$revision" \
    node "$ROOT_DIR/scripts/prod-app-smoke.mjs" "$ENV_FILE"
}

restore_previous_runtime() {
  if ! docker image inspect "$PREVIOUS_IMAGE" >/dev/null 2>&1; then
    echo "No previous production image is available for automatic restoration." >&2
    return 1
  fi
  echo "Restoring the previous production application image." >&2
  docker tag "$PREVIOUS_IMAGE" "$CURRENT_IMAGE"
  start_runtime
  run_smoke
}

deploy() {
  local image
  # Retention is part of an explicitly authorized deploy, never status/smoke.
  node "$ROOT_DIR/scripts/docker-storage.mjs" cleanup --apply
  image="$(build_release_image)"
  promote_image "$image"
  if ! run_migrations || ! start_runtime || ! run_smoke; then
    echo "Production application deployment failed." >&2
    restore_previous_runtime || true
    return 1
  fi
  echo "Production application deployment completed and passed public smoke."
  if ! node "$ROOT_DIR/scripts/docker-storage.mjs" cleanup --apply; then
    echo "Deployment is healthy, but project image retention needs operator attention." >&2
    return 1
  fi
}

COMMAND="${1:-}"
if [[ -z "$COMMAND" ]]; then
  usage
  exit 2
fi

case "$COMMAND" in
  build)
    require_prod_checkout
    require_release_source
    validate_environment
    build_release_image
    ;;
  deploy)
    require_prod_checkout
    require_release_source
    validate_environment
    require_terminal_broker_port_available
    deploy
    ;;
  migrate)
    require_prod_checkout
    require_release_source
    validate_environment
    run_migrations
    ;;
  rollback)
    require_prod_checkout
    require_release_source
    validate_environment
    require_terminal_broker_port_available
    restore_previous_runtime
    ;;
  smoke)
    require_prod_checkout
    validate_environment
    run_smoke
    ;;
  status)
    require_prod_checkout
    compose ps
    ;;
  up)
    require_prod_checkout
    require_release_source
    validate_environment
    require_terminal_broker_port_available
    docker image inspect "$CURRENT_IMAGE" >/dev/null
    run_migrations
    start_runtime
    run_smoke
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
