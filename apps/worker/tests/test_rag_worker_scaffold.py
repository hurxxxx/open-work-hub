# ruff: noqa: E402

from __future__ import annotations

from datetime import datetime
import importlib
import sqlite3
import sys
from pathlib import Path

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from aidoo_api.core.db import Base  # noqa: E402
from aidoo_api.core.telemetry import (
    bootstrap_telemetry,
    get_tracer_provider,
    start_as_current_span,
)  # noqa: E402
from aidoo_api.domains.auth.models import Team, User, Workspace  # noqa: E402
from aidoo_api.domains.docs.models import (  # noqa: E402
    DocMeetingAccess,
    NativeDoc,
    NativeDocContainer,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from aidoo_api.domains.meeting.models import (  # noqa: E402
    Meeting,
    MeetingAttendee,
    MeetingDocLink,
    MeetingRecording,
    MeetingTaskLink,
)
from aidoo_api.domains.pms.models import (  # noqa: E402
    Folder,
    Issue,
    IssueComment,
    IssueLabel,
    IssueUserAccess,
    Label,
    Milestone,
    TaskList,
)
from aidoo_api.domains.planner.models import PlannerEvent  # noqa: E402
from aidoo_api.domains.rag.contracts import RagSyncLane, RagSyncOperation  # noqa: E402
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE  # noqa: E402
from aidoo_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE  # noqa: E402
from aidoo_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE  # noqa: E402
from aidoo_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE  # noqa: E402
from aidoo_api.domains.rag.providers import (  # noqa: E402
    RagProviderConfigurationError,
    RagProviderTransientError,
)
from aidoo_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob  # noqa: E402
from aidoo_api.domains.rag.outbox import (  # noqa: E402
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)
from aidoo_api.domains.pms.rag_sync import (  # noqa: E402
    PMS_LABEL_RECOMPUTE_SCOPE,
    PMS_MEETING_VISIBILITY_SCOPE,
)


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
                    (
                        "7",
                        "rag_grounded_answer",
                        "local_only",
                        "Grounded answer synthesis for workspace RAG queries.",
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


def test_sync_resource_worker_span_inherits_outbox_trace_context(
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

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    bootstrap_telemetry(service_name="aidoo-worker-test")
    exporter = InMemorySpanExporter()
    provider = get_tracer_provider()
    assert provider is not None
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with start_as_current_span(
        tracer_name="tests.worker",
        span_name="tests.rag_parent",
    ) as parent_span:
        parent_span_id = parent_span.get_span_context().span_id
        with Session(engine) as session:
            with session.begin():
                session.add(
                    Workspace(
                        id="ws-1",
                        key="ws-1",
                        name="Workspace 1",
                        description="",
                        active=True,
                    )
                )
                job = enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-1",
                )
                job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "disabled"
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert "tests.rag_parent" in spans
    assert "rag.sync_resource" in spans
    child_span = spans["rag.sync_resource"]
    assert child_span.parent is not None
    assert child_span.parent.span_id == parent_span_id
    assert child_span.context.trace_id == spans["tests.rag_parent"].context.trace_id

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1


def test_recompute_visibility_worker_marks_terminal_statuses(
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

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            disabled_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-1",
            )
            disabled_job_id = disabled_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(disabled_job_id) == "disabled"

    with Session(engine) as session:
        stored = session.get(RagVisibilityRecomputeJob, disabled_job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.last_error is None

    with Session(engine) as session:
        with session.begin():
            enabled_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-2",
            )
            enabled_job_id = enabled_job.id

    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(enabled_job_id) == "unsupported_scope_type"

    with Session(engine) as session:
        stored = session.get(RagVisibilityRecomputeJob, enabled_job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.last_error == "unsupported scope_type: workspace_membership"


def test_sync_resource_worker_ignores_already_closed_job(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocContainer.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-doc-owner@aidoo.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.sync_resource.run(job_id) == "succeeded"
    assert tasks_module.sync_resource.run(job_id) == "ignored"

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_recompute_visibility_worker_ignores_already_closed_job(
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

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(job_id) == "disabled"
    assert tasks_module.recompute_visibility.run(job_id) == "ignored"

    with Session(engine) as session:
        stored = session.get(RagVisibilityRecomputeJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1


def test_recompute_visibility_worker_queues_docs_sync_jobs_for_meeting_scope(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            Meeting.__table__,
            MeetingDocLink.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        email="worker-doc-owner@aidoo.local",
                        full_name="Worker Doc Owner",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        email="worker-attendee@aidoo.local",
                        full_name="Worker Attendee",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Meeting Linked Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                Meeting(
                    id="meeting-1",
                    workspace_id="ws-1",
                    organizer_id="user-1",
                    notes_doc_id=None,
                    notes_page_id=None,
                    title="Worker Meeting",
                    agenda="",
                    start_at=datetime(2026, 4, 22, 0, 0, 0),
                    end_at=datetime(2026, 4, 22, 1, 0, 0),
                    status="scheduled",
                )
            )
            session.add(
                MeetingDocLink(
                    id="meeting-doc-1",
                    meeting_id="meeting-1",
                    doc_id="doc-1",
                    added_by_id="user-1",
                )
            )
            session.add(
                DocMeetingAccess(
                    id="grant-1",
                    doc_id="doc-1",
                    user_id="user-2",
                    access_level="read",
                    granted_by_meeting_id="meeting-1",
                    granted_by_user_id="user-1",
                    reason="meeting_attendee",
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="meeting",
                scope_id="meeting-1",
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        stored_visibility_job = session.get(RagVisibilityRecomputeJob, visibility_job_id)
        assert stored_visibility_job is not None
        assert stored_visibility_job.status == "succeeded"
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == NATIVE_DOC_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "doc-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1
        assert queued_jobs[0].lane == "backfill"


def test_recompute_visibility_worker_uses_cursor_doc_ids_when_meeting_is_missing(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            Meeting.__table__,
            MeetingDocLink.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-doc-owner@aidoo.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Deleted Meeting Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="meeting",
                scope_id="meeting-deleted",
                cursor={"doc_ids": ["doc-1"]},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == NATIVE_DOC_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "doc-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1


def test_recompute_visibility_worker_queues_pms_visibility_updates_for_meeting_scope(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Issue.__table__,
            Meeting.__table__,
            MeetingTaskLink.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
            IssueUserAccess.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        email="worker-owner@aidoo.local",
                        full_name="Worker Owner",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        email="worker-reader@aidoo.local",
                        full_name="Worker Reader",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Team 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="LIST1",
                    name="List 1",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    created_by_id="user-1",
                )
            )
            session.add(
                Issue(
                    id="issue-1",
                    list_id="list-1",
                    issue_number=1,
                    title="Meeting linked issue",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            session.add(
                Meeting(
                    id="meeting-1",
                    workspace_id="ws-1",
                    organizer_id="user-1",
                    notes_doc_id=None,
                    notes_page_id=None,
                    title="Worker Meeting",
                    agenda="",
                    start_at=datetime(2026, 4, 22, 0, 0, 0),
                    end_at=datetime(2026, 4, 22, 1, 0, 0),
                    status="scheduled",
                )
            )
            session.add(
                MeetingTaskLink(
                    id="meeting-task-1",
                    meeting_id="meeting-1",
                    issue_id="issue-1",
                    added_by_id="user-1",
                )
            )
            session.add(
                IssueUserAccess(
                    id="grant-1",
                    issue_id="issue-1",
                    user_id="user-2",
                    access_level="read",
                    granted_by_meeting_id="meeting-1",
                    granted_by_user_id="user-1",
                    reason="meeting_attendee",
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type=PMS_MEETING_VISIBILITY_SCOPE,
                scope_id="meeting-1",
                cursor={"issue_ids": ["issue-1"], "operation": "visibility_update"},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == PMS_ISSUE_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "issue-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1
        assert queued_jobs[0].lane == "backfill"


def test_recompute_visibility_worker_uses_cursor_issue_ids_when_pms_meeting_is_missing(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Issue.__table__,
            Meeting.__table__,
            MeetingTaskLink.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
            IssueUserAccess.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-owner@aidoo.local",
                    full_name="Worker Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Team 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="LIST1",
                    name="List 1",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    created_by_id="user-1",
                )
            )
            session.add(
                Issue(
                    id="issue-1",
                    list_id="list-1",
                    issue_number=1,
                    title="Deleted meeting issue",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type=PMS_MEETING_VISIBILITY_SCOPE,
                scope_id="meeting-deleted",
                cursor={"issue_ids": ["issue-1"], "operation": "visibility_update"},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == PMS_ISSUE_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "issue-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1


def test_recompute_visibility_worker_uses_cursor_issue_ids_for_deleted_pms_label_scope(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Issue.__table__,
            Label.__table__,
            IssueLabel.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-owner@aidoo.local",
                    full_name="Worker Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Team 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="LIST1",
                    name="List 1",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    created_by_id="user-1",
                )
            )
            session.add(
                Issue(
                    id="issue-1",
                    list_id="list-1",
                    issue_number=1,
                    title="Deleted label issue",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type=PMS_LABEL_RECOMPUTE_SCOPE,
                scope_id="label-deleted",
                cursor={"issue_ids": ["issue-1"], "operation": "upsert"},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == PMS_ISSUE_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "issue-1",
                    RagSyncJob.operation == RagSyncOperation.UPSERT.value,
                )
            )
        )
        assert len(queued_jobs) == 1


def test_sync_resource_worker_upserts_docs_projection_with_fake_provider(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocContainer.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-doc-owner@aidoo.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="doc-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "doc-1"
    assert snapshot.resource_type == NATIVE_DOC_RESOURCE_TYPE
    assert "worker sync content" in snapshot.text_content

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_deletes_docs_projection_with_fake_provider(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocContainer.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-doc-owner@aidoo.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            upsert_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            upsert_job_id = upsert_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.sync_resource.run(upsert_job_id) == "succeeded"

    with Session(engine) as session:
        with session.begin():
            delete_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
                operation=RagSyncOperation.DELETE,
            )
            delete_job_id = delete_job.id

    result = tasks_module.sync_resource.run(delete_job_id)

    assert result == "deleted"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="doc-1:0")
    assert snapshot is None

    with Session(engine) as session:
        stored = session.get(RagSyncJob, delete_job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_upserts_planner_projection_with_fake_provider(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            PlannerEvent.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-planner-owner@aidoo.local",
                    full_name="Worker Planner Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                PlannerEvent(
                    id="event-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Planner Sync Event",
                    description="Discuss roadmap",
                    location="Pangyo",
                    visibility="public",
                    all_day=False,
                    start_at=datetime(2026, 5, 20, 1, 0, 0),
                    end_at=datetime(2026, 5, 20, 2, 0, 0),
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=PLANNER_EVENT_RESOURCE_TYPE,
                resource_id="event-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="event-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "event-1"
    assert snapshot.resource_type == PLANNER_EVENT_RESOURCE_TYPE
    assert snapshot.source_kind == "planner_event"
    assert snapshot.metadata["visibility"] == "public"
    assert "workspace_public:ws-1" in snapshot.visibility_refs

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_upserts_meeting_projection_with_fake_provider(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Meeting.__table__,
            MeetingAttendee.__table__,
            MeetingTaskLink.__table__,
            MeetingDocLink.__table__,
            MeetingRecording.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        email="worker-meeting-organizer@aidoo.local",
                        full_name="Worker Meeting Organizer",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        email="worker-meeting-attendee@aidoo.local",
                        full_name="Worker Meeting Attendee",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                Meeting(
                    id="meeting-1",
                    workspace_id="ws-1",
                    organizer_id="user-1",
                    title="Worker Meeting Sync",
                    agenda="Discuss launch blockers",
                    start_at=datetime(2026, 5, 20, 1, 0, 0),
                    end_at=datetime(2026, 5, 20, 2, 0, 0),
                    status="scheduled",
                )
            )
            session.add(
                MeetingAttendee(
                    id="attendee-1",
                    meeting_id="meeting-1",
                    user_id="user-2",
                    role="required",
                    response="accepted",
                )
            )
            session.add(
                MeetingRecording(
                    id="recording-1",
                    meeting_id="meeting-1",
                    storage_key="meeting/meeting-1/recording-1.webm",
                    file_size=100,
                    mime_type="audio/webm",
                    idempotency_key="meeting-rag-recording",
                    uploaded_by_id="user-1",
                    source="manual_upload",
                    transcription_status="done",
                    progress_pct=100,
                    transcript_text="Budget risk was reviewed and owners were assigned.",
                    summary_text="Owners assigned and budget risk reviewed.",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=MEETING_RESOURCE_TYPE,
                resource_id="meeting-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="meeting-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "meeting-1"
    assert snapshot.resource_type == MEETING_RESOURCE_TYPE
    assert snapshot.source_kind == "meeting"
    assert "meeting_organizer:user-1" in snapshot.visibility_refs
    assert "meeting_attendee:user-2" in snapshot.visibility_refs
    assert "budget risk reviewed" in snapshot.text_content.lower()

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_upserts_pms_issue_projection_with_fake_provider(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Milestone.__table__,
            Label.__table__,
            Issue.__table__,
            IssueLabel.__table__,
            IssueComment.__table__,
            IssueUserAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        email="worker-pms-reporter@aidoo.local",
                        full_name="Worker PMS Reporter",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        email="worker-pms-grantee@aidoo.local",
                        full_name="Worker PMS Grantee",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Worker PMS Team",
                    description="",
                    active=True,
                    trashed_at=None,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="PMS1",
                    name="Worker PMS List",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            session.add(
                Issue(
                    id="issue-1",
                    list_id="list-1",
                    issue_number=1,
                    title="Worker PMS Issue",
                    description="Issue projection body",
                    description_blocks=[{"type": "paragraph", "text": "Issue projection blocks"}],
                    status="backlog",
                    priority="high",
                    assignee_id=None,
                    reporter_id="user-1",
                    parent_id=None,
                    milestone_id=None,
                    start_date=None,
                    due_date=None,
                    board_position=1,
                    estimate_hours=None,
                    recurrence_rule=None,
                    archived=False,
                )
            )
            session.add(
                IssueComment(
                    id="comment-1",
                    issue_id="issue-1",
                    author_id="user-1",
                    body="Need a follow-up",
                    body_blocks=None,
                )
            )
            session.add(
                IssueUserAccess(
                    id="grant-1",
                    issue_id="issue-1",
                    user_id="user-2",
                    access_level="read",
                    granted_by_meeting_id="meeting-1",
                    granted_by_user_id="user-1",
                    reason="meeting_attendee",
                    expires_at=None,
                    revoked_at=None,
                    revoked_by_user_id=None,
                    revoke_reason=None,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=PMS_ISSUE_RESOURCE_TYPE,
                resource_id="issue-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="issue-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "issue-1"
    assert snapshot.resource_type == PMS_ISSUE_RESOURCE_TYPE
    assert snapshot.source_kind == "pms_issue"
    assert snapshot.metadata["team_id"] == "team-1"
    assert "issue_grant:user-2" in snapshot.visibility_refs
    assert "Need a follow-up" in snapshot.text_content

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_provider_bundle_uses_qdrant_vector_index_when_configured(
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
    monkeypatch.setenv("AIDOO_VECTOR_INDEX_PROVIDER", "qdrant")
    monkeypatch.setenv("AIDOO_QDRANT_URL", "http://qdrant.test:6333")
    monkeypatch.setenv("AIDOO_QDRANT_API_KEY", "secret")

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    tasks_module._provider_bundle.cache_clear()
    rag_runtime = importlib.import_module("aidoo_api.domains.rag.runtime")

    created: dict[str, str | None] = {}

    class StubQdrantVectorIndexClient:
        def __init__(self, *, url: str | None = None, api_key: str | None = None) -> None:
            created["url"] = url
            created["api_key"] = api_key

    monkeypatch.setattr(rag_runtime, "QdrantVectorIndexClient", StubQdrantVectorIndexClient)

    bundle = tasks_module._provider_bundle()

    assert isinstance(bundle.vector_index, StubQdrantVectorIndexClient)
    assert created == {
        "url": "http://qdrant.test:6333",
        "api_key": "secret",
    }


def test_collection_name_matches_model_scoped_runtime_resolution(
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
    monkeypatch.setenv("AIDOO_EMBEDDING_PROVIDER", "deepinfra")
    monkeypatch.setenv("DEEPINFRA_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")

    collection = tasks_module._collection_name()

    assert collection == "doowon-rag-qwen-qwen3-embedding-8b"


def test_worker_settings_ignore_deepinfra_alias_validation_when_provider_not_selected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    settings_module = _reload_worker_module("aidoo_worker.settings")
    settings = settings_module.Settings(
        _env_file=None,
        DOOWON_POSTGRES_DSN=_worker_dsn(db_path),
        DOOWON_WORKER_POSTGRES_DSN=_worker_dsn(db_path),
        AIDOO_RAG_ENABLED="0",
        AIDOO_EMBEDDING_PROVIDER="fake",
        AIDOO_RERANK_PROVIDER="fake",
        DEEPINFRA_BASE_URL="http://127.0.0.1:8080/openai",
    )

    assert settings.rag_enabled is False
    assert settings.rag_deepinfra_base_url == "http://127.0.0.1:8080/openai"


def test_sync_resource_worker_schedules_retry_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RetryScheduled(Exception):
        pass

    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-retry",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    retry_calls: list[int] = []

    def fake_retry(*, exc, countdown, **_kwargs):
        assert isinstance(exc, RuntimeError)
        retry_calls.append(countdown)
        raise RetryScheduled()

    monkeypatch.setattr(tasks_module.sync_resource, "retry", fake_retry)

    with pytest.raises(RetryScheduled):
        tasks_module.sync_resource.run(job_id)

    assert retry_calls == [7]
    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "pending"
        assert stored.attempts == 1
        assert stored.next_retry_at is not None
        assert stored.last_error == "boom"


def test_sync_resource_worker_merges_retry_when_duplicate_pending_job_exists(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    class _FakeSignature:
        def apply_async(self, *, queue: str, retry: bool) -> None:
            del queue, retry

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            del task_name, args, immutable
            return _FakeSignature()

    monkeypatch.setattr(
        "aidoo_api.domains.rag.outbox._get_celery_client",
        lambda: _FakeCeleryClient(),
    )

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            original_job_id = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-retry-merge",
            ).id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    merged_pending_id: str | None = None

    def _inject_duplicate_pending(_session, job):
        nonlocal merged_pending_id
        with Session(engine) as competing_session:
            with competing_session.begin():
                merged_pending_id = enqueue_rag_sync_job(
                    competing_session,
                    workspace_id=job.workspace_id,
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=RagSyncOperation(job.operation),
                    lane=RagSyncLane(job.lane),
                    content_checksum=job.content_checksum,
                    visibility_checksum=job.visibility_checksum,
                    trace_context=job.trace_context,
                ).id
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks_module, "_process_sync_job", _inject_duplicate_pending)
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("merged retry must not schedule a Celery retry"),
    )

    result = tasks_module.sync_resource.run(original_job_id)

    assert result == "retry_merged"
    assert merged_pending_id is not None
    with Session(engine) as session:
        original = session.get(RagSyncJob, original_job_id)
        merged = session.get(RagSyncJob, merged_pending_id)
        assert original is not None
        assert merged is not None
        assert original.status == "cancelled"
        assert original.next_retry_at is None
        assert original.last_error == f"merged_retry_into:{merged_pending_id}: boom"
        assert merged.status == "pending"


def test_sync_resource_worker_uses_retry_after_for_transient_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RetryScheduled(Exception):
        pass

    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-rate-limit",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(
            RagProviderTransientError("slow down", retry_after_seconds=19)
        ),
    )

    retry_calls: list[int] = []

    def fake_retry(*, exc, countdown, **_kwargs):
        assert isinstance(exc, RagProviderTransientError)
        retry_calls.append(countdown)
        raise RetryScheduled()

    monkeypatch.setattr(tasks_module.sync_resource, "retry", fake_retry)

    with pytest.raises(RetryScheduled):
        tasks_module.sync_resource.run(job_id)

    assert retry_calls == [19]


def test_sync_resource_worker_cancels_non_retryable_provider_configuration_errors(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_MAX_ATTEMPTS", "3")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-bad-config",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(
            RagProviderConfigurationError("bad qdrant schema")
        ),
    )
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("non-retryable provider errors must not schedule retry"),
    )

    result = tasks_module.sync_resource.run(job_id)

    assert result == "non_retryable_error"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.last_error == "non_retryable: bad qdrant schema"


def test_sync_resource_worker_dead_letters_poison_message_after_max_attempts(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_JOB_MAX_ATTEMPTS", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-dead",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(RuntimeError("poison")),
    )
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("dead-letter path must not schedule retry"),
    )

    result = tasks_module.sync_resource.run(job_id)

    assert result == "dead_letter"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.next_retry_at is None
        assert stored.last_error == "dead_letter: poison"


def test_sync_backfill_worker_drains_chunked_batch_with_throttle(
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
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_BACKFILL_BATCH_SIZE", "2")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_BACKFILL_THROTTLE_MS", "50")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            backfill_ids = [
                enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id=f"doc-backfill-{index}",
                    lane=RagSyncLane.BACKFILL,
                ).id
                for index in range(1, 4)
            ]
            realtime_id = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-realtime",
                lane=RagSyncLane.REALTIME,
            ).id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    processed: list[str] = []
    sleeps: list[float] = []
    monkeypatch.setattr(tasks_module, "_process_sync_job", lambda _session, job: processed.append(job.id) or "succeeded")
    monkeypatch.setattr(tasks_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = tasks_module.sync_backfill_resource.run(backfill_ids[0])

    assert result == "succeeded"
    assert processed == backfill_ids[:2]
    assert sleeps == [0.05]

    with Session(engine) as session:
        first = session.get(RagSyncJob, backfill_ids[0])
        second = session.get(RagSyncJob, backfill_ids[1])
        third = session.get(RagSyncJob, backfill_ids[2])
        realtime = session.get(RagSyncJob, realtime_id)
        assert first is not None and first.status == "succeeded"
        assert second is not None and second.status == "succeeded"
        assert third is not None and third.status == "pending"
        assert realtime is not None and realtime.status == "pending"
