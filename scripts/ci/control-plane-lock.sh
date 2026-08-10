#!/usr/bin/env bash

open_alm_ci_control_plane_default_lock_file() {
  printf '%s\n' "/home/open-alm/.local/state/open-alm-ci-control-plane.lock"
}

acquire_open_alm_ci_control_plane_lock() {
  local requested_lock_file="${1:-$(open_alm_ci_control_plane_default_lock_file)}"

  if [[ -n "${OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD:-}" ]]; then
    if [[ "${OPEN_ALM_CI_CONTROL_PLANE_LOCK_FILE:-}" != "$requested_lock_file" ]] ||
       [[ ! "$OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD" =~ ^[0-9]+$ ]] ||
       ! : >&"$OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD" ||
       ! flock -n "$OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD"; then
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

  exec {OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD}>"$requested_lock_file"
  chmod 600 "$requested_lock_file"
  if ! flock -n "$OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD"; then
    exec {OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD}>&-
    unset OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD
    echo "Another CI control-plane mutation is active." >&2
    return 2
  fi
  OPEN_ALM_CI_CONTROL_PLANE_LOCK_FILE="$requested_lock_file"
  export OPEN_ALM_CI_CONTROL_PLANE_LOCK_FD
  export OPEN_ALM_CI_CONTROL_PLANE_LOCK_FILE
}
