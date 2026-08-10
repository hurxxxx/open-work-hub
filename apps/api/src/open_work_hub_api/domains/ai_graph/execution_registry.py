from __future__ import annotations

from collections.abc import Callable

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.ai_graph.models import AiGraphRun


AiGraphExecutor = Callable[[str], str]
AiGraphExecutorKey = tuple[str, str]
_executors: dict[AiGraphExecutorKey, AiGraphExecutor] = {}


def register_ai_graph_executor(
    graph_id: str,
    graph_version: str,
    executor: AiGraphExecutor,
) -> None:
    normalized_id = graph_id.strip()
    normalized_version = graph_version.strip()
    if not normalized_id or not normalized_version:
        raise ValueError("AI graph executor requires graph_id and graph_version")
    key = (normalized_id, normalized_version)
    if key in _executors and _executors[key] is not executor:
        raise ValueError(
            f"AI graph executor already registered: {normalized_id}@{normalized_version}"
        )
    _executors[key] = executor


def execute_registered_ai_graph(run_id: str) -> str:
    with get_session_factory()() as db:
        run = db.get(AiGraphRun, run_id)
        if run is None:
            raise LookupError(run_id)
        key = (run.graph_id, run.graph_version)
        executor = _executors.get(key)
    if executor is None:
        raise LookupError(
            f"AI graph executor not registered: {run.graph_id}@{run.graph_version}"
        )
    return executor(run_id)


def reset_ai_graph_executors() -> None:
    _executors.clear()


__all__ = [
    "execute_registered_ai_graph",
    "register_ai_graph_executor",
    "reset_ai_graph_executors",
]
