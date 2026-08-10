from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExternalPlannerHint:
    intent: str
    output_kind: str


_DEFAULT_PLANNER_HINT = ExternalPlannerHint(intent="read", output_kind="answer")
_PLANNER_HINTS_BY_RUNTIME_PROFILE: Mapping[str, ExternalPlannerHint] = {
    "grounded_report": ExternalPlannerHint(intent="report", output_kind="artifact"),
    "high_risk_action": ExternalPlannerHint(
        intent="write",
        output_kind="approval_preview",
    ),
}


def external_planner_hint_for_runtime_profile(runtime_profile: str) -> ExternalPlannerHint:
    return _PLANNER_HINTS_BY_RUNTIME_PROFILE.get(
        runtime_profile,
        _DEFAULT_PLANNER_HINT,
    )


__all__ = ["ExternalPlannerHint", "external_planner_hint_for_runtime_profile"]
