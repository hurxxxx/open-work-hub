from __future__ import annotations

import asyncio
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.conversations import app_persistence
from ai_do_api.domains.conversations.app_scope_adapters import PPT_JOB_SCOPE_REF
from ai_do_api.domains.ppt_generator.app_catalog import PPT_ASSISTANT_WORKSPACE_APP
from ai_do_api.domains.ppt_generator import service
from ai_do_api.domains.ppt_generator.families import FAMILIES, resolve_family
from ai_do_api.domains.ppt_generator.source_images import (
    extract_source_images as source_image_extract,
)
from ai_do_api.domains.ppt_generator.source_images import (
    render_schedule_images as schedule_image_render,
)
from ai_do_api.domains.ppt_generator.models import (
    PptJob,
    PptTemplatePreviewImage,
    utcnow_naive,
)
from ai_do_api.domains.ppt_generator.schemas import (
    CancelResponse,
    ChatEditRequest,
    ChatEditResponse,
    FamilyInfo,
    FinalizeResponse,
    GenerateResponse,
    JobListItem,
    JobListResponse,
    JobStatusResponse,
    TemplatePreviewImageInfo,
)

require_ppt_generator_app_enabled = require_workspace_app_enabled(
    PPT_ASSISTANT_WORKSPACE_APP.app_id,
    error_code="ppt_generator.app_disabled",
)

router = APIRouter(
    prefix="/ppt-generator",
    tags=["ppt-generator"],
    dependencies=[Depends(require_ppt_generator_app_enabled)],
)

_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_FILE_BYTES = 50 * 1024 * 1024
_MAX_FILES = 10
_MAX_TOPIC_CHARS = 100
_MAX_INSTRUCTIONS_CHARS = 2000
_MAX_SHORT_FORM_CHARS = 80
# 참고 URL — 외부 Claude 검색 힌트로만 전달(서버가 직접 fetch 하지 않음).
_MAX_REFERENCE_URL_CHARS = 500
# Cap the combined size of all attachments in one request so a single caller
# cannot pin hundreds of MB in memory (10 files × 50 MB). Each file is still
# read with a budget bounded by the remaining total, so peak memory stays near
# this ceiling rather than per-file × file-count.
_MAX_TOTAL_UPLOAD_BYTES = 120 * 1024 * 1024


def _template_preview_info(
    preview: PptTemplatePreviewImage,
) -> TemplatePreviewImageInfo | None:
    url = service.template_preview_url(preview)
    if url is None:
        return None
    return TemplatePreviewImageInfo(
        id=preview.id,
        url=url,
        sort_order=preview.sort_order,
        created_at=preview.created_at,
    )


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("true", "1", "on", "yes")


def _clean_limited_text(value: str | None, *, max_chars: int, code: str) -> str:
    text = (value or "").strip()
    if len(text) > max_chars:
        raise localized_http_exception(
            status_code=422,
            code=code,
            max_length=max_chars,
        )
    return text


async def _read_upload(file: UploadFile, *, max_bytes: int) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise localized_http_exception(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                code="ppt_generator.upload_too_large",
            )
    return bytes(data)


