"""Service layer for the image-wizard feature.

Owns CRUD on `ImageGeneration`, brief composition via the chat LLM pool,
reference-image upload to MinIO, and Celery dispatch of the actual image
generation task.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from io import BytesIO
from typing import Any
from uuid import uuid4

from celery import Celery
from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.i18n import localized_http_exception
from aidoo_api.core.llm import LlmTaskContext, complete_chat
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import ensure_bucket, get_minio_client
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import NativeDoc, NativeDocPage
from aidoo_api.domains.docs.service import can_read_native_doc_for_rag
from aidoo_api.domains.images.models import ImageGeneration, utcnow_naive
from aidoo_api.domains.images.prompt import build_brief_messages
from aidoo_api.domains.images.schemas import (
    BriefRequest,
    BriefVersionOut,
    ImageDownloadResponse,
    ImageGenerationCreateRequest,
    ImageGenerationListResponse,
    ImageGenerationOut,
    ImageGenerationPatchRequest,
    ReferenceImageRole,
    ReferenceImageUploadOut,
)
from aidoo_api.domains.meeting.models import Meeting
from aidoo_api.domains.pms.access import can_read_issue_for_rag, has_list_access
from aidoo_api.domains.pms.models import Issue, TaskList


logger = logging.getLogger(__name__)


_VALID_ROLES: tuple[str, ...] = ("style", "composition", "content")
_VALID_KINDS: tuple[str, ...] = ("meeting", "task", "doc")
_BRIEF_TASK_KIND = "batch_generation"
_GENERATE_IMAGE_TASK_NAME = "images.generate_image"


# --- Helpers ---------------------------------------------------------------


def _require_enabled() -> None:
    if not get_settings().image_enabled:
        raise localized_http_exception(
            status_code=503,
            code="images.feature_disabled",
        )


def _load(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
    require_owner: bool = True,
) -> ImageGeneration:
    row = db.scalar(
        select(ImageGeneration).where(
            ImageGeneration.id == generation_id,
            ImageGeneration.workspace_id == workspace.id,
            ImageGeneration.trashed_at.is_(None),
        )
    )
    if row is None:
        raise localized_http_exception(status_code=404, code="images.not_found")
    if require_owner and row.owner_id != user.id:
        raise localized_http_exception(status_code=403, code="images.forbidden")
    return row


def _serialize(row: ImageGeneration) -> ImageGenerationOut:
    return ImageGenerationOut.model_validate(row, from_attributes=True)


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    celery_client = Celery(
        "aidoo_api_images",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )
    celery_client.conf.update(
        broker_connection_retry=False,
        broker_connection_retry_on_startup=False,
        broker_connection_max_retries=0,
        task_publish_retry=False,
        broker_transport_options={
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry_on_timeout": False,
        },
    )
    return celery_client


def _flatten_doc_text(pages: list[NativeDocPage], *, max_chars: int = 1500) -> str:
    """Flatten a doc's page blocks into plain text up to ``max_chars``."""
    parts: list[str] = []
    used = 0
    for page in pages:
        title = (page.title or "").strip()
        if title:
            parts.append(title)
            used += len(title) + 1
        for block in page.content_blocks or []:
            if not isinstance(block, dict):
                continue
            content = block.get("content")
            if not isinstance(content, list):
                continue
            for piece in content:
                if not isinstance(piece, dict):
                    continue
                text = piece.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                    used += len(text) + 1
                    if used >= max_chars:
                        return "\n".join(parts)[:max_chars]
    return "\n".join(parts)[:max_chars]


