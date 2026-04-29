from __future__ import annotations

from typing import Protocol

from aidoo_api.domains.ai.runtime.external_planner import (
    ExternalPlannerExecutionResult,
    ExternalPlannerRequest,
)
from aidoo_api.domains.ai.runtime.external_search import (
    ExternalSearchExecutionResult,
    ExternalSearchRequest,
)


class ExternalPlannerExecutionAdapter(Protocol):
    adapter_id: str
    execution_provider: str

    def execute(self, request: ExternalPlannerRequest) -> ExternalPlannerExecutionResult:
        """Execute an external planner request and return a trace-safe summary result."""


class ExternalSearchExecutionAdapter(Protocol):
    adapter_id: str
    execution_provider: str

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        """Execute an external search request and return a normalized, trace-safe result."""


__all__ = [
    "ExternalPlannerExecutionAdapter",
    "ExternalSearchExecutionAdapter",
]
