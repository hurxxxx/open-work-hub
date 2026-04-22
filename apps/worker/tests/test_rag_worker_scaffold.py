from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest


def _worker_db_path(tmp_path: Path) -> Path:
    return tmp_path / "worker-rag.sqlite3"


def _worker_dsn(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _init_worker_db(
    db_path: Path,
    *,
    create_policy_table: bool,
    seed_policy_rows: bool,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        if create_policy_table:
            connection.execute(
                """
                CREATE TABLE llm_policies (
                    id TEXT PRIMARY KEY,
                    task_kind TEXT NOT NULL,
                    policy_mode TEXT NOT NULL,
                    description TEXT NOT NULL,
                    updated_by TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        if seed_policy_rows:
            connection.executemany(
                """
                INSERT INTO llm_policies (
                    id, task_kind, policy_mode, description, updated_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "1",
                        "chatbot",
                        "local_only",
                        "Interactive chat — user-facing",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "2",
                        "meeting_summary",
                        "local_only",
                        "Meeting transcript summarization (worker)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "3",
                        "meeting_insight_actions",
                        "local_only",
                        "Meeting action-item extraction (worker/read refresh)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "4",
                        "meeting_insight_decisions",
                        "local_only",
                        "Meeting decision extraction (worker/read refresh)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "5",
                        "meeting_insight_followup",
                        "local_only",
                        "Meeting follow-up schedule extraction (worker/read refresh)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "6",
                        "batch_generation",
                        "local_only",
                        "Long-form batch generation (reports etc.)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                ],
            )
        connection.commit()
    finally:
        connection.close()


def _reload_worker_module(module_name: str):
    for cached_name in list(sys.modules):
        if cached_name == "aidoo_worker" or cached_name.startswith("aidoo_worker."):
            sys.modules.pop(cached_name, None)
    return importlib.import_module(module_name)


def test_celery_routes_rag_tasks_to_dedicated_queues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))

    celery_module = _reload_worker_module("aidoo_worker.celery_app")
    routes = celery_module.celery_app.conf.task_routes

    assert routes["rag.sync_resource"]["queue"] == "rag_sync_realtime"
    assert routes["rag.sync_backfill_resource"]["queue"] == "rag_sync_backfill"
    assert routes["rag.recompute_visibility"]["queue"] == "rag_visibility_recompute"
