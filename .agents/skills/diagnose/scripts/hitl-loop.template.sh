#!/usr/bin/env bash
# Human-in-the-loop reproduction loop.
# Copy this file, edit the steps below, and run it.
# The agent runs the script; the user follows prompts in their terminal.
#
# Usage:
#   bash hitl-loop.template.sh
#
# Two helpers:
#   step "<instruction>"          → show instruction, wait for Enter
#   capture VAR "<question>"      → show question, read response into VAR
#
# Capture only a bounded reproduction signal, never raw logs or credentials.

set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  printf '%s\n' 'Copy this template, set REPRO_INSTRUCTION to the task-specific reproduction action, then run it interactively. Do not paste raw logs, tokens, prompts, or customer data.'
  exit 0
fi

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- edit below ---------------------------------------------------------

REPRO_INSTRUCTION=""
if [[ -z "$REPRO_INSTRUCTION" ]]; then
  printf '%s\n' 'Set REPRO_INSTRUCTION in a task-local copy before running this template.' >&2
  exit 2
fi
step "$REPRO_INSTRUCTION"
capture REPRODUCED "Did the specified failure reproduce? (y/n/unknown; no raw error text)"
case "$REPRODUCED" in
  y|n|unknown) ;;
  *) REPRODUCED=unknown ;;
esac

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'REPRODUCED=%s\n' "$REPRODUCED"
