"""Worker task: drive image generation through the image runtime adapter registry.

Triggered by ``POST /workspaces/{slug}/images/generations/{id}/approve``. The
runtime adapter receives the approved brief + reference images (if any) and
emits one image. We persist the bytes to MinIO and update the row.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, uuid5

from celery.exceptions import Ignore
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.runtime import (
    db_session as _db_session,
    ensure_api_src_on_path as _ensure_api_src_on_path,
    minio_client as _minio_client,
    workspace_root as _workspace_root,
)
from open_work_hub_worker.settings import get_settings


_ensure_api_src_on_path()

from open_work_hub_api.domains.images.models import ImageGeneration  # noqa: E402
from open_work_hub_api.domains.images.agent_runtime import (  # noqa: E402
    ImageGenerationRuntimeResult,
    ImageRuntimeConfigurationError,
    select_image_agent_runtime_adapter,
)
from open_work_hub_api.domains.images.execution_profile import (  # noqa: E402
    image_execution_requested_options,
)
from open_work_hub_api.domains.images.model_settings_service import (  # noqa: E402
    ImageModelSettingsError,
    ResolvedImageExecution,
    resolve_profiled_image_execution,
)
from open_work_hub_api.domains.images.prompt import sanitize_image_plan_text  # noqa: E402
from open_work_hub_api.domains.images.template_catalog import (  # noqa: E402
    get_builtin_template,
    get_user_template_source_id,
)
from open_work_hub_api.domains.auth.models import User, Workspace  # noqa: E402
from open_work_hub_api.domains.pms.models import Notification  # noqa: E402


logger = logging.getLogger(__name__)


_ALLOWED_REFERENCE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_image_execution(
    session: Session,
    row: ImageGeneration,
    settings: Any,
) -> tuple[ResolvedImageExecution, dict[str, Any]]:
    execution_profile = dict(row.image_execution_profile or {})
    resolved = resolve_profiled_image_execution(
        session,
        execution_profile,
        settings=settings,
    )
    return resolved, execution_profile


def _load(session: Session, generation_id: str) -> ImageGeneration | None:
    row = session.get(ImageGeneration, generation_id)
    if row is None or row.trashed_at is not None:
        return None
    return row


def _load_fresh(session: Session, generation_id: str) -> ImageGeneration | None:
    row = session.get(ImageGeneration, generation_id, populate_existing=True)
    if row is None or row.trashed_at is not None:
        return None
    return row


def _is_owned_ref_key(row: ImageGeneration, key: str) -> bool:
    return key.startswith(f"images/refs/{row.id}/")


def _is_owned_result_key(row: ImageGeneration, key: str) -> bool:
    return key == f"images/results/{row.workspace_id}/{row.id}.png"


def _remove_object(key: str) -> None:
    settings = get_settings()
    try:
        _minio_client().remove_object(settings.minio_bucket, key)
    except Exception:
        logger.warning("images.generate: failed to remove object %s", key, exc_info=True)


def _generation_action_url(session: Session, row: ImageGeneration) -> str:
    workspace = session.get(Workspace, row.workspace_id)
    params = {
        "gen": row.id,
        "step": "4",
    }
    if workspace is not None and workspace.key:
        params["workspace"] = workspace.key
    return f"/tool/image-wizard?{urlencode(params)}"


def _notification_copy(
    *,
    locale: str,
    outcome: str,
    reason: str | None = None,
) -> tuple[str, str]:
    if locale == "en-US":
        if outcome == "succeeded":
            return "Image generation finished", "Your generated image is ready."
        return (
            "Image generation failed",
            reason or "The image generation did not finish.",
        )
    if outcome == "succeeded":
        return "이미지 생성이 완료되었습니다", "생성된 이미지를 확인할 수 있습니다."
    return (
        "이미지 생성에 실패했습니다",
        reason or "이미지 생성이 완료되지 않았습니다.",
    )


def _notify_generation_finished(
    session: Session,
    row: ImageGeneration,
    *,
    outcome: str,
    reason: str | None = None,
) -> None:
    notification_id = str(uuid5(NAMESPACE_URL, f"open-work-hub:image-generation:{row.id}:{outcome}"))
    if session.get(Notification, notification_id) is not None:
        return
    user = session.get(User, row.owner_id)
    locale = str(getattr(user, "locale", None) or "ko-KR")
    title, body = _notification_copy(locale=locale, outcome=outcome, reason=reason)
    session.add(
        Notification(
            id=notification_id,
            user_id=row.owner_id,
            type=f"image_generation_{outcome}",
            title=title,
            body=body,
            reference_type="image_generation",
            reference_id=row.id,
            action_url=_generation_action_url(session, row),
        )
    )
    session.commit()


def _mark_failed(session: Session, generation_id: str, reason: str) -> None:
    session.rollback()
    row = _load_fresh(session, generation_id)
    if row is None:
        return
    if row.image_status == "cancelled":
        return
    row.image_status = "failed"
    row.failure_reason = (reason or "unknown error")[:500]
    row.celery_task_id = None
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    _notify_generation_finished(session, row, outcome="failed", reason=row.failure_reason)


def _mark_retrying(session: Session, generation_id: str, reason: str) -> None:
    session.rollback()
    row = _load_fresh(session, generation_id)
    if row is None:
        return
    if row.image_status == "cancelled":
        return
    row.image_status = "queued"
    row.failure_reason = (reason or "retrying")[:500]
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()


def _claim_generation(
    session: Session,
    *,
    generation_id: str,
    task_id: str | None,
) -> ImageGeneration | None:
    row = session.scalar(
        select(ImageGeneration).where(ImageGeneration.id == generation_id).with_for_update()
    )
    if row is None or row.trashed_at is not None:
        return None
    if row.image_status == "running":
        if task_id and row.celery_task_id == task_id:
            row.failure_reason = None
            row.updated_at = _utcnow()
            session.add(row)
            session.commit()
            return row
        return None
    if row.image_status != "queued":
        return None
    if row.celery_task_id and task_id and row.celery_task_id != task_id:
        logger.info(
            "images.generate: ignoring stale task generation=%s row_task=%s task=%s",
            generation_id,
            row.celery_task_id,
            task_id,
        )
        return None
    row.image_status = "running"
    row.celery_task_id = task_id or row.celery_task_id
    row.failure_reason = None
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    return row


def _download_reference_images(
    row: ImageGeneration,
) -> list[tuple[str, str, bytes]]:
    """Returns list of (role, content_type, bytes)."""
    settings = get_settings()
    client = _minio_client()
    out: list[tuple[str, str, bytes]] = []
    for ref in row.reference_image_keys or []:
        if not isinstance(ref, dict):
            continue
        key = ref.get("storage_key")
        if not isinstance(key, str) or not key:
            continue
        if not _is_owned_ref_key(row, key):
            logger.warning("images.generate: skipping foreign reference key %s", key)
            continue
        role = str(ref.get("role") or "style")
        content_type = str(ref.get("content_type") or "image/png")
        if content_type not in _ALLOWED_REFERENCE_CONTENT_TYPES:
            logger.warning("images.generate: skipping non-image reference %s", key)
            continue
        try:
            response = client.get_object(settings.minio_bucket, key)
            try:
                data = response.read(settings.image_reference_max_bytes + 1)
            finally:
                try:
                    response.close()
                    response.release_conn()
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("images.generate: failed to fetch reference %s: %s", key, exc)
            continue
        if len(data) > settings.image_reference_max_bytes:
            logger.warning("images.generate: skipping oversized reference %s", key)
            continue
        out.append((role, content_type, data))
        if len(out) >= settings.image_max_reference_uploads:
            break
    return out


def _download_result_image(row: ImageGeneration) -> bytes | None:
    if row.image_status != "succeeded" or not row.image_storage_key:
        return None
    if not _is_owned_result_key(row, row.image_storage_key):
        logger.warning(
            "images.generate: skipping unexpected template result key generation=%s key=%s",
            row.id,
            row.image_storage_key,
        )
        return None

    settings = get_settings()
    try:
        response = _minio_client().get_object(settings.minio_bucket, row.image_storage_key)
        try:
            return response.read(settings.image_reference_max_bytes + 1)
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass
    except Exception as exc:
        logger.warning(
            "images.generate: failed to fetch template result %s: %s",
            row.id,
            exc,
        )
        return None


def _load_template_reference_images(
    session: Session,
    row: ImageGeneration,
) -> list[tuple[str, str, bytes]]:
    template_id = str(row.template_id or "").strip()
    if not template_id:
        return []

    builtin = get_builtin_template(template_id)
    if builtin is not None:
        asset_path = _workspace_root() / "apps" / "web" / "public" / builtin.asset_path.lstrip("/")
        try:
            data = asset_path.read_bytes()
        except FileNotFoundError:
            logger.warning("images.generate: template sample missing: %s", asset_path)
            return []
        if len(data) > get_settings().image_reference_max_bytes:
            logger.warning("images.generate: template sample too large: %s", asset_path)
            return []
        return [("template composition", "image/png", data)]

    source_id = get_user_template_source_id(template_id)
    if source_id is None:
        return []
    source = session.get(ImageGeneration, source_id)
    if (
        source is None
        or source.trashed_at is not None
        or source.workspace_id != row.workspace_id
        or source.owner_id != row.owner_id
    ):
        return []
    data = _download_result_image(source)
    if not data or len(data) > get_settings().image_reference_max_bytes:
        return []
    return [("template composition", "image/png", data)]


async def run_image_agent(
    *,
    provider_id: str,
    adapter_id: str | None = None,
    brief_text: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    reference_images: list[tuple[str, str, bytes]],
    max_turns: int,
    supervisor_model: str,
    image_model: str,
    api_key: str,
    base_url: str,
    enable_web_search: bool,
    workspace_id: str = "unknown",
    user_id: str | None = None,
    generation_id: str | None = None,
    execution_profile: dict[str, object] | None = None,
    db: Session | None = None,
) -> ImageGenerationRuntimeResult:
    adapter = select_image_agent_runtime_adapter(provider_id, adapter_id=adapter_id)
    return await adapter.generate_image(
        brief_text=brief_text,
        style=style,
        layout=layout,
        reference_images=reference_images,
        max_turns=max_turns,
        supervisor_model=supervisor_model,
        image_model=image_model,
        api_key=api_key,
        base_url=base_url,
        enable_web_search=enable_web_search,
        workspace_id=workspace_id,
        user_id=user_id,
        generation_id=generation_id,
        execution_profile=execution_profile,
        db=db,
    )


@celery_app.task(
    name="images.generate_image",
    bind=True,
    acks_late=True,
    max_retries=2,
    task_time_limit=900,
    task_soft_time_limit=840,
)
def generate_image(self, generation_id: str) -> str:
    settings = get_settings()
    if not settings.image_enabled:
        logger.warning("images.generate: feature disabled, skipping %s", generation_id)
        with _db_session() as session:
            _mark_failed(session, generation_id, "Image generation feature is disabled")
        raise Ignore()

    session = _db_session()
    try:
        task_id = getattr(self.request, "id", None)
        row = _claim_generation(session, generation_id=generation_id, task_id=task_id)
        if row is None:
            raise Ignore()
        resolved, execution_profile = _resolve_image_execution(session, row, settings)
        if not row.image_execution_profile:
            row.image_execution_profile = execution_profile
            session.add(row)
            session.commit()
        requested_options = image_execution_requested_options(
            execution_profile,
            max_reference_uploads=settings.image_max_reference_uploads,
        )
        provider_id = resolved.provider_id
        adapter_id = resolved.adapter_id
        generation_model = resolved.generation_model_id
        planner_model = resolved.supervisor_model_id
        base_url = resolved.endpoint_url
        api_key = resolved.api_key.get_secret_value() if resolved.api_key else ""
        enable_web_search = resolved.generation_web_search_enabled
        max_iterations = resolved.max_iterations
        max_reference_uploads = int(requested_options["max_reference_uploads"])

        versions = list(row.brief_versions or [])
        if not versions:
            _mark_failed(session, generation_id, "Brief is empty")
            raise Ignore()
        last = versions[-1]
        brief_text = ""
        if isinstance(last, dict):
            brief_text = str(last.get("text") or "").strip()
        if not brief_text:
            _mark_failed(session, generation_id, "Brief text is empty")
            raise Ignore()
        brief_text = sanitize_image_plan_text(brief_text)
        if not brief_text:
            _mark_failed(session, generation_id, "Image plan is empty")
            raise Ignore()

        reference_images = [
            *_load_template_reference_images(session, row),
            *_download_reference_images(row),
        ][:max_reference_uploads]

        result = asyncio.run(
            asyncio.wait_for(
                run_image_agent(
                    provider_id=provider_id,
                    adapter_id=adapter_id,
                    brief_text=brief_text,
                    style=row.style or {},
                    layout=row.layout or {},
                    reference_images=reference_images,
                    max_turns=max_iterations,
                    supervisor_model=planner_model,
                    image_model=generation_model,
                    api_key=api_key,
                    base_url=base_url,
                    enable_web_search=enable_web_search,
                    workspace_id=row.workspace_id,
                    user_id=row.owner_id,
                    generation_id=row.id,
                    execution_profile=execution_profile,
                    db=session,
                ),
                timeout=settings.image_request_timeout_seconds,
            )
        )

        image_bytes = result.image_bytes
        if not image_bytes:
            _mark_failed(session, generation_id, "Agent did not return an image")
            raise Ignore()

        row = _load_fresh(session, generation_id)
        if row is None:
            raise Ignore()
        if row.image_status == "cancelled":
            raise Ignore()
        if task_id and row.celery_task_id and row.celery_task_id != task_id:
            raise Ignore()

        storage_key = f"images/results/{row.workspace_id}/{row.id}.png"
        try:
            _minio_client().put_object(
                settings.minio_bucket,
                storage_key,
                io.BytesIO(image_bytes),
                length=len(image_bytes),
                content_type="image/png",
            )
        except Exception:
            logger.exception("images.generate: storage put failed for %s", generation_id)
            _mark_failed(session, generation_id, "Storage upload failed")
            raise Ignore()

        row = _load_fresh(session, generation_id)
        if row is None:
            raise Ignore()
        if row.image_status == "cancelled":
            _remove_object(storage_key)
            raise Ignore()
        row.image_storage_key = storage_key
        row.image_model = generation_model
        row.image_execution_profile = execution_profile
        row.agent_trace_id = result.agent_trace_id
        row.image_status = "succeeded"
        row.failure_reason = None
        row.completed_at = _utcnow()
        row.updated_at = _utcnow()
        row.celery_task_id = None
        session.add(row)
        session.commit()
        _notify_generation_finished(session, row, outcome="succeeded")
        return row.id
    except Ignore:
        raise
    except ImageRuntimeConfigurationError as exc:
        logger.error(
            "images.generate: image runtime configuration error for %s: %s", generation_id, exc
        )
        _mark_failed(session, generation_id, str(exc))
        raise Ignore()
    except ImageModelSettingsError as exc:
        logger.error(
            "images.generate: image model settings error for %s: %s",
            generation_id,
            exc.code,
        )
        _mark_failed(session, generation_id, exc.code)
        raise Ignore()
    except Exception as exc:
        logger.exception("images.generate: unexpected error for %s", generation_id)
        if self.request.retries >= self.max_retries:
            _mark_failed(session, generation_id, "Image generation failed")
            raise Ignore()
        _mark_retrying(session, generation_id, "Retrying image generation")
        raise self.retry(exc=exc, countdown=min(120, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