@router.get("/families", response_model=list[FamilyInfo])
def list_families(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[FamilyInfo]:
    previews_by_family: dict[str, list[TemplatePreviewImageInfo]] = {}
    for preview in service.list_template_preview_images(db, workspace.id):
        item = _template_preview_info(preview)
        if item is None:
            continue
        previews_by_family.setdefault(preview.family_id, []).append(item)

    return [
        FamilyInfo(
            id=key,
            name=fam["name"],
            aspect=fam["aspect"],
            multi_body=fam.get("multi_body", True),
            preview_images=previews_by_family.get(key, []),
        )
        for key, fam in FAMILIES.items()
    ]


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    content: str = Form(""),
    family: str | None = Form(None),
    template: str | None = Form(None),
    purpose: str | None = Form(None),
    audience: str | None = Form(None),
    reference_url: str | None = Form(None),
    extra_notes: str | None = Form(None),
    slide_range: str | None = Form(None),
    language: str = Form("Korean"),
    tone: str = Form("default"),
    instructions: str | None = Form(None),
    include_title_slide: str | None = Form("true"),
    include_table_of_contents: str | None = Form("false"),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> GenerateResponse:
    fam_key = family or template
    family_key, fam = resolve_family(fam_key)
    raw_topic = _clean_limited_text(
        content,
        max_chars=_MAX_TOPIC_CHARS,
        code="ppt_generator.topic_too_long",
    )
    clean_instructions = (
        _clean_limited_text(
            instructions,
            max_chars=_MAX_INSTRUCTIONS_CHARS,
            code="ppt_generator.instructions_too_long",
        )
        or None
    )
    # 좌측(외부/Claude) 비기밀 컨텍스트 — 주제와 함께 외부 검색 힌트로 쓰일 수 있음.
    clean_purpose = _clean_limited_text(
        purpose,
        max_chars=_MAX_TOPIC_CHARS,
        code="ppt_generator.form_field_too_long",
    )
    clean_audience = _clean_limited_text(
        audience,
        max_chars=_MAX_TOPIC_CHARS,
        code="ppt_generator.form_field_too_long",
    )
    clean_reference_url = _clean_limited_text(
        reference_url,
        max_chars=_MAX_REFERENCE_URL_CHARS,
        code="ppt_generator.form_field_too_long",
    )
    # 우측(내부/Qwen) 기밀 컨텍스트 — 외부로 절대 나가지 않고 본문 생성에만 쓰임.
    clean_extra_notes = _clean_limited_text(
        extra_notes,
        max_chars=_MAX_INSTRUCTIONS_CHARS,
        code="ppt_generator.instructions_too_long",
    )
    language = (
        _clean_limited_text(
            language,
            max_chars=_MAX_SHORT_FORM_CHARS,
            code="ppt_generator.form_field_too_long",
        )
        or "Korean"
    )
    tone = (
        _clean_limited_text(
            tone,
            max_chars=_MAX_SHORT_FORM_CHARS,
            code="ppt_generator.form_field_too_long",
        )
        or "default"
    )
    slide_range = (
        _clean_limited_text(
            slide_range,
            max_chars=_MAX_SHORT_FORM_CHARS,
            code="ppt_generator.form_field_too_long",
        )
        or None
    )

    incoming_files = [f for f in (files or []) if f and f.filename]
    if len(incoming_files) > _MAX_FILES:
        raise localized_http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="ppt_generator.too_many_files",
            max_count=_MAX_FILES,
        )
    uploads: list[tuple[str, bytes, str]] = []
    total_bytes = 0
    for f in incoming_files:
        # Read with a budget that is the smaller of the per-file cap and the
        # remaining total budget, so the combined upload can't exceed the cap.
        budget = min(_MAX_FILE_BYTES, _MAX_TOTAL_UPLOAD_BYTES - total_bytes)
        data = await _read_upload(f, max_bytes=budget)
        total_bytes += len(data)
        uploads.append((f.filename, data, f.content_type or ""))

    # 첨부 파싱(PDF/docx 추출·OCR 포함)은 블로킹·CPU 부하가 커서 스레드로 오프로드한다.
    file_context, ok_files, failed_files = await asyncio.to_thread(
        service.extract_uploaded_files, uploads
    )

    # 사진 자리(비고칸)가 있는 양식만 첨부 PDF/PPTX 에서 이미지를 추출(나머지는 낭비).
    # 추출·저장·매칭은 전부 서버 내부에서만 수행(외부 전송 없음).
    source_images: list[dict] = []
    schedule_images: list[dict] = []
    embed_pptx: tuple[str, bytes] | None = None
    # 이미지 추출은 CPU/서브프로세스 블로킹 작업이므로 스레드로 오프로드해 이벤트 루프를 막지
    # 않는다(특히 아래 schedule_image_render 는 LibreOffice 서브프로세스를 호출).
    if fam.get("design") in ("doowon-seminar", "doowon-education"):
        try:
            source_images = await asyncio.to_thread(source_image_extract, uploads)
        except Exception:
            source_images = []
    # 세미나 & 출장 보고서: 첨부 스프레드시트의 도형/화살표 시트를 렌더해 첫 본문 페이지 비고칸에
    # '첨부 일정표' 똑딱이(OLE)로 삽입한다(색·화살표·병합헤더가 있는 복잡한 월별 일정/현금흐름표를
    # 원본 그대로 담기 위함). LibreOffice headless 변환이라 블로킹 → 반드시 스레드에서 실행.
    if fam.get("design") == "doowon-seminar":
        try:
            schedule_images = await asyncio.to_thread(schedule_image_render, uploads)
        except Exception:
            schedule_images = []
    # 교육 보고서: 첨부한 첫 .pptx 를 '똑딱이'(OLE)로 임베드할 결과보고서로 사용.
    if fam.get("design") == "doowon-education":
        for _name, _data, _mime in uploads:
            if _name and _name.lower().endswith(".pptx") and _data:
                embed_pptx = (_name, _data)
                break

    template_preview_images = service.list_template_preview_reference_images(
        db,
        workspace.id,
        family_key,
    )

    # external_context = 좌측 비기밀 입력(용도/대상·발표 대상·참고 URL). 주제와 함께
    # 외부 Claude 최신정보 검색 힌트로만 쓰인다. 첨부/기타 참고사항은 절대 포함하지 않는다.
    external_context = {
        "purpose": clean_purpose or "",
        "audience": clean_audience or "",
        "reference_url": clean_reference_url or "",
    }
    has_external_context = any(external_context.values())

    # raw_topic = 사용자가 입력한 ≤100자 주제(외부 Claude 최신정보 검색에만 쓰임).
    # merged = 주제 + 비기밀 메타(용도/대상) + 첨부 문서 + 기타 참고사항(내부 Qwen 에만 쓰임).
    # 기밀 파일·기타 참고사항은 외부 Claude 로 가지 않는다.
    external_topic = raw_topic
    merged_parts: list[str] = []
    if raw_topic:
        merged_parts.append(raw_topic)
    if clean_purpose:
        merged_parts.append(f"[용도/대상]\n{clean_purpose}")
    if clean_audience:
        merged_parts.append(f"[발표 대상]\n{clean_audience}")
    if file_context:
        merged_parts.append(f"[첨부 문서 내용]\n{file_context}")
    if clean_extra_notes:
        merged_parts.append(f"[기타 참고사항]\n{clean_extra_notes}")
    merged = "\n\n".join(merged_parts)
    if not merged:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ppt_generator.empty_input",
        )

    try:
        job = service.create_job(
            db,
            current_user,
            workspace,
            content=merged,
            topic=external_topic,
            external_context=external_context if has_external_context else None,
            family=family_key,
            slide_range=slide_range,
            language=language,
            tone=tone,
            instructions=clean_instructions,
            include_title_slide=_truthy(include_title_slide),
            include_toc=_truthy(include_table_of_contents),
            attached_files=ok_files,
            failed_files=failed_files,
            source_images=source_images,
            schedule_images=schedule_images,
            embed_pptx=embed_pptx,
            template_preview_images=template_preview_images,
        )
    except service.PptGeneratorEnqueueError:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ppt_generator.enqueue_failed",
        ) from None

    return GenerateResponse(
        job_id=job.id,
        status=job.status,
        family=family_key,
        family_name=fam["name"],
        aspect=fam["aspect"],
        n_slides=job.n_slides,
        attached_files=ok_files,
        failed_files=failed_files,  # type: ignore[arg-type]
    )


