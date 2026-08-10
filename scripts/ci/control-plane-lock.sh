#!/usr/bin/env bash

ai_do_ci_control_plane_default_lock_file() {
  printf '%s\n' "/home/dwdcc/.local/state/ai-do-ci-control-plane.lock"
}

acquire_ai_do_ci_control_plane_lock() {
  local requested_lock_file="${1:-$(ai_do_ci_control_plane_default_lock_file)}"

  if [[ -n "${AI_DO_CI_CONTROL_PLANE_LOCK_FD:-}" ]]; then
    if [[ "${AI_DO_CI_CONTROL_PLANE_LOCK_FILE:-}" != "$requested_lock_file" ]] ||
       [[ ! "$AI_DO_CI_CONTROL_PLANE_LOCK_FD" =~ ^[0-9]+$ ]] ||
       ! : >&"$AI_DO_CI_CONTROL_PLANE_LOCK_FD" ||
       ! flock -n "$AI_DO_CI_CONTROL_PLANE_LOCK_FD"; then
      echo "Inherited CI control-plane lock state is invalid." >&2
      return 2
    fi
    return 0
  fi

  if ! command -v flock >/dev/null 2>&1; then
    echo "Required command is unavailable: flock." >&2
    return 2
  fi
  if [[ ! -d "$(dirname "$requested_lock_file")" ]]; then
    echo "CI control-plane lock directory is unavailable." >&2
    return 2
  fi

  exec {AI_DO_CI_CONTROL_PLANE_LOCK_FD}>"$requested_lock_file"
  chmod 600 "$requested_lock_file"
  if ! flock -n "$AI_DO_CI_CONTROL_PLANE_LOCK_FD"; then
    exec {AI_DO_CI_CONTROL_PLANE_LOCK_FD}>&-
    unset AI_DO_CI_CONTROL_PLANE_LOCK_FD
    echo "Another CI control-plane mutation is active." >&2
    return 2
  fi
  AI_DO_CI_CONTROL_PLANE_LOCK_FILE="$requested_lock_file"
  export AI_DO_CI_CONTROL_PLANE_LOCK_FD
  export AI_DO_CI_CONTROL_PLANE_LOCK_FILE
}
