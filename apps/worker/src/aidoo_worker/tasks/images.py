"""Worker task: drive OpenAI image generation via the OpenAI Agents SDK.

Triggered by ``POST /workspaces/{slug}/images/generations/{id}/approve``. The
agent receives the approved brief + reference images (if any) and emits one
image. We persist the bytes to MinIO and update the row.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from celery.exceptions import Ignore
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from aidoo_worker.celery_app import celery_app
from aidoo_worker.settings import get_settings


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[5]


def _ensure_api_src_on_path() -> None:
    api_src = _workspace_root() / "apps" / "api" / "src"
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))


_ensure_api_src_on_path()

from aidoo_api.domains.images.models import ImageGeneration  # noqa: E402
from aidoo_api.domains.images.prompt import (  # noqa: E402
    ILLUSTRATOR_SYSTEM_PROMPT,
    build_agent_prompt,
)


logger = logging.getLogger(__name__)


_VALID_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
_VALID_BACKGROUNDS = {"transparent", "opaque", "auto"}
_VALID_QUALITIES = {"low", "medium", "high", "auto"}
_ALLOWED_REFERENCE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _db_session() -> Session:
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return Session(engine)


def _minio_client():
    from minio import Minio

    settings = get_settings()
    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    host = parsed.netloc or parsed.path
    return Minio(
        host,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def _api_key() -> str:
    settings = get_settings()
    return settings.image_api_key.strip() or os.environ.get("OPENAI_API_KEY", "").strip()


def _normalize_size(value: str) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned in _VALID_SIZES else "1024x1024"


def _normalize_background(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned == "white" or cleaned == "dark":
        # Treat preset palette backgrounds as opaque so the prompt language
        # carries the exact requested look.
        return "opaque"
    return cleaned if cleaned in _VALID_BACKGROUNDS else "auto"


def _normalize_background_for_model(value: str, *, image_model: str) -> str:
    background = _normalize_background(value)
    if background == "transparent" and image_model.startswith("gpt-image-2"):
        logger.info("images.generate: coercing transparent background to auto for %s", image_model)
        return "auto"
    return background


def _normalize_quality(value: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in _VALID_QUALITIES else "high"


def _load(session: Session, generation_id: str) -> ImageGeneration | None:
    row = session.get(ImageGeneration, generation_id)
    if row is None or row.trashed_at is not None:
        return None
    return row


def _is_owned_ref_key(row: ImageGeneration, key: str) -> bool:
    return key.startswith(f"images/refs/{row.id}/")


def _mark_failed(session: Session, generation_id: str, reason: str) -> None:
    row = session.get(ImageGeneration, generation_id)
    if row is None:
        return
    row.image_status = "failed"
    row.failure_reason = (reason or "unknown error")[:500]
    row.celery_task_id = None
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()


def _mark_retrying(session: Session, generation_id: str, reason: str) -> None:
    row = session.get(ImageGeneration, generation_id)
    if row is None:
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
        select(ImageGeneration)
        .where(ImageGeneration.id == generation_id)
        .with_for_update()
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
            logger.warning(
                "images.generate: failed to fetch reference %s: %s", key, exc
            )
            continue
        if len(data) > settings.image_reference_max_bytes:
            logger.warning("images.generate: skipping oversized reference %s", key)
            continue
        out.append((role, content_type, data))
        if len(out) >= settings.image_max_reference_uploads:
            break
    return out


def _build_agent_input_items(
    *,
    brief_text: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    reference_images: list[tuple[str, str, bytes]],
) -> list[dict[str, Any]]:
    text = build_agent_prompt(
        brief_text=brief_text,
        style=style,
        layout=layout,
        reference_roles=[role for role, _, _ in reference_images],
    )
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for _role, content_type, data in reference_images:
        b64 = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{content_type};base64,{b64}",
                "detail": "high",
            }
        )
    return [{"role": "user", "content": content}]


def _extract_image_bytes(result: Any) -> tuple[bytes | None, str | None]:
    """Pull the last successful ImageGenerationCall.result out of the run.

    Returns ``(image_bytes, agent_trace_id)``.
    """
    image_bytes: bytes | None = None
    new_items = getattr(result, "new_items", None) or []
    for item in new_items:
        raw = getattr(item, "raw_item", None)
        item_type = getattr(raw, "type", None) if raw is not None else None
        if item_type == "image_generation_call":
            status = getattr(raw, "status", None)
            data = getattr(raw, "result", None)
            if status == "completed" and isinstance(data, str) and data:
                try:
                    image_bytes = base64.b64decode(data)
                except Exception:
                    image_bytes = None
    trace_id = (
        getattr(result, "_trace_id", None)
        or getattr(result, "trace_id", None)
        or getattr(getattr(result, "context", None), "trace_id", None)
    )
    if not isinstance(trace_id, str):
        trace_id = None
    return image_bytes, trace_id


async def _run_agent(
    *,
    brief_text: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    reference_images: list[tuple[str, str, bytes]],
    max_iterations: int,
    supervisor_model: str,
    image_model: str,
    api_key: str,
    base_url: str,
) -> Any:
    # Local import so plain DB-only tests can run without the SDK installed.
    from agents import Agent, ImageGenerationTool, OpenAIProvider, RunConfig, Runner

    size = _normalize_size(str((layout or {}).get("aspect") or ""))
    background = _normalize_background_for_model(
        str((style or {}).get("background") or ""),
        image_model=image_model,
    )
    quality = _normalize_quality(str((style or {}).get("quality") or ""))

    tool = ImageGenerationTool(
        tool_config={
            "type": "image_generation",
            "model": image_model,
            "size": size,
            "background": background,
            "quality": quality,
            "moderation": "auto",
            "output_format": "png",
        }
    )
    agent = Agent(
        name="infographic-illustrator",
        instructions=ILLUSTRATOR_SYSTEM_PROMPT,
        model=supervisor_model,
        tools=[tool],
    )
    input_items = _build_agent_input_items(
        brief_text=brief_text,
        style=style,
        layout=layout,
        reference_images=reference_images,
    )
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key=api_key, base_url=base_url),
        workflow_name="AIDOO Image Generation",
        trace_metadata={
            "source": "images.generate",
            "image_model": image_model,
            "supervisor_model": supervisor_model,
        },
    )
    return await Runner.run(
        agent,
        input=input_items,
        max_turns=max_iterations + 1,
        run_config=run_config,
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
    api_key = _api_key()
    if not api_key:
        logger.error("images.generate: no API key configured for %s", generation_id)
        with _db_session() as session:
            _mark_failed(session, generation_id, "No image API key configured")
        raise Ignore()

    session = _db_session()
    try:
        task_id = getattr(self.request, "id", None)
        row = _claim_generation(session, generation_id=generation_id, task_id=task_id)
        if row is None:
            raise Ignore()

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

        reference_images = _download_reference_images(row)

        result = asyncio.run(
            asyncio.wait_for(
                _run_agent(
                    brief_text=brief_text,
                    style=row.style or {},
                    layout=row.layout or {},
                    reference_images=reference_images,
                    max_iterations=settings.image_agent_max_iterations,
                    supervisor_model=settings.image_supervisor_model,
                    image_model=settings.image_model,
                    api_key=api_key,
                    base_url=settings.image_base_url,
                ),
                timeout=settings.image_request_timeout_seconds,
            )
        )

        image_bytes, trace_id = _extract_image_bytes(result)
        if not image_bytes:
            _mark_failed(session, generation_id, "Agent did not return an image")
            raise Ignore()

        row = session.get(ImageGeneration, generation_id)
        if row is None or row.trashed_at is not None:
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

        row = session.get(ImageGeneration, generation_id)
        if row is None or row.trashed_at is not None:
            raise Ignore()
        row.image_storage_key = storage_key
        row.image_model = settings.image_model
        row.agent_trace_id = trace_id
        row.image_status = "succeeded"
        row.failure_reason = None
        row.completed_at = _utcnow()
        row.updated_at = _utcnow()
        row.celery_task_id = None
        session.add(row)
        session.commit()
        return row.id
    except Ignore:
        raise
    except Exception as exc:
        logger.exception("images.generate: unexpected error for %s", generation_id)
        if self.request.retries >= self.max_retries:
            _mark_failed(session, generation_id, "Image generation failed")
            raise Ignore()
        _mark_retrying(session, generation_id, "Retrying image generation")
        raise self.retry(exc=exc, countdown=min(120, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
