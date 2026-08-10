#!/usr/bin/env bash
set -euo pipefail

GATEWAY_ROOT="${OPEN_WORK_HUB_INFERENCE_GATEWAY_ROOT:-/projects/open-work-hub/open-work-hub-inference-gateway}"
COMMAND="${1:-status}"

if [[ ! -x "$GATEWAY_ROOT/scripts/inference-gateway-service.sh" ]]; then
  echo "Inference Gateway checkout is not ready at $GATEWAY_ROOT" >&2
  exit 1
fi

exec "$GATEWAY_ROOT/scripts/inference-gateway-service.sh" "$COMMAND"
