# ruff: noqa: E402

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

import open_work_hub_api.platform_extensions as platform_extensions  # noqa: E402


REQUIRED_PROVIDER_IDS = ("anthropic", "gemini", "local", "openai")


def _worker_db_path(tmp_path: Path) -> Path:
    return tmp_path / "worker-llm.sqlite3"


def _worker_dsn(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _init_worker_db(
    db_path: Path,
    *,
    create_routing_tables: bool,
    seed_provider_rows: bool,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        if create_routing_tables:
            connection.execute(
                """
                CREATE TABLE ai_model_provider_configs (
                    provider_id TEXT PRIMARY KEY
                )
                """
            )
            connection.execute("CREATE TABLE ai_model_catalog_entries (id TEXT PRIMARY KEY)")
            connection.execute(
                "CREATE TABLE ai_model_route_overrides (workload_id TEXT PRIMARY KEY)"
            )
        if seed_provider_rows:
            connection.executemany(
                "INSERT INTO ai_model_provider_configs (provider_id) VALUES (?)",
                [(provider_id,) for provider_id in REQUIRED_PROVIDER_IDS],
            )
        connection.commit()
    finally:
        connection.close()


def _reload_worker_module(module_name: str):
    for cached_name in list(sys.modules):
        if cached_name == "open_work_hub_worker" or cached_name.startswith("open_work_hub_worker."):
            sys.modules.pop(cached_name, None)
    return importlib.import_module(module_name)


def test_celery_app_fails_fast_when_llm_routing_tables_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=False,
        seed_provider_rows=False,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_WORKER_QUEUE_GROUP", "all")

    with pytest.raises(RuntimeError, match="Run API migrations before starting the worker"):
        _reload_worker_module("open_work_hub_worker.celery_app")


def test_celery_app_skips_llm_routing_precheck_for_non_llm_queue_group(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=False,
        seed_provider_rows=False,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_WORKER_QUEUE_GROUP", "default")

    celery_module = _reload_worker_module("open_work_hub_worker.celery_app")

    assert celery_module.settings.queue_group == "default"
    assert celery_module.celery_app.main == "open_work_hub_worker"


def test_meeting_summarize_uses_complete_chat_without_local_precheck(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))

    meeting_module = _reload_worker_module("open_work_hub_worker.tasks.meeting")

    recording = SimpleNamespace(
        id="rec-1",
        uploaded_by_id="user-1",
        summary_text=None,
        transcript_text="회의 전사",
        progress_pct=60,
        meeting=SimpleNamespace(id="meeting-1"),
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
    captured: dict[str, Any] = {}

    from open_work_hub_api.domains.meeting import rag_sync as meeting_rag_sync

    monkeypatch.setattr(
        meeting_rag_sync, "enqueue_meeting_rag_sync_by_id", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(meeting_module, "_db_session", lambda: fake_session)
    monkeypatch.setattr(meeting_module, "_load_active_recording", lambda *_args: recording)
    monkeypatch.setattr(meeting_module, "_meeting_requester_is_participant", lambda *_args: True)
    monkeypatch.setattr(meeting_module, "_heartbeat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(meeting_module, "_mark_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        meeting_module,
        "can_use_app",
        lambda *_args, **_kwargs: True,
    )

    def fake_execute_llm(workload_id, context, db, **kwargs):
        captured["workload_id"] = workload_id
        captured["context"] = context
        captured["db"] = db
        captured["messages"] = kwargs["messages"]
        return SimpleNamespace(
            completion=SimpleNamespace(text="요약 결과"),
            decision=SimpleNamespace(
                policy="local_only", chosen_pool="local", forced_local=False, pii_hits=[]
            ),
            config=SimpleNamespace(provider="local-runtime", canonical_model="local/test-model"),
        )

    monkeypatch.setattr(
        meeting_module,
        "execute_llm",
        fake_execute_llm,
    )

    result = meeting_module.summarize_recording.run("rec-1")

    assert result == "rec-1"
    assert recording.summary_text == "요약 결과"
    assert captured["db"] is fake_session
    assert captured["workload_id"] == "meeting_summary"
    assert captured["context"].app_id == "meeting"
    assert captured["context"].actor_user_id == "user-1"
    assert not hasattr(captured["context"], "workspace_id")


def test_mail_sync_task_imports_after_control_plane_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))

    mail_module = _reload_worker_module("open_work_hub_worker.tasks.mail")

    assert mail_module.sync_mail_job.name == "mail.sync_job"
    assert mail_module.sync_mail_account.name == "mail.sync_account"
    assert mail_module.dispatch_due_sync_jobs.name == "mail.dispatch_due_sync_jobs"


def test_celery_app_initializes_platform_extensions_with_worker_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER", "openai")

    captured: dict[str, Any] = {}

    def fake_initialize_platform_extensions(settings) -> object:
        captured["settings"] = settings
        return object()

    monkeypatch.setattr(
        platform_extensions,
        "initialize_platform_extensions",
        fake_initialize_platform_extensions,
    )

    _reload_worker_module("open_work_hub_worker.celery_app")

    settings = captured["settings"]
    assert settings.__class__.__module__ == "open_work_hub_worker.settings"
    assert settings.ai_default_external_llm_provider == "openai"


def test_meeting_extract_insights_invokes_worker_service_without_stopping_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))

    meeting_module = _reload_worker_module("open_work_hub_worker.tasks.meeting")

    recording = SimpleNamespace(
        id="rec-2",
        uploaded_by_id="user-1",
        summary_text="요약 결과",
        transcript_text="회의 전사",
        progress_pct=90,
        meeting=SimpleNamespace(id="meeting-1"),
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

    from open_work_hub_api.domains.meeting import rag_sync as meeting_rag_sync

    monkeypatch.setattr(
        meeting_rag_sync, "enqueue_meeting_rag_sync_by_id", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(meeting_module, "_db_session", lambda: fake_session)
    monkeypatch.setattr(meeting_module, "_load_active_recording", lambda *_args: recording)
    monkeypatch.setattr(meeting_module, "_meeting_requester_is_participant", lambda *_args: True)
    monkeypatch.setattr(
        meeting_module,
        "_heartbeat",
        lambda _session, _recording, pct, status_name=None: heartbeats.append((pct, status_name)),
    )
    monkeypatch.setattr(
        meeting_module,
        "can_use_app",
        lambda *_args, **_kwargs: True,
    )

    def fake_extract(db, **kwargs):
        captured["db"] = db
        captured["kwargs"] = kwargs
        return {}

    monkeypatch.setattr(
        meeting_module,
        "meeting_insights_module",
        lambda: SimpleNamespace(extract_and_persist_meeting_insights=fake_extract),
    )

    result = meeting_module.extract_meeting_insights.run("rec-2")

    assert result == "rec-2"
    assert captured["db"] is fake_session
    assert captured["kwargs"] == {
        "recording_id": "rec-2",
        "source": "worker.meeting.extract_insights",
        "actor_user_id": "user-1",
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
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))

    meeting_module = _reload_worker_module("open_work_hub_worker.tasks.meeting")

    imported = meeting_module.meeting_insights_module()

    assert imported.__name__ == "open_work_hub_api.domains.meeting.insights"


def test_meeting_mark_failed_rolls_back_pending_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", _worker_dsn(db_path))

    meeting_module = _reload_worker_module("open_work_hub_worker.tasks.meeting")
    recording = SimpleNamespace(
        transcription_status="summarizing",
        failure_reason=None,
    )

    class FakeSession:
        def __init__(self) -> None:
            self.events: list[str] = []

        def rollback(self) -> None:
            self.events.append("rollback")

        def get(self, _model, _recording_id):
            self.events.append("get")
            return recording

        def add(self, _value) -> None:
            self.events.append("add")

        def commit(self) -> None:
            self.events.append("commit")

    session = FakeSession()

    meeting_module._mark_failed(session, "rec-1", "provider failed")

    assert session.events == ["rollback", "get", "add", "commit"]
    assert recording.transcription_status == "failed"
    assert recording.failure_reason == "provider failed"
