from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from aidoo_api.domains.ai.runtime.external_egress import ExternalEgressDecision


EXTERNAL_SEARCH_ADAPTER_ID = "external_search_v0"

ExternalSearchStatus = Literal["disabled", "ready"]
ExternalSearchDisabledReason = Literal[
    "capability_mismatch",
    "egress_denied",
    "sanitized_empty",
]


class ExternalSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: Literal["external_search_v0"] = EXTERNAL_SEARCH_ADAPTER_ID
    status: ExternalSearchStatus
    provider: str | None = None
    disabled_reason: ExternalSearchDisabledReason | None = None
    egress_reason: str | None = None
    query: str = ""


def build_external_search_request(
    *,
    egress_decision: ExternalEgressDecision,
) -> ExternalSearchRequest:
    if egress_decision.capability != "search":
        return ExternalSearchRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="capability_mismatch",
            egress_reason=egress_decision.reason,
        )
    if not egress_decision.allow_external:
        return ExternalSearchRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="egress_denied",
            egress_reason=egress_decision.reason,
        )
    sanitized_query = egress_decision.sanitized_query.strip()
    if not sanitized_query:
        return ExternalSearchRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="sanitized_empty",
            egress_reason=egress_decision.reason,
        )
    return ExternalSearchRequest(
        status="ready",
        provider=egress_decision.provider,
        egress_reason=egress_decision.reason,
        query=sanitized_query,
    )


def summarize_external_search_request(
    request: ExternalSearchRequest,
) -> dict[str, object]:
    return {
        "adapter_id": request.adapter_id,
        "status": request.status,
        "provider": request.provider,
        "disabled_reason": request.disabled_reason,
        "egress_reason": request.egress_reason,
        "query_present": bool(request.query),
    }


__all__ = [
    "EXTERNAL_SEARCH_ADAPTER_ID",
    "ExternalSearchDisabledReason",
    "ExternalSearchRequest",
    "ExternalSearchStatus",
    "build_external_search_request",
    "summarize_external_search_request",
]