def _hydrate_context_refs(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    raw_refs: list[Any],
) -> list[dict[str, Any]]:
    """Refresh snapshot fields by re-loading the referenced entities."""
    hydrated: list[dict[str, Any]] = []
    for ref in raw_refs or []:
        if not isinstance(ref, dict):
            continue
        kind = str(ref.get("kind") or "").lower()
        ref_id = str(ref.get("id") or "")
        if kind not in _VALID_KINDS or not ref_id:
            continue
        accessible = False
        snapshot: dict[str, Any] = {}
        if kind == "meeting":
            meeting = db.scalar(
                select(Meeting).where(
                    Meeting.id == ref_id,
                    Meeting.workspace_id == workspace.id,
                )
            )
            if meeting is not None:
                accessible = True
                snapshot = {
                    "title": meeting.title,
                    "agenda": meeting.agenda,
                    "summary": meeting.agenda,
                }
        elif kind == "doc":
            if not can_read_native_doc_for_rag(db, user=user, doc_id=ref_id):
                continue
            doc = db.scalar(
                select(NativeDoc).where(
                    NativeDoc.id == ref_id,
                    NativeDoc.workspace_id == workspace.id,
                    NativeDoc.trashed_at.is_(None),
                )
            )
            if doc is not None:
                accessible = True
                pages = list(
                    db.scalars(
                        select(NativeDocPage)
                        .where(
                            NativeDocPage.doc_id == doc.id,
                            NativeDocPage.trashed_at.is_(None),
                        )
                        .order_by(NativeDocPage.sort_order.asc())
                        .limit(5)
                    )
                )
                snapshot = {
                    "title": doc.title,
                    "body": _flatten_doc_text(pages),
                }
        elif kind == "task":
            # ref_id may target either a TaskList or an Issue. Try TaskList
            # first; fall back to Issue.
            tlist = db.scalar(
                select(TaskList)
                .join(Team, Team.id == TaskList.team_id)
                .where(
                    TaskList.id == ref_id,
                    Team.workspace_id == workspace.id,
                    Team.active.is_(True),
                    Team.trashed_at.is_(None),
                )
            )
            if tlist is not None:
                if not has_list_access(db, user, tlist.id):
                    continue
                accessible = True
                issues = list(
                    db.scalars(
                        select(Issue)
                        .where(Issue.list_id == tlist.id, Issue.archived.is_(False))
                        .order_by(Issue.created_at.desc())
                        .limit(15)
                    )
                )
                snapshot = {
                    "title": tlist.name,
                    "description": tlist.description,
                    "status": tlist.status,
                    "issues": [
                        f"[{issue.status}] {issue.title}" for issue in issues
                    ],
                }
            else:
                issue = db.scalar(
                    select(Issue)
                    .join(TaskList, TaskList.id == Issue.list_id)
                    .join(Team, Team.id == TaskList.team_id)
                    .where(
                        Issue.id == ref_id,
                        Issue.archived.is_(False),
                        Team.workspace_id == workspace.id,
                        Team.active.is_(True),
                        Team.trashed_at.is_(None),
                    )
                )
                if issue is not None:
                    if not can_read_issue_for_rag(db, user=user, issue_id=issue.id):
                        continue
                    accessible = True
                    snapshot = {
                        "title": issue.title,
                        "status": issue.status,
                        "description": issue.description,
                    }

        if not accessible:
            continue

        # Merge user-supplied snapshot values in case the user already passed
        # title/summary fields the LLM should see.
        user_snapshot = ref.get("snapshot") or {}
        if isinstance(user_snapshot, dict):
            for key in ("title", "summary"):
                value = user_snapshot.get(key)
                if isinstance(value, str) and value.strip() and not snapshot.get(key):
                    snapshot[key] = value.strip()
        hydrated.append({"kind": kind, "id": ref_id, "snapshot": snapshot})
    return hydrated


def _ref_storage_key(generation_id: str) -> str:
    return f"images/refs/{generation_id}/{uuid4().hex}"


def _is_owned_ref_key(row: ImageGeneration, key: str) -> bool:
    return key.startswith(f"images/refs/{row.id}/")


def _is_owned_result_key(row: ImageGeneration, key: str) -> bool:
    return key == f"images/results/{row.workspace_id}/{row.id}.png"


def _owned_reference_count(row: ImageGeneration) -> int:
    return sum(
        1
        for ref in row.reference_image_keys or []
        if isinstance(ref, dict)
        and isinstance(ref.get("storage_key"), str)
        and _is_owned_ref_key(row, ref["storage_key"])
    )


def _mark_brief_drafting(row: ImageGeneration) -> None:
    if row.brief_status == "ready":
        row.brief_status = "drafting"


# --- CRUD ------------------------------------------------------------------


