from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from celery.exceptions import Ignore
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

from open_work_hub_worker.tasks import meeting, rag_sync, recording, search_index

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.app_access_models import (
    AppAccessPolicy,
    AppGroupGrant,
    AppUserGrant,
)
from open_work_hub_api.domains.auth.models import CompanyAppControl, User, UserSystemRole
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.meeting.models import Meeting, MeetingAttendee
from open_work_hub_api.domains.organization.models import OrganizationUnit


@pytest.fixture
def company_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                User,
                UserSystemRole,
                OrganizationUnit,
                CompanyAppControl,
                AppAccessPolicy,
                AppGroupGrant,
                AppUserGrant,
                Group,
                GroupMember,
                Meeting,
                MeetingAttendee,
            )
        ],
    )
    with Session(engine) as db:
        db.add(
            User(
                id="user-1",
                login_id="user-1",
                email="user@example.test",
                full_name="Worker user",
                password_hash="unused-test-hash",
            )
        )
        db.add(Group(id="group-1", name="Allowed workers", kind="manual"))
        db.add(GroupMember(group_id="group-1", user_id="user-1"))
        for app_id in ("recording", "meeting", "docs"):
            db.add(CompanyAppControl(app_id=app_id, enabled=True))
            db.add(AppAccessPolicy(app_id=app_id, audience="selected"))
            db.add(AppGroupGrant(app_id=app_id, group_id="group-1"))
        db.commit()
        yield db
    engine.dispose()


@pytest.mark.parametrize(
    "revoke", ["master", "app_grant", "group_member", "group", "user", "blocked"]
)
def test_recording_worker_rechecks_current_company_admission(company_db, monkeypatch, revoke):
    current = SimpleNamespace(id="recording-1", owner_id="user-1", celery_task_id="attempt-1")
    failures = []
    monkeypatch.setattr(recording, "_mark_failed", lambda *args, **kwargs: failures.append(args[2]))
    recording._ensure_recording_execution_allowed(
        company_db, current, stage="summary", expected_attempt_id="attempt-1"
    )

    mutations = {
        "master": update(CompanyAppControl)
        .where(CompanyAppControl.app_id == "recording")
        .values(enabled=False),
        "app_grant": delete(AppGroupGrant).where(AppGroupGrant.app_id == "recording"),
        "group_member": delete(GroupMember),
        "group": update(Group).values(active=False),
        "user": update(User).values(status="inactive"),
        "blocked": update(User).values(login_blocked=True),
    }
    company_db.execute(mutations[revoke])
    company_db.commit()
    with pytest.raises(Ignore):
        recording._ensure_recording_execution_allowed(
            company_db, current, stage="summary", expected_attempt_id="attempt-1"
        )
    assert failures == ["Recording app execution disabled or requester membership revoked."]


def test_meeting_worker_rechecks_current_participation(company_db, monkeypatch):
    company_db.add(
        Meeting(
            id="meeting-1",
            organizer_id="organizer-1",
            title="Business meeting",
            start_at=datetime(2026, 9, 8),
            end_at=datetime(2026, 9, 9),
        )
    )
    company_db.add(MeetingAttendee(id="attendee-1", meeting_id="meeting-1", user_id="user-1"))
    company_db.commit()
    current = SimpleNamespace(
        id="recording-1", uploaded_by_id="user-1", meeting=SimpleNamespace(id="meeting-1")
    )
    failures = []
    monkeypatch.setattr(meeting, "_mark_failed", lambda *args: failures.append(args[2]))
    meeting._ensure_meeting_execution_allowed(company_db, current)

    company_db.execute(delete(MeetingAttendee))
    company_db.commit()
    with pytest.raises(Ignore):
        meeting._ensure_meeting_execution_allowed(company_db, current)
    assert failures == ["Meeting app execution disabled or requester membership revoked."]


def test_system_projection_workers_recheck_company_master(company_db):
    search_job = SimpleNamespace(entity_type="doc")
    rag_job = SimpleNamespace(resource_type="docs_native_doc", scope_kind="company")
    assert search_index._search_job_app_enabled(company_db, search_job)
    assert rag_sync._sync_job_app_enabled(company_db, rag_job)
    company_db.execute(
        update(CompanyAppControl).where(CompanyAppControl.app_id == "docs").values(enabled=False)
    )
    company_db.commit()
    assert not search_index._search_job_app_enabled(company_db, search_job)
    assert not rag_sync._sync_job_app_enabled(company_db, rag_job)


