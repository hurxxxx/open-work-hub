#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="${OPEN_WORK_HUB_VALIDATION_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
image="${OPEN_WORK_HUB_VALIDATION_IMAGE:-open-work-hub-validation:node22-python312}"
docker_config_dir="${OPEN_WORK_HUB_VALIDATION_DOCKER_CONFIG:-$repo_root/.runtime/ci-validation-docker-config}"
postgres_major=""
postgres_client_image=""
platform=""
print_only=0

usage() {
  cat <<'USAGE'
usage: build-ci-validation-image.sh --postgres-major MAJOR [options]
  --postgres-major MAJOR          Installed project/CI PostgreSQL server major (required to build)
  --postgres-client-image DIGEST  postgres@sha256:... from a previous verified build
  --platform PLATFORM            linux/amd64 or linux/arm64 (default: Docker server platform)
  --print-contract               Print source/dependency identities without Docker or building

Without an explicit digest, resolve the official postgres:<MAJOR>-bookworm tag
to an immutable manifest digest. Reuse a matching verified image, otherwise build.
USAGE
}

while (( $# )); do
  case "$1" in
    --postgres-major|--postgres-client-image|--platform)
      if (( $# < 2 )) || [[ -z "$2" ]]; then
        echo "Missing value for $1" >&2
        exit 2
      fi
      case "$1" in
        --postgres-major) postgres_major="$2" ;;
        --postgres-client-image) postgres_client_image="$2" ;;
        --platform) platform="$2" ;;
      esac
      shift 2
      ;;
    --print-contract) print_only=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [[ -n "$postgres_major" && ! "$postgres_major" =~ ^[1-9][0-9]+$ ]]; then
  echo "PostgreSQL major must be an integer >= 10." >&2
  exit 2
fi
if [[ -n "$postgres_client_image" && ! "$postgres_client_image" =~ ^postgres@sha256:[a-f0-9]{64}$ ]]; then
  echo "PostgreSQL client image must be an immutable official postgres@sha256 digest." >&2
  exit 2
fi
if [[ -n "$platform" && "$platform" != linux/amd64 && "$platform" != linux/arm64 ]]; then
  echo "Validation platform must be linux/amd64 or linux/arm64." >&2
  exit 2
fi

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

verify_portable_client_paths() {
  if grep -Fq 'linux-gnu' "$repo_root/ops/ci/validation-runner/Dockerfile"; then
    echo "Validation image must discover architecture-specific PostgreSQL client paths." >&2
    return 2
  fi
}

print_contract() {
  printf 'image=%s\n' "$image"
  printf 'dockerfile_sha256=%s\n' "$(sha256sum "$repo_root/ops/ci/validation-runner/Dockerfile" | awk '{print $1}')"
  printf 'api_dependency_sha256=%s\n' "$(api_dependency_sha256)"
  printf 'node_dependency_sha256=%s\n' "$(node_dependency_sha256)"
  printf 'worker_dependency_sha256=%s\n' "$(worker_dependency_sha256)"
  printf 'builder_sha256=%s\n' "$(sha256sum "$repo_root/scripts/build-ci-validation-image.sh" | awk '{print $1}')"
  printf 'postgres_major=%s\n' "$postgres_major"
  printf 'postgres_client_image=%s\n' "$postgres_client_image"
  printf 'platform=%s\n' "$platform"
}

