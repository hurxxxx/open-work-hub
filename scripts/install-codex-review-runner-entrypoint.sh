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

sudo install -o root -g root -m 755 "$repo_root/scripts/codex-review-ci.sh" "$target"
echo "Installed Open Work Hub Codex review runner entrypoint: ${target}"
