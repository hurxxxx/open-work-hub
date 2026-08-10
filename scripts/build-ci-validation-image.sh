#!/usr/bin/env bash
set -Eeuo pipefail

validation_image_repo_root="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
)"
if [[ "${BASH_SOURCE[0]}" == "$0" ]] &&
   [[ -n "${AI_DO_VALIDATION_REPO_ROOT:-}" ]]; then
  validation_image_repo_root="$AI_DO_VALIDATION_REPO_ROOT"
fi

AI_DO_VALIDATION_IMAGE="ai-do-validation:node25-python312-pg18-api-a3e8c22a3552-worker-3149583cef20-node-e7c57b3bacf9-484482bced42"
AI_DO_VALIDATION_IMAGE_ID="sha256:89345c7907b296ea557a61e9a4c956ee9915c3fb9b611b3923f36bcc4c65d526"
AI_DO_VALIDATION_DOCKERFILE_SHA256="484482bced42fc34de9efc211022aa4bc39c5cf533bf4d29e435f378b9ce4a14"
AI_DO_API_DEPENDENCY_SHA256="a3e8c22a3552c93ab0108e3a8085a7a6581b21b06617ff03b66af07292a058b3"
AI_DO_NODE_DEPENDENCY_SHA256="e7c57b3bacf997bd39ddb5532225ed427231a4dcc03fe189e75390edc7b0bef1"
AI_DO_WORKER_DEPENDENCY_SHA256="3149583cef207cba735026353ddfa068de461899b45bead09ecd7cbd926d87ef"

