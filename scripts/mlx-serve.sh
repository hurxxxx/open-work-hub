#!/usr/bin/env bash
# Launch mlx-lm's OpenAI-compatible server for local LLM.
#
# Usage:
#   bash scripts/mlx-serve.sh            # foreground
#   nohup bash scripts/mlx-serve.sh &    # background
#
# Default model: mlx-community/Qwen3.6-35B-A3B-4bit
# Default port:  8080 (matches DOOWON_LLM_LOCAL_BASE_URL default)
#
# Override via env:
#   MLX_MODEL=mlx-community/Qwen3.6-35B-A3B-8bit MLX_PORT=8090 bash scripts/mlx-serve.sh
set -euo pipefail

MLX_HOST="${MLX_HOST:-127.0.0.1}"
MLX_PORT="${MLX_PORT:-8080}"
MLX_MODEL="${MLX_MODEL:-mlx-community/Qwen3.6-35B-A3B-4bit}"
MLX_VENV="${MLX_VENV:-$HOME/.local/share/mlx-lm-venv}"

# Create venv on first run.
if [[ ! -x "$MLX_VENV/bin/mlx_lm.server" ]]; then
  echo "[mlx-serve] bootstrapping venv at $MLX_VENV ..."
  python3 -m venv "$MLX_VENV"
  "$MLX_VENV/bin/pip" install --upgrade pip --quiet
  "$MLX_VENV/bin/pip" install --quiet mlx-lm
fi

echo "[mlx-serve] model=$MLX_MODEL host=$MLX_HOST port=$MLX_PORT"
exec "$MLX_VENV/bin/mlx_lm.server" \
  --model "$MLX_MODEL" \
  --host "$MLX_HOST" \
  --port "$MLX_PORT"
