from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import ceil, log2
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1, max_length=160)
    relevant_resource_ids: list[str] = Field(min_length=1)
    ranked_resource_ids: list[str] = Field(default_factory=list, max_length=100)
    latency_ms: int = Field(default=0, ge=0)
    acl_violation_count: int = Field(default=0, ge=0)
    citation_failure_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "RetrievalEvaluationCase":
        if len(set(self.relevant_resource_ids)) != len(self.relevant_resource_ids):
            raise ValueError("relevant_resource_ids must be unique")
        if len(set(self.ranked_resource_ids)) != len(self.ranked_resource_ids):
            raise ValueError("ranked_resource_ids must be unique")
        return self


class RetrievalEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_count: int = Field(ge=0)
    recall_at_k: float = Field(ge=0, le=1)
    mrr_at_k: float = Field(ge=0, le=1)
    ndcg_at_k: float = Field(ge=0, le=1)
    p95_latency_ms: int = Field(ge=0)
    acl_violation_count: int = Field(ge=0)
    citation_failure_count: int = Field(ge=0)


class RetrievalQualityGateArtifact(BaseModel):
    """Versioned evidence consumed by fail-closed index activation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_version: Literal[2, 3]
    corpus_id: str = Field(min_length=1, max_length=160)
    corpus_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    index_generation: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    keyword_index_uuid: str = Field(min_length=1, max_length=160)
    keyword_index_config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    keyword_index_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    qdrant_physical_id: str | None = Field(default=None, min_length=1, max_length=512)
    qdrant_config_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    qdrant_content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    embedding_model_identity: str | None = Field(default=None, min_length=1, max_length=512)
    embedding_config_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    reranker_model_identity: str | None = Field(default=None, min_length=1, max_length=512)
    reranker_config_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_files_event_watermark: int | None = Field(default=None, ge=0)
    source_resource_count: int | None = Field(default=None, ge=0)
    source_identity_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_acl_envelope_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    judgment_acl_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    hybrid: RetrievalEvaluationReport
    bm25: RetrievalEvaluationReport
    dense: RetrievalEvaluationReport

    @model_validator(mode="after")
    def validate_generation_identity(self) -> "RetrievalQualityGateArtifact":
        v3_fields = (
            "qdrant_physical_id",
            "qdrant_config_sha256",
            "qdrant_content_sha256",
            "embedding_model_identity",
            "embedding_config_sha256",
            "reranker_model_identity",
            "reranker_config_sha256",
            "source_files_event_watermark",
            "source_resource_count",
            "source_identity_sha256",
            "source_artifact_sha256",
            "source_acl_envelope_sha256",
            "judgment_acl_sha256",
        )
        if self.artifact_version == 3:
            missing = [name for name in v3_fields if getattr(self, name) is None]
            if missing:
                raise ValueError("artifact_version 3 requires " + ", ".join(missing))
        elif any(getattr(self, name) is not None for name in v3_fields):
            raise ValueError("artifact_version 2 cannot include v3 generation identity")
        return self


class RetrievalQualityCorpusCase(BaseModel):
    """A stable, access-aware judged query used to build a quality artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(min_length=1, max_length=160)
    user_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    relevant_resource_ids: list[str] = Field(min_length=1, max_length=100)
    forbidden_resource_ids: list[str] = Field(default_factory=list, max_length=100)
    source_kinds: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_resource_ids(self) -> "RetrievalQualityCorpusCase":
        relevant = set(self.relevant_resource_ids)
        forbidden = set(self.forbidden_resource_ids)
        if len(relevant) != len(self.relevant_resource_ids):
            raise ValueError("relevant_resource_ids must be unique")
        if len(forbidden) != len(self.forbidden_resource_ids):
            raise ValueError("forbidden_resource_ids must be unique")
        if relevant & forbidden:
            raise ValueError("relevant and forbidden resource ids must not overlap")
        return self


