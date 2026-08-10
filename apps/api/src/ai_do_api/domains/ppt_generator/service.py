"""PPT 자동 생성 — 서비스 계층.

작업(PptJob) 생성/조회, 업로드 파일 텍스트 추출, Celery enqueue, MinIO 산출물 입출력을 담당.
실제 생성 파이프라인(LLM→pptx→미리보기)은 워커 태스크 ``ppt_generator.generate`` 가 수행한다.
"""

from __future__ import annotations

import logging
import io
import os
from functools import lru_cache

from celery import Celery
from sqlalchemy.orm import Session, joinedload

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import ensure_bucket, get_minio_client
from ai_do_api.core.worker_queue_contract import (
    PPT_GENERATE_QUEUE,
    PPT_GENERATOR_CHAT_EDIT_TASK_NAME,
    PPT_GENERATOR_FINALIZE_TASK_NAME,
    PPT_GENERATOR_GENERATE_TASK_NAME,
)
from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.document_processing.contracts import UnsupportedDocumentType
from ai_do_api.domains.document_processing.extractors import extract_document
from ai_do_api.domains.media.proxy_urls import build_media_proxy_url
from ai_do_api.domains.ppt_generator.families import resolve_family
from ai_do_api.domains.ppt_generator.models import (
    PptJob,
    PptTemplatePreviewImage,
    utcnow_naive,
)
from ai_do_api.domains.ppt_generator.prompts import compute_slide_count

logger = logging.getLogger(__name__)

TASK_KIND = "ppt_generate"
# 표지 하단 작성자 표기 — 개인 이름 대신 소속 고정 문구로 노출한다.
_COVER_AUTHOR_LABEL = "기술연구소"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_QUEUE_FAILURE_MESSAGE = "작업 큐에 등록하지 못했습니다. 잠시 후 다시 시도해 주세요."
_CHAT_QUEUE_FAILURE_MESSAGE = "수정 요청을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."

_ALLOWED_EXTS = {
    ".pdf",
    ".docx",
    ".txt",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".webp",
    ".pptx",
}
# 컨텍스트가 너무 길면 LLM이 max_tokens 안에서 JSON 완결 못 함 → 줄임
_MAX_CONTEXT_CHARS = 20000

# 텍스트 레이어가 없는 PDF/이미지(스캔본 등)의 OCR 폴백 — 사내 Tesseract(PyMuPDF 내장)만 사용.
# easyocr/torch·외부 비전 API 불필요, 외부 전송 없음. Tesseract 가 없으면 폴백은 조용히 no-op.
_OCR_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
_OCR_LANGS = "kor+eng"
_OCR_DPI = 200
_OCR_MAX_PAGES = 10
_TESSDATA_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tessdata",
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
)
_MAX_TEMPLATE_REFERENCE_IMAGES_PER_JOB = 4


class PptGeneratorEnqueueError(RuntimeError):
    """Raised after the persisted job state has been marked failed."""


# ============================================================
# Celery
# ============================================================
@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "ai_do_api_ppt_generator_app",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def _enqueue(task_name: str, job_id: str) -> str:
    client = _get_celery_client()
    result = client.signature(task_name, args=[job_id], immutable=True).apply_async(
        queue=PPT_GENERATE_QUEUE, retry=False
    )
    return str(result.id)


# ============================================================
# MinIO object keys
# ============================================================
def job_prefix(workspace_id: str, job_id: str) -> str:
    return f"ppt-generator/{workspace_id}/{job_id}"


def pptx_object_key(workspace_id: str, job_id: str) -> str:
    return f"{job_prefix(workspace_id, job_id)}/output.pptx"


