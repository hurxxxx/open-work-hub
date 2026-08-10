from __future__ import annotations

import json
import logging
from datetime import timedelta
from datetime import date, datetime
from typing import Any, Literal

from fastapi import status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.core.principal import CallerPrincipal
from open_alm_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from open_alm_api.domains.auth.access import record_audit_log
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingInsight,
    MeetingRecording,
)
from open_alm_api.domains.meeting.schemas import MeetingAvailabilityResponse
from open_alm_api.domains.planner.event_time import parse_iso_or_date
from open_alm_api.domains.recording.models import Recording, RecordingTarget


logger = logging.getLogger(__name__)

InsightType = Literal["action", "decision", "followup_schedule"]

STATUS_DRAFT = "draft"
STATUS_SUPERSEDED = "superseded"
ACTIVE_RECORDING_INSIGHT_STATUSES = ("draft", "accepted", "rejected")
MAX_FOLLOWUP_AVAILABILITY_RANGE = timedelta(days=31)


class InsightSourceSpan(BaseModel):
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    quote: str | None = Field(default=None, max_length=1000)


class ActionInsightCandidate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    proposed_assignee_user_id: str | None = None
    proposed_due_date: date | None = None
    proposed_list_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_span: InsightSourceSpan | None = None


class DecisionInsightCandidate(BaseModel):
    statement: str = Field(..., min_length=1, max_length=4000)
    rationale: str | None = Field(default=None, max_length=4000)
    decided_by_user_ids: list[str] | None = Field(default=None, max_length=50)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_span: InsightSourceSpan | None = None


class ProposedSlot(BaseModel):
    start_at: datetime
    end_at: datetime


class FollowupInsightCandidate(BaseModel):
    proposed_title: str = Field(..., min_length=1, max_length=200)
    duration_minutes: int = Field(..., ge=15, le=1440)
    proposed_slots: list[ProposedSlot] = Field(default_factory=list)
    attendee_user_ids: list[str] | None = Field(default=None, max_length=50)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_span: InsightSourceSpan | None = None


class _ActionInsightEnvelope(BaseModel):
    items: list[ActionInsightCandidate] = Field(default_factory=list)


class _DecisionInsightEnvelope(BaseModel):
    items: list[DecisionInsightCandidate] = Field(default_factory=list)


class _FollowupInsightEnvelope(BaseModel):
    items: list[FollowupInsightCandidate] = Field(default_factory=list)


_INSIGHT_TASK_KIND: dict[InsightType, str] = {
    "action": "meeting_insight_actions",
    "decision": "meeting_insight_decisions",
    "followup_schedule": "meeting_insight_followup",
}

_INSIGHT_ENVELOPE_MODEL = {
    "action": _ActionInsightEnvelope,
    "decision": _DecisionInsightEnvelope,
    "followup_schedule": _FollowupInsightEnvelope,
}


def _meeting_service():
    from open_alm_api.domains.meeting import service as meeting_service

    return meeting_service


def _recording_transcript(recording: MeetingRecording | Recording) -> str:
    return (recording.transcript_text or "").strip()


def _recording_summary(recording: MeetingRecording | Recording) -> str:
    return (getattr(recording, "summary_text", None) or "").strip()


def _meeting_context_block(meeting: Meeting, recording: MeetingRecording | Recording) -> str:
    attendee_names = ", ".join(
        attendee.user.full_name for attendee in meeting.attendees if attendee.user is not None
    )
    transcript = _recording_transcript(recording)
    summary = _recording_summary(recording)
    transcript_excerpt = transcript[:12000]
    return (
        f"회의 제목: {meeting.title}\n"
        f"시작: {meeting.start_at.isoformat()}\n"
        f"종료: {meeting.end_at.isoformat()}\n"
        f"참석자: {attendee_names or '-'}\n\n"
        f"[요약]\n{summary}\n\n"
        f"[전사 발췌]\n{transcript_excerpt}"
    )