class RetrievalQualityCorpus(BaseModel):
    """The exact versioned input whose raw bytes are bound to activation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_version: Literal[1]
    corpus_id: str = Field(min_length=1, max_length=160)
    cases: list[RetrievalQualityCorpusCase] = Field(min_length=60)

    @model_validator(mode="after")
    def validate_query_ids(self) -> "RetrievalQualityCorpus":
        query_ids = [case.query_id for case in self.cases]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("query_id values must be unique")
        return self


@dataclass(frozen=True, slots=True)
class RetrievalQualityGateResult:
    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalEmbeddingGenerationIdentity:
    model_identity: str
    config_sha256: str


@dataclass(frozen=True, slots=True)
class RetrievalRerankerGenerationIdentity:
    model_identity: str
    config_sha256: str


def retrieval_embedding_generation_identity(
    settings: object,
) -> RetrievalEmbeddingGenerationIdentity:
    """Return a secret-free identity for the embedding runtime used by a generation."""

    from open_work_hub_api.domains.rag.provider_factory import (
        embedding_provider_collection_model_name,
    )

    model_identity = embedding_provider_collection_model_name(settings).strip()
    if not model_identity:
        raise ValueError("embedding model identity is unavailable")
    config = {
        "provider": str(getattr(settings, "rag_embedding_provider", "") or "").strip().lower(),
        "model_identity": model_identity,
        "revision": getattr(settings, "rag_local_embedding_revision", None),
        "device": getattr(settings, "rag_local_embedding_device", None),
        "dtype": getattr(settings, "rag_local_embedding_dtype", None),
        "batch_size": getattr(settings, "rag_local_embedding_batch_size", None),
        "max_seq_length": getattr(settings, "rag_local_embedding_max_seq_length", None),
        "normalize": getattr(settings, "rag_local_embedding_normalize", None),
        "query_prompt_name": getattr(
            settings,
            "rag_local_embedding_query_prompt_name",
            None,
        ),
        "query_prefix": getattr(settings, "rag_local_embedding_query_prefix", None),
        "trust_remote_code": getattr(
            settings,
            "rag_local_embedding_trust_remote_code",
            None,
        ),
    }
    canonical = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RetrievalEmbeddingGenerationIdentity(
        model_identity=model_identity,
        config_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def retrieval_reranker_generation_identity(
    settings: object,
) -> RetrievalRerankerGenerationIdentity:
    """Return the secret-free identity of the reranker runtime actually in use."""

    provider = str(getattr(settings, "rag_rerank_provider", "") or "").strip().lower()
    disabled = provider in {"", "none", "disabled"}
    configured_model = str(getattr(settings, "rag_local_reranker_model", "") or "").strip()
    if disabled:
        model_identity = "disabled"
        config: dict[str, object] = {
            "provider": provider,
            "enabled": False,
        }
    else:
        model_identity = f"{provider}:{configured_model}" if configured_model else provider
        config = _enabled_reranker_generation_config(
            settings=settings,
            provider=provider,
            configured_model=configured_model,
        )
    canonical = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RetrievalRerankerGenerationIdentity(
        model_identity=model_identity,
        config_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _enabled_reranker_generation_config(
    *,
    settings: object,
    provider: str,
    configured_model: str,
) -> dict[str, object]:
    candidate_k = getattr(settings, "rag_rerank_candidate_k", None)
    common: dict[str, object] = {
        "provider": provider,
        "enabled": True,
        "model": configured_model,
        "candidate_k": candidate_k,
    }
    if provider in {"local", "local_cross_encoder", "cross_encoder"}:
        revision = getattr(settings, "rag_local_reranker_revision", None)
        return {
            **common,
            "revision": str(revision).strip() if revision else None,
            "device": str(getattr(settings, "rag_local_reranker_device", "") or "").strip().lower()
            or "auto",
            "dtype": str(getattr(settings, "rag_local_reranker_dtype", "") or "").strip().lower()
            or "auto",
            "batch_size": getattr(settings, "rag_local_reranker_batch_size", None),
            "max_length": getattr(settings, "rag_local_reranker_max_length", None),
            "trust_remote_code": getattr(
                settings,
                "rag_local_reranker_trust_remote_code",
                None,
            ),
        }
    if provider == "inference_gateway":
        from open_work_hub_api.domains.rag.provider_factory import inference_gateway_v1_base_url

        # The gateway client sends all retrieved candidates in one request and
        # build_rerank_document_text bounds each document at 2,000 characters.
        # Local model batch/max settings are not passed by provider_factory.
        return {
            **common,
            "endpoint": inference_gateway_v1_base_url(settings),
            "request_batching": "all_candidates",
            "document_max_chars": 2_000,
        }
    return common


def evaluate_retrieval_cases(
    cases: list[RetrievalEvaluationCase],
    *,
    k: int = 10,
) -> RetrievalEvaluationReport:
    if k <= 0:
        raise ValueError("k must be positive")
    if len({case.query_id for case in cases}) != len(cases):
        raise ValueError("query_id values must be unique")
    if not cases:
        return RetrievalEvaluationReport(
            query_count=0,
            recall_at_k=0.0,
            mrr_at_k=0.0,
            ndcg_at_k=0.0,
            p95_latency_ms=0,
            acl_violation_count=0,
            citation_failure_count=0,
        )

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for case in cases:
        relevant = set(case.relevant_resource_ids)
        ranked = case.ranked_resource_ids[:k]
        recalls.append(len(relevant.intersection(ranked)) / len(relevant))
        first_relevant_rank = next(
            (rank for rank, resource_id in enumerate(ranked, start=1) if resource_id in relevant),
            None,
        )
        reciprocal_ranks.append(0.0 if first_relevant_rank is None else 1 / first_relevant_rank)
        dcg = sum(
            1 / log2(rank + 1)
            for rank, resource_id in enumerate(ranked, start=1)
            if resource_id in relevant
        )
        ideal_count = min(len(relevant), k)
        ideal_dcg = sum(1 / log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcgs.append(0.0 if ideal_dcg == 0 else dcg / ideal_dcg)

    latencies = sorted(case.latency_ms for case in cases)
    p95_index = max(0, ceil(len(latencies) * 0.95) - 1)
    return RetrievalEvaluationReport(
        query_count=len(cases),
        recall_at_k=_mean(recalls),
        mrr_at_k=_mean(reciprocal_ranks),
        ndcg_at_k=_mean(ndcgs),
        p95_latency_ms=latencies[p95_index],
        acl_violation_count=sum(case.acl_violation_count for case in cases),
        citation_failure_count=sum(case.citation_failure_count for case in cases),
    )


def evaluate_hybrid_quality_gate(
    *,
    hybrid: RetrievalEvaluationReport,
    bm25: RetrievalEvaluationReport,
    dense: RetrievalEvaluationReport,
    minimum_query_count: int = 60,
    required_relative_uplift: float = 0.05,
    max_p95_latency_ms: int = 5_000,
    minimum_hybrid_recall_at_k: float = 0.80,
    minimum_hybrid_mrr_at_k: float = 0.50,
    minimum_hybrid_ndcg_at_k: float = 0.50,
) -> RetrievalQualityGateResult:
    reasons: list[str] = []
    reports = {"hybrid": hybrid, "bm25": bm25, "dense": dense}
    for name, report in reports.items():
        if report.query_count < minimum_query_count:
            reasons.append(f"{name}_query_count<{minimum_query_count}")
    if len({report.query_count for report in reports.values()}) != 1:
        reasons.append("corpus_query_count_mismatch")
    if any(report.acl_violation_count for report in reports.values()):
        reasons.append("acl_violations")
    if any(report.citation_failure_count for report in reports.values()):
        reasons.append("citation_failures")
    if any(report.p95_latency_ms > max_p95_latency_ms for report in reports.values()):
        reasons.append(f"p95_latency_ms>{max_p95_latency_ms}")
    absolute_floors = {
        "hybrid_recall_at_k": (hybrid.recall_at_k, minimum_hybrid_recall_at_k),
        "hybrid_mrr_at_k": (hybrid.mrr_at_k, minimum_hybrid_mrr_at_k),
        "hybrid_ndcg_at_k": (hybrid.ndcg_at_k, minimum_hybrid_ndcg_at_k),
    }
    for metric, (actual, minimum) in absolute_floors.items():
        if not 0 <= minimum <= 1:
            raise ValueError(f"{metric} minimum must be between 0 and 1")
        if actual + 1e-12 < minimum:
            reasons.append(f"{metric}<{minimum:g}")

    best_recall = max(bm25.recall_at_k, dense.recall_at_k)
    if hybrid.recall_at_k + 1e-12 < best_recall:
        reasons.append("recall_regression")

    # nDCG and MRR are normalized to 1.0. Cap the relative-uplift target at
    # that ceiling so a perfect baseline does not make the gate impossible.
    ndcg_target = min(
        1.0,
        max(bm25.ndcg_at_k, dense.ndcg_at_k) * (1 + required_relative_uplift),
    )
    mrr_target = min(
        1.0,
        max(bm25.mrr_at_k, dense.mrr_at_k) * (1 + required_relative_uplift),
    )
    if hybrid.ndcg_at_k + 1e-12 < ndcg_target and hybrid.mrr_at_k + 1e-12 < mrr_target:
        reasons.append("ranking_uplift_below_target")
    return RetrievalQualityGateResult(passed=not reasons, reasons=tuple(reasons))


def validate_quality_gate_artifact(
    artifact: RetrievalQualityGateArtifact,
    *,
    expected_index_generation: str,
    expected_corpus_id: str | None = None,
    expected_corpus_sha256: str | None = None,
) -> RetrievalQualityGateResult:
    gate = evaluate_hybrid_quality_gate(
        hybrid=artifact.hybrid,
        bm25=artifact.bm25,
        dense=artifact.dense,
    )
    reasons = list(gate.reasons)
    if artifact.index_generation != expected_index_generation:
        reasons.append("index_generation_mismatch")
    if expected_corpus_id is not None and artifact.corpus_id != expected_corpus_id:
        reasons.append("corpus_id_mismatch")
    if expected_corpus_sha256 is not None and artifact.corpus_sha256 != expected_corpus_sha256:
        reasons.append("corpus_sha256_mismatch")
    return RetrievalQualityGateResult(passed=not reasons, reasons=tuple(reasons))


def retrieval_quality_corpus_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
