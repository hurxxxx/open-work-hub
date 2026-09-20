#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/ops/compose/open-work-hub-prod.app.yml"
ENV_FILE="$ROOT_DIR/.env"
COMPOSE_PROJECT_NAME="open-work-hub-prod-app"
IMAGE_REPOSITORY="open-work-hub-app"
CURRENT_IMAGE="$IMAGE_REPOSITORY:prod"
PREVIOUS_IMAGE="$IMAGE_REPOSITORY:prod-previous"
CANDIDATE_IMAGE="$IMAGE_REPOSITORY:candidate"
ROLLBACK_ENV_FILE=""
ROLLBACK_IMAGE=""
ROLLBACK_BUNDLE=""
RELEASE_MR=""
DEPLOY_IMAGE=""
RELEASE_SOURCE_REVISION=""
RELEASE_REVISION=""
RELEASE_TREE=""
RELEASE_PLATFORM=""
RELEASE_BENTO_URL_SHA256=""
RELEASE_PIPELINE=""
RELEASE_CONTRACT=""

usage() {
  echo "Usage: $0 {prepare|deploy|migrate|rollback|smoke|status|up}" >&2
  echo "  prepare --release-mr <iid>" >&2
  echo "  deploy --release-mr <iid> --image sha256:<image-id> [--rollback-env-file <secure-backup> --rollback-image sha256:<image-id>]" >&2
  echo "  rollback [--rollback-env-file <secure-backup> --rollback-image sha256:<image-id>]" >&2
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

acquire_operation_lock() {
  local lock_directory="$ROOT_DIR/.runtime/prod-app"
  if ! command -v flock >/dev/null 2>&1; then
    echo "Production release operations require flock from util-linux." >&2
    return 1
  fi
  mkdir -p "$lock_directory" || return 1
  chmod 700 "$lock_directory" || return 1
  exec 9>"$lock_directory/operation.lock"
  chmod 600 "$lock_directory/operation.lock" || return 1
  if ! flock -n 9; then
    echo "Another production release operation is already running." >&2
    return 1
  fi
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
    "Production Hermes Terminal broker port 127.0.0.1:$port is already in use by another listener; refusing before release preparation or migration." \
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

image_id() {
  docker image inspect --format '{{.Id}}' "${1:?image is required}"
}

image_label() {
  local image="${1:?image is required}"
  local label="${2:?label is required}"
  docker image inspect --format "{{ index .Config.Labels \"$label\" }}" "$image"
}

load_release_contract() {
  local release_mr="${1:?release MR is required}"
  local evidence bento_server_url
  local -a fields
  evidence="$(
    node "$ROOT_DIR/scripts/prod-app-release.mjs" "$ROOT_DIR" "$release_mr"
  )" || return 1
  mapfile -t fields <<<"$evidence"
  if [[ "${#fields[@]}" -ne 3 ]]; then
    echo "Release MR evidence returned an invalid contract." >&2
    return 1
  fi
  RELEASE_SOURCE_REVISION="${fields[0]}"
  RELEASE_REVISION="${fields[1]}"
  RELEASE_PIPELINE="${fields[2]}"
  RELEASE_TREE="$(git -C "$ROOT_DIR" rev-parse 'HEAD^{tree}')" || return 1
  RELEASE_PLATFORM="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')" || return 1
  if [[ ! "$RELEASE_PLATFORM" =~ ^linux/(amd64|arm64)$ ]]; then
    echo "Production image platform must be linux/amd64 or linux/arm64." >&2
    return 1
  fi
  bento_server_url="$(
    node "$ROOT_DIR/scripts/prod-app-config.mjs" \
      "$ENV_FILE" \
      --print-bento-server-url
  )" || return 1
  RELEASE_BENTO_URL_SHA256="$(
    printf '%s' "$bento_server_url" | sha256sum | awk '{print $1}'
  )" || return 1
  RELEASE_CONTRACT="$(
    printf '%s\n' \
      'open-work-hub-production-release-v1' \
      "$RELEASE_REVISION" \
      "$RELEASE_SOURCE_REVISION" \
      "$RELEASE_TREE" \
      "$RELEASE_PLATFORM" \
      "$RELEASE_BENTO_URL_SHA256" \
      | sha256sum | awk '{print $1}'
  )" || return 1
}

