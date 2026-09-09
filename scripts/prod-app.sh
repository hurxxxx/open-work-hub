#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/ops/compose/open-work-hub-prod.app.yml"
ENV_FILE="$ROOT_DIR/.env"
COMPOSE_PROJECT_NAME="open-work-hub-prod-app"
IMAGE_REPOSITORY="open-work-hub-app"
CURRENT_IMAGE="$IMAGE_REPOSITORY:prod"
PREVIOUS_IMAGE="$IMAGE_REPOSITORY:prod-previous"
ROLLBACK_ENV_FILE=""
ROLLBACK_IMAGE=""
ROLLBACK_BUNDLE=""

usage() {
  echo "Usage: $0 {build|deploy|migrate|rollback|smoke|status|up}" >&2
  echo "  deploy|rollback [--rollback-env-file <secure-backup> --rollback-image sha256:<image-id>]" >&2
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
  local config_script="${1:-$ROOT_DIR/scripts/prod-app-config.mjs}"
  local config_env="${2:-$ENV_FILE}"
  port="$(
    node "$config_script" \
      "$config_env" \
      --print-hermes-terminal-broker-port
  )" || return 1
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

compose() (
  # Compose interpolation prefers exported shell values over --env-file. The
  # validated release file owns product/provider configuration in both paths.
  local compose_env_name
  while IFS= read -r compose_env_name; do
    case "$compose_env_name" in
      OPEN_WORK_HUB_*|OPENROUTER_API_KEY) unset "$compose_env_name" || return 1 ;;
    esac
  done < <(compgen -e)
  docker compose \
    --project-name "$COMPOSE_PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    "$@"
)

image_revision() {
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "${1:?image is required}"
}

build_release_image() {
  local revision short_revision image bento_server_url
  node "$ROOT_DIR/scripts/docker-storage.mjs" check >&2 || return 1
  revision="$(git -C "$ROOT_DIR" rev-parse HEAD)" || return 1
  short_revision="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD)" || return 1
  image="$IMAGE_REPOSITORY:$short_revision"
  bento_server_url="$(
    node "$ROOT_DIR/scripts/prod-app-config.mjs" \
      "$ENV_FILE" \
      --print-bento-server-url
  )" || return 1
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
    docker tag "$CURRENT_IMAGE" "$PREVIOUS_IMAGE" || return 1
  fi
  docker tag "$image" "$CURRENT_IMAGE" || return 1
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
  revision="$(image_revision "$CURRENT_IMAGE")" || return 1
  OPEN_WORK_HUB_EXPECTED_REVISION="$revision" \
    node "$ROOT_DIR/scripts/prod-app-smoke.mjs" "$ENV_FILE"
}

prepare_rollback_runtime() {
  local expected_image="${1:?expected image is required}"
  if [[ -z "$ROLLBACK_IMAGE" ]]; then
    return 0
  fi
  ROLLBACK_BUNDLE="$(
    node "$ROOT_DIR/scripts/prod-app-rollback.mjs" prepare \
      "$ROOT_DIR" "$ROLLBACK_ENV_FILE" "$ROLLBACK_IMAGE" "$expected_image"
  )" || return 1
  require_terminal_broker_port_available \
    "$ROLLBACK_BUNDLE/scripts/prod-app-config.mjs" "$ROLLBACK_BUNDLE/.env" || return 1
}

rollback_compose() {
  local ENV_FILE="$ROLLBACK_BUNDLE/.env"
  local COMPOSE_FILE="$ROLLBACK_BUNDLE/ops/compose/open-work-hub-prod.app.yml"
  compose "$@"
}

restore_previous_runtime() {
  if [[ -n "$ROLLBACK_IMAGE" ]]; then
    if [[ -z "$ROLLBACK_BUNDLE" ]]; then
      echo "An explicit rollback requires a validated image/environment bundle." >&2
      return 1
    fi
    echo "Restoring the pinned production image, environment, and deployment definitions." >&2
    # Stop every container in this application project, including new release
    # orphans. Persistent volumes and the separate database project are retained.
    rollback_compose down --remove-orphans || return 1
    node "$ROOT_DIR/scripts/prod-app-rollback.mjs" restore-env \
      "$ROOT_DIR" "$ROLLBACK_BUNDLE" "$ROLLBACK_IMAGE" || return 1
    docker tag "$ROLLBACK_IMAGE" "$CURRENT_IMAGE" || return 1
    local COMPOSE_FILE="$ROLLBACK_BUNDLE/ops/compose/open-work-hub-prod.app.yml"
    local ENV_FILE="$ROLLBACK_BUNDLE/.env"
    start_runtime || return 1
    local revision
    revision="$(image_revision "$ROLLBACK_IMAGE")" || return 1
    OPEN_WORK_HUB_EXPECTED_REVISION="$revision" \
      node "$ROLLBACK_BUNDLE/scripts/prod-app-smoke.mjs" "$ENV_FILE" || return 1
    return 0
  fi
  if ! docker image inspect "$PREVIOUS_IMAGE" >/dev/null 2>&1; then
    echo "No previous production image is available for automatic restoration." >&2
    return 1
  fi
  echo "Restoring the previous production application image." >&2
  docker tag "$PREVIOUS_IMAGE" "$CURRENT_IMAGE" || return 1
  start_runtime || return 1
  run_smoke || return 1
}

report_deployment_failure() {
  local restore_image="${1:?restoration decision is required}"
  echo "Production application deployment failed." >&2
  if [[ "$restore_image" == "yes" || -n "$ROLLBACK_IMAGE" ]]; then
    if ! restore_previous_runtime; then
      echo "Production application restoration failed; operator recovery is required." >&2
      return 1
    fi
    echo "The previous production application was restored and passed smoke." >&2
  fi
  return 1
}

deploy() {
  local image
  # Retention is part of an explicitly authorized deploy, never status/smoke.
  node "$ROOT_DIR/scripts/docker-storage.mjs" cleanup --apply || return 1
  if ! image="$(build_release_image)"; then
    report_deployment_failure no
    return 1
  fi
  if ! promote_image "$image"; then
    report_deployment_failure yes
    return 1
  fi
  if ! run_migrations || ! start_runtime || ! run_smoke; then
    report_deployment_failure yes
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

shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rollback-env-file)
      if [[ $# -lt 2 || -n "$ROLLBACK_ENV_FILE" || -z "$2" ]]; then usage; exit 2; fi
      ROLLBACK_ENV_FILE="$2"
      shift 2
      ;;
    --rollback-image)
      if [[ $# -lt 2 || -n "$ROLLBACK_IMAGE" || -z "$2" ]]; then usage; exit 2; fi
      ROLLBACK_IMAGE="$2"
      shift 2
      ;;
    *) usage; exit 2 ;;
  esac
done
if [[ -n "$ROLLBACK_ENV_FILE" || -n "$ROLLBACK_IMAGE" ]]; then
  if [[ -z "$ROLLBACK_ENV_FILE" || -z "$ROLLBACK_IMAGE" || ( "$COMMAND" != "deploy" && "$COMMAND" != "rollback" ) ]]; then
    usage
    exit 2
  fi
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
    prepare_rollback_runtime "$CURRENT_IMAGE"
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
    if [[ -n "$ROLLBACK_IMAGE" ]]; then
      prepare_rollback_runtime "$PREVIOUS_IMAGE"
    else
      validate_environment
      require_terminal_broker_port_available
    fi
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
