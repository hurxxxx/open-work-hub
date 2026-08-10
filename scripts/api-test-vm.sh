#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTEST_PID=""
CLEANUP_DONE=0
CLEANUP_STATUS=0

if [[ -z "${OPEN_ALM_API_TEST_RUN_ID:-}" ]]; then
  if [[ -n "${CI_JOB_ID:-}" ]]; then
    OPEN_ALM_API_TEST_RUN_ID="$CI_JOB_ID"
  elif [[ -r /proc/sys/kernel/random/uuid ]]; then
    read -r OPEN_ALM_API_TEST_RUN_ID </proc/sys/kernel/random/uuid
  else
    OPEN_ALM_API_TEST_RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  fi
fi
export OPEN_ALM_API_TEST_RUN_ID

cleanup_test_resources() {
  if [[ "$CLEANUP_DONE" -eq 1 ]]; then
    return "$CLEANUP_STATUS"
  fi
  CLEANUP_DONE=1
  if ! (
    cd "$ROOT_DIR/apps/api"
    uv run --python 3.12 python tests/integration_infra.py cleanup-current
  ); then
    echo "warning: unable to clean shared API integration resources for run ${OPEN_ALM_API_TEST_RUN_ID}" >&2
    CLEANUP_STATUS=1
  fi
  return "$CLEANUP_STATUS"
}

handle_exit() {
  local exit_code="$?"
  trap - EXIT
  if ! cleanup_test_resources && [[ "$exit_code" -eq 0 ]]; then
    exit_code=1
  fi
  exit "$exit_code"
}

handle_signal() {
  local exit_code="$1"
  trap '' INT TERM
  if [[ -n "$PYTEST_PID" ]]; then
    kill -TERM "$PYTEST_PID" 2>/dev/null || true
    wait "$PYTEST_PID" 2>/dev/null || true
    PYTEST_PID=""
  fi
  cleanup_test_resources || true
  exit "$exit_code"
}

trap handle_exit EXIT
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

if [[ "${1:-}" == "--cleanup-only" ]]; then
  if [[ "$#" -ne 1 ]]; then
    echo "usage: $0 --cleanup-only" >&2
    exit 2
  fi
  cleanup_test_resources
  exit 0
fi

echo "API test run id: ${OPEN_ALM_API_TEST_RUN_ID}" >&2
cd "$ROOT_DIR/apps/api"
uv run --python 3.12 --group dev python -m pytest "$@" &
PYTEST_PID=$!

pytest_status=0
wait "$PYTEST_PID" || pytest_status=$?
PYTEST_PID=""
exit "$pytest_status"
