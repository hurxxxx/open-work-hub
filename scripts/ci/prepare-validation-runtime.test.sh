#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
helper="$repo_root/scripts/ci/prepare-validation-runtime.sh"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT

combined_sha256() {
  local file_path
  for file_path in "$@"; do
    sha256sum "$file_path" | awk '{print $1}'
  done | sha256sum | awk '{print $1}'
}

node_marker="$temporary_root/node.sha256"
api_marker="$temporary_root/api.sha256"
worker_marker="$temporary_root/worker.sha256"
node_runtime="$temporary_root/node-runtime"
api_runtime="$temporary_root/api-runtime"
worker_runtime="$temporary_root/worker-runtime"
mkdir -p "$node_runtime" "$api_runtime" "$worker_runtime"

combined_sha256 \
  "$repo_root/package.json" \
  "$repo_root/pnpm-lock.yaml" \
  "$repo_root/pnpm-workspace.yaml" \
  "$repo_root/packages/contracts/package.json" \
  "$repo_root/packages/core-web/package.json" \
  "$repo_root/packages/ui/package.json" >"$node_marker"
combined_sha256 \
  "$repo_root/apps/api/pyproject.toml" \
  "$repo_root/apps/api/uv.lock" >"$api_marker"
combined_sha256 \
  "$repo_root/apps/worker/pyproject.toml" \
  "$repo_root/apps/worker/uv.lock" >"$worker_marker"

runtime_env=(
  "OPEN_ALM_NODE_IMAGE_DEPENDENCY_FILE=$node_marker"
  "OPEN_ALM_API_IMAGE_DEPENDENCY_FILE=$api_marker"
  "OPEN_ALM_WORKER_IMAGE_DEPENDENCY_FILE=$worker_marker"
  "OPEN_ALM_NODE_IMAGE_MODULES=$node_runtime"
  "OPEN_ALM_API_IMAGE_VENV=$api_runtime"
  "OPEN_ALM_WORKER_IMAGE_VENV=$worker_runtime"
  "OPEN_ALM_NODE_CHECKOUT_MODULES_LINK=$temporary_root/checkout/node_modules"
  "OPEN_ALM_API_CHECKOUT_VENV_LINK=$temporary_root/checkout/.runtime/ci-api-venv"
  "OPEN_ALM_WORKER_CHECKOUT_VENV_LINK=$temporary_root/checkout/.runtime/ci-worker-venv"
)

env "${runtime_env[@]}" bash "$helper"
env "${runtime_env[@]}" bash "$helper"
test "$(readlink "$temporary_root/checkout/node_modules")" = "$node_runtime"
test \
  "$(readlink "$temporary_root/checkout/.runtime/ci-api-venv")" \
  = "$api_runtime"
test \
  "$(readlink "$temporary_root/checkout/.runtime/ci-worker-venv")" \
  = "$worker_runtime"

printf '%064d\n' 0 >"$worker_marker"
if env "${runtime_env[@]}" bash "$helper" \
  >"$temporary_root/mismatch.out" \
  2>"$temporary_root/mismatch.err"; then
  echo "expected worker dependency mismatch to fail" >&2
  exit 1
fi
grep -F \
  'Validation image worker dependency mismatch:' \
  "$temporary_root/mismatch.err" >/dev/null
