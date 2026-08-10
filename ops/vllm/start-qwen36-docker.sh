#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-/srv/vllm/qwen36-docker.env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

: "${MODEL_ID:?MODEL_ID must be set explicitly in the runtime env file}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${MAX_MODEL_LEN:=131328}"
: "${GPU_MEMORY_UTILIZATION:=0.80}"
: "${MAX_NUM_SEQS:=64}"
: "${HF_CACHE:=/home/open-alm/.cache/huggingface}"
: "${VLLM_CACHE:=/home/open-alm/.cache/vllm}"
: "${VLLM_IMAGE:=vllm/vllm-openai:cu130-nightly}"
: "${VLLM_CONTAINER_NAME:=vllm-local}"

mkdir -p "${HF_CACHE}" "${VLLM_CACHE}"

if [[ -n "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
elif [[ -n "${HUGGING_FACE_HUB_TOKEN:-}" && -z "${HF_TOKEN:-}" ]]; then
  export HF_TOKEN="${HUGGING_FACE_HUB_TOKEN}"
fi

extra_args=()
if [[ -n "${REVISION:-}" ]]; then
  extra_args+=(--revision "${REVISION}")
fi

served_model_names=()
if [[ -n "${SERVED_MODEL_NAMES:-}" ]]; then
  IFS=',' read -r -a configured_names <<< "${SERVED_MODEL_NAMES}"
  for configured_name in "${configured_names[@]}"; do
    configured_name="${configured_name#"${configured_name%%[![:space:]]*}"}"
    configured_name="${configured_name%"${configured_name##*[![:space:]]}"}"
    if [[ -z "${configured_name}" ]]; then
      echo "SERVED_MODEL_NAMES contains an empty model name" >&2
      exit 2
    fi
    served_model_names+=("${configured_name}")
  done
elif [[ -n "${SERVED_MODEL_NAME:-}" ]]; then
  served_model_names+=("${SERVED_MODEL_NAME}")
fi
if ((${#served_model_names[@]} == 0)); then
  served_model_names+=("${MODEL_ID}")
fi
if [[ "${ALLOW_SERVED_MODEL_ALIASES:-0}" != "1" ]]; then
  for served_model_name in "${served_model_names[@]}"; do
    if [[ "${served_model_name}" != "${MODEL_ID}" ]]; then
      echo "served model aliases require ALLOW_SERVED_MODEL_ALIASES=1" >&2
      exit 2
    fi
  done
fi
extra_args+=(--served-model-name "${served_model_names[@]}")

if [[ -n "${QUANTIZATION:-}" ]]; then
  extra_args+=(--quantization "${QUANTIZATION}")
fi
if [[ -n "${DTYPE:-}" ]]; then
  extra_args+=(--dtype "${DTYPE}")
fi
if [[ -n "${ATTENTION_BACKEND:-}" ]]; then
  extra_args+=(--attention-backend "${ATTENTION_BACKEND}")
fi
if [[ -n "${MOE_BACKEND:-}" ]]; then
  extra_args+=(--moe-backend "${MOE_BACKEND}")
fi
if [[ -n "${SPECULATIVE_CONFIG:-}" ]]; then
  extra_args+=(--speculative-config "${SPECULATIVE_CONFIG}")
fi
if [[ -n "${KV_CACHE_DTYPE:-}" ]]; then
  extra_args+=(--kv-cache-dtype "${KV_CACHE_DTYPE}")
fi
if [[ -n "${MAX_NUM_BATCHED_TOKENS:-}" ]]; then
  extra_args+=(--max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}")
fi
if [[ -n "${TOOL_CALL_PARSER:-}" ]]; then
  extra_args+=(--tool-call-parser "${TOOL_CALL_PARSER}")
fi
if [[ -n "${REASONING_PARSER:-}" ]]; then
  extra_args+=(--reasoning-parser "${REASONING_PARSER}")
fi
if [[ -n "${DEFAULT_CHAT_TEMPLATE_KWARGS:-}" ]]; then
  extra_args+=(--default-chat-template-kwargs "${DEFAULT_CHAT_TEMPLATE_KWARGS}")
fi
if [[ -n "${GENERATION_CONFIG:-}" ]]; then
  extra_args+=(--generation-config "${GENERATION_CONFIG}")
fi
if [[ -n "${OVERRIDE_GENERATION_CONFIG:-}" ]]; then
  extra_args+=(--override-generation-config "${OVERRIDE_GENERATION_CONFIG}")
fi
if [[ "${TRUST_REMOTE_CODE:-0}" == "1" ]]; then
  extra_args+=(--trust-remote-code)
fi
if [[ "${ENABLE_AUTO_TOOL_CHOICE:-0}" == "1" ]]; then
  extra_args+=(--enable-auto-tool-choice)
fi
if [[ "${ENABLE_CHUNKED_PREFILL:-0}" == "1" ]]; then
  extra_args+=(--enable-chunked-prefill)
fi
if [[ "${ASYNC_SCHEDULING:-0}" == "1" ]]; then
  extra_args+=(--async-scheduling)
fi

exec /usr/bin/docker run --rm \
  --name "${VLLM_CONTAINER_NAME}" \
  --gpus all \
  --privileged \
  --oom-score-adj 500 \
  --network host \
  --ipc=host \
  --shm-size 32g \
  -e HF_TOKEN \
  -e HUGGING_FACE_HUB_TOKEN \
  -e VLLM_FLASHINFER_MOE_BACKEND \
  -e VLLM_USE_FLASHINFER_MOE_FP4 \
  -e VLLM_FP8_MOE_BACKEND \
  -e FLASHINFER_DISABLE_VERSION_CHECK \
  -e CUTE_DSL_ARCH \
  -e VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS \
  -v "${HF_CACHE}:/root/.cache/huggingface" \
  -v "${VLLM_CACHE}:/root/.cache/vllm" \
  "${VLLM_IMAGE}" \
  "${MODEL_ID}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --load-format "${LOAD_FORMAT:-fastsafetensors}" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --enable-prefix-caching \
  "${extra_args[@]}"
