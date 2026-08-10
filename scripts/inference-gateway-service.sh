#!/usr/bin/env bash
set -euo pipefail

GATEWAY_ROOT="${AI_DO_INFERENCE_GATEWAY_ROOT:-/projects/ai-do/ai-do-inference-gateway}"
COMMAND="${1:-status}"

if [[ ! -x "$GATEWAY_ROOT/scripts/inference-gateway-service.sh" ]]; then
  echo "Inference Gateway checkout is not ready at $GATEWAY_ROOT" >&2
  exit 1
fi

exec "$GATEWAY_ROOT/scripts/inference-gateway-service.sh" "$COMMAND"