verify_image() {
  docker --config "$docker_config_dir" run --rm --pull=never \
    --network none --platform "$platform" \
    "$image" \
    bash -euo pipefail -c '
      expected_major="$1"
      node --version
      pnpm --version
      python --version
      uv --version
      tmux -V
      test "$(cat /opt/open-work-hub/locks/api/postgres-major)" = "$expected_major"
      pg_dump --version | grep -Eq "^pg_dump \(PostgreSQL\) ${expected_major}\."
      pg_restore --version | grep -Eq "^pg_restore \(PostgreSQL\) ${expected_major}\."
      psql --version | grep -Eq "^psql \(PostgreSQL\) ${expected_major}\."
      test -r "$OPEN_WORK_HUB_API_IMAGE_DEPENDENCY_FILE"
      test -r "$OPEN_WORK_HUB_NODE_IMAGE_DEPENDENCY_FILE"
      test -r "$OPEN_WORK_HUB_WORKER_IMAGE_DEPENDENCY_FILE"
      test "$(cat "$OPEN_WORK_HUB_API_IMAGE_DEPENDENCY_FILE")" = "$2"
      test "$(cat "$OPEN_WORK_HUB_NODE_IMAGE_DEPENDENCY_FILE")" = "$3"
      test "$(cat "$OPEN_WORK_HUB_WORKER_IMAGE_DEPENDENCY_FILE")" = "$4"
      cd /opt/open-work-hub/node-runtime
      pnpm exec nx --version
      node -e '\''const { chromium } = require("@playwright/test"); chromium.launch({ headless: true }).then((browser) => browser.close()).catch((error) => { console.error(error); process.exit(1); })'\''
    ' -- "$postgres_major" "$(api_dependency_sha256)" "$(node_dependency_sha256)" "$(worker_dependency_sha256)"
}

build_image() {
  if [[ -z "$postgres_major" ]]; then
    echo "Use --postgres-major with the installed project/CI server major; there is no fixed default." >&2
    return 2
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required to build the validation image." >&2
    return 2
  fi
  mkdir -p "$docker_config_dir"
  if [[ -z "$platform" ]]; then
    platform="$(docker --config "$docker_config_dir" version --format '{{.Server.Os}}/{{.Server.Arch}}')"
  fi
  if [[ "$platform" != linux/amd64 && "$platform" != linux/arm64 ]]; then
    echo "Validation requires a Linux AMD64 or ARM64 Docker server/platform." >&2
    return 2
  fi
  if [[ -z "$postgres_client_image" ]]; then
    if ! command -v jq >/dev/null 2>&1; then
      echo "jq is required to resolve the PostgreSQL image manifest." >&2
      return 2
    fi
    local digest
    digest="$(docker --config "$docker_config_dir" buildx imagetools inspect \
      --format '{{json .Manifest}}' "postgres:${postgres_major}-bookworm" | jq -er '.digest')"
    if [[ ! "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
      echo "Unable to resolve the official PostgreSQL image to an immutable digest." >&2
      return 2
    fi
    postgres_client_image="postgres@$digest"
  fi
  local contract_sha256 existing_contract
  contract_sha256="$(print_contract | sha256sum | awk '{print $1}')"
  existing_contract="$(docker --config "$docker_config_dir" image inspect \
    --format '{{index .Config.Labels "io.open-work-hub.validation.contract"}}' "$image" 2>/dev/null || true)"
  if [[ "$existing_contract" == "$contract_sha256" ]]; then
    verify_image
    print_contract
    echo "Reused and verified ${image}."
    return
  fi
  docker --config "$docker_config_dir" build \
    --platform "$platform" \
    --build-arg "POSTGRES_MAJOR=$postgres_major" \
    --build-arg "POSTGRES_CLIENT_IMAGE=$postgres_client_image" \
    --build-arg "VALIDATION_CONTRACT_SHA256=$contract_sha256" \
    --build-arg "API_DEPENDENCY_SHA256=$(api_dependency_sha256)" \
    --build-arg "NODE_DEPENDENCY_SHA256=$(node_dependency_sha256)" \
    --build-arg "WORKER_DEPENDENCY_SHA256=$(worker_dependency_sha256)" \
    --file "$repo_root/ops/ci/validation-runner/Dockerfile" \
    --tag "$image" \
    "$repo_root"
  verify_image
  print_contract
  echo "Built and verified ${image}."
}

verify_portable_client_paths
if (( print_only )); then
  print_contract
else
  build_image
fi
