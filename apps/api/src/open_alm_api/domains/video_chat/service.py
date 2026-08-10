from __future__ import annotations

import re
from ipaddress import ip_address
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import Settings, get_settings
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.meeting.models import Meeting
from open_alm_api.domains.meeting.permissions import ensure_meeting_participant, is_participant
from open_alm_api.domains.video_chat.livekit_tokens import create_livekit_join_token
from open_alm_api.domains.video_chat.models import VideoChatSession
from open_alm_api.domains.video_chat.schemas import (
    VideoChatJoinTokenResponse,
    VideoChatSessionCreateRequest,
    VideoChatSessionListResponse,
    VideoChatSessionOut,
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _settings() -> Settings:
    return get_settings()


def _require_enabled(settings: Settings) -> None:
    if not settings.video_chat_enabled:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="video_chat.disabled",
        )


def _require_livekit_configured(settings: Settings) -> None:
    if not (
        settings.livekit_url.strip()
        and settings.livekit_api_key.strip()
        and settings.livekit_api_secret.strip()
    ):
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="video_chat.livekit_not_configured",
        )


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip("[]").lower()
    if normalized in {"localhost", "testserver"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _livekit_netloc(host: str, port: int | None) -> str:
    normalized = host.strip()
    if ":" in normalized and not normalized.startswith("["):
        normalized = f"[{normalized}]"
    return f"{normalized}:{port}" if port else normalized


def _livekit_url_for_browser(*, settings: Settings, request_host: str | None) -> str:
    public_url = settings.livekit_public_url.strip()
    if public_url:
        return public_url

    configured_url = settings.livekit_url.strip()
    parsed = urlsplit(configured_url)
    if not parsed.hostname:
        return configured_url
    if not _is_loopback_host(parsed.hostname):
        return configured_url
    if not request_host or _is_loopback_host(request_host):
        return configured_url

    return urlunsplit(
        (
            parsed.scheme or "ws",
            _livekit_netloc(request_host, parsed.port),
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _safe_room_fragment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
    return normalized or "workspace"


def _room_name(*, settings: Settings, workspace: Workspace, session_id: str) -> str:
    prefix = _safe_room_fragment(settings.video_chat_room_prefix)[:32]
    workspace_part = _safe_room_fragment(workspace.key)[:40]
    return f"{prefix}-{workspace_part}-{session_id}"


def _display_name(user: User) -> str:
    return user.full_name or user.email or user.id


def _serialize(session: VideoChatSession) -> VideoChatSessionOut:
    return VideoChatSessionOut(
        id=session.id,
        workspace_id=session.workspace_id,
        meeting_id=session.meeting_id,
        room_name=session.room_name,
        title=session.title,
        status=session.status,
        provider=session.provider,
        started_by_id=session.started_by_id,
        started_by_name=_display_name(session.started_by),
        started_at=session.started_at,
        ended_at=session.ended_at,
        recording_status=session.recording_status,
        recording_egress_id=session.recording_egress_id,
        recording_id=session.recording_id,
        captions_status=session.captions_status,
        captions_started_at=session.captions_started_at,
        captions_ended_at=session.captions_ended_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _load_session(db: Session, *, workspace: Workspace, session_id: str) -> VideoChatSession:
    session = db.scalar(
        select(VideoChatSession)
        .options(selectinload(VideoChatSession.started_by))
        .where(
            VideoChatSession.id == session_id,
            VideoChatSession.workspace_id == workspace.id,
        )
    )
    if session is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="video_chat.session_not_found",
        )
    return session


def _ensure_session_access(
    db: Session, *, workspace: Workspace, user: User, session: VideoChatSession
) -> None:
    if not session.meeting_id:
        return
    meeting = db.scalar(
        select(Meeting).where(
            Meeting.id == session.meeting_id,
            Meeting.workspace_id == workspace.id,
        )
    )
    if meeting is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="video_chat.meeting_not_found",
        )
    ensure_meeting_participant(db, user, meeting)


def _ensure_session_host(*, user: User, session: VideoChatSession) -> None:
    if session.started_by_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="video_chat.host_required",
        )


def _load_meeting_for_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str | None,
) -> Meeting | None:
    if not meeting_id:
        return None
    meeting = db.scalar(
        select(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.workspace_id == workspace.id,
        )
    )
    if meeting is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="video_chat.meeting_not_found",
        )
    ensure_meeting_participant(db, user, meeting)
    return meeting


