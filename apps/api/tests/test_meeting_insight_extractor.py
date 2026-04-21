from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import AuditLog, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.meeting import insights as meeting_insights
from aidoo_api.domains.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingInsight,
    MeetingRecording,
)
from aidoo_api.domains.planner.service import parse_iso_or_date


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _create_meeting_and_recording(
    client: TestClient,
    *,
    recording_id: str | None = None,
) -> tuple[dict, str]:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        user = load_user_graph(db, session["user"]["id"])
        assert workspace is not None
        assert user is not None

        meeting = Meeting(
            id=new_id(),
            workspace_id=workspace.id,
            organizer_id=user.id,
            title="Insight Source Meeting",
            agenda="AI insight extraction",
            start_at=parse_iso_or_date("2026-05-20T01:00:00+00:00"),
            end_at=parse_iso_or_date("2026-05-20T02:00:00+00:00"),
            status="scheduled",
        )
        db.add(meeting)
        db.flush()
        db.add(
            MeetingAttendee(
                id=new_id(),
                meeting_id=meeting.id,
                user_id=user.id,
                role="required",
                response="accepted",
            )
        )
        recording = MeetingRecording(
            id=recording_id or new_id(),
            meeting_id=meeting.id,
            storage_key=f"meeting-recordings/{meeting.id}/recording.webm",
            duration_sec=120,
            file_size=256,
            mime_type="audio/webm",
            idempotency_key=f"idem-{meeting.id}",
            uploaded_by_id=user.id,
            source="manual_upload",
            transcription_status="done",
            progress_pct=100,
            transcript_text="로그인 플로우를 정리하고 후속 회의를 잡자.",
            summary_text="액션과 후속 회의가 필요하다.",
        )
        db.add(recording)
        db.commit()
        return session, recording.id


def _response_with_content(content: str):
    return (
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        ),
        None,
        None,
    )