api_dependency_sha256() {
  {
    sha256sum "$validation_image_repo_root/apps/api/pyproject.toml" |
      awk '{print $1}'
    sha256sum "$validation_image_repo_root/apps/api/uv.lock" |
      awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

node_dependency_sha256() {
  {
    sha256sum "$validation_image_repo_root/package.json" | awk '{print $1}'
    sha256sum "$validation_image_repo_root/pnpm-lock.yaml" | awk '{print $1}'
    sha256sum "$validation_image_repo_root/pnpm-workspace.yaml" |
      awk '{print $1}'
    sha256sum \
      "$validation_image_repo_root/packages/contracts/package.json" |
      awk '{print $1}'
    sha256sum \
      "$validation_image_repo_root/packages/core-web/package.json" |
      awk '{print $1}'
    sha256sum "$validation_image_repo_root/packages/ui/package.json" |
      awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

worker_dependency_sha256() {
  {
    sha256sum "$validation_image_repo_root/apps/worker/pyproject.toml" |
      awk '{print $1}'
    sha256sum "$validation_image_repo_root/apps/worker/uv.lock" |
      awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

verify_validation_image_source_contract() {
  local actual_dockerfile_sha256
  local actual_api_dependency_sha256
  local actual_node_dependency_sha256
  local actual_worker_dependency_sha256

  actual_dockerfile_sha256="$(
    sha256sum \
      "$validation_image_repo_root/ops/ci/validation-runner/Dockerfile" |
      awk '{print $1}'
  )"
  if [[ "$actual_dockerfile_sha256" != "$AI_DO_VALIDATION_DOCKERFILE_SHA256" ]]; then
    echo "Validation image tag does not match the Dockerfile content digest." >&2
    return 2
  fi

  actual_api_dependency_sha256="$(api_dependency_sha256)"
  if [[ "$actual_api_dependency_sha256" != "$AI_DO_API_DEPENDENCY_SHA256" ]]; then
    echo \
      "Validation image API dependencies do not match apps/api/pyproject.toml and uv.lock." \
      >&2
    return 2
  fi

  actual_node_dependency_sha256="$(node_dependency_sha256)"
  if [[ "$actual_node_dependency_sha256" != "$AI_DO_NODE_DEPENDENCY_SHA256" ]]; then
    echo \
      "Validation image Node dependencies do not match the pinned workspace inputs." \
      >&2
    return 2
  fi

  actual_worker_dependency_sha256="$(worker_dependency_sha256)"
  if [[ "$actual_worker_dependency_sha256" != "$AI_DO_WORKER_DEPENDENCY_SHA256" ]]; then
    echo \
      "Validation image worker dependencies do not match apps/worker/pyproject.toml and uv.lock." \
      >&2
    return 2
  fi

  if [[ ! "$AI_DO_VALIDATION_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo \
      "Validation image ID is not pinned to an inspected local sha256 identity." \
      >&2
    return 2
  fi
}

print_validation_image_contract() {
  printf 'image=%s\n' "$AI_DO_VALIDATION_IMAGE"
  printf 'image_id=%s\n' "$AI_DO_VALIDATION_IMAGE_ID"
  printf 'dockerfile_sha256=%s\n' "$AI_DO_VALIDATION_DOCKERFILE_SHA256"
  printf 'api_dependency_sha256=%s\n' "$AI_DO_API_DEPENDENCY_SHA256"
  printf 'node_dependency_sha256=%s\n' "$AI_DO_NODE_DEPENDENCY_SHA256"
  printf 'worker_dependency_sha256=%s\n' "$AI_DO_WORKER_DEPENDENCY_SHA256"
}

build_and_verify_validation_image() {
  local docker_config_dir
  local built_image_id
  local built_dockerfile_sha256
  local built_api_dependency_sha256
  local built_node_dependency_sha256
  local built_worker_dependency_sha256

  verify_validation_image_source_contract
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required to build the pinned validation image." >&2
    return 2
  fi

  docker_config_dir="${AI_DO_VALIDATION_DOCKER_CONFIG:-$validation_image_repo_root/.runtime/ci-validation-docker-config}"
  mkdir -p "$docker_config_dir"

  docker --config "$docker_config_dir" build \
    --pull=false \
    --provenance=false \
    --build-arg "API_DEPENDENCY_SHA256=${AI_DO_API_DEPENDENCY_SHA256}" \
    --build-arg "NODE_DEPENDENCY_SHA256=${AI_DO_NODE_DEPENDENCY_SHA256}" \
    --build-arg "WORKER_DEPENDENCY_SHA256=${AI_DO_WORKER_DEPENDENCY_SHA256}" \
    --label \
      "ai.do.validation.dockerfile-sha256=${AI_DO_VALIDATION_DOCKERFILE_SHA256}" \
    --label \
      "ai.do.validation.api-dependency-sha256=${AI_DO_API_DEPENDENCY_SHA256}" \
    --label \
      "ai.do.validation.node-dependency-sha256=${AI_DO_NODE_DEPENDENCY_SHA256}" \
    --label \
      "ai.do.validation.worker-dependency-sha256=${AI_DO_WORKER_DEPENDENCY_SHA256}" \
    --file \
      "$validation_image_repo_root/ops/ci/validation-runner/Dockerfile" \
    --tag "$AI_DO_VALIDATION_IMAGE" \
    "$validation_image_repo_root"

  built_image_id="$(
    docker --config "$docker_config_dir" image inspect \
      --format '{{.Id}}' "$AI_DO_VALIDATION_IMAGE"
  )"
  built_dockerfile_sha256="$(
    docker --config "$docker_config_dir" image inspect \
      --format \
        '{{ index .Config.Labels "ai.do.validation.dockerfile-sha256" }}' \
      "$AI_DO_VALIDATION_IMAGE"
  )"
  built_api_dependency_sha256="$(
    docker --config "$docker_config_dir" image inspect \
      --format \
        '{{ index .Config.Labels "ai.do.validation.api-dependency-sha256" }}' \
      "$AI_DO_VALIDATION_IMAGE"
  )"
  built_node_dependency_sha256="$(
    docker --config "$docker_config_dir" image inspect \
      --format \
        '{{ index .Config.Labels "ai.do.validation.node-dependency-sha256" }}' \
      "$AI_DO_VALIDATION_IMAGE"
  )"
  built_worker_dependency_sha256="$(
    docker --config "$docker_config_dir" image inspect \
      --format \
        '{{ index .Config.Labels "ai.do.validation.worker-dependency-sha256" }}' \
      "$AI_DO_VALIDATION_IMAGE"
  )"
  if [[ "$built_image_id" != "$AI_DO_VALIDATION_IMAGE_ID" ]] ||
     [[ "$built_dockerfile_sha256" != "$AI_DO_VALIDATION_DOCKERFILE_SHA256" ]] ||
     [[ "$built_api_dependency_sha256" != "$AI_DO_API_DEPENDENCY_SHA256" ]] ||
     [[ "$built_node_dependency_sha256" != "$AI_DO_NODE_DEPENDENCY_SHA256" ]] ||
     [[ "$built_worker_dependency_sha256" != "$AI_DO_WORKER_DEPENDENCY_SHA256" ]]; then
    echo \
      "Built validation image does not match its pinned image, Dockerfile, and API dependency identities." \
      >&2
    return 2
  fi

  docker --config "$docker_config_dir" run --rm --pull=never \
    --network none \
    --volume "$validation_image_repo_root:/workspace:ro" \
    "$AI_DO_VALIDATION_IMAGE" \
    bash -lc '
      node --version
      pnpm --version
      python --version
      uv --version
      test "$(<"$AI_DO_API_IMAGE_DEPENDENCY_FILE")" = "'"$AI_DO_API_DEPENDENCY_SHA256"'"
      test "$(<"$AI_DO_API_IMAGE_NODE_DEPENDENCY_FILE")" = "'"$AI_DO_NODE_DEPENDENCY_SHA256"'"
      test "$(<"$AI_DO_WORKER_IMAGE_DEPENDENCY_FILE")" = "'"$AI_DO_WORKER_DEPENDENCY_SHA256"'"
      UV_OFFLINE=1 "$AI_DO_API_IMAGE_VENV/bin/python" -I -c \
        "import pytest, xdist; assert pytest.version_tuple[0] == 8"
      UV_OFFLINE=1 "$AI_DO_WORKER_IMAGE_VENV/bin/python" -I -c \
        "import pytest; assert pytest.version_tuple[0] == 8"
      (
        cd /opt/ai-do/node-runtime
        pnpm exec nx --version
        pnpm exec openapi-typescript --version
      )
      mkdir -p /tmp/codec-runtime/scripts
      cp /workspace/scripts/blocknote-collab-codec.mjs \
        /tmp/codec-runtime/scripts/
      ln -s "$AI_DO_API_IMAGE_NODE_MODULES" \
        /tmp/codec-runtime/node_modules
      printf "%s" "{\"blocks\":[]}" |
        (
          cd /tmp/codec-runtime
          node scripts/blocknote-collab-codec.mjs encode
        ) |
        grep -F "\"yjs_state\":" >/dev/null
    '
  docker --config "$docker_config_dir" run --rm --pull=never \
    --network none \
    --volume "$validation_image_repo_root:/workspace:ro" \
    --workdir /workspace \
    "$AI_DO_VALIDATION_IMAGE" \
    bash -lc '
      UV_OFFLINE=1 "$AI_DO_API_IMAGE_VENV/bin/python" \
        scripts/check-api-test-budget.py --output /tmp/api-test-report.json
    '

  echo \
    "Built and verified ${AI_DO_VALIDATION_IMAGE} (${AI_DO_VALIDATION_IMAGE_ID})."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    "")
      build_and_verify_validation_image
      ;;
    --verify-source-only)
      verify_validation_image_source_contract
      ;;
    --print-contract)
      verify_validation_image_source_contract
      print_validation_image_contract
      ;;
    *)
      echo \
        "usage: $0 [--verify-source-only|--print-contract]" \
        >&2
      exit 2
      ;;
  esac
fi
