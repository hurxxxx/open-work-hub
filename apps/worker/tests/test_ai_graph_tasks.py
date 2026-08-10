from __future__ import annotations

import pytest

from ai_do_worker.tasks import ai_graph as ai_graph_tasks


def test_terminal_graph_failure_marks_celery_task_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_graph_tasks,
        "execute_registered_ai_graph",
        lambda _run_id: "failed",
    )

    with pytest.raises(
        ai_graph_tasks.AiGraphTerminalFailure,
        match="ai_graph_terminal_failure:run-failed",
    ):
        ai_graph_tasks.run_ai_graph.run("run-failed")


def test_completed_graph_result_is_returned(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_graph_tasks,
        "execute_registered_ai_graph",
        lambda _run_id: "completed",
    )

    assert ai_graph_tasks.run_ai_graph.run("run-completed") == "completed"
