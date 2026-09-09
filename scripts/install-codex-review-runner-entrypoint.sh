#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${CODEX_REVIEW_RUNNER_SCRIPT:-/usr/local/bin/open-work-hub-codex-review-ci}"

if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "Installing from dirty checkout; ensure this is intentional." >&2
fi

bash -n "$repo_root/scripts/codex-review-ci.sh"
command -v codex >/dev/null 2>&1 ||
  { echo "codex CLI is unavailable." >&2; exit 2; }
command -v node >/dev/null 2>&1 && command -v glab >/dev/null 2>&1 ||
  { echo "node and glab are required for authenticated review metadata checks." >&2; exit 2; }

node_bin="$(readlink -f "$(command -v node)")"
# The privileged helper must never execute a user-writable interpreter.
node_path="$node_bin"
while :; do
  [[ "$(stat -c %u "$node_path")" == 0 ]] &&
    (( (8#$(stat -c %a "$node_path") & 8#022) == 0 )) ||
    { echo "Node.js and every parent directory must be root-owned and not group/other-writable." >&2; exit 2; }
  [[ "$node_path" != / ]] || break
  node_path="$(dirname "$node_path")"
done
id owh-review-evidence >/dev/null 2>&1 ||
  { echo "Prepare the isolated owh-review-evidence account as documented first." >&2; exit 2; }
sudo install -d -o root -g root -m 755 /usr/local/libexec
helper_tmp="$(mktemp)"
trap 'rm -f "$helper_tmp"' EXIT
{ printf '#!%s\n' "$node_bin"; tail -n +2 "$repo_root/scripts/codex-review-evidence.mjs"; } >"$helper_tmp"
sudo install -o root -g root -m 755 "$helper_tmp" /usr/local/libexec/open-work-hub-review-evidence
sudo install -o root -g root -m 755 "$repo_root/scripts/codex-review-ci.sh" "$target"
echo "Installed Open Work Hub Codex review runner entrypoint: ${target}"