def _insight_prompt(
    insight_type: InsightType, meeting: Meeting, recording: MeetingRecording | Recording
) -> list[dict[str, str]]:
    context_block = _meeting_context_block(meeting, recording)
    if insight_type == "action":
        system = (
            "당신은 회의 액션 아이템 추출기다. "
            "응답은 반드시 JSON 객체 하나여야 하며 최상위 키는 items 뿐이다. "
            "items 각 원소는 title, description?, proposed_assignee_user_id?, proposed_due_date?, proposed_list_id?, confidence?, "
            "source_span?({start_ms?, end_ms?, quote?}) 만 포함한다. "
            "실제 해야 할 일만 포함하고, 추측은 confidence를 낮게 두며 불필요한 설명 문장은 금지한다."
        )
    elif insight_type == "decision":
        system = (
            "당신은 회의 결정사항 추출기다. "
            "응답은 반드시 JSON 객체 하나여야 하며 최상위 키는 items 뿐이다. "
            "items 각 원소는 statement, rationale?, decided_by_user_ids?, confidence?, source_span?만 포함한다. "
            "명시적으로 합의된 결정만 반환하고, 미확정 논의는 제외한다."
        )
    else:
        system = (
            "당신은 후속 회의 일정 제안 추출기다. "
            "응답은 반드시 JSON 객체 하나여야 하며 최상위 키는 items 뿐이다. "
            "items 각 원소는 proposed_title, duration_minutes, proposed_slots[{start_at,end_at}], attendee_user_ids?, confidence?, "
            "source_span?만 포함한다. "
            "follow-up 회의가 필요하지 않으면 빈 items를 반환한다."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": context_block},
    ]


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
    return stripped


def _payload_from_candidate(
    candidate: BaseModel,
) -> tuple[dict[str, Any], float | None, dict[str, Any] | None]:
    payload = candidate.model_dump(mode="json", exclude_none=True)
    confidence = payload.pop("confidence", None)
    source_span = payload.pop("source_span", None)
    return payload, confidence, source_span


def _serialize_insight(insight: MeetingInsight) -> dict[str, Any]:
    return {
        "id": insight.id,
        "meeting_id": insight.meeting_id,
        "recording_id": insight.recording_id,
        "workspace_id": insight.workspace_id,
        "insight_type": insight.insight_type,
        "payload": insight.payload_json,
        "confidence": insight.confidence,
        "source_span": insight.source_span,
        "status": insight.status,
        "accepted_as_kind": insight.accepted_as_kind,
        "accepted_as_id": insight.accepted_as_id,
        "created_by_run_id": insight.created_by_run_id,
        "created_at": insight.created_at,
    }


def _canonical_recording_tables_available(db: Session) -> bool:
    try:
        inspector = inspect(db.get_bind())
        return inspector.has_table(Recording.__tablename__) and inspector.has_table(
            RecordingTarget.__tablename__
        )
    except Exception:  # noqa: BLE001
        return False


def _latest_canonical_meeting_recording(
    db: Session,
    *,
    workspace_id: str,
    meeting_id: str,
    require_transcript: bool = False,
) -> Recording | None:
    if not _canonical_recording_tables_available(db):
        return None
    query = (
        select(Recording)
        .join(RecordingTarget)
        .options(selectinload(Recording.targets))
        .where(
            Recording.workspace_id == workspace_id,
            Recording.trashed_at.is_(None),
            RecordingTarget.target_app == "meeting",
            RecordingTarget.target_type == "meeting",
            RecordingTarget.target_id == meeting_id,
        )
        .order_by(RecordingTarget.sort_order.desc(), Recording.started_at.desc())
    )
    if require_transcript:
        query = query.where(Recording.transcript_text.is_not(None))
    return db.scalar(query)


def _load_latest_ready_recording(
    db: Session, *, meeting_id: str
) -> MeetingRecording | Recording | None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is not None:
        recording = _latest_canonical_meeting_recording(
            db,
            workspace_id=meeting.workspace_id,
            meeting_id=meeting.id,
            require_transcript=True,
        )
        if recording is not None:
            return recording
    return db.scalar(
        select(MeetingRecording)
        .where(
            MeetingRecording.meeting_id == meeting_id,
            MeetingRecording.summary_text.is_not(None),
            MeetingRecording.transcript_text.is_not(None),
        )
        .order_by(MeetingRecording.sequence_no.desc(), MeetingRecording.created_at.desc())
    )


def _load_ready_recording_context(
    db: Session,
    *,
    recording_id: str,
) -> tuple[MeetingRecording | Recording, str, str | None]:
    if _canonical_recording_tables_available(db):
        recording = db.scalar(
            select(Recording)
            .where(Recording.id == recording_id)
            .options(selectinload(Recording.targets))
        )
        if recording is not None:
            meeting_target = next(
                (
                    target
                    for target in recording.targets
                    if target.target_app == "meeting" and target.target_type == "meeting"
                ),
                None,
            )
            if meeting_target is None:
                raise localized_http_exception(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="meeting.recording_not_found",
                )
            if not recording.transcript_text:
                raise localized_http_exception(
                    status_code=status.HTTP_409_CONFLICT,
                    code="meeting.recording_summary_unavailable",
                )
            return recording, meeting_target.target_id, None

    legacy = db.scalar(select(MeetingRecording).where(MeetingRecording.id == recording_id))
    if legacy is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="meeting.recording_not_found",
        )
    if not legacy.summary_text or not legacy.transcript_text:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="meeting.recording_summary_unavailable",
        )
    return legacy, legacy.meeting_id, legacy.id


