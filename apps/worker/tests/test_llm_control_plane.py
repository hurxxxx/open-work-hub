from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _worker_db_path(tmp_path: Path) -> Path:
    return tmp_path / "worker-llm.sqlite3"


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


def test_celery_app_fails_fast_when_llm_policy_table_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=False,
        seed_policy_rows=False,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))

    with pytest.raises(RuntimeError, match="Run API migrations before starting the worker"):
        _reload_worker_module("aidoo_worker.celery_app")


def test_meeting_summarize_uses_complete_chat_without_local_precheck(
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

    meeting_module = _reload_worker_module("aidoo_worker.tasks.meeting")

    recording = SimpleNamespace(
        id="rec-1",
        summary_text=None,
        transcript_text="회의 전사",
        progress_pct=60,
        meeting=SimpleNamespace(workspace_id="ws-1"),
        transcription_status="summarizing",
    )

    class FakeSession:
        def __init__(self) -> None:
            self.recording = recording

        def get(self, _model, _recording_id):
            return self.recording

        def add(self, _value) -> None:
            return None

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    fake_session = FakeSession()
    captured: dict[str, object] = {}

    monkeypatch.setattr(meeting_module, "_db_session", lambda: fake_session)
    monkeypatch.setattr(meeting_module, "_load_active_recording", lambda *_args: recording)
    monkeypatch.setattr(meeting_module, "_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(meeting_module, "_mark_failed", lambda *_args, **_kwargs: None)

    def fake_complete_chat(context, db, **kwargs):
        captured["context"] = context
        captured["db"] = db
        captured["messages"] = kwargs["messages"]
        return (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="요약 결과"))]
            ),
            SimpleNamespace(
                policy="local_only",
                chosen_pool="local",
                forced_local=False,
                pii_hits=[],
            ),
            SimpleNamespace(provider="mlx-lm", canonical_model="qwen/qwen3.6-35b-a3b"),
        )

    monkeypatch.setattr(meeting_module, "complete_chat", fake_complete_chat)

    result = meeting_module.summarize_recording.run("rec-1")

    assert result == "rec-1"
    assert recording.summary_text == "요약 결과"
    assert captured["db"] is fake_session
    assert captured["context"].task_kind == "meeting_summary"
    assert captured["context"].workspace_id == "ws-1"


def test_meeting_extract_insights_invokes_worker_service_without_stopping_pipeline(
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

    meeting_module = _reload_worker_module("aidoo_worker.tasks.meeting")

    recording = SimpleNamespace(
        id="rec-2",
        summary_text="요약 결과",
        transcript_text="회의 전사",
        progress_pct=90,
        meeting=SimpleNamespace(workspace_id="ws-1"),
        transcription_status="extracting_insights",
    )

    class FakeSession:
        def __init__(self) -> None:
            self.recording = recording
            self.committed = False
            self.rolled_back = False

        def get(self, _model, _recording_id):
            return self.recording

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            return None

    fake_session = FakeSession()
    captured: dict[str, object] = {}
    heartbeats: list[tuple[int, str | None]] = []

    monkeypatch.setattr(meeting_module, "_db_session", lambda: fake_session)
    monkeypatch.setattr(meeting_module, "_load_active_recording", lambda *_args: recording)
    monkeypatch.setattr(
        meeting_module,
        "_heartbeat",
        lambda _session, _recording, pct, status_name=None: heartbeats.append((pct, status_name)),
    )

    def fake_extract(db, **kwargs):
        captured["db"] = db
        captured["kwargs"] = kwargs
        return {}

    monkeypatch.setattr(
        meeting_module,
        "_meeting_insights_module",
        lambda: SimpleNamespace(extract_and_persist_meeting_insights=fake_extract),
    )

    result = meeting_module.extract_meeting_insights.run("rec-2")

    assert result == "rec-2"
    assert captured["db"] is fake_session
    assert captured["kwargs"] == {
        "recording_id": "rec-2",
        "source": "worker.meeting.extract_insights",
        "actor_user_id": None,
    }
    assert fake_session.committed is True
    assert fake_session.rolled_back is False
    assert heartbeats == [(90, "extracting_insights"), (92, "generating_doc")]


def test_meeting_insights_module_imports_under_worker_env(
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

    meeting_module = _reload_worker_module("aidoo_worker.tasks.meeting")

    imported = meeting_module._meeting_insights_module()

    assert imported.__name__ == "aidoo_api.domains.meeting.insights"
