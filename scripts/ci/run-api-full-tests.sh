#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATUS=0

run_segment() {
  local name="${1:?segment name is required}"
  shift

  printf '[api-test-full] start %s\n' "$name" >&2
  if (cd "$ROOT_DIR/apps/api" && "$@"); then
    printf '[api-test-full] pass %s\n' "$name" >&2
  else
    local segment_status=$?
    printf '[api-test-full] fail %s status=%s\n' "$name" "$segment_status" >&2
    STATUS=1
  fi
}

default_external_integration_env() {
  export OPEN_WORK_HUB_TEST_REDIS_URL="${OPEN_WORK_HUB_TEST_REDIS_URL:-${OPEN_WORK_HUB_API_COLLAB_REDIS_URL:-}}"
  export OPEN_WORK_HUB_TEST_MINIO_ENDPOINT="${OPEN_WORK_HUB_TEST_MINIO_ENDPOINT:-${OPEN_WORK_HUB_MINIO_ENDPOINT:-}}"
  export OPEN_WORK_HUB_TEST_MINIO_ACCESS_KEY="${OPEN_WORK_HUB_TEST_MINIO_ACCESS_KEY:-${OPEN_WORK_HUB_MINIO_ACCESS_KEY:-}}"
  export OPEN_WORK_HUB_TEST_MINIO_SECRET_KEY="${OPEN_WORK_HUB_TEST_MINIO_SECRET_KEY:-${OPEN_WORK_HUB_MINIO_SECRET_KEY:-}}"
  export OPEN_WORK_HUB_TEST_OPENSEARCH_URL="${OPEN_WORK_HUB_TEST_OPENSEARCH_URL:-${OPEN_WORK_HUB_OPENSEARCH_URL:-}}"
}

run_segment \
  fast \
  uv run --python 3.12 --group dev python -m pytest \
  -n "${OPEN_WORK_HUB_API_PYTEST_WORKERS:-8}" \
  --dist=worksteal \
  -m "not slow and not external_integration and not migration"

run_segment \
  slow \
  uv run --python 3.12 --group dev python -m pytest \
  -m "slow and not external_integration and not migration"

run_segment \
  migration \
  uv run --python 3.12 --group dev python -m pytest \
  -m migration

default_external_integration_env
run_segment \
  external_integration \
  bash "$ROOT_DIR/scripts/api-test-vm.sh" -m external_integration

exit "$STATUS"