def list_sessions(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    status_filter: str | None = None,
) -> VideoChatSessionListResponse:
    _require_enabled(_settings())
    query = (
        select(VideoChatSession)
        .options(
            selectinload(VideoChatSession.started_by),
            selectinload(VideoChatSession.meeting).selectinload(Meeting.attendees),
        )
        .where(VideoChatSession.workspace_id == workspace.id)
        .order_by(VideoChatSession.started_at.desc())
    )
    if status_filter:
        query = query.where(VideoChatSession.status == status_filter)
    items = db.scalars(query).all()
    visible_items = [
        item
        for item in items
        if item.meeting_id is None
        or (item.meeting is not None and is_participant(user, item.meeting))
    ]
    return VideoChatSessionListResponse(
        items=[_serialize(item) for item in visible_items],
        total=len(visible_items),
    )


def create_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    payload: VideoChatSessionCreateRequest,
) -> VideoChatSessionOut:
    settings = _settings()
    _require_enabled(settings)
    _load_meeting_for_session(
        db,
        workspace=workspace,
        user=user,
        meeting_id=payload.meeting_id,
    )
    session_id = new_id()
    title = (payload.title or "").strip() or "Video chat"
    session = VideoChatSession(
        id=session_id,
        workspace_id=workspace.id,
        meeting_id=payload.meeting_id,
        room_name=_room_name(settings=settings, workspace=workspace, session_id=session_id),
        title=title,
        started_by_id=user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    session.started_by = user
    return _serialize(session)


def get_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
) -> VideoChatSessionOut:
    _require_enabled(_settings())
    session = _load_session(db, workspace=workspace, session_id=session_id)
    _ensure_session_access(db, workspace=workspace, user=user, session=session)
    return _serialize(session)


def create_join_token(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
    request_host: str | None = None,
) -> VideoChatJoinTokenResponse:
    settings = _settings()
    _require_enabled(settings)
    _require_livekit_configured(settings)
    session = _load_session(db, workspace=workspace, session_id=session_id)
    if session.status != "open":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="video_chat.session_closed",
        )
    _ensure_session_access(db, workspace=workspace, user=user, session=session)

    identity = f"{workspace.id}:{user.id}:{new_id()}"
    display_name = _display_name(user)
    expires_at = _utcnow() + timedelta(seconds=settings.video_chat_token_ttl_seconds)
    token = create_livekit_join_token(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        identity=identity,
        display_name=display_name,
        room_name=session.room_name,
        ttl_seconds=settings.video_chat_token_ttl_seconds,
    )
    return VideoChatJoinTokenResponse(
        session=_serialize(session),
        livekit_url=_livekit_url_for_browser(
            settings=settings,
            request_host=request_host,
        ),
        token=token,
        identity=identity,
        display_name=display_name,
        expires_at=expires_at,
    )


def end_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
) -> VideoChatSessionOut:
    _require_enabled(_settings())
    session = _load_session(db, workspace=workspace, session_id=session_id)
    _ensure_session_access(db, workspace=workspace, user=user, session=session)
    _ensure_session_host(user=user, session=session)
    if session.status != "ended":
        now = _utcnow()
        session.status = "ended"
        session.ended_at = now
        session.updated_at = now
        db.add(session)
        db.commit()
        db.refresh(session)
    return _serialize(session)


def start_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
) -> VideoChatSessionOut:
    settings = _settings()
    _require_enabled(settings)
    if not settings.video_chat_recording_enabled:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="video_chat.recording_not_enabled",
        )
    if not settings.livekit_egress_api_url.strip():
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="video_chat.egress_not_configured",
        )
    session = _load_session(db, workspace=workspace, session_id=session_id)
    _ensure_session_access(db, workspace=workspace, user=user, session=session)
    return _serialize(session)


def stop_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
) -> VideoChatSessionOut:
    _require_enabled(_settings())
    session = _load_session(db, workspace=workspace, session_id=session_id)
    _ensure_session_access(db, workspace=workspace, user=user, session=session)
    if session.recording_status not in {"recording", "starting"}:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="video_chat.recording_not_active",
        )
    return _serialize(session)


def start_captions(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
) -> VideoChatSessionOut:
    settings = _settings()
    _require_enabled(settings)
    if not settings.video_chat_captions_enabled:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="video_chat.captions_not_enabled",
        )
    session = _load_session(db, workspace=workspace, session_id=session_id)
    _ensure_session_access(db, workspace=workspace, user=user, session=session)
    return _serialize(session)


def stop_captions(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: str,
) -> VideoChatSessionOut:
    _require_enabled(_settings())
    session = _load_session(db, workspace=workspace, session_id=session_id)
    _ensure_session_access(db, workspace=workspace, user=user, session=session)
    if session.captions_status not in {"on", "starting"}:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="video_chat.captions_not_active",
        )
    return _serialize(session)
