#!/usr/bin/env bash

set -euo pipefail

# Reapply the local VS Code Codex extension fix for GitHub issue 16849.
# Usage: pnpm fix:codex-issue-16849

before='"open-in-targets":async()=>{throw new Error("open-in-target not supported in extension")},"set-preferred-app":async()=>{throw new Error("open-in-target not supported in extension")}'
after='"open-in-targets":async()=>({targets:[]}),"set-preferred-app":async()=>({})'

roots=(
  "$HOME/.vscode/extensions"
  "$HOME/.vscode-insiders/extensions"
  "$HOME/.cursor/extensions"
)

patched_any=0
found_any=0

for root in "${roots[@]}"; do
  [[ -d "$root" ]] || continue

  while IFS= read -r extension_dir; do
    [[ -n "$extension_dir" ]] || continue
    found_any=1

    extension_js="$extension_dir/out/extension.js"
    [[ -f "$extension_js" ]] || continue

    set +e
    EXTENSION_JS="$extension_js" BEFORE="$before" AFTER="$after" node <<'NODE'
const fs = require('fs');

const path = process.env.EXTENSION_JS;
const before = process.env.BEFORE;
const after = process.env.AFTER;
const text = fs.readFileSync(path, 'utf8');

if (text.includes(after)) {
  console.log(`already patched: ${path}`);
  process.exit(10);
}

const matchCount = text.split(before).length - 1;
if (matchCount !== 1) {
  console.log(`pattern not found: ${path}`);
  process.exit(20);
}

const backupPath = `${path}.bak-issue-16849-${new Date().toISOString().replace(/[:.]/g, '-')}`;
fs.copyFileSync(path, backupPath);
fs.writeFileSync(path, text.replace(before, after), 'utf8');
console.log(`patched: ${path}`);
console.log(`backup: ${backupPath}`);
NODE
    status=$?
    set -e

    if [[ $status -eq 0 ]]; then
      patched_any=1
    elif [[ $status -eq 10 || $status -eq 20 ]]; then
      :
    else
      exit "$status"
    fi
  done < <(find "$root" -maxdepth 1 -type d -name 'openai.chatgpt-*' | sort)
done

if [[ $found_any -eq 0 ]]; then
  echo "No installed openai.chatgpt VS Code extension was found."
  exit 1
fi

if [[ $patched_any -eq 1 ]]; then
  echo "Reload VS Code windows with 'Developer: Reload Window' to apply the patched extension."
else
  echo "No new patch was applied."
fi
