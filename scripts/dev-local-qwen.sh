#!/usr/bin/env bash

set -Eeuo pipefail

MODEL_REF="${OPEN_WORK_HUB_DEV_QWEN_MODEL_REF:-ai/qwen3.6:35B-A3B-UD-Q4_K_M}"
OPENAI_BASE_URL="${OPEN_WORK_HUB_LLM_LOCAL_BASE_URL:-http://127.0.0.1:12434/engines/v1}"
COMMAND="${1:-status}"

require_model_runner() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker CLI is required." >&2
    exit 1
  fi
  if ! docker model status >/dev/null 2>&1; then
    echo "Docker Model Runner is not running. Enable it in Docker Desktop first." >&2
    exit 1
  fi
}

show_status() {
  docker model status
  docker model list
  docker model ps
  printf '\nOpenAI-compatible models endpoint: %s/models\n' "$OPENAI_BASE_URL"
  curl -fsS --max-time 10 "${OPENAI_BASE_URL}/models" || true
  printf '\n'
}

smoke_model() {
  QWEN_OPENAI_BASE_URL="$OPENAI_BASE_URL" \
  QWEN_MODEL_REF="$MODEL_REF" \
  python3 - <<'PY'
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


base_url = os.environ["QWEN_OPENAI_BASE_URL"].rstrip("/")
preferred_model = os.environ["QWEN_MODEL_REF"]

with urlopen(f"{base_url}/models", timeout=15) as response:
    models_payload = json.loads(response.read().decode("utf-8"))
model_ids = [
    item.get("id")
    for item in models_payload.get("data", [])
    if isinstance(item, dict) and isinstance(item.get("id"), str)
]
model = next((item for item in model_ids if "qwen3.6" in item.lower()), None)
if model is None:
    raise SystemExit(
        f"Qwen3.6 is not exposed by {base_url}/models. "
        f"Pull and start {preferred_model} first."
    )

payload = json.dumps(
    {
        "model": model,
        "messages": [
            {"role": "system", "content": "Answer with exactly READY."},
            {"role": "user", "content": "Health check"},
        ],
        "temperature": 0,
        "max_tokens": 16,
        "chat_template_kwargs": {"enable_thinking": False},
    }
).encode("utf-8")
request = Request(
    f"{base_url}/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    method="POST",
)
with urlopen(request, timeout=1200) as response:
    completion = json.loads(response.read().decode("utf-8"))
text = completion["choices"][0]["message"]["content"].strip()
if text != "READY":
    raise SystemExit(f"Local Qwen returned an unexpected smoke response: {text!r}")
print(f"Local Qwen smoke passed: model={model}, response={text!r}")
PY
}

require_model_runner

case "$COMMAND" in
  pull)
    docker model pull "$MODEL_REF"
    ;;
  start)
    docker model run --detach "$MODEL_REF"
    ;;
  up)
    docker model pull "$MODEL_REF"
    docker model run --detach "$MODEL_REF"
    ;;
  status)
    show_status
    ;;
  smoke)
    smoke_model
    ;;
  *)
    echo "Usage: $0 {pull|start|up|status|smoke}" >&2
    exit 2
    ;;
esac