def _load_existing_draft_insights(
    db: Session,
    *,
    meeting_id: str,
    insight_type: InsightType,
) -> list[MeetingInsight]:
    return list(
        db.scalars(
            select(MeetingInsight)
            .where(
                MeetingInsight.meeting_id == meeting_id,
                MeetingInsight.insight_type == insight_type,
                MeetingInsight.status == STATUS_DRAFT,
            )
            .order_by(MeetingInsight.created_at.asc())
        )
    )


def _load_existing_recording_insights(
    db: Session,
    *,
    recording_id: str,
    insight_type: InsightType,
) -> list[MeetingInsight]:
    return list(
        db.scalars(
            select(MeetingInsight)
            .where(
                MeetingInsight.recording_id == recording_id,
                MeetingInsight.insight_type == insight_type,
                MeetingInsight.status.in_(ACTIVE_RECORDING_INSIGHT_STATUSES),
            )
            .order_by(MeetingInsight.created_at.asc())
        )
    )


def _supersede_draft_insights(
    db: Session,
    *,
    meeting_id: str,
    insight_type: InsightType,
) -> list[MeetingInsight]:
    existing_drafts = _load_existing_draft_insights(
        db,
        meeting_id=meeting_id,
        insight_type=insight_type,
    )
    for existing in existing_drafts:
        existing.status = STATUS_SUPERSEDED
        db.add(existing)
    return existing_drafts


def _record_created_audit(
    db: Session,
    *,
    meeting_id: str,
    workspace_id: str,
    recording_id: str,
    actor_user_id: str | None,
    created_counts: dict[str, int],
) -> None:
    if not created_counts:
        return
    record_audit_log(
        db,
        action="ai_meeting_insight_created",
        entity_kind="meeting",
        entity_id=meeting_id,
        actor_user_id=actor_user_id,
        summary=f"Meeting insights extracted for {meeting_id}",
        payload={
            "workspace_id": workspace_id,
            "meeting_id": meeting_id,
            "recording_id": recording_id,
            "insight_counts": created_counts,
        },
    )


def extract_and_persist_meeting_insights(
    db: Session,
    *,
    recording_id: str,
    source: str,
    actor_user_id: str | None,
    refresh: bool = False,
    insight_types: tuple[InsightType, ...] = ("action", "decision", "followup_schedule"),
    created_by_run_id: str | None = None,
) -> dict[InsightType, list[MeetingInsight]]:
    recording, meeting_id, insight_recording_id = _load_ready_recording_context(
        db,
        recording_id=recording_id,
    )

    meeting = db.scalar(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.attendees).selectinload(MeetingAttendee.user))
    )
    if meeting is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="meeting.not_found"
        )

    created_counts: dict[str, int] = {}
    results: dict[InsightType, list[MeetingInsight]] = {}
    for insight_type in insight_types:
        if not refresh and insight_recording_id is not None:
            existing_for_recording = _load_existing_recording_insights(
                db,
                recording_id=insight_recording_id,
                insight_type=insight_type,
            )
            if existing_for_recording:
                results[insight_type] = existing_for_recording
                continue

        messages = _insight_prompt(insight_type, meeting, recording)
        context = LlmTaskContext(
            source=source,
            actor_user_id=actor_user_id,
            workspace_id=meeting.workspace_id,
            task_kind=_INSIGHT_TASK_KIND[insight_type],
            app_id="meeting",
            principal_kind="system" if actor_user_id is None else "user",
            principal_id=actor_user_id,
        )
        try:
            completion = execute_llm(
                context.task_kind,
                LlmWorkloadContext.from_task_context(context),
                db,
                messages=messages,
                temperature=0.2,
                max_tokens=4000,
                reasoning_effort="none",
                agent_run_id=created_by_run_id,
            ).completion
            raw_content = completion.text.strip()
            payload = json.loads(_extract_json_object(raw_content))
            envelope_model = _INSIGHT_ENVELOPE_MODEL[insight_type]
            parsed_envelope = envelope_model.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as error:
            logger.warning(
                "Meeting insight extraction skipped due to invalid %s payload for recording %s",
                insight_type,
                recording.id,
                exc_info=error,
            )
            continue
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "Meeting insight extraction failed for %s on recording %s",
                insight_type,
                recording.id,
                exc_info=error,
            )
            continue

        created_items: list[MeetingInsight] = []
        existing_drafts = _load_existing_draft_insights(
            db,
            meeting_id=meeting.id,
            insight_type=insight_type,
        )
        if not parsed_envelope.items:
            if refresh and existing_drafts:
                results[insight_type] = existing_drafts
            else:
                results[insight_type] = []
            continue

        _supersede_draft_insights(db, meeting_id=meeting.id, insight_type=insight_type)
        for candidate in parsed_envelope.items:
            payload_json, confidence, source_span = _payload_from_candidate(candidate)
            insight = MeetingInsight(
                id=new_id(),
                meeting_id=meeting.id,
                recording_id=insight_recording_id,
                workspace_id=meeting.workspace_id,
                insight_type=insight_type,
                payload_json=payload_json,
                confidence=confidence,
                source_span=source_span,
                status=STATUS_DRAFT,
                created_by_run_id=created_by_run_id,
            )
            db.add(insight)
            created_items.append(insight)
        db.flush()
        results[insight_type] = created_items
        created_counts[insight_type] = len(created_items)

    _record_created_audit(
        db,
        meeting_id=meeting.id,
        workspace_id=meeting.workspace_id,
        recording_id=recording.id,
        actor_user_id=actor_user_id,
        created_counts=created_counts,
    )
    return results