candidate_matches_contract() {
  local image="${1:?image is required}"
  [[ "$(image_label "$image" 'io.open-work-hub.release.contract')" == "$RELEASE_CONTRACT" ]]
}

verify_release_image() {
  local image="${1:?image is required}"
  local expected_revision="${2:?revision is required}"
  if [[ "$(image_revision "$image")" != "$expected_revision" ]]; then
    echo "Release image revision does not match the production source." >&2
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

verify_candidate_image() {
  local image="${1:?image is required}"
  local actual_id
  actual_id="$(image_id "$image")" || return 1
  if [[ ! "$actual_id" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    echo "Release candidate does not have an immutable image ID." >&2
    return 1
  fi
  verify_release_image "$image" "$RELEASE_REVISION" || return 1
  local label expected
  while IFS=$'\t' read -r label expected; do
    if [[ "$(image_label "$image" "$label")" != "$expected" ]]; then
      echo "Release candidate metadata does not match the verified release." >&2
      return 1
    fi
  done <<EOF
io.open-work-hub.release.contract	$RELEASE_CONTRACT
io.open-work-hub.release.source-revision	$RELEASE_SOURCE_REVISION
io.open-work-hub.release.tree	$RELEASE_TREE
io.open-work-hub.release.platform	$RELEASE_PLATFORM
io.open-work-hub.release.bento-url-sha256	$RELEASE_BENTO_URL_SHA256
io.open-work-hub.release.merge-request	$RELEASE_MR
EOF
  local recorded_pipeline
  recorded_pipeline="$(
    image_label "$image" 'io.open-work-hub.release.pipeline'
  )" || return 1
  if [[ ! "$recorded_pipeline" =~ ^[1-9][0-9]*$ ]]; then
    echo "Release candidate does not record valid build-time pipeline evidence." >&2
    return 1
  fi
}

prepare_candidate_image() {
  local bento_server_url build_image
  build_image="$IMAGE_REPOSITORY:candidate-${RELEASE_CONTRACT:0:12}"
  if docker image inspect "$CANDIDATE_IMAGE" >/dev/null 2>&1 \
    && candidate_matches_contract "$CANDIDATE_IMAGE"; then
    verify_candidate_image "$CANDIDATE_IMAGE" || return 1
    image_id "$CANDIDATE_IMAGE"
    return
  fi
  if docker image inspect "$build_image" >/dev/null 2>&1; then
    verify_candidate_image "$build_image" || return 1
    docker tag "$build_image" "$CANDIDATE_IMAGE" || return 1
    image_id "$CANDIDATE_IMAGE"
    return
  fi
  node "$ROOT_DIR/scripts/docker-storage.mjs" check >&2 || return 1
  bento_server_url="$(
    node "$ROOT_DIR/scripts/prod-app-config.mjs" \
      "$ENV_FILE" \
      --print-bento-server-url
  )" || return 1
  git -C "$ROOT_DIR" archive --format=tar HEAD \
    | docker build \
    --file ops/app/Dockerfile \
    --target runtime \
    --platform "$RELEASE_PLATFORM" \
    --build-arg "OPEN_WORK_HUB_BENTO_SERVER_URL=$bento_server_url" \
    --build-arg "OPEN_WORK_HUB_BUILD_REVISION=$RELEASE_REVISION" \
    --build-arg "OPEN_WORK_HUB_RELEASE_CONTRACT=$RELEASE_CONTRACT" \
    --build-arg "OPEN_WORK_HUB_RELEASE_SOURCE_REVISION=$RELEASE_SOURCE_REVISION" \
    --build-arg "OPEN_WORK_HUB_RELEASE_TREE=$RELEASE_TREE" \
    --build-arg "OPEN_WORK_HUB_RELEASE_PLATFORM=$RELEASE_PLATFORM" \
    --build-arg "OPEN_WORK_HUB_RELEASE_BENTO_URL_SHA256=$RELEASE_BENTO_URL_SHA256" \
    --build-arg "OPEN_WORK_HUB_RELEASE_MR=$RELEASE_MR" \
    --build-arg "OPEN_WORK_HUB_RELEASE_PIPELINE=$RELEASE_PIPELINE" \
    --tag "$build_image" \
    - >&2 || return 1
  verify_candidate_image "$build_image" || return 1
  docker tag "$build_image" "$CANDIDATE_IMAGE" || return 1
  image_id "$CANDIDATE_IMAGE"
}

require_deploy_image() {
  local image="${1:?image is required}"
  local actual_id
  if [[ ! "$image" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    echo "Deployment requires the full immutable candidate image ID." >&2
    return 1
  fi
  actual_id="$(image_id "$image")" || return 1
  if [[ "$actual_id" != "$image" ]]; then
    echo "Deployment image ID does not resolve to the requested candidate." >&2
    return 1
  fi
  verify_candidate_image "$image"
}

promote_image() {
  local image="${1:?image is required}"
  local candidate_id current_id
  candidate_id="$(image_id "$image")" || return 1
  if docker image inspect "$CURRENT_IMAGE" >/dev/null 2>&1; then
    current_id="$(image_id "$CURRENT_IMAGE")" || return 1
    if [[ "$current_id" == "$candidate_id" ]]; then
      return 0
    fi
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
  local image="${1:?image is required}"
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
    --release-mr)
      if [[ $# -lt 2 || -n "$RELEASE_MR" || -z "$2" ]]; then usage; exit 2; fi
      RELEASE_MR="$2"
      shift 2
      ;;
    --image)
      if [[ $# -lt 2 || -n "$DEPLOY_IMAGE" || -z "$2" ]]; then usage; exit 2; fi
      DEPLOY_IMAGE="$2"
      shift 2
      ;;
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
if [[ "$COMMAND" == "prepare" ]]; then
  if [[ -z "$RELEASE_MR" || -n "$DEPLOY_IMAGE" || -n "$ROLLBACK_ENV_FILE" || -n "$ROLLBACK_IMAGE" ]]; then
    usage
    exit 2
  fi
elif [[ "$COMMAND" == "deploy" ]]; then
  if [[ -z "$RELEASE_MR" || -z "$DEPLOY_IMAGE" ]]; then
    usage
    exit 2
  fi
elif [[ -n "$RELEASE_MR" || -n "$DEPLOY_IMAGE" ]]; then
  usage
  exit 2
fi
if [[ -n "$ROLLBACK_ENV_FILE" || -n "$ROLLBACK_IMAGE" ]]; then
  if [[ -z "$ROLLBACK_ENV_FILE" || -z "$ROLLBACK_IMAGE" || ( "$COMMAND" != "deploy" && "$COMMAND" != "rollback" ) ]]; then
    usage
    exit 2
  fi
fi

case "$COMMAND" in
  prepare)
    require_prod_checkout
    require_release_source
    acquire_operation_lock
    validate_environment
    load_release_contract "$RELEASE_MR"
    prepare_candidate_image
    ;;
  deploy)
    require_prod_checkout
    require_release_source
    acquire_operation_lock
    prepare_rollback_runtime "$CURRENT_IMAGE"
    validate_environment
    require_terminal_broker_port_available
    load_release_contract "$RELEASE_MR"
    require_deploy_image "$DEPLOY_IMAGE"
    deploy "$DEPLOY_IMAGE"
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
    acquire_operation_lock
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
