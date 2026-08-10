"""Service layer for the image-wizard feature."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.images.agent_runtime import (
    ImageBriefRuntimeResult,
    ImageRuntimeConfigurationError,
    ImageRuntimeProviderError,
    select_image_agent_runtime_adapter,
)
from open_work_hub_api.domains.images.context_ref_hydration import hydrate_context_refs
from open_work_hub_api.domains.images.execution_profile import (
    build_image_execution_profile as build_image_execution_profile_payload,
)
from open_work_hub_api.domains.images.model_settings_service import (
    ImageModelSettingsError,
    ResolvedImageExecution,
    resolve_active_image_execution,
)
from open_work_hub_api.domains.images.generation_jobs import (
    dispatch_image_generation,
    revoke_image_generation,
)
from open_work_hub_api.domains.images.models import ImageGeneration, utcnow_naive
from open_work_hub_api.domains.images.prompt import (
    build_direct_edit_prompt,
    build_brief_messages,
    sanitize_image_plan_text,
)
from open_work_hub_api.domains.images.reference_images import (
    ReferenceImagePolicy,
    VALID_REFERENCE_ROLES,
    detect_reference_content_type,
    is_allowed_declared_reference_content_type,
)
from open_work_hub_api.domains.images.schemas import (
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
from open_work_hub_api.domains.images.storage import (
    RESULT_IMAGE_CONTENT_TYPE,
    presign_image_object,
    put_reference_image_object,
    read_image_object,
    remove_image_objects,
)


logger = logging.getLogger(__name__)


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


def build_image_execution_profile(
    db: Session,
    row: ImageGeneration,
    *,
    resolved: ResolvedImageExecution | None = None,
) -> dict[str, object]:
    settings = get_settings()
    execution = resolved or resolve_active_image_execution(db, settings=settings)
    return build_image_execution_profile_payload(
        row,
        execution,
        max_reference_uploads=settings.image_max_reference_uploads,
    )


def brief_input_from_messages(messages: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for message in messages:
        if message.get("role") == "system":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            blocks.append(content)
    return "\n\n".join(blocks).strip()


def run_brief_agent(
    *,
    provider_id: str,
    adapter_id: str | None = None,
    input_text: str,
    model: str,
    api_key: str,
    base_url: str,
    workspace_id: str,
    user_id: str,
    generation_id: str,
    enable_web_search: bool,
    execution_profile: dict[str, object] | None = None,
    db: Session | None = None,
) -> ImageBriefRuntimeResult:
    adapter = select_image_agent_runtime_adapter(provider_id, adapter_id=adapter_id)
    return adapter.run_brief(
        input_text=input_text,
        model=model,
        api_key=api_key,
        base_url=base_url,
        workspace_id=workspace_id,
        user_id=user_id,
        generation_id=generation_id,
        enable_web_search=enable_web_search,
        execution_profile=execution_profile,
        db=db,
    )


def _reference_policy(row: ImageGeneration) -> ReferenceImagePolicy:
    return ReferenceImagePolicy(generation_id=row.id, workspace_id=row.workspace_id)


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
    if payload.is_template:
        raise localized_http_exception(status_code=409, code="images.not_ready")
    row = ImageGeneration(
        id=new_id(),
        workspace_id=workspace.id,
        owner_id=user.id,
        template_id=payload.template_id,
        is_template=payload.is_template,
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
    mutable_prompt_fields = set(payload.model_fields_set) - {"is_template"}
    if row.brief_status == "approved" and mutable_prompt_fields:
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")
    if "is_template" in payload.model_fields_set and payload.is_template is not None:
        if payload.is_template and (
            row.image_status != "succeeded" or not row.image_storage_key
        ):
            raise localized_http_exception(status_code=409, code="images.not_ready")
        row.is_template = payload.is_template
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


def set_generation_template(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
    is_template: bool,
) -> ImageGenerationOut:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if is_template and (row.image_status != "succeeded" or not row.image_storage_key):
        raise localized_http_exception(status_code=409, code="images.not_ready")
    row.is_template = is_template
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
    is_template: bool | None = None,
    has_image_activity: bool | None = None,
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
    if is_template is not None:
        stmt = stmt.where(ImageGeneration.is_template.is_(is_template))
    if has_image_activity is not None:
        active_statuses = ("queued", "running", "succeeded", "failed", "cancelled")
        if has_image_activity:
            stmt = stmt.where(ImageGeneration.image_status.in_(active_statuses))
        else:
            stmt = stmt.where(ImageGeneration.image_status == "idle")
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
    keys = _reference_policy(row).owned_object_keys(
        row.reference_image_keys,
        row.image_storage_key,
    )
    for failure in remove_image_objects(keys):
        logger.warning(
            "images.delete: failed to remove object %s",
            failure.storage_key,
            exc_info=failure.exc,
        )
    row.trashed_at = utcnow_naive()
    db.add(row)
    db.commit()


def cancel_generation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generation_id: str,
) -> ImageGenerationOut:
    _require_enabled()
    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.image_status == "cancelled":
        return _serialize(row)
    if row.image_status not in {"queued", "running"}:
        raise localized_http_exception(status_code=409, code="images.not_running")

    celery_task_id = row.celery_task_id
    row.image_status = "cancelled"
    row.failure_reason = "Cancelled by user"
    row.celery_task_id = None
    row.completed_at = utcnow_naive()
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()

    if celery_task_id:
        try:
            revoke_image_generation(celery_task_id)
        except Exception:
            logger.warning(
                "images.cancel: failed to revoke celery task generation=%s task=%s",
                row.id,
                celery_task_id,
                exc_info=True,
            )

    db.refresh(row)
    return _serialize(row)


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
    if role not in VALID_REFERENCE_ROLES:
        raise localized_http_exception(status_code=422, code="images.invalid_role")
    if len(data) <= 0:
        raise localized_http_exception(status_code=422, code="images.empty_upload")
    if len(data) > settings.image_reference_max_bytes:
        raise localized_http_exception(status_code=413, code="images.upload_too_large")
    detected_content_type = detect_reference_content_type(data)
    if detected_content_type is None:
        raise localized_http_exception(status_code=422, code="images.invalid_content_type")
    if not is_allowed_declared_reference_content_type(content_type):
        raise localized_http_exception(status_code=422, code="images.invalid_content_type")

    row = _load(db, workspace=workspace, user=user, generation_id=generation_id)
    if row.brief_status == "approved":
        raise localized_http_exception(status_code=409, code="images.locked_after_approval")
    policy = _reference_policy(row)
    refs = policy.owned_reference_entries(row.reference_image_keys)
    if len(refs) >= settings.image_max_reference_uploads:
        raise localized_http_exception(status_code=409, code="images.too_many_refs")

    storage_key = policy.reference_storage_key()
    try:
        put_reference_image_object(
            storage_key=storage_key,
            data=data,
            content_type=detected_content_type,
        )
    except Exception as exc:
        logger.exception("images.upload_reference: storage put failed")
        raise localized_http_exception(status_code=502, code="images.upload_failed") from exc

    entry = policy.reference_entry(
        storage_key=storage_key,
        role=role,
        content_type=detected_content_type,
        size_bytes=len(data),
        original_name=original_name,
    )
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
    if _reference_policy(row).is_owned_reference_key(storage_key):
        failures = remove_image_objects([storage_key])
        if failures:
            logger.warning(
                "images.delete_reference: failed to remove object %s",
                storage_key,
                exc_info=failures[0].exc,
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

    hydrated = hydrate_context_refs(
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
        current_date=datetime.now(UTC).date().isoformat(),
        prior_brief=prior_brief,
        edit_instruction=edit_instruction,
    )

    settings = get_settings()

    try:
        resolved = resolve_active_image_execution(db, settings=settings)
        execution_profile = build_image_execution_profile(db, row, resolved=resolved)
        response = run_brief_agent(
            provider_id=resolved.provider_id,
            adapter_id=resolved.adapter_id,
            input_text=brief_input_from_messages(messages),
            model=resolved.supervisor_model_id,
            api_key=(resolved.api_key.get_secret_value() if resolved.api_key else ""),
            base_url=resolved.endpoint_url,
            workspace_id=workspace.id,
            user_id=user.id,
            generation_id=row.id,
            enable_web_search=resolved.brief_web_search_enabled,
            execution_profile=execution_profile,
            db=db,
        )
    except ImageModelSettingsError as exc:
        logger.warning("images.brief: image model settings error: %s", exc.code)
        raise localized_http_exception(
            status_code=503,
            code=exc.code,
            **exc.context,
        ) from exc
    except ImageRuntimeConfigurationError as exc:
        logger.warning("images.brief: image runtime configuration error: %s", exc)
        raise localized_http_exception(
            status_code=502,
            code="images.brief_failed",
        ) from exc
    except ImageRuntimeProviderError as exc:
        logger.warning("images.brief: provider runtime error: %s", exc)
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

    text = sanitize_image_plan_text(response.text)
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
    try:
        row.image_execution_profile = build_image_execution_profile(db, row)
    except ImageModelSettingsError as exc:
        raise localized_http_exception(
            status_code=503,
            code=exc.code,
            **exc.context,
        ) from exc
    row.failure_reason = None
    row.approved_at = utcnow_naive()
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()

    try:
        row.celery_task_id = dispatch_image_generation(row.id)
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
    if not _reference_policy(row).is_owned_result_key(row.image_storage_key):
        logger.warning(
            "images.download: refusing unexpected result key generation=%s key=%s",
            row.id,
            row.image_storage_key,
        )
        raise localized_http_exception(status_code=409, code="images.not_ready")
    expires = timedelta(minutes=15)
    url = presign_image_object(storage_key=row.image_storage_key, expires=expires)
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
    if not _reference_policy(row).is_owned_result_key(row.image_storage_key):
        logger.warning(
            "images.download: refusing unexpected result key generation=%s key=%s",
            row.id,
            row.image_storage_key,
        )
        raise localized_http_exception(status_code=409, code="images.not_ready")

    try:
        return read_image_object(row.image_storage_key), RESULT_IMAGE_CONTENT_TYPE
    except Exception as exc:
        logger.warning("images.download: storage read failed for %s", row.id, exc_info=True)
        raise localized_http_exception(status_code=409, code="images.not_ready") from exc
