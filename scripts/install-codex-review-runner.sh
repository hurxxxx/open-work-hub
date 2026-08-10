#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${CODEX_REVIEW_RUNNER_SCRIPT:-/home/dwdcc/.local/bin/ai-do-codex-review-ci}"
current_branch="$(git -C "$repo_root" branch --show-current)"

if [[ "$current_branch" != "dev" ]]; then
  echo "Refusing to install Codex review runner from branch ${current_branch:-<detached>}; use clean dev after merge." >&2
  exit 2
fi
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "Refusing to install Codex review runner from a dirty checkout." >&2
  exit 2
fi
source "$repo_root/scripts/ci/control-plane-lock.sh"
acquire_ai_do_ci_control_plane_lock

git -C "$repo_root" fetch --quiet origin dev
local_head="$(git -C "$repo_root" rev-parse HEAD)"
remote_head="$(git -C "$repo_root" rev-parse origin/dev)"
if [[ "$local_head" != "$remote_head" ]]; then
  echo "Refusing to install Codex review runner: local dev is not origin/dev (${local_head} != ${remote_head})." >&2
  exit 2
fi

bash -n "$repo_root/scripts/codex-review-ci.sh"
if ! command -v codex >/dev/null 2>&1; then
  echo "Refusing to install Codex review runner: codex CLI is unavailable." >&2
  exit 2
fi
if ! /usr/bin/python3 -I -c 'import yaml; assert tuple(map(int, yaml.__version__.split("."))) >= (6, 0)' >/dev/null 2>&1; then
  echo "Refusing to install Codex review runner: Python PyYAML 6+ is required." >&2
  exit 2
fi
if ! ci_contract_variant="$(
  bash "$repo_root/scripts/codex-review-ci.sh" \
    --validate-gitlab-ci-contract "$repo_root/.gitlab-ci.yml"
)"; then
  echo "Refusing to install Codex review runner: .gitlab-ci.yml violates the runner-owned contract." >&2
  exit 2
fi

review_permissions="$(
  bash "$repo_root/scripts/codex-review-ci.sh" \
    --print-review-permissions "$repo_root"
)"
probe_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$probe_dir"
}
trap cleanup EXIT
sensitive_path="/home/dwdcc/.codex/auth.json"
if [[ ! -r "$sensitive_path" ]]; then
  sensitive_path="/home/dwdcc/.config/glab-cli/config.yml"
fi
if [[ ! -r "$sensitive_path" ]]; then
  echo "Refusing to install Codex review runner: no readable credential file is available for the isolation probe." >&2
  exit 2
fi
ln -s "$sensitive_path" "$probe_dir/credential-link"
if ! codex sandbox \
  -c "permissions.review=${review_permissions}" \
  -P review \
  -C "$probe_dir" \
  /usr/bin/bash -c \
    'test -r "$1/agents.md" && ! test -r "$2" && ! test -r "$3"' \
    _ "$repo_root" "$sensitive_path" "$probe_dir/credential-link"; then
  echo "Refusing to install Codex review runner: repository-only read isolation probe failed." >&2
  exit 2
fi
codex \
  --strict-config \
  -c project_doc_max_bytes=0 \
  -c 'project_doc_fallback_filenames=[]' \
  -c features.apps=false \
  -c features.remote_plugin=false \
  -c features.multi_agent=false \
  -c 'model_reasoning_effort="high"' \
  -c 'web_search="disabled"' \
  -c 'default_permissions="review"' \
  -c "permissions.review=${review_permissions}" \
  -c 'shell_environment_policy.inherit="none"' \
  -c allow_login_shell=false \
  exec \
  --ignore-user-config \
  --ignore-rules \
  --ephemeral \
  --cd "$repo_root" \
  --skip-git-repo-check \
  --help >/dev/null

mkdir -p "$(dirname "$target")"
install -m 700 "$repo_root/scripts/codex-review-ci.sh" "$target"

echo "Installed Codex review runner script from ${local_head} to ${target} (${ci_contract_variant})"