def _require_job(db: Session, workspace: Workspace, user: User, job_id: str):
    job = service.get_job(db, workspace.id, job_id, user.id)
    if job is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ppt_generator.job_not_found",
        )
    return job


def _job_list_item(job: PptJob) -> JobListItem:
    return JobListItem(
        job_id=job.id,
        status=job.status,
        title=service.public_job_title(job),
        family=job.family,
        aspect=job.aspect,
        n_slides=job.n_slides,
        error=job.error,
        rev=service.rev_of(job),
        pptx_ready=job.pptx_key is not None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> JobListResponse:
    jobs = service.list_jobs(db, workspace.id, current_user.id, limit=limit)
    return JobListResponse(items=[_job_list_item(job) for job in jobs])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> JobStatusResponse:
    job = _require_job(db, workspace, current_user, job_id)
    heartbeat_age: int | None = None
    if job.status in ("pending", "running") and job.updated_at is not None:
        heartbeat_age = max(0, int((utcnow_naive() - job.updated_at).total_seconds()))
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        title=service.public_job_title(job),
        message=job.message or "",
        family=job.family,
        aspect=job.aspect,
        n_slides=job.n_slides,
        error=job.error,
        rev=service.rev_of(job),
        chat_result=job.chat_result,
        slides_spec=job.slides_spec,
        pptx_ready=job.pptx_key is not None,
        research_sources=list((job.params or {}).get("research_sources") or []),
        heartbeat_age_seconds=heartbeat_age,
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    job = _require_job(db, workspace, current_user, job_id)
    service.delete_job(db, job)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}/download")
