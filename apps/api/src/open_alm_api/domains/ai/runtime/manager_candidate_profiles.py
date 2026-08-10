from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from open_alm_api.domains.ai.runtime.contracts import RiskLevel, RuntimeProfile


TerminalDependencyPolicy = Literal["domain_agents", "verifier_or_all_prior"]


@dataclass(frozen=True)
class TerminalAgentPolicy:
    agent_id: str
    purpose: str
    dependency_policy: TerminalDependencyPolicy


@dataclass(frozen=True)
class GroundedEvidencePolicy:
    planner_agent_id: str
    planner_purpose: str
    executor_agent_id: str
    executor_purpose: str
    verifier_agent_id: str
    verifier_purpose: str


@dataclass(frozen=True)
class DeterministicManagerCandidateProfile:
    runtime_profile: RuntimeProfile
    intent: str
    domain_agent_ids: tuple[str, ...]
    domain_purpose_template: str
    risk: RiskLevel
    output_kind: str
    terminal_agent: TerminalAgentPolicy
    grounded_evidence: GroundedEvidencePolicy | None = None
    requires_domain_agent: bool = False
    requires_approval_preview: bool = False


GROUNDED_REPORT_PROFILE = DeterministicManagerCandidateProfile(
    runtime_profile="grounded_report",
    intent="report",
    domain_agent_ids=(
        "domain.pms",
        "domain.meeting",
        "domain.docs",
        "domain.planner",
        "domain.rag",
    ),
    domain_purpose_template="Collect evidence with {agent_id}.",
    risk="medium",
    output_kind="artifact",
    terminal_agent=TerminalAgentPolicy(
        agent_id="writer.template",
        purpose="Write the grounded report artifact.",
        dependency_policy="verifier_or_all_prior",
    ),
    grounded_evidence=GroundedEvidencePolicy(
        planner_agent_id="search.planner",
        planner_purpose="Build the evidence search plan.",
        executor_agent_id="search.executor",
        executor_purpose="Execute scoped evidence search.",
        verifier_agent_id="verifier.grounding",
        verifier_purpose="Verify evidence coverage and unsupported claims.",
    ),
)
HIGH_RISK_ACTION_PROFILE = DeterministicManagerCandidateProfile(
    runtime_profile="high_risk_action",
    intent="write",
    domain_agent_ids=("domain.pms", "domain.meeting", "domain.docs", "domain.planner"),
    domain_purpose_template="Collect write-context evidence with {agent_id}.",
    risk="high",
    output_kind="approval_preview",
    terminal_agent=TerminalAgentPolicy(
        agent_id="approval.proposal_preview",
        purpose="Build a user-reviewable write proposal preview.",
        dependency_policy="domain_agents",
    ),
    requires_domain_agent=True,
    requires_approval_preview=True,
)
DETERMINISTIC_MANAGER_CANDIDATE_PROFILES = {
    profile.runtime_profile: profile
    for profile in (GROUNDED_REPORT_PROFILE, HIGH_RISK_ACTION_PROFILE)
}
DETERMINISTIC_MANAGER_CANDIDATE_RUNTIME_PROFILES = frozenset(
    DETERMINISTIC_MANAGER_CANDIDATE_PROFILES
)


__all__ = [
    "DETERMINISTIC_MANAGER_CANDIDATE_PROFILES",
    "DETERMINISTIC_MANAGER_CANDIDATE_RUNTIME_PROFILES",
    "DeterministicManagerCandidateProfile",
    "GROUNDED_REPORT_PROFILE",
    "GroundedEvidencePolicy",
    "HIGH_RISK_ACTION_PROFILE",
    "TerminalAgentPolicy",
    "TerminalDependencyPolicy",
]