def create_generation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    payload: ImageGenerationCreateRequest,
) -> ImageGenerationOut:
    _require_enabled()
    row = ImageGeneration(
        id=new_id(),
        workspace_id=workspace.id,
        owner_id=user.id,
        use_case=payload.use_case,
        use_case_other=payload.use_case_other,
        style=payload.style.model_dump(),
        layout=payload.layout.model_dump(),
        details=payload.details.model_dump(),
        context_refs=[ref.model_dump() for ref in payload.context_refs],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


def patch_generation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
    payload: ImageGenerationPatchRequest,
) -> ImageGenerationOut:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.brief_status == "approved":
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")
    if payload.use_case is not None:
        row.use_case = payload.use_case
        _mark_brief_drafting(row)
    if payload.use_case_other is not None:
        row.use_case_other = payload.use_case_other
        _mark_brief_drafting(row)
    if payload.style is not None:
        row.style = payload.style.model_dump()
        _mark_brief_drafting(row)
    if payload.layout is not None:
        row.layout = payload.layout.model_dump()
        _mark_brief_drafting(row)
    if payload.details is not None:
        row.details = payload.details.model_dump()
        _mark_brief_drafting(row)
    if payload.context_refs is not None:
        row.context_refs = [ref.model_dump() for ref in payload.context_refs]
        _mark_brief_drafting(row)
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


def get_generation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> ImageGenerationOut:
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    return _serialize(row)


def list_generations(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    limit: int = 20,
    image_status: str | None = None,
    use_case: str | None = None,
) -> ImageGenerationListResponse:
    _require_enabled()
    limit = max(1, min(100, limit))
    stmt = (
        select(ImageGeneration)
        .where(
            ImageGeneration.workspace_id == workspace.id,
            ImageGeneration.owner_id == user.id,
            ImageGeneration.trashed_at.is_(None),
        )
        .order_by(ImageGeneration.created_at.desc())
        .limit(limit + 1)
    )
    if image_status:
        stmt = stmt.where(ImageGeneration.image_status == image_status)
    if use_case:
        stmt = stmt.where(ImageGeneration.use_case == use_case)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > limit
    items = rows[:limit]
    return ImageGenerationListResponse(
        items=[_serialize(row) for row in items],
        next_cursor="more" if has_more else None,
    )


def delete_generation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> None:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    settings = get_settings()
    client = get_minio_client()
    keys: list[str] = []
    for ref in row.reference_image_keys or []:
        if isinstance(ref, dict):
            key = ref.get("storage_key")
            if isinstance(key, str) and _is_owned_ref_key(row, key):
                keys.append(key)
    if row.image_storage_key and _is_owned_result_key(row, row.image_storage_key):
        keys.append(row.image_storage_key)
    for key in keys:
        try:
            client.remove_object(settings.minio_bucket, key)
        except Exception:
            logger.warning("images.delete: failed to remove object %s", key, exc_info=True)
    row.trashed_at = utcnow_naive()
    db.add(row)
    db.commit()


# --- Reference images ------------------------------------------------------


