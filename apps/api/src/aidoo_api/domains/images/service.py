"""Service layer for the image-wizard feature.

Owns CRUD on `ImageGeneration`, brief composition via the OpenAI Agents SDK,
reference-image upload to MinIO, and Celery dispatch of the actual image
generation task.
"""

from __future__ import annotations

import logging
import os
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
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import ensure_bucket, get_minio_client
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import NativeDoc, NativeDocPage
from aidoo_api.domains.docs.service import can_read_native_doc_for_rag
from aidoo_api.domains.images.models import ImageGeneration, utcnow_naive
from aidoo_api.domains.images.prompt import (
    BRIEF_SYSTEM_PROMPT,
    build_direct_edit_prompt,
    build_brief_messages,
    sanitize_image_plan_text,
)
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
from aidoo_api.domains.meeting.service import can_read_meeting_for_rag
from aidoo_api.domains.pms.access import can_read_issue_for_rag, has_list_access
from aidoo_api.domains.pms.models import Issue, TaskList


logger = logging.getLogger(__name__)


_VALID_ROLES: tuple[str, ...] = ("style", "composition", "content")
_VALID_KINDS: tuple[str, ...] = ("meeting", "task", "doc")
_IMAGE_GENERATION_QUEUE = "image_generation"
_ALLOWED_REFERENCE_CONTENT_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/webp",
)
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


def _image_api_key() -> str:
    settings = get_settings()
    return settings.image_api_key.strip() or os.environ.get("OPENAI_API_KEY", "").strip()


def _brief_input_from_messages(messages: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for message in messages:
        if message.get("role") == "system":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            blocks.append(content)
    return "\n\n".join(blocks).strip()


def _extract_agent_text(result: Any) -> str:
    final_output = getattr(result, "final_output", None)
    if isinstance(final_output, str):
        return final_output.strip()
    if final_output is not None:
        return str(final_output).strip()
    return ""


def _run_brief_agent(
    *,
    input_text: str,
    model: str,
    api_key: str,
    base_url: str,
    workspace_id: str,
    user_id: str,
    generation_id: str,
) -> Any:
    # Local import so DB-only tests can import the service without initializing
    # the SDK until the image feature is actually used.
    from agents import Agent, ModelSettings, OpenAIProvider, RunConfig, Runner

    agent = Agent(
        name="image-brief-designer",
        instructions=BRIEF_SYSTEM_PROMPT,
        model=model,
        model_settings=ModelSettings(max_tokens=2200),
    )
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key=api_key, base_url=base_url),
        workflow_name="AIDOO Image Plan",
        trace_metadata={
            "source": "images.brief",
            "workspace_id": workspace_id,
            "actor_user_id": user_id,
            "generation_id": generation_id,
        },
    )
    return Runner.run_sync(
        agent,
        input=input_text,
        max_turns=1,
        run_config=run_config,
    )


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
            if not can_read_meeting_for_rag(
                db,
                user=user,
                workspace_id=workspace.id,
                meeting_id=ref_id,
            ):
                continue
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


def _detect_reference_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise localized_http_exception(status_code=422, code="images.invalid_content_type")


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
        template_id=payload.template_id,
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
    if "template_id" in payload.model_fields_set:
        row.template_id = payload.template_id or None
        _mark_brief_drafting(row)
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
    detected_content_type = _detect_reference_content_type(data)
    declared_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if (
        declared_content_type
        and declared_content_type != "application/octet-stream"
        and declared_content_type not in _ALLOWED_REFERENCE_CONTENT_TYPES
    ):
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
            content_type=detected_content_type,
        )
    except Exception as exc:
        logger.exception("images.upload_reference: storage put failed")
        raise localized_http_exception(status_code=502, code="images.upload_failed") from exc

    entry = {
        "storage_key": storage_key,
        "role": role,
        "content_type": detected_content_type,
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
        template_name=row.template_id or None,
        prior_brief=prior_brief,
        edit_instruction=edit_instruction,
    )

    settings = get_settings()
    api_key = _image_api_key()
    if not api_key:
        raise localized_http_exception(status_code=502, code="images.brief_failed")

    try:
        response = _run_brief_agent(
            input_text=_brief_input_from_messages(messages),
            model=settings.image_supervisor_model,
            api_key=api_key,
            base_url=settings.image_base_url,
            workspace_id=workspace.id,
            user_id=user.id,
            generation_id=row.id,
        )
    except OpenAIError as exc:
        logger.warning("images.brief: OpenAI SDK error: %s", exc)
        raise localized_http_exception(
            status_code=502,
            code="images.brief_failed",
        ) from exc
    except Exception as exc:
        logger.warning("images.brief: Agents SDK error", exc_info=True)
        raise localized_http_exception(
            status_code=502,
            code="images.brief_failed",
        ) from exc

    text = sanitize_image_plan_text(_extract_agent_text(response))
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


def _prepare_direct_edit_brief(row: ImageGeneration) -> None:
    """Create an internal prompt for edit jobs that intentionally skip review."""

    if row.brief_versions:
        return
    details = row.details if isinstance(row.details, dict) else {}
    if details.get("source_image_requires_plan"):
        return
    source_generation_id = str(details.get("source_generation_id") or "").strip()
    edit_instruction = str(details.get("source_image_edit_instruction") or "").strip()
    if not source_generation_id or not edit_instruction:
        return
    text = build_direct_edit_prompt(
        edit_instruction=edit_instruction,
        style=row.style or {},
    )
    if not text:
        return
    row.brief_versions = [
        {
            "text": text,
            "created_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "edit_instruction": edit_instruction,
            "internal": True,
        }
    ]
    row.brief_status = "ready"


def approve_and_dispatch(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> ImageGenerationOut:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    _prepare_direct_edit_brief(row)
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
            queue=_IMAGE_GENERATION_QUEUE,
        )
        row.celery_task_id = getattr(async_result, "id", None)
        db.add(row)
        db.commit()
    except Exception as exc:
        logger.exception("images.approve: failed to dispatch celery task")
        row.image_status = "failed"
        row.failure_reason = "Dispatch failed"
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
    if not _is_owned_result_key(row, row.image_storage_key):
        logger.warning(
            "images.download: refusing unexpected result key generation=%s key=%s",
            row.id,
            row.image_storage_key,
        )
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


def read_result_image(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> tuple[bytes, str]:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.image_status != "succeeded" or not row.image_storage_key:
        raise localized_http_exception(status_code=409, code="images.not_ready")
    if not _is_owned_result_key(row, row.image_storage_key):
        logger.warning(
            "images.download: refusing unexpected result key generation=%s key=%s",
            row.id,
            row.image_storage_key,
        )
        raise localized_http_exception(status_code=409, code="images.not_ready")

    settings = get_settings()
    try:
        response = get_minio_client().get_object(
            settings.minio_bucket,
            row.image_storage_key,
        )
        try:
            return response.read(), "image/png"
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass
    except Exception as exc:
        logger.warning("images.download: storage read failed for %s", row.id, exc_info=True)
        raise localized_http_exception(status_code=409, code="images.not_ready") from exc
