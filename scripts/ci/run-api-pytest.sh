#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
api_root="$repo_root/apps/api"
lane="${1:-}"
if [[ "$#" -gt 0 ]]; then
  shift
fi

usage() {
  echo "usage: $0 <standard|slow|migration|external> [pytest path ...]" >&2
}

case "$lane" in
  standard)
    pytest_marker="not slow and not external_integration and not migration"
    ;;
  slow)
    pytest_marker="slow and not external_integration and not migration"
    ;;
  migration)
    pytest_marker="migration"
    ;;
  external)
    pytest_marker="external_integration"
    ;;
  *)
    usage
    exit 2
    ;;
esac

api_dependency_sha256() {
  {
    sha256sum "$api_root/pyproject.toml" | awk '{print $1}'
    sha256sum "$api_root/uv.lock" | awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

node_dependency_sha256() {
  {
    sha256sum "$repo_root/package.json" | awk '{print $1}'
    sha256sum "$repo_root/pnpm-lock.yaml" | awk '{print $1}'
    sha256sum "$repo_root/pnpm-workspace.yaml" | awk '{print $1}'
    sha256sum "$repo_root/packages/contracts/package.json" | awk '{print $1}'
    sha256sum "$repo_root/packages/core-web/package.json" | awk '{print $1}'
    sha256sum "$repo_root/packages/ui/package.json" | awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

actual_dependency_sha256="$(api_dependency_sha256)"
dependency_mode="${OPEN_ALM_API_DEPENDENCY_MODE:-offline}"
dependency_marker_name=".open-alm-api-dependency-sha256"

case "$dependency_mode" in
  offline)
    api_venv="${OPEN_ALM_API_IMAGE_VENV:-/opt/open-alm/venvs/api}"
    image_dependency_file="${OPEN_ALM_API_IMAGE_DEPENDENCY_FILE:-/opt/open-alm/locks/api/dependency.sha256}"
    if [[ ! -r "$image_dependency_file" ]]; then
      echo "Offline API dependency identity is unavailable: ${image_dependency_file}" >&2
      exit 2
    fi
    read -r image_dependency_sha256 <"$image_dependency_file"
    if [[ "$image_dependency_sha256" != "$actual_dependency_sha256" ]]; then
      echo \
        "Offline API dependency mismatch: image=${image_dependency_sha256} checkout=${actual_dependency_sha256}." \
        >&2
      echo \
        "Use one explicit dependency-bootstrap job for this lock change; ordinary lanes never sync." \
        >&2
      exit 2
    fi
    export UV_OFFLINE=1
    ;;
  bootstrap)
    api_venv="${OPEN_ALM_API_BOOTSTRAP_VENV:-}"
    if [[ -z "$api_venv" || "$api_venv" != /* || "$api_venv" == "/" ]]; then
      echo \
        "OPEN_ALM_API_BOOTSTRAP_VENV must be an explicit absolute path in bootstrap mode." \
        >&2
      exit 2
    fi
    if [[ "$api_venv" == "${OPEN_ALM_API_IMAGE_VENV:-/opt/open-alm/venvs/api}" ]]; then
      echo "Bootstrap mode refuses to modify the immutable image venv." >&2
      exit 2
    fi
    bootstrap_dependency_file="$api_venv/$dependency_marker_name"
    if [[ -r "$bootstrap_dependency_file" ]] &&
       [[ "$(<"$bootstrap_dependency_file")" == "$actual_dependency_sha256" ]] &&
       [[ -x "$api_venv/bin/python" ]]; then
      echo \
        "[api-dependencies] reusing bootstrap venv digest=${actual_dependency_sha256}" \
        >&2
    else
      if [[ -e "$api_venv" ]]; then
        echo \
          "Bootstrap venv exists without the current dependency identity: ${api_venv}" \
          >&2
        echo "Use a clean digest-scoped OPEN_ALM_API_BOOTSTRAP_VENV path." >&2
        exit 2
      fi
      if ! command -v uv >/dev/null 2>&1; then
        echo "uv is required for the explicit API dependency bootstrap." >&2
        exit 2
      fi
      mkdir -p "$(dirname "$api_venv")"
      unset UV_OFFLINE
      echo \
        "[api-dependencies] bootstrapping digest=${actual_dependency_sha256}" \
        >&2
      UV_PROJECT_ENVIRONMENT="$api_venv" \
        UV_COMPILE_BYTECODE=1 \
        uv sync \
          --directory "$api_root" \
          --frozen \
          --python 3.12 \
          --group dev \
          --no-install-project
      printf '%s\n' "$actual_dependency_sha256" >"$bootstrap_dependency_file"
    fi
    export UV_OFFLINE=1
    ;;
  *)
    echo "OPEN_ALM_API_DEPENDENCY_MODE must be offline or bootstrap." >&2
    exit 2
    ;;
esac

api_python="$api_venv/bin/python"
if [[ ! -x "$api_python" ]]; then
  echo "API validation Python is unavailable: ${api_python}" >&2
  exit 2
fi

actual_node_dependency_sha256="$(node_dependency_sha256)"
image_node_dependency_file="${OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE:-/opt/open-alm/node-runtime/dependency.sha256}"
image_node_modules="${OPEN_ALM_API_IMAGE_NODE_MODULES:-/opt/open-alm/node-runtime/node_modules}"
checkout_node_modules="${OPEN_ALM_API_CHECKOUT_NODE_MODULES_LINK:-$repo_root/node_modules}"
if [[ ! -r "$image_node_dependency_file" ]]; then
  echo \
    "API Node dependency identity is unavailable: ${image_node_dependency_file}" \
    >&2
  exit 2
fi
read -r image_node_dependency_sha256 <"$image_node_dependency_file"
if [[ "$image_node_dependency_sha256" != "$actual_node_dependency_sha256" ]]; then
  echo \
    "API Node dependency mismatch: image=${image_node_dependency_sha256} checkout=${actual_node_dependency_sha256}." \
    >&2
  exit 2
fi
if [[ "$image_node_modules" != /* || ! -d "$image_node_modules" ]]; then
  echo \
    "API Node runtime is unavailable: ${image_node_modules}" \
    >&2
  exit 2
fi
if [[ "$checkout_node_modules" != /* || "$checkout_node_modules" == "/" ]]; then
  echo \
    "OPEN_ALM_API_CHECKOUT_NODE_MODULES_LINK must be an explicit absolute path." \
    >&2
  exit 2
fi
if [[ -L "$checkout_node_modules" ]]; then
  if [[ "$(readlink "$checkout_node_modules")" != "$image_node_modules" ]]; then
    echo \
      "API Node runtime link points to an unexpected target: ${checkout_node_modules}" \
      >&2
    exit 2
  fi
elif [[ ! -e "$checkout_node_modules" ]]; then
  ln -s "$image_node_modules" "$checkout_node_modules"
fi

export VIRTUAL_ENV="$api_venv"
export UV_PROJECT_ENVIRONMENT="$api_venv"
export PATH="$api_venv/bin:$PATH"

if [[ "${OPEN_ALM_API_CLEANUP_ONLY:-0}" == "1" ]]; then
  if [[ "$lane" != "external" || "$#" -ne 0 ]]; then
    echo "OPEN_ALM_API_CLEANUP_ONLY=1 requires the external lane without test paths." >&2
    exit 2
  fi
  cd "$api_root"
  exec "$api_python" tests/integration_infra.py cleanup-current
fi

if [[ "${OPEN_ALM_API_PREPARE_ONLY:-0}" == "1" ]]; then
  "$api_python" -I -c \
    'import pytest, xdist; assert pytest.version_tuple[0] == 8'
  echo \
    "[api-dependencies] ready mode=${dependency_mode} digest=${actual_dependency_sha256}" \
    >&2
  exit 0
fi

if [[ "$#" -eq 0 ]]; then
  set -- tests
fi

pytest_args=(-q -m "$pytest_marker")
if [[ "$lane" == "standard" ]]; then
  pytest_workers="${OPEN_ALM_API_PYTEST_WORKERS:-8}"
  pytest_scheduler="${OPEN_ALM_API_PYTEST_SCHEDULER:-worksteal}"
  if [[ ! "$pytest_workers" =~ ^[1-9][0-9]*$ ]]; then
    echo "OPEN_ALM_API_PYTEST_WORKERS must be a positive integer." >&2
    exit 2
  fi
  case "$pytest_scheduler" in
    load)
      pytest_maxschedchunk="${OPEN_ALM_API_PYTEST_MAXSCHEDCHUNK:-1}"
      if [[ ! "$pytest_maxschedchunk" =~ ^[1-9][0-9]*$ ]]; then
        echo "OPEN_ALM_API_PYTEST_MAXSCHEDCHUNK must be a positive integer." >&2
        exit 2
      fi
      pytest_args+=(
        -n "$pytest_workers"
        --dist load
        --maxschedchunk "$pytest_maxschedchunk"
      )
      ;;
    worksteal)
      pytest_args+=(-n "$pytest_workers" --dist worksteal)
      ;;
    *)
      echo "OPEN_ALM_API_PYTEST_SCHEDULER must be load or worksteal." >&2
      exit 2
      ;;
  esac
  pytest_args+=(--durations 50 --durations-min 1)
fi
pytest_args+=("$@")

if [[ "$lane" != "external" ]]; then
  cd "$api_root"
  if [[ "${OPEN_ALM_API_ALLOW_EMPTY:-0}" != "1" ]]; then
    exec "$api_python" -m pytest "${pytest_args[@]}"
  fi
  pytest_status=0
  "$api_python" -m pytest "${pytest_args[@]}" || pytest_status=$?
  if [[ "$pytest_status" -eq 5 ]]; then
    echo "[api-tests] lane=${lane} has no selected test items" >&2
    exit 0
  fi
  exit "$pytest_status"
fi

pytest_pid=""
cleanup_done=0
cleanup_status=0

if [[ -z "${OPEN_ALM_API_TEST_RUN_ID:-}" ]]; then
  if [[ -n "${CI_JOB_ID:-}" ]]; then
    OPEN_ALM_API_TEST_RUN_ID="$CI_JOB_ID"
  elif [[ -r /proc/sys/kernel/random/uuid ]]; then
    read -r OPEN_ALM_API_TEST_RUN_ID </proc/sys/kernel/random/uuid
  else
    OPEN_ALM_API_TEST_RUN_ID="$("$api_python" -I -c \
      'import uuid; print(uuid.uuid4())')"
  fi
fi
export OPEN_ALM_API_TEST_RUN_ID

cleanup_external_resources() {
  if [[ "$cleanup_done" -eq 1 ]]; then
    return "$cleanup_status"
  fi
  cleanup_done=1
  if ! (
    cd "$api_root"
    "$api_python" tests/integration_infra.py cleanup-current
  ); then
    echo \
      "warning: unable to clean shared API integration resources for run ${OPEN_ALM_API_TEST_RUN_ID}" \
      >&2
    cleanup_status=1
  fi
  return "$cleanup_status"
}

handle_exit() {
  local exit_code="$?"
  trap - EXIT
  if ! cleanup_external_resources && [[ "$exit_code" -eq 0 ]]; then
    exit_code=1
  fi
  exit "$exit_code"
}

handle_signal() {
  local exit_code="$1"
  trap '' INT TERM
  if [[ -n "$pytest_pid" ]]; then
    kill -TERM "$pytest_pid" 2>/dev/null || true
    wait "$pytest_pid" 2>/dev/null || true
    pytest_pid=""
  fi
  cleanup_external_resources || true
  exit "$exit_code"
}

trap handle_exit EXIT
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

echo "API test run id: ${OPEN_ALM_API_TEST_RUN_ID}" >&2
cd "$api_root"
"$api_python" -m pytest "${pytest_args[@]}" &
pytest_pid=$!

pytest_status=0
wait "$pytest_pid" || pytest_status=$?
pytest_pid=""
if [[ "$pytest_status" -eq 5 && "${OPEN_ALM_API_ALLOW_EMPTY:-0}" == "1" ]]; then
  echo "[api-tests] lane=external has no selected test items" >&2
  pytest_status=0
fi
exit "$pytest_status"
