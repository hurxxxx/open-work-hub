from __future__ import annotations

from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.admin.document_processing_schemas import (
    AdminDocumentProcessingResponse,
    DocumentChunkingStatusResponse,
    DocumentKeywordIndexStatusResponse,
    DocumentModelStatusResponse,
    DocumentOcrStatusResponse,
    DocumentProviderHealthResponse,
    DocumentRerankStatusResponse,
    DocumentVectorIndexStatusResponse,
    DocumentVisionStatusResponse,
    DocumentVisionWorkloadResponse,
    LegacyIssueDocumentStatusResponse,
)
from open_alm_api.domains.ai.model_settings_service import get_ai_model_settings_snapshot
from open_alm_api.domains.legacy_issues.settings import get_legacy_issue_settings
from open_alm_api.domains.rag.chunking import (
    DEFAULT_HARD_MAX_CHARS,
    DEFAULT_INDEX_TEXT_MAX_CHARS,
    DEFAULT_MIN_CHARS,
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
)
from open_alm_api.domains.rag.runtime import (
    get_rag_runtime_health,
    resolve_default_collection_name,
)


def _normalized_languages(value: str) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def _uses_inference_gateway(provider: str) -> bool:
    return provider.strip().lower() == "inference_gateway"


def build_admin_document_processing_snapshot(
    db: Session,
) -> AdminDocumentProcessingResponse:
    settings = get_settings()
    legacy = get_legacy_issue_settings()
    health = get_rag_runtime_health()
    provider_health = [
        DocumentProviderHealthResponse(
            provider_name=str(item.get("provider_name", "unknown")),
            ready=bool(item.get("ready", False)),
        )
        for item in health.get("providers", [])
        if isinstance(item, dict)
    ]

    model_settings = get_ai_model_settings_snapshot(db)
    document_workloads = [
        workload
        for workload in model_settings.workloads
        if workload.management_surface == "document_processing"
    ]
    vision_workloads = [
        DocumentVisionWorkloadResponse(
            workload_id=workload.workload_id,
            owner_domain=workload.owner_domain,
            app_ids=workload.app_ids,
            effective_route=workload.effective_route,
            provider_id=(
                workload.resolved_routes[0].provider_id if workload.resolved_routes else None
            ),
            model_key=(workload.resolved_routes[0].model_key if workload.resolved_routes else None),
            max_output_tokens=(
                workload.local_max_output_tokens
                if workload.effective_route == "local"
                else workload.external_max_output_tokens
            ),
            ready=workload.ready,
            readiness_code=workload.readiness_code,
        )
        for workload in document_workloads
    ]

    inference_endpoint_configured = bool(settings.inference_gateway_base_url.strip())
    inference_credential_configured = bool(settings.inference_gateway_api_key.strip())
    active_collection = (
        resolve_default_collection_name(settings)
        if settings.rag_vector_index_provider.strip().lower() == "qdrant"
        else None
    )

    return AdminDocumentProcessingResponse(
        enabled=settings.rag_enabled,
        ready=bool(health.get("ready", False)),
        query_timeout_ms=settings.rag_query_timeout_ms,
        providers=provider_health,
        ocr=DocumentOcrStatusResponse(
            provider=settings.rag_ocr_provider,
            endpoint_configured=(
                inference_endpoint_configured
                if _uses_inference_gateway(settings.rag_ocr_provider)
                else True
            ),
            credential_configured=(
                inference_credential_configured
                if _uses_inference_gateway(settings.rag_ocr_provider)
                else False
            ),
            force_ocr=settings.rag_docling_force_ocr,
            engine=settings.rag_docling_ocr_engine,
            languages=_normalized_languages(settings.rag_docling_ocr_langs),
            minimum_text_chars=settings.rag_docling_min_text_chars,
        ),
        vision=DocumentVisionStatusResponse(
            enabled=settings.rag_vision_ocr_enabled,
            timeout_seconds=settings.rag_vision_ocr_timeout_seconds,
            max_pages=settings.rag_vision_ocr_max_pages,
            dpi=settings.rag_vision_ocr_dpi,
            max_new_tokens=settings.rag_vision_ocr_max_new_tokens,
            workloads=vision_workloads,
        ),
        embedding=DocumentModelStatusResponse(
            provider=settings.rag_embedding_provider,
            endpoint_configured=(
                inference_endpoint_configured
                if _uses_inference_gateway(settings.rag_embedding_provider)
                else True
            ),
            credential_configured=(
                inference_credential_configured
                if _uses_inference_gateway(settings.rag_embedding_provider)
                else False
            ),
            model=settings.rag_local_embedding_model,
            revision=settings.rag_local_embedding_revision,
            batch_size=settings.rag_local_embedding_batch_size,
        ),
        rerank=DocumentRerankStatusResponse(
            provider=settings.rag_rerank_provider,
            endpoint_configured=(
                inference_endpoint_configured
                if _uses_inference_gateway(settings.rag_rerank_provider)
                else True
            ),
            credential_configured=(
                inference_credential_configured
                if _uses_inference_gateway(settings.rag_rerank_provider)
                else False
            ),
            model=settings.rag_local_reranker_model,
            revision=settings.rag_local_reranker_revision,
            batch_size=settings.rag_local_reranker_batch_size,
            candidate_limit=settings.rag_rerank_candidate_k,
        ),
        vector_index=DocumentVectorIndexStatusResponse(
            provider=settings.rag_vector_index_provider,
            endpoint_configured=bool(settings.rag_qdrant_url.strip()),
            credential_configured=bool(settings.rag_qdrant_api_key.strip()),
            collection_prefix=settings.rag_qdrant_collection_prefix,
            active_collection=active_collection,
        ),
        keyword_index=DocumentKeywordIndexStatusResponse(
            provider=settings.keyword_search_backend,
            endpoint_configured=bool(settings.opensearch_url.strip()),
            index_prefix=settings.opensearch_index_prefix,
        ),
        chunking=DocumentChunkingStatusResponse(
            strategy="default_korean_v1",
            target_chars=DEFAULT_TARGET_CHARS,
            hard_max_chars=DEFAULT_HARD_MAX_CHARS,
            overlap_chars=DEFAULT_OVERLAP_CHARS,
            minimum_chars=DEFAULT_MIN_CHARS,
            index_text_max_chars=DEFAULT_INDEX_TEXT_MAX_CHARS,
        ),
        legacy_issues=LegacyIssueDocumentStatusResponse(
            attachment_index_enabled=legacy.ai_attachment_index_enabled,
            always_use_vision=legacy.ai_attachment_index_vlm_always,
            vision_max_pages=legacy.ai_attachment_index_vision_max_pages,
            maximum_chunks=legacy.ai_attachment_index_max_chunks,
            semantic_search_enabled=legacy.ai_semantic_enabled,
            write_embeddings_enabled=legacy.ai_index_embeddings_on_write,
            embedding_dimensions=legacy.ai_embedding_dimensions,
        ),
    )


__all__ = ["build_admin_document_processing_snapshot"]
