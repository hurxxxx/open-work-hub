from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RuntimeProfile = Literal[
    "interactive_read",
    "grounded_report",
    "long_doc",
    "high_risk_action",
]
RUNTIME_PROFILE_VALUES = frozenset(
    {
        "interactive_read",
        "grounded_report",
        "long_doc",
        "high_risk_action",
    }
)
RiskLevel = Literal["low", "medium", "high"]
RunStatus = Literal[
    "pending",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "abandoned",
]
InvocationStatus = Literal[
    "pending",
    "running",
    "awaiting_approval",
    "resumed",
    "completed",
    "failed",
    "cancelled",
    "abandoned",
]
GraphScheduleState = Literal["planned"]
TrustLevel = Literal["trusted", "mixed", "untrusted"]
AuthorityClass = Literal[
    "internal_system_of_record",
    "official_regulation",
    "standard_body",
    "vendor_official",
    "public_web",
    "unknown",
]


class AgentInvocationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    inputs_ref: str | None = None
    must_run_after: list[str] = Field(default_factory=list)
    purpose: str = Field(min_length=1)


class ExecutionGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)
    risk: RiskLevel
    output_kind: str = Field(min_length=1)
    invocations: list[AgentInvocationSpec] = Field(default_factory=list)
    requires_verifier: bool = False
    requires_approval_preview: bool = False

    @field_validator("domains")
    @classmethod
    def _domains_must_not_repeat(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("domains must not contain duplicates")
        return value


class GraphScheduleStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_seq: int = Field(ge=0)
    agent_id: str = Field(min_length=1)
    state: GraphScheduleState = "planned"
    depends_on_agent_ids: list[str] = Field(default_factory=list)


class GraphExecutionSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: GraphScheduleState = "planned"
    execution_enabled: bool = False
    steps: list[GraphScheduleStep] = Field(default_factory=list)


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    keywords: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    source_kinds: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    candidate_top_k: int = Field(default=0, ge=0)
    rerank_top_k: int = Field(default=0, ge=0)
    final_evidence_token_budget: int = Field(default=0, ge=0)
    external_search_used: bool = False
    external_search_provider: str | None = None
    sanitized_query_ref: str | None = None


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    score: float | None = None
    freshness: str | None = None
    access_scope: str | None = None
    provenance: str | None = None
    trust_level: TrustLevel | None = None
    authority_class: AuthorityClass | None = None


class EvidenceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intents_covered: list[str] = Field(default_factory=list)
    intents_missed: list[str] = Field(default_factory=list)


class EvidenceQuality(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verifier_status: str | None = None
    ready_for_grounded_write: bool = False
    failed_node_count: int = Field(default=0, ge=0)
    evidence_item_count: int = Field(default=0, ge=0)
    tool_result_count: int = Field(default=0, ge=0)


class EvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_version: Literal["evidence_packet.v1"] = "evidence_packet.v1"
    intent: str | None = None
    output_kind: str | None = None
    source_agent_ids: list[str] = Field(default_factory=list)
    query_plan: QueryPlan
    items: list[EvidenceItem] = Field(default_factory=list)
    coverage: EvidenceCoverage = Field(default_factory=EvidenceCoverage)
    quality: EvidenceQuality = Field(default_factory=EvidenceQuality)
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_quality_counts(self) -> "EvidencePacket":
        item_count = len(self.items)
        if self.quality.evidence_item_count == item_count:
            return self
        object.__setattr__(
            self,
            "quality",
            self.quality.model_copy(update={"evidence_item_count": item_count}),
        )
        return self


class AgentRunContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    requested_by_user_id: str = Field(min_length=1)
    status: RunStatus
    runtime_profile: RuntimeProfile = "interactive_read"
    graph_enabled: bool = False
    model_profile_id: str | None = None
    fallback_reason: str | None = None


class AgentInvocationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    invocation_seq: int = Field(ge=0)
    agent_id: str = Field(min_length=1)
    status: InvocationStatus
    purpose: str = Field(min_length=1)
    input_ref: str | None = None
    output_ref: str | None = None
    error: str | None = None


class AgentTraceEventContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    invocation_id: str | None = None
    run_seq: int = Field(ge=0)
    invocation_seq: int = Field(ge=0)
    event_seq: int = Field(ge=0)
    event_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
