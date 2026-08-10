"""AI security pipeline exemption registry.

These exemptions are intentionally evaluated before AI security scanning,
masking, and policy-rule resolution. They are for app-level workflows where
external transfer of the working payload is an approved part of the product
contract, while normal provider allowlists, task registration, budgets, and
audit logging still apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ai_do_api.domains.ai.security_policy import AiSecurityPolicyContext


AI_SECURITY_PIPELINE_EXEMPT_REASON = "ai_security_pipeline_exempt"


@dataclass(frozen=True)
class AiSecurityPipelineExemptionDecision:
    allowed: bool = False
    reason_code: str = "no_matching_ai_security_pipeline_exemption"
    exemption_id: str | None = None
    exemption_name: str | None = None
    matched_scope: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _BuiltInAiSecurityPipelineExemption:
    exemption_id: str
    exemption_name: str
    app_id: str
    task_kind: str
    capability: str
    provider: str


_BUILTIN_EXEMPTIONS: tuple[_BuiltInAiSecurityPipelineExemption, ...] = ()


def resolve_ai_security_pipeline_exemption(
    context: AiSecurityPolicyContext,
) -> AiSecurityPipelineExemptionDecision:
    normalized = _NormalizedContext.from_policy_context(context)
    for exemption in _BUILTIN_EXEMPTIONS:
        if normalized.matches(exemption):
            return AiSecurityPipelineExemptionDecision(
                allowed=True,
                reason_code=AI_SECURITY_PIPELINE_EXEMPT_REASON,
                exemption_id=exemption.exemption_id,
                exemption_name=exemption.exemption_name,
                matched_scope={
                    "app_id": exemption.app_id,
                    "task_kind": exemption.task_kind,
                    "capability": exemption.capability,
                    "provider": exemption.provider,
                },
            )
    return AiSecurityPipelineExemptionDecision()


@dataclass(frozen=True)
class _NormalizedContext:
    app_id: str | None
    task_kind: str | None
    capability: str | None
    provider: str | None

    @classmethod
    def from_policy_context(cls, context: AiSecurityPolicyContext) -> "_NormalizedContext":
        return cls(
            app_id=_clean_app_id(context.app_id),
            task_kind=_clean_token(context.task_kind),
            capability=_clean_token(context.capability),
            provider=_clean_token(context.provider),
        )

    def matches(self, exemption: _BuiltInAiSecurityPipelineExemption) -> bool:
        return (
            self.app_id == exemption.app_id
            and self.task_kind == exemption.task_kind
            and self.capability == exemption.capability
            and self.provider == exemption.provider
        )


def _clean_app_id(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _clean_token(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized or None


__all__ = [
    "AI_SECURITY_PIPELINE_EXEMPT_REASON",
    "AiSecurityPipelineExemptionDecision",
    "resolve_ai_security_pipeline_exemption",
]