def fetch_object_bytes(key: str) -> bytes | None:
    settings = get_settings()
    client = get_minio_client()
    try:
        resp = client.get_object(settings.minio_bucket, key)
    except Exception:
        return None
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def _put_object_bytes(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    ensure_bucket()
    get_minio_client().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


# ============================================================
# 파일 텍스트 추출 (다중 파일)
# ============================================================
def _ensure_tessdata_prefix() -> None:
    """TESSDATA_PREFIX 가 안 잡혀 있으면 흔한 설치 경로에서 찾아 설정(있을 때만)."""
    if os.environ.get("TESSDATA_PREFIX"):
        return
    for cand in _TESSDATA_CANDIDATES:
        if os.path.isdir(cand):
            os.environ["TESSDATA_PREFIX"] = cand
            return


def _ocr_document_text(content: bytes, ext: str) -> str:
    """텍스트 레이어가 없는 PDF/이미지를 사내 Tesseract(PyMuPDF 내장)로 OCR → 텍스트.

    스캔 이미지 PDF·이미지 첨부 등 일반 추출 텍스트가 빈 경우의 폴백. 전부 로컬에서 수행하며
    외부 전송 없음. Tesseract·언어데이터가 없으면 예외를 삼키고 빈 문자열 반환(폴백 실패 처리).
    """
    try:
        import fitz  # PyMuPDF
    except Exception:
        return ""
    _ensure_tessdata_prefix()
    filetype = "pdf" if ext == ".pdf" else ext.lstrip(".").replace("jpeg", "jpg").replace("tiff", "tif")
    try:
        doc = fitz.open(stream=content, filetype=filetype)
    except Exception:
        return ""
    parts: list[str] = []
    try:
        for pno in range(min(doc.page_count, _OCR_MAX_PAGES)):
            try:
                page = doc.load_page(pno)
                textpage = page.get_textpage_ocr(language=_OCR_LANGS, dpi=_OCR_DPI, full=True)
                text = (page.get_text("text", textpage=textpage) or "").strip()
            except Exception:
                continue
            if text:
                parts.append(text)
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return "\n".join(parts).strip()


def extract_uploaded_files(
    files: list[tuple[str, bytes, str]],
) -> tuple[str, list[str], list[dict]]:
    """``(filename, content_bytes, mime_type)`` 리스트에서 텍스트를 추출해 병합.

    반환: ``(merged_text, succeeded_names, failed[{name, reason}])``.
    """
    chunks: list[str] = []
    succeeded: list[str] = []
    failed: list[dict] = []
    total_len = 0

    for filename, content, mime_type in files:
        if not filename:
            continue
        # 누적 텍스트가 이미 컨텍스트 상한을 넘었으면 이후 파일은 어차피 잘려나가므로
        # 비싼 추출(PDF/OCR 등)을 더 돌리지 않고 중단.
        if total_len >= _MAX_CONTEXT_CHARS:
            break
        ext = os.path.splitext(filename)[1].lower()
        if ext not in _ALLOWED_EXTS:
            failed.append({"name": filename, "reason": f"지원되지 않는 확장자 ({ext})"})
            continue
        try:
            if ext == ".txt":
                text = content.decode("utf-8", errors="replace").strip()
            else:
                bundle = extract_document(
                    document_id="ppt-gen",
                    filename=filename,
                    mime_type=mime_type or "application/octet-stream",
                    content=content,
                )
                text = (bundle.normalized_text or "").strip()
            label = filename
            if not text and ext in _OCR_EXTS:
                # 텍스트 레이어가 없으면(스캔 PDF·이미지 등) 사내 Tesseract OCR 로 폴백.
                try:
                    text = _ocr_document_text(content, ext)
                except Exception:  # noqa: BLE001 — OCR 실패는 무시(해당 파일만 실패 처리)
                    logger.exception("ppt_generator OCR 폴백 실패: %s", filename)
                    text = ""
                if text:
                    label = f"{filename} (OCR)"
            if text:
                chunk = f"[{label}]\n{text}"
                chunks.append(chunk)
                total_len += len(chunk) + 2  # join 시 "\n\n" 구분자 포함
                succeeded.append(filename)
            else:
                failed.append({"name": filename, "reason": "텍스트가 추출되지 않음"})
        except UnsupportedDocumentType:
            # 이미지 첨부 등 텍스트 추출기가 없는 형식은 사내 Tesseract OCR 로 폴백.
            ocr_text = ""
            if ext in _OCR_EXTS:
                try:
                    ocr_text = _ocr_document_text(content, ext)
                except Exception:  # noqa: BLE001
                    logger.exception("ppt_generator OCR 폴백 실패: %s", filename)
            if ocr_text:
                chunk = f"[{filename} (OCR)]\n{ocr_text}"
                chunks.append(chunk)
                total_len += len(chunk) + 2
                succeeded.append(filename)
            else:
                failed.append({"name": filename, "reason": f"지원되지 않는 확장자 ({ext})"})
        except Exception:  # noqa: BLE001 — 한 파일 실패가 전체를 막지 않도록
            # 내부 예외 원문은 로그에만. 사용자에겐 일반화된 사유만 노출(내부 정보 유출 금지).
            logger.exception("ppt_generator 첨부 파일 처리 실패: %s", filename)
            failed.append({"name": filename, "reason": "파일을 처리하지 못했습니다."})

    merged = "\n\n".join(chunks)
    if len(merged) > _MAX_CONTEXT_CHARS:
        merged = merged[:_MAX_CONTEXT_CHARS] + "\n\n[이하 생략]"
    return merged, succeeded, failed


# ============================================================
# 작업 생성 / 조회
# ============================================================
def create_job(
    db: Session,
    user: User,
    workspace: Workspace,
    *,
    content: str,
    topic: str = "",
    external_context: dict | None = None,
    family: str | None,
    slide_range: str | None,
    language: str,
    tone: str,
    instructions: str | None,
    include_title_slide: bool,
    include_toc: bool,
    attached_files: list[str],
    failed_files: list[dict],
    source_images: list[dict] | None = None,
    schedule_images: list[dict] | None = None,
    embed_pptx: tuple[str, bytes] | None = None,
    template_preview_images: list[dict] | None = None,
) -> PptJob:
    family_key, fam = resolve_family(family)

    if fam.get("multi_body", True):
        n_slides = compute_slide_count(content, slide_range, include_title_slide, include_toc)
    else:
        n_slides = 2
        include_title_slide = True
        include_toc = False

    params = {
        "topic": topic,  # ≤100자 순수 주제 — 외부 Claude 최신정보 검색 전용
        # 좌측 비기밀 메타(용도/대상·발표 대상·참고 URL) — 외부 검색 힌트로만 쓰임.
        "external_context": external_context or None,
        "language": language or "Korean",
        "tone": tone or "default",
        "instructions": instructions,
        "include_title_slide": include_title_slide,
        "include_toc": include_toc,
        "slide_range": slide_range,
        "attached_files": attached_files,
        "failed_files": failed_files,
        # 표지 하단 작성자 — 개인 이름 대신 소속(팀) 고정 문구.
        # (worker 가 cover 의 AUTHOR 로 사용 → pptx/미리보기 공통 반영)
        "author_name": _COVER_AUTHOR_LABEL,
    }
    if template_preview_images:
        params["template_preview_images"] = template_preview_images[
            :_MAX_TEMPLATE_REFERENCE_IMAGES_PER_JOB
        ]

    job = PptJob(
        id=new_id(),
        workspace_id=workspace.id,
        user_id=user.id,
        status="pending",
        message="작업 큐 등록됨",
        family=family_key,
        aspect=fam["aspect"],
        n_slides=n_slides,
        content=content,
        params=params,
    )
    db.add(job)
    db.flush()

    # 첨부 사진(있으면) → MinIO 저장 + params 에 참조 기록. 워커가 렌더 시 비고칸에 매칭해 넣는다.
    # 바이트는 DB(params)에 넣지 않고 MinIO 에만. params 엔 키 + 크기 + 근접매칭용 텍스트(상한)만.
    if source_images:
        refs: list[dict] = []
        prefix = job_prefix(workspace.id, job.id)
        for i, im in enumerate(source_images):
            data = im.get("data")
            if not data:
                continue
            ext = (im.get("ext") or "png").lower()
            key = f"{prefix}/src-images/{i}.{ext}"
            try:
                _put_object_bytes(key, data, f"image/{ext}")
            except Exception:
                continue
            refs.append(
                {
                    "key": key,
                    "w": im.get("w"),
                    "h": im.get("h"),
                    "text": (im.get("text") or "")[:600],
                }
            )
        if refs:
            job.params = {**(job.params or {}), "source_images": refs}

    # 첨부 스프레드시트의 도형/화살표 시트를 렌더한 일정표 이미지(있으면) → MinIO 저장 + params 참조.
    # 워커가 첫 본문 페이지 비고칸에 '첨부 일정표' 똑딱이(OLE)로 임베드한다(원본 표를 그대로 담는 용도).
    if schedule_images:
        sched_refs: list[dict] = []
        prefix = job_prefix(workspace.id, job.id)
        for i, im in enumerate(schedule_images):
            data = im.get("data")
            if not data:
                continue
            ext = (im.get("ext") or "png").lower()
            key = f"{prefix}/sched-images/{i}.{ext}"
            try:
                _put_object_bytes(key, data, f"image/{ext}")
            except Exception:
                continue
            sched_refs.append(
                {
                    "key": key,
                    "w": im.get("w"),
                    "h": im.get("h"),
                    "text": (im.get("text") or "")[:600],
                    "sheet": (im.get("sheet") or "")[:200],
                }
            )
        if sched_refs:
            job.params = {**(job.params or {}), "schedule_images": sched_refs}

    # 첨부한 .pptx(있으면) → '똑딱이'(OLE)로 임베드할 결과보고서 덱. 원본 바이트를 MinIO 에 보관.
    if embed_pptx and embed_pptx[1]:
        emb_name, emb_data = embed_pptx
        emb_key = f"{job_prefix(workspace.id, job.id)}/embed/source.pptx"
        try:
            _put_object_bytes(emb_key, emb_data, _PPTX_MIME)
            job.params = {
                **(job.params or {}),
                "embed_pptx": {"key": emb_key, "filename": emb_name},
            }
        except Exception:
            pass

    # 워커가 job 행을 읽기 전에 반드시 커밋해 둔다 — enqueue 를 먼저 하면 워커가
    # 커밋되지 않은 행을 session.get 으로 못 찾고 조용히 종료해 작업이 영구히 pending 으로 멈춘다.
    db.commit()
    db.refresh(job)
    try:
        task_id = _enqueue(PPT_GENERATOR_GENERATE_TASK_NAME, job.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ppt_generator.generate enqueue failed (job=%s)", job.id)
        job.status = "error"
        job.message = "생성 실패"
        job.error = _QUEUE_FAILURE_MESSAGE
        job.updated_at = utcnow_naive()
        db.add(job)
        db.commit()
        db.refresh(job)
        raise PptGeneratorEnqueueError(_QUEUE_FAILURE_MESSAGE) from exc
    job.celery_task_id = task_id
    db.commit()
    return job


def get_job(db: Session, workspace_id: str, job_id: str, user_id: str) -> PptJob | None:
    """작업을 워크스페이스 + 소유자(user) 단위로 스코핑. 어느 한쪽이라도 불일치면 None."""
    job = db.get(PptJob, job_id)
    if (
        job is None
        or job.workspace_id != workspace_id
        or job.user_id != user_id
        or job.deleted_at is not None
    ):
        return None
    return job


def list_template_preview_images(
    db: Session,
    workspace_id: str,
) -> list[PptTemplatePreviewImage]:
    return (
        db.query(PptTemplatePreviewImage)
        .options(joinedload(PptTemplatePreviewImage.media))
        .filter(
            PptTemplatePreviewImage.workspace_id == workspace_id,
            PptTemplatePreviewImage.deleted_at.is_(None),
        )
        .order_by(
            PptTemplatePreviewImage.family_id.asc(),
            PptTemplatePreviewImage.sort_order.asc(),
            PptTemplatePreviewImage.created_at.asc(),
        )
        .all()
    )


def list_template_preview_reference_images(
    db: Session,
    workspace_id: str,
    family_id: str,
) -> list[dict]:
    refs: list[dict] = []
    for preview in list_template_preview_images(db, workspace_id):
        if preview.family_id != family_id or preview.media is None:
            continue
        media = preview.media
        refs.append(
            {
                "storage_key": media.storage_key,
                "filename": media.filename,
                "content_type": media.content_type,
                "size_bytes": media.size_bytes,
                "sort_order": preview.sort_order,
            }
        )
        if len(refs) >= _MAX_TEMPLATE_REFERENCE_IMAGES_PER_JOB:
            break
    return refs


def template_preview_url(preview: PptTemplatePreviewImage) -> str | None:
    media = preview.media
    if media is None:
        return None
    settings = get_settings()
    return build_media_proxy_url(
        media,
        api_prefix=settings.api_prefix,
        secret=settings.minio_secret_key,
    )


def public_job_title(job: PptJob) -> str | None:
    """Return the safe user-facing title for a generated deck.

    Do not derive a title from ``content``: it can contain extracted attachment
    text. ``params.topic`` is the user-entered <=100 character topic only.
    """
    params = job.params if isinstance(job.params, dict) else {}
    topic = params.get("topic")
    if not isinstance(topic, str):
        return None
    title = topic.strip()
    return title[:100] or None


def list_jobs(
    db: Session,
    workspace_id: str,
    user_id: str,
    *,
    limit: int = 30,
) -> list[PptJob]:
    safe_limit = max(1, min(limit, 100))
    return (
        db.query(PptJob)
        .filter(
            PptJob.workspace_id == workspace_id,
            PptJob.user_id == user_id,
            PptJob.deleted_at.is_(None),
        )
        .order_by(PptJob.created_at.desc(), PptJob.id.desc())
        .limit(safe_limit)
        .all()
    )


def delete_job(db: Session, job: PptJob) -> None:
    job.deleted_at = utcnow_naive()
    job.updated_at = job.deleted_at
    db.add(job)
    db.commit()


def start_chat_edit(
    db: Session,
    job: PptJob,
    message: str,
    history: list[dict],
    *,
    conversation_id: str | None = None,
) -> None:
    """챗봇 수정 요청을 워커에 위임. 즉시 processing 상태로 표시한다."""
    job.chat_result = {
        "status": "processing",
        "message": message,
        "history": (history or [])[-6:],
        "conversation_id": conversation_id,
        "answer": "",
        "intent": None,
        "refreshed_slide_index": None,
        "rev": (job.chat_result or {}).get("rev", 0) + 1,
    }
    job.updated_at = utcnow_naive()
    db.commit()
    try:
        _enqueue(PPT_GENERATOR_CHAT_EDIT_TASK_NAME, job.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ppt_generator.chat_edit enqueue failed (job=%s)", job.id)
        job.chat_result = {
            **(job.chat_result or {}),
            "status": "error",
            "answer": _CHAT_QUEUE_FAILURE_MESSAGE,
            "intent": "chat",
            "refreshed_slide_index": None,
        }
        job.updated_at = utcnow_naive()
        db.add(job)
        db.commit()
        raise PptGeneratorEnqueueError(_QUEUE_FAILURE_MESSAGE) from exc


def request_cancel(db: Session, job: PptJob) -> None:
    """진행 중(pending/running) PPT 생성 작업을 취소한다.

    Celery 태스크를 revoke(terminate=False) 해 **아직 시작 안 한** 태스크는 실행 자체를 막고,
    행 상태를 'cancelled' 로 표시한다. 이미 실행 중인 태스크는 즉시 끊지 않고(블로킹 LLM 호출
    중단은 워커를 죽여야 가능) 워커가 체크포인트/완료 시점에 결과를 폐기한다(_set 가드).
    프론트는 'cancelled' 상태를 받으면 폴링을 멈추고 입력 화면으로 돌아간다.
    """
    task_id = job.celery_task_id
    if task_id:
        try:
            _get_celery_client().control.revoke(task_id, terminate=False)
        except Exception:  # noqa: BLE001 — revoke 실패해도 상태는 cancelled 로 남긴다
            logger.warning(
                "ppt_generator.cancel revoke failed (job=%s)", job.id, exc_info=True
            )
    job.status = "cancelled"
    job.message = "생성이 취소되었습니다."
    job.error = None
    job.updated_at = utcnow_naive()
    db.add(job)
    db.commit()
    db.refresh(job)


def start_finalize(db: Session, job: PptJob) -> None:
    """'PPT로 전환' 요청을 워커에 위임. slides_spec → .pptx 빌드를 enqueue 한다.

    이전 산출물 키를 비워 다운로드 게이트(pptx_key 존재)가 새 빌드 완료를
    기다리도록 한다. error 도 비워 직전 finalize 실패 흔적을 지운다.
    """
    previous_pptx_key = job.pptx_key
    job.pptx_key = None
    job.error = None
    job.message = "PPT 변환 중..."
    job.updated_at = utcnow_naive()
    db.commit()
    try:
        _enqueue(PPT_GENERATOR_FINALIZE_TASK_NAME, job.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ppt_generator.finalize enqueue failed (job=%s)", job.id)
        job.pptx_key = previous_pptx_key
        job.error = _QUEUE_FAILURE_MESSAGE
        job.message = "변환 실패"
        job.updated_at = utcnow_naive()
        db.add(job)
        db.commit()
        raise PptGeneratorEnqueueError(_QUEUE_FAILURE_MESSAGE) from exc


def rev_of(job: PptJob) -> int:
    """미리보기/다운로드 캐시버스팅 토큰 (updated_at epoch 초)."""
    try:
        return int(job.updated_at.timestamp())
    except Exception:
        return 0
