#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
helper="$repo_root/scripts/build-ci-validation-image.sh"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT

mkdir -p \
  "$temporary_root/apps/api" \
  "$temporary_root/apps/worker" \
  "$temporary_root/ops/ci/validation-runner" \
  "$temporary_root/packages/contracts" \
  "$temporary_root/packages/core-web" \
  "$temporary_root/packages/ui"
cp "$repo_root/apps/api/pyproject.toml" "$temporary_root/apps/api/"
cp "$repo_root/apps/api/uv.lock" "$temporary_root/apps/api/"
cp "$repo_root/apps/worker/pyproject.toml" "$temporary_root/apps/worker/"
cp "$repo_root/apps/worker/uv.lock" "$temporary_root/apps/worker/"
cp "$repo_root/package.json" "$temporary_root/"
cp "$repo_root/pnpm-lock.yaml" "$temporary_root/"
cp "$repo_root/pnpm-workspace.yaml" "$temporary_root/"
cp \
  "$repo_root/packages/contracts/package.json" \
  "$temporary_root/packages/contracts/"
cp \
  "$repo_root/packages/core-web/package.json" \
  "$temporary_root/packages/core-web/"
cp "$repo_root/packages/ui/package.json" "$temporary_root/packages/ui/"
cp \
  "$repo_root/ops/ci/validation-runner/Dockerfile" \
  "$temporary_root/ops/ci/validation-runner/"

contract="$(
  AI_DO_VALIDATION_REPO_ROOT="$temporary_root" \
    bash "$helper" --print-contract
)"
grep -F \
  'image=ai-do-validation:node25-python312-pg18-api-a3e8c22a3552-worker-3149583cef20-node-e7c57b3bacf9-484482bced42' \
  <<<"$contract" >/dev/null
grep -F \
  'image_id=sha256:89345c7907b296ea557a61e9a4c956ee9915c3fb9b611b3923f36bcc4c65d526' \
  <<<"$contract" >/dev/null
grep -F \
  'dockerfile_sha256=484482bced42fc34de9efc211022aa4bc39c5cf533bf4d29e435f378b9ce4a14' \
  <<<"$contract" >/dev/null
grep -F \
  'api_dependency_sha256=a3e8c22a3552c93ab0108e3a8085a7a6581b21b06617ff03b66af07292a058b3' \
  <<<"$contract" >/dev/null
grep -F \
  'node_dependency_sha256=e7c57b3bacf997bd39ddb5532225ed427231a4dcc03fe189e75390edc7b0bef1' \
  <<<"$contract" >/dev/null
grep -F \
  'worker_dependency_sha256=3149583cef207cba735026353ddfa068de461899b45bead09ecd7cbd926d87ef' \
  <<<"$contract" >/dev/null

printf '\n# contract mismatch\n' \
  >>"$temporary_root/apps/api/pyproject.toml"
if AI_DO_VALIDATION_REPO_ROOT="$temporary_root" \
  bash "$helper" --verify-source-only \
  >"$temporary_root/mismatch.out" 2>"$temporary_root/mismatch.err"; then
  echo "expected changed API dependency inputs to fail source verification" >&2
  exit 1
fi
grep -F \
  'Validation image API dependencies do not match' \
  "$temporary_root/mismatch.err" >/dev/null

if grep -Eq \
  '\b(gitlab-runner|glab|systemctl|service|docker restart)\b' \
  "$helper"; then
  echo "validation image build helper must not mutate runner control state" >&2
  exit 1
fi

echo "build-ci-validation-image contract tests passed"
