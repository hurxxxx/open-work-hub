#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
api_root="$repo_root/apps/api"
worker_root="$repo_root/apps/worker"

combined_sha256() {
  local file_path
  for file_path in "$@"; do
    sha256sum "$file_path" | awk '{print $1}'
  done | sha256sum | awk '{print $1}'
}

verify_identity() {
  local label="$1"
  local marker_file="$2"
  local actual_sha256="$3"
  local image_sha256
  if [[ ! -r "$marker_file" ]]; then
    echo "Validation image ${label} identity is unavailable: ${marker_file}" >&2
    exit 2
  fi
  read -r image_sha256 <"$marker_file"
  if [[ "$image_sha256" != "$actual_sha256" ]]; then
    echo \
      "Validation image ${label} dependency mismatch: image=${image_sha256} checkout=${actual_sha256}." \
      >&2
    exit 2
  fi
}

link_runtime() {
  local label="$1"
  local target="$2"
  local link_path="$3"
  if [[ "$target" != /* || ! -d "$target" ]]; then
    echo "Validation image ${label} runtime is unavailable: ${target}" >&2
    exit 2
  fi
  if [[ "$link_path" != /* || "$link_path" == "/" ]]; then
    echo "Validation ${label} link must be an explicit absolute path." >&2
    exit 2
  fi
  if [[ -L "$link_path" ]]; then
    if [[ "$(readlink "$link_path")" != "$target" ]]; then
      echo \
        "Validation ${label} link points to an unexpected target: ${link_path}" \
        >&2
      exit 2
    fi
    return
  fi
  if [[ -e "$link_path" ]]; then
    echo \
      "Validation ${label} link path already exists and is not the image runtime: ${link_path}" \
      >&2
    exit 2
  fi
  mkdir -p "$(dirname "$link_path")"
  ln -s "$target" "$link_path"
}

node_dependency_sha256="$(
  combined_sha256 \
    "$repo_root/package.json" \
    "$repo_root/pnpm-lock.yaml" \
    "$repo_root/pnpm-workspace.yaml" \
    "$repo_root/packages/contracts/package.json" \
    "$repo_root/packages/core-web/package.json" \
    "$repo_root/packages/ui/package.json"
)"
api_dependency_sha256="$(
  combined_sha256 "$api_root/pyproject.toml" "$api_root/uv.lock"
)"
worker_dependency_sha256="$(
  combined_sha256 "$worker_root/pyproject.toml" "$worker_root/uv.lock"
)"

node_marker="${OPEN_ALM_NODE_IMAGE_DEPENDENCY_FILE:-/opt/open-alm/node-runtime/dependency.sha256}"
api_marker="${OPEN_ALM_API_IMAGE_DEPENDENCY_FILE:-/opt/open-alm/locks/api/dependency.sha256}"
worker_marker="${OPEN_ALM_WORKER_IMAGE_DEPENDENCY_FILE:-/opt/open-alm/locks/worker/dependency.sha256}"
node_runtime="${OPEN_ALM_NODE_IMAGE_MODULES:-/opt/open-alm/node-runtime/node_modules}"
api_runtime="${OPEN_ALM_API_IMAGE_VENV:-/opt/open-alm/venvs/api}"
worker_runtime="${OPEN_ALM_WORKER_IMAGE_VENV:-/opt/open-alm/venvs/worker}"

verify_identity "Node" "$node_marker" "$node_dependency_sha256"
verify_identity "API" "$api_marker" "$api_dependency_sha256"
verify_identity "worker" "$worker_marker" "$worker_dependency_sha256"
link_runtime \
  "Node" \
  "$node_runtime" \
  "${OPEN_ALM_NODE_CHECKOUT_MODULES_LINK:-$repo_root/node_modules}"
link_runtime \
  "API" \
  "$api_runtime" \
  "${OPEN_ALM_API_CHECKOUT_VENV_LINK:-$repo_root/.runtime/ci-api-venv}"
link_runtime \
  "worker" \
  "$worker_runtime" \
  "${OPEN_ALM_WORKER_CHECKOUT_VENV_LINK:-$repo_root/.runtime/ci-worker-venv}"

echo \
  "[validation-runtime] ready node=${node_dependency_sha256} api=${api_dependency_sha256} worker=${worker_dependency_sha256}"