def upload_reference_image(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
    role: ReferenceImageRole,
    content_type: str,
    data: bytes,
    original_name: str,
) -> ReferenceImageUploadOut:
    _require_enabled()
    settings = get_settings()
    if role not in _VALID_ROLES:
        raise localized_http_exception(status_code=422, code="images.invalid_role")
    if len(data) <= 0:
        raise localized_http_exception(status_code=422, code="images.empty_upload")
    if len(data) > settings.image_reference_max_bytes:
        raise localized_http_exception(status_code=413, code="images.upload_too_large")
    if not (content_type or "").startswith("image/"):
        raise localized_http_exception(status_code=422, code="images.invalid_content_type")

    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.brief_status == "approved":
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")
    refs = [
        ref
        for ref in row.reference_image_keys or []
        if isinstance(ref, dict)
        and isinstance(ref.get("storage_key"), str)
        and _is_owned_ref_key(row, ref["storage_key"])
    ]
    if _owned_reference_count(row) >= settings.image_max_reference_uploads:
        raise localized_http_exception(status_code=409, code="images.too_many_refs")

    ensure_bucket()
    storage_key = _ref_storage_key(row.id)
    try:
        get_minio_client().put_object(
            settings.minio_bucket,
            storage_key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
    except Exception as exc:
        logger.exception("images.upload_reference: storage put failed")
        raise localized_http_exception(status_code=502, code="images.upload_failed") from exc

    entry = {
        "storage_key": storage_key,
        "role": role,
        "content_type": content_type,
        "size_bytes": len(data),
        "original_name": original_name[:200],
    }
    refs.append(entry)
    row.reference_image_keys = refs
    _mark_brief_drafting(row)
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    return ReferenceImageUploadOut(**entry)


def delete_reference_image(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
    storage_key: str,
) -> None:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.brief_status == "approved":
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")
    refs = list(row.reference_image_keys or [])
    new_refs = [
        ref for ref in refs if not (isinstance(ref, dict) and ref.get("storage_key") == storage_key)
    ]
    if len(new_refs) == len(refs):
        raise localized_http_exception(status_code=404, code="images.ref_not_found")
    row.reference_image_keys = new_refs
    _mark_brief_drafting(row)
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    settings = get_settings()
    if _is_owned_ref_key(row, storage_key):
        try:
            get_minio_client().remove_object(settings.minio_bucket, storage_key)
        except Exception:
            logger.warning(
                "images.delete_reference: failed to remove object %s", storage_key, exc_info=True
            )


# --- Brief generation ------------------------------------------------------


def generate_brief(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
    payload: BriefRequest,
) -> BriefVersionOut:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.brief_status == "approved":
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")

    edit_instruction = (payload.edit_instruction or "").strip() or None
    versions = list(row.brief_versions or [])
    prior_brief: str | None = None
    if edit_instruction and versions:
        last = versions[-1]
        if isinstance(last, dict):
            prior_brief = str(last.get("text") or "").strip() or None

    hydrated = _hydrate_context_refs(
        db, workspace=workspace, user=user, raw_refs=row.context_refs or []
    )
    reference_image_count = len(row.reference_image_keys or [])
    messages = build_brief_messages(
        use_case=row.use_case,
        use_case_other=row.use_case_other,
        style=row.style or {},
        layout=row.layout or {},
        details=row.details or {},
        context_refs=hydrated,
        reference_image_count=reference_image_count,
        prior_brief=prior_brief,
        edit_instruction=edit_instruction,
    )

    context = LlmTaskContext(
        source="images.brief",
        actor_user_id=user.id,
        workspace_id=workspace.id,
        task_kind=_BRIEF_TASK_KIND,
    )
    try:
        response, _decision, _config = complete_chat(
            context,
            db,
            messages=messages,
            temperature=0.4,
            max_tokens=1500,
            reasoning_effort="none",
        )
    except OpenAIError as exc:
        logger.warning("images.brief: LLM error: %s", exc)
        raise localized_http_exception(
            status_code=502,
            code="images.brief_failed",
        ) from exc

    text = ""
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str):
            text = content.strip()
    if not text:
        raise localized_http_exception(status_code=502, code="images.brief_empty")

    new_entry = {
        "text": text,
        "created_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "edit_instruction": edit_instruction,
    }
    versions.append(new_entry)
    row.brief_versions = versions
    row.brief_status = "ready"
    # Re-running brief regenerates the context_refs snapshots so they're fresh
    # for the eventual image generation step too.
    row.context_refs = hydrated
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    return BriefVersionOut(
        text=text,
        created_at=datetime.fromisoformat(new_entry["created_at"]),
        edit_instruction=edit_instruction,
    )


# --- Approve + dispatch ----------------------------------------------------


def approve_and_dispatch(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> ImageGenerationOut:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if not (row.brief_versions or []):
        raise localized_http_exception(status_code=409, code="images.brief_not_ready")
    if row.image_status in {"queued", "running"}:
        raise localized_http_exception(status_code=409, code="images.already_running")
    if row.brief_status == "approved" and row.image_status != "failed":
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")
    if row.brief_status not in {"ready", "approved"}:
        raise localized_http_exception(status_code=409, code="images.brief_not_ready")

    row.brief_status = "approved"
    row.image_status = "queued"
    row.failure_reason = None
    row.approved_at = utcnow_naive()
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()

    try:
        async_result = _get_celery_client().send_task(
            _GENERATE_IMAGE_TASK_NAME,
            args=[row.id],
            queue="meeting_transcribe",
        )
        row.celery_task_id = getattr(async_result, "id", None)
        db.add(row)
        db.commit()
    except Exception as exc:
        logger.exception("images.approve: failed to dispatch celery task")
        row.image_status = "failed"
        row.failure_reason = f"dispatch failed: {exc}"[:500]
        row.updated_at = utcnow_naive()
        db.add(row)
        db.commit()
        raise localized_http_exception(
            status_code=502, code="images.dispatch_failed"
        ) from exc

    db.refresh(row)
    return _serialize(row)


# --- Download --------------------------------------------------------------


def presign_download(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> ImageDownloadResponse:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.image_status != "succeeded" or not row.image_storage_key:
        raise localized_http_exception(status_code=409, code="images.not_ready")
    settings = get_settings()
    expires = timedelta(minutes=15)
    url = get_minio_client().presigned_get_object(
        settings.minio_bucket,
        row.image_storage_key,
        expires=expires,
    )
    return ImageDownloadResponse(
        url=url,
        expires_at=utcnow_naive() + expires,
    )
