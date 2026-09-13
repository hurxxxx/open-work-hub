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
glab_bin="$(readlink -f "$(command -v glab)")"
# Neither privileged executable nor its parent directories may be user-writable.
for executable in "$node_bin" "$glab_bin"; do
  [[ -f "$executable" && -x "$executable" ]] || exit 2
  checked_path="$executable"
  while :; do
    [[ "$(stat -c %u "$checked_path")" == 0 ]] &&
      (( (8#$(stat -c %a "$checked_path") & 8#022) == 0 )) ||
      { echo "Node.js/glab and every parent directory must be root-owned and not group/other-writable." >&2; exit 2; }
    [[ "$checked_path" != / ]] || break
    checked_path="$(dirname "$checked_path")"
  done
done
id owh-review-evidence >/dev/null 2>&1 ||
  { echo "Prepare the isolated owh-review-evidence account as documented first." >&2; exit 2; }
sudo install -d -o root -g root -m 755 /usr/local/libexec
helper_tmp="$(mktemp)"
trap 'rm -f "$helper_tmp"' EXIT
"$node_bin" --input-type=module - "$repo_root/scripts/codex-review-evidence.mjs" "$node_bin" "$glab_bin" >"$helper_tmp" <<'NODE'
import fs from 'node:fs';
const [source, node, glab] = process.argv.slice(2);
const code = fs.readFileSync(source, 'utf8');
const marker = 'const installedGlabBin = null;';
if (code.split(marker).length !== 2) throw new Error('Invalid evidence helper template');
process.stdout.write(code.replace(/^#![^\n]*/, () => `#!${node}`)
  .replace(marker, () => `const installedGlabBin = ${JSON.stringify(glab)};`));
NODE
sudo install -o root -g root -m 755 "$helper_tmp" /usr/local/libexec/open-work-hub-review-evidence
sudo install -o root -g root -m 755 "$repo_root/scripts/codex-review-ci.sh" "$target"
echo "Installed Open Work Hub Codex review runner entrypoint: ${target}"