def download(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    job = _require_job(db, workspace, current_user, job_id)
    # 'PPT로 전환'(finalize)으로 .pptx 가 빌드된 뒤에만 다운로드 가능.
    if not job.pptx_key:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ppt_generator.file_not_ready",
        )
    data = service.fetch_object_bytes(job.pptx_key)
    if data is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ppt_generator.file_not_found",
        )
    filename = quote("두원공조_PPT.pptx")
    return Response(
        content=data,
        media_type=_PPTX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/jobs/{job_id}/chat-edit", response_model=ChatEditResponse)
def chat_edit(
    job_id: str,
    payload: ChatEditRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ChatEditResponse:
    job = _require_job(db, workspace, current_user, job_id)
    if job.status != "completed" or not job.slides_spec:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ppt_generator.job_not_ready",
        )
    # 직전 수정 턴이 아직 워커에서 처리 중이면 중복 enqueue 거부 — 동시 실행 시
    # 두 워커가 같은 slides_spec/미리보기 객체를 덮어써 한쪽 수정이 유실되는 것을 막는다.
    # 단, 워커가 비정상 종료해 'processing' 이 5분 넘게 굳은 경우는 죽은 것으로 보고 재시도 허용.
    chat_status = (job.chat_result or {}).get("status")
    fresh = job.updated_at is not None and (utcnow_naive() - job.updated_at < timedelta(minutes=5))
    if chat_status == "processing" and fresh:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ppt_generator.chat_in_progress",
        )
    conversation = app_persistence.get_or_create_app_conversation(
        db,
        workspace=workspace,
        user=current_user,
        conversation_id=payload.conversation_id,
        scope_ref=PPT_JOB_SCOPE_REF,
        scope_resource_id=job.id,
    )
    history = _ppt_chat_history_from_turns(
        app_persistence.recent_turns_for_prompt(conversation, limit=6)
    )
    if not history:
        history = payload.history
    app_persistence.append_user_app_turn(
        db,
        conversation=conversation,
        content=payload.message.strip(),
        meta={"kind": "ppt_job", "job_id": job.id},
    )
    try:
        service.start_chat_edit(
            db,
            job,
            payload.message.strip(),
            history,
            conversation_id=conversation.id,
        )
    except service.PptGeneratorEnqueueError:
        _append_ppt_chat_error_turn(
            db,
            conversation=conversation,
            job_id=job.id,
            message="수정 요청을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ppt_generator.enqueue_failed",
        ) from None
    return ChatEditResponse(
        ok=True,
        status="processing",
        message="수정 요청을 처리 중입니다.",
        conversation_id=conversation.id,
    )


def _append_ppt_chat_error_turn(db: Session, *, conversation, job_id: str, message: str) -> None:
    try:
        app_persistence.append_assistant_app_turn(
            db,
            conversation=conversation,
            content=message,
            meta={"kind": "ppt_job", "job_id": job_id, "response_status": "error"},
        )
    except Exception:  # noqa: BLE001
        db.rollback()


def _ppt_chat_history_from_turns(turns) -> list[dict]:
    return [
        {"role": turn.role, "content": turn.content}
        for turn in turns
        if turn.role in ("user", "assistant") and turn.content.strip()
    ]


@router.post("/jobs/{job_id}/finalize", response_model=FinalizeResponse)
def finalize(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> FinalizeResponse:
    """HTML 미리보기에서 다듬은 slides_spec 을 .pptx 로 빌드(전환)하도록 워커에 위임."""
    job = _require_job(db, workspace, current_user, job_id)
    if job.status != "completed" or not job.slides_spec:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ppt_generator.job_not_ready",
        )
    try:
        service.start_finalize(db, job)
    except service.PptGeneratorEnqueueError:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ppt_generator.enqueue_failed",
        ) from None
    return FinalizeResponse(ok=True, status="processing")


@router.post("/jobs/{job_id}/cancel", response_model=CancelResponse)
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> CancelResponse:
    """진행 중인 생성 작업을 취소한다. 아직 시작 안 한 태스크는 실행을 막고, 실행 중이면
    워커가 완료 시점에 결과를 폐기하도록 행을 'cancelled' 로 표시한다."""
    job = _require_job(db, workspace, current_user, job_id)
    if job.status not in ("pending", "running"):
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ppt_generator.job_not_cancellable",
        )
    service.request_cancel(db, job)
    return CancelResponse(ok=True, status="cancelled")