def test_recording_worker_discards_provider_result_after_admission_revocation(
    company_db, monkeypatch
):
    result = SimpleNamespace(transcript_text="Business transcript", summary_text=None, version=1)
    current = SimpleNamespace(
        id="recording-1",
        owner_id="user-1",
        celery_task_id="attempt-1",
        result=result,
        summary_status="pending",
        progress_pct=60,
        title="Recording",
        started_at=datetime(2026, 9, 8),
    )
    failures = []
    monkeypatch.setattr(recording, "_db_session", lambda: company_db)
    monkeypatch.setattr(recording, "_load_active_recording", lambda *args: current)
    monkeypatch.setattr(recording, "_lock_current_recording_attempt", lambda *args: current)
    monkeypatch.setattr(recording, "_heartbeat", lambda *args, **kwargs: None)
    monkeypatch.setattr(recording, "_mark_failed", lambda *args, **kwargs: failures.append(args[2]))

    def provider(_db, **kwargs):
        assert kwargs["actor_user_id"] == "user-1"
        company_db.execute(delete(GroupMember))
        company_db.commit()
        return "Summary must not be published"

    monkeypatch.setattr(recording, "_complete_local_agent", provider)
    with pytest.raises(Ignore):
        recording.analyze_transcript.run({"recording_id": current.id, "attempt_id": "attempt-1"})
    assert result.summary_text is None
    assert failures == ["Recording app execution disabled or requester membership revoked."]


def test_meeting_publication_requires_live_docs_admission(company_db):
    current = SimpleNamespace(uploaded_by_id="user-1", linked_task_id=None)
    meeting._ensure_meeting_publication_allowed(company_db, current)
    company_db.execute(delete(AppGroupGrant).where(AppGroupGrant.app_id == "docs"))
    company_db.commit()
    with pytest.raises(meeting.PermanentError, match="Docs app admission revoked"):
        meeting._ensure_meeting_publication_allowed(company_db, current)


def test_meeting_task_publication_rechecks_app_and_source_as_uploader(company_db, monkeypatch):
    company_db.add(CompanyAppControl(app_id="pms", enabled=True))
    company_db.add(AppAccessPolicy(app_id="pms", audience="selected"))
    company_db.add(AppGroupGrant(app_id="pms", group_id="group-1"))
    company_db.commit()
    current = SimpleNamespace(uploaded_by_id="user-1", linked_task_id="task-1")
    seen = []
    monkeypatch.setattr(
        meeting, "_ensure_task_writable", lambda db, user, task_id: seen.append((user.id, task_id))
    )
    meeting._ensure_meeting_publication_allowed(company_db, current)
    assert seen == [("user-1", "task-1")]

    def source_revoked(*args):
        raise HTTPException(status_code=403)

    monkeypatch.setattr(meeting, "_ensure_task_writable", source_revoked)
    with pytest.raises(meeting.PermanentError, match="PMS task write access revoked"):
        meeting._ensure_meeting_publication_allowed(company_db, current)
    company_db.execute(delete(AppGroupGrant).where(AppGroupGrant.app_id == "pms"))
    company_db.commit()
    with pytest.raises(meeting.PermanentError, match="PMS app admission revoked"):
        meeting._ensure_meeting_publication_allowed(company_db, current)


def test_rag_worker_checks_master_again_after_embedding_before_vector_write(
    company_db, monkeypatch
):
    job = SimpleNamespace(
        resource_type="docs_native_doc",
        resource_id="doc-1",
        scope_kind="company",
        operation="upsert",
    )
    writes = []

    class Provider:
        def sync_projection_with_fence(self, projection, *, collection, before_vector_write):
            company_db.execute(
                update(CompanyAppControl)
                .where(CompanyAppControl.app_id == "docs")
                .values(enabled=False)
            )
            company_db.commit()
            before_vector_write()
            writes.append(projection)
            return SimpleNamespace(chunk_count=1)

    monkeypatch.setattr(
        rag_sync,
        "_rag_runtime_for_job",
        lambda *args: SimpleNamespace(collection="test", service=Provider()),
    )
    monkeypatch.setattr(rag_sync, "_load_projection_for_job", lambda *args, **kwargs: object())
    monkeypatch.setattr(rag_sync, "_ensure_projection_matches_job", lambda *args: None)
    monkeypatch.setattr(rag_sync, "_projection_with_job_fence", lambda projection, job: projection)
    monkeypatch.setattr(
        rag_sync,
        "_resource_adapter_for_job",
        lambda job: SimpleNamespace(
            app_id="docs",
            on_projection_prepared_event=None,
            on_projection_prepared=None,
            on_projection_synced=None,
        ),
    )
    with pytest.raises(rag_sync.RagAppDisabled):
        rag_sync._process_sync_job(company_db, job)
    assert writes == []
