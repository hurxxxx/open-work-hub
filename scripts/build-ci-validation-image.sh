#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="${OPEN_WORK_HUB_VALIDATION_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
image="${OPEN_WORK_HUB_VALIDATION_IMAGE:-open-work-hub-validation:node22-python312}"
docker_config_dir="${OPEN_WORK_HUB_VALIDATION_DOCKER_CONFIG:-$repo_root/.runtime/ci-validation-docker-config}"

combined_sha256() {
  local file_path
  for file_path in "$@"; do
    sha256sum "$file_path" | awk '{print $1}'
  done | sha256sum | awk '{print $1}'
}

api_dependency_sha256() {
  combined_sha256 "$repo_root/apps/api/pyproject.toml" "$repo_root/apps/api/uv.lock"
}

node_dependency_sha256() {
  combined_sha256 \
    "$repo_root/package.json" \
    "$repo_root/pnpm-lock.yaml" \
    "$repo_root/pnpm-workspace.yaml" \
    "$repo_root/packages/contracts/package.json" \
    "$repo_root/packages/core-web/package.json" \
    "$repo_root/packages/ui/package.json"
}

worker_dependency_sha256() {
  combined_sha256 "$repo_root/apps/worker/pyproject.toml" "$repo_root/apps/worker/uv.lock"
}

print_contract() {
  printf 'image=%s\n' "$image"
  printf 'dockerfile_sha256=%s\n' "$(sha256sum "$repo_root/ops/ci/validation-runner/Dockerfile" | awk '{print $1}')"
  printf 'api_dependency_sha256=%s\n' "$(api_dependency_sha256)"
  printf 'node_dependency_sha256=%s\n' "$(node_dependency_sha256)"
  printf 'worker_dependency_sha256=%s\n' "$(worker_dependency_sha256)"
}

build_image() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required to build the validation image." >&2
    return 2
  fi
  mkdir -p "$docker_config_dir"
  docker --config "$docker_config_dir" build \
    --build-arg "API_DEPENDENCY_SHA256=$(api_dependency_sha256)" \
    --build-arg "NODE_DEPENDENCY_SHA256=$(node_dependency_sha256)" \
    --build-arg "WORKER_DEPENDENCY_SHA256=$(worker_dependency_sha256)" \
    --file "$repo_root/ops/ci/validation-runner/Dockerfile" \
    --tag "$image" \
    "$repo_root"
  docker --config "$docker_config_dir" run --rm --pull=never \
    --network none \
    "$image" \
    bash -lc '
      node --version
      pnpm --version
      python --version
      uv --version
      test -r "$OPEN_WORK_HUB_API_IMAGE_DEPENDENCY_FILE"
      test -r "$OPEN_WORK_HUB_NODE_IMAGE_DEPENDENCY_FILE"
      test -r "$OPEN_WORK_HUB_WORKER_IMAGE_DEPENDENCY_FILE"
    '
  echo "Built and verified ${image}."
}

case "${1:-}" in
  "")
    build_image
    ;;
  --print-contract)
    print_contract
    ;;
  *)
    echo "usage: $0 [--print-contract]" >&2
    exit 2
    ;;
esac