def test_extract_and_persist_meeting_insights_persists_valid_types_and_skips_invalid(
    client: TestClient,
    monkeypatch,
) -> None:
    session, recording_id = _create_meeting_and_recording(client, recording_id="recording-insight-1")
    task_kinds: list[str] = []

    def fake_complete_chat(context, _db, **_kwargs):
        task_kinds.append(context.task_kind)
        if context.task_kind == "meeting_insight_actions":
            return _response_with_content(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "로그인 플로우 정리",
                                "description": "OAuth 리다이렉트 경로 점검",
                                "confidence": 0.91,
                                "source_span": {
                                    "start_ms": 10,
                                    "end_ms": 55,
                                    "quote": "로그인 플로우를 정리합시다.",
                                },
                            }
                        ]
                    }
                )
            )
        if context.task_kind == "meeting_insight_decisions":
            return _response_with_content("not-json")
        return _response_with_content(
            json.dumps(
                {
                    "items": [
                        {
                            "proposed_title": "후속 점검 회의",
                            "duration_minutes": 30,
                            "proposed_slots": [
                                {
                                    "start_at": "2026-05-21T01:00:00Z",
                                    "end_at": "2026-05-21T01:30:00Z",
                                }
                            ],
                            "attendee_user_ids": [session["user"]["id"]],
                            "confidence": 0.73,
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(meeting_insights, "complete_chat", fake_complete_chat)

    with get_session_factory()() as db:
        result = meeting_insights.extract_and_persist_meeting_insights(
            db,
            recording_id=recording_id,
            source="worker.meeting.extract_insights",
            actor_user_id=None,
        )
        db.commit()

        stored = list(
            db.scalars(
                select(MeetingInsight)
                .where(MeetingInsight.recording_id == recording_id)
                .order_by(MeetingInsight.insight_type.asc())
            )
        )
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "ai_meeting_insight_created")
        )

    assert task_kinds == [
        "meeting_insight_actions",
        "meeting_insight_decisions",
        "meeting_insight_followup",
    ]
    assert set(result.keys()) == {"action", "followup_schedule"}
    assert {item.insight_type for item in stored} == {"action", "followup_schedule"}
    assert audit is not None
    assert audit.payload["recording_id"] == recording_id
    assert audit.payload["insight_counts"] == {"action": 1, "followup_schedule": 1}


def test_extract_and_persist_meeting_insights_refresh_supersedes_existing_drafts(
    client: TestClient,
    monkeypatch,
) -> None:
    _session, recording_id = _create_meeting_and_recording(client, recording_id="recording-insight-2")

    def fake_complete_chat(context, _db, **_kwargs):
        assert context.task_kind == "meeting_insight_actions"
        return _response_with_content(
            json.dumps(
                {
                    "items": [
                        {
                            "title": "새 액션 아이템",
                            "description": "최신 제안",
                            "confidence": 0.88,
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr(meeting_insights, "complete_chat", fake_complete_chat)

    with get_session_factory()() as db:
        recording = db.get(MeetingRecording, recording_id)
        assert recording is not None
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        old_insight = MeetingInsight(
            id=new_id(),
            meeting_id=recording.meeting_id,
            recording_id=recording.id,
            workspace_id=workspace.id,
            insight_type="action",
            payload_json={"title": "기존 액션"},
            confidence=0.2,
            source_span=None,
            status="draft",
            accepted_as_kind=None,
            accepted_as_id=None,
            created_by_run_id=None,
        )
        db.add(old_insight)
        db.commit()

        result = meeting_insights.extract_and_persist_meeting_insights(
            db,
            recording_id=recording_id,
            source="worker.meeting.extract_insights",
            actor_user_id=None,
            refresh=True,
            insight_types=("action",),
        )
        db.commit()
        db.refresh(old_insight)
        action_insights = list(
            db.scalars(
                select(MeetingInsight)
                .where(
                    MeetingInsight.recording_id == recording_id,
                    MeetingInsight.insight_type == "action",
                )
                .order_by(MeetingInsight.created_at.asc())
            )
        )

    assert old_insight.status == "superseded"
    assert len(result["action"]) == 1
    assert len(action_insights) == 2
    assert [item.status for item in action_insights] == ["superseded", "draft"]
    assert action_insights[-1].payload_json["title"] == "새 액션 아이템"


def test_extract_and_persist_meeting_insights_refresh_with_empty_items_keeps_existing_drafts(
    client: TestClient,
    monkeypatch,
) -> None:
    _session, recording_id = _create_meeting_and_recording(client, recording_id="recording-insight-3")

    def fake_complete_chat(context, _db, **_kwargs):
        assert context.task_kind == "meeting_insight_actions"
        return _response_with_content(json.dumps({"items": []}))

    monkeypatch.setattr(meeting_insights, "complete_chat", fake_complete_chat)

    with get_session_factory()() as db:
        recording = db.get(MeetingRecording, recording_id)
        assert recording is not None
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        old_insight = MeetingInsight(
            id=new_id(),
            meeting_id=recording.meeting_id,
            recording_id=recording.id,
            workspace_id=workspace.id,
            insight_type="action",
            payload_json={"title": "기존 액션"},
            confidence=0.2,
            source_span=None,
            status="draft",
            accepted_as_kind=None,
            accepted_as_id=None,
            created_by_run_id=None,
        )
        db.add(old_insight)
        db.commit()

        result = meeting_insights.extract_and_persist_meeting_insights(
            db,
            recording_id=recording_id,
            source="worker.meeting.extract_insights",
            actor_user_id=None,
            refresh=True,
            insight_types=("action",),
        )
        db.commit()
        db.refresh(old_insight)
        action_insights = list(
            db.scalars(
                select(MeetingInsight)
                .where(
                    MeetingInsight.recording_id == recording_id,
                    MeetingInsight.insight_type == "action",
                )
                .order_by(MeetingInsight.created_at.asc())
            )
        )

    assert old_insight.status == "draft"
    assert len(result["action"]) == 1
    assert result["action"][0].id == old_insight.id
    assert len(action_insights) == 1


def test_extract_and_persist_meeting_insights_reuses_existing_recording_insights_without_refresh(
    client: TestClient,
    monkeypatch,
) -> None:
    _session, recording_id = _create_meeting_and_recording(client, recording_id="recording-insight-4")

    monkeypatch.setattr(
        meeting_insights,
        "complete_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )

    with get_session_factory()() as db:
        recording = db.get(MeetingRecording, recording_id)
        assert recording is not None
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        accepted_insight = MeetingInsight(
            id=new_id(),
            meeting_id=recording.meeting_id,
            recording_id=recording.id,
            workspace_id=workspace.id,
            insight_type="decision",
            payload_json={"statement": "기존 결정사항"},
            confidence=0.5,
            source_span=None,
            status="accepted",
            accepted_as_kind="note",
            accepted_as_id="note-1",
            created_by_run_id=None,
        )
        db.add(accepted_insight)
        db.commit()

        result = meeting_insights.extract_and_persist_meeting_insights(
            db,
            recording_id=recording_id,
            source="worker.meeting.extract_insights",
            actor_user_id=None,
            refresh=False,
            insight_types=("decision",),
        )

    assert len(result["decision"]) == 1
    assert result["decision"][0].id == accepted_insight.id
