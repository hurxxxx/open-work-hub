# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_work_hub_api.core.settings import Settings as ApiSettings  # noqa: E402
from open_work_hub_worker.settings import Settings as WorkerSettings  # noqa: E402


SHARED_RUNTIME_SETTING_FIELDS = (
    "asr_backend",
    "llm_external_allowed_providers",
    "ai_allowed_external_providers",
    "ai_default_external_llm_provider",
    "ai_default_external_search_provider",
    "ai_external_llm_enabled",
    "ai_external_planner_execution_adapter",
    "ai_external_planner_execution_enabled",
    "ai_external_planning_enabled",
    "ai_external_quality_review_enabled",
    "ai_external_reasoning_enabled",
    "ai_external_search_execution_adapter",
    "ai_external_search_execution_enabled",
    "rag_enabled",
    "files_retrieval_enabled",
    "rag_query_timeout_ms",
    "rag_qdrant_url",
    "rag_qdrant_api_key",
    "rag_qdrant_collection_prefix",
    "rag_vector_index_provider",
    "rag_embedding_provider",
    "rag_ocr_provider",
    "rag_rerank_provider",
    "rag_rerank_candidate_k",
    "rag_preload_on_startup",
    "rag_fail_startup_on_preload_error",
    "inference_gateway_base_url",
    "inference_gateway_api_key",
    "rag_local_embedding_model",
    "rag_local_embedding_revision",
    "rag_local_embedding_device",
    "rag_local_embedding_dtype",
    "rag_local_embedding_batch_size",
    "rag_local_embedding_max_seq_length",
    "rag_local_embedding_normalize",
    "rag_local_embedding_query_prompt_name",
    "rag_local_embedding_query_prefix",
    "rag_local_embedding_trust_remote_code",
    "rag_local_reranker_model",
    "rag_local_reranker_revision",
    "rag_local_reranker_device",
    "rag_local_reranker_dtype",
    "rag_local_reranker_batch_size",
    "rag_local_reranker_max_length",
    "rag_local_reranker_trust_remote_code",
    "rag_docling_force_ocr",
    "rag_docling_ocr_engine",
    "rag_docling_ocr_langs",
    "rag_docling_min_text_chars",
    "rag_vision_ocr_enabled",
    "rag_vision_ocr_timeout_seconds",
    "rag_vision_ocr_max_pages",
    "rag_vision_ocr_dpi",
    "rag_vision_ocr_max_new_tokens",
    "opensearch_url",
    "opensearch_index_prefix",
    "keyword_search_backend",
)


def test_api_worker_shared_runtime_settings_contracts_match() -> None:
    mismatches: list[str] = []
    for field_name in SHARED_RUNTIME_SETTING_FIELDS:
        api_field = ApiSettings.model_fields.get(field_name)
        worker_field = WorkerSettings.model_fields.get(field_name)
        if api_field is None:
            mismatches.append(f"API Settings missing {field_name}")
            continue
        if worker_field is None:
            mismatches.append(f"Worker Settings missing {field_name}")
            continue
        if api_field.validation_alias != worker_field.validation_alias:
            mismatches.append(
                f"{field_name} alias differs: "
                f"api={api_field.validation_alias!r} "
                f"worker={worker_field.validation_alias!r}"
            )
        if api_field.default != worker_field.default:
            mismatches.append(
                f"{field_name} default differs: "
                f"api={api_field.default!r} worker={worker_field.default!r}"
            )

    assert not mismatches, "\n".join(mismatches)