def _ensure_meeting_access(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
) -> Meeting:
    return _meeting_service().load_meeting_for_participant(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=meeting_id,
    )


def _ensure_insights_available(
    db: Session,
    *,
    meeting: Meeting,
    insight_type: InsightType,
    source: str,
    actor_user_id: str | None,
    refresh: bool,
) -> list[MeetingInsight]:
    existing = _load_existing_draft_insights(
        db,
        meeting_id=meeting.id,
        insight_type=insight_type,
    )
    if not refresh:
        return existing

    recording = _load_latest_ready_recording(db, meeting_id=meeting.id)
    if recording is None:
        if refresh:
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="meeting.recording_summary_unavailable",
            )
        return existing

    extracted = extract_and_persist_meeting_insights(
        db,
        recording_id=recording.id,
        source=source,
        actor_user_id=actor_user_id,
        refresh=refresh,
        insight_types=(insight_type,),
    )
    db.commit()
    return extracted.get(insight_type, [])


def list_action_insights(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
    refresh: bool = False,
) -> dict[str, Any]:
    meeting = _ensure_meeting_access(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=meeting_id,
    )
    items = _ensure_insights_available(
        db,
        meeting=meeting,
        insight_type="action",
        source="ai.tool.meeting.extract_actions",
        actor_user_id=user.id,
        refresh=refresh,
    )
    return {"items": [_serialize_insight(item) for item in items]}


def list_decision_insights(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
    refresh: bool = False,
) -> dict[str, Any]:
    meeting = _ensure_meeting_access(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=meeting_id,
    )
    items = _ensure_insights_available(
        db,
        meeting=meeting,
        insight_type="decision",
        source="ai.tool.meeting.extract_decisions",
        actor_user_id=user.id,
        refresh=refresh,
    )
    return {"items": [_serialize_insight(item) for item in items]}


def _slot_range(items: list[MeetingInsight]) -> tuple[datetime, datetime] | None:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for item in items:
        for slot in item.payload_json.get("proposed_slots", []):
            try:
                start_at = parse_iso_or_date(str(slot["start_at"]))
                end_at = parse_iso_or_date(str(slot["end_at"]))
            except Exception:  # noqa: BLE001
                continue
            starts.append(start_at)
            ends.append(end_at)
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _validate_followup_availability_range(
    slot_range: tuple[datetime, datetime] | None,
) -> tuple[datetime, datetime] | None:
    if slot_range is None:
        return None
    if slot_range[1] <= slot_range[0]:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.range_to_after_from",
        )
    if (slot_range[1] - slot_range[0]) > MAX_FOLLOWUP_AVAILABILITY_RANGE:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.availability_range_too_large",
            days=31,
        )
    return slot_range


def draft_followup_schedule(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
    attendee_user_ids: list[str] | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    meeting = _ensure_meeting_access(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=meeting_id,
    )
    items = _ensure_insights_available(
        db,
        meeting=meeting,
        insight_type="followup_schedule",
        source="ai.tool.meeting.draft_followup_schedule",
        actor_user_id=user.id,
        refresh=refresh,
    )
    selected_attendee_user_ids = attendee_user_ids or [
        attendee.user_id for attendee in meeting.attendees
    ]
    availability: MeetingAvailabilityResponse | None = None
    slot_range = _validate_followup_availability_range(_slot_range(items))
    if selected_attendee_user_ids and slot_range is not None:
        availability = _meeting_service().list_meeting_availability(
            db,
            workspace=workspace,
            principal=principal,
            viewer=user,
            user_ids=selected_attendee_user_ids,
            from_at=slot_range[0],
            to_at=slot_range[1],
        )
    return {
        "items": [_serialize_insight(item) for item in items],
        "attendee_user_ids": selected_attendee_user_ids,
        "availability": (
            availability.model_dump(mode="json", by_alias=True)
            if availability is not None
            else None
        ),
    }
