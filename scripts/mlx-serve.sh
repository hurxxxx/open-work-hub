#!/usr/bin/env bash
# Launch mlx-lm's OpenAI-compatible server for local LLM.
#
# Usage:
#   bash scripts/mlx-serve.sh            # foreground
#   nohup bash scripts/mlx-serve.sh &    # background
#
# Default port:  8080 (matches OPEN_ALM_LLM_LOCAL_BASE_URL default)
#
# Override via env:
#   MLX_MODEL=mlx-community/<model> MLX_PORT=8090 bash scripts/mlx-serve.sh
#   MLX_CHAT_TEMPLATE_ARGS='{"some_model_specific_option":false}' bash scripts/mlx-serve.sh
set -euo pipefail

MLX_HOST="${MLX_HOST:-127.0.0.1}"
MLX_PORT="${MLX_PORT:-8080}"
MLX_MODEL="${MLX_MODEL:-}"
MLX_VENV="${MLX_VENV:-$HOME/.local/share/mlx-lm-venv}"
MLX_CHAT_TEMPLATE_ARGS="${MLX_CHAT_TEMPLATE_ARGS:-}"

if [[ -z "$MLX_MODEL" ]]; then
  echo "[mlx-serve] Set MLX_MODEL." >&2
  exit 2
fi

# Create venv on first run.
if [[ ! -x "$MLX_VENV/bin/mlx_lm.server" ]]; then
  echo "[mlx-serve] bootstrapping venv at $MLX_VENV ..."
  python3 -m venv "$MLX_VENV"
  "$MLX_VENV/bin/pip" install --upgrade pip --quiet
  "$MLX_VENV/bin/pip" install --quiet mlx-lm
fi

echo "[mlx-serve] model=$MLX_MODEL host=$MLX_HOST port=$MLX_PORT"
server_args=(
  --model "$MLX_MODEL"
  --host "$MLX_HOST"
  --port "$MLX_PORT"
)
if [[ -n "$MLX_CHAT_TEMPLATE_ARGS" ]]; then
  server_args+=(--chat-template-args "$MLX_CHAT_TEMPLATE_ARGS")
fi
exec "$MLX_VENV/bin/mlx_lm.server" "${server_args[@]}"
