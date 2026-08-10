from __future__ import annotations

import base64
from io import BytesIO

from collections.abc import Callable

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import (
    resolve_workspace_role,
)
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.roles import workspace_role_allows
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.meal_invoice_ocr import catalog, corrections, service, vocab
from ai_do_api.domains.meal_invoice_ocr.app_catalog import MEAL_INVOICE_OCR_WORKSPACE_APP
from ai_do_api.domains.meal_invoice_ocr.export import export_documents_xlsx
from ai_do_api.domains.meal_invoice_ocr.schemas import (
    MealInvoiceCatalogInfoResponse,
    MealInvoiceCorrectionListResponse,
    MealInvoiceCorrectionRecord,
    MealInvoiceCorrectionSaveRequest,
    MealInvoiceCorrectionSaveResponse,
    MealInvoiceExportRequest,
    MealInvoiceExtractResponse,
)

_UPLOAD_CHUNK_BYTES = 1024 * 1024

# JSON body 엔드포인트는 파싱(=전체 buffering) 전에 content-length 로 요청 크기를 거절한다.
# FastAPI 는 dependency 해석보다 먼저 body 를 읽으므로 Depends 로는 파싱 전 차단이 불가능하고,
# 운영 프록시(nginx)는 API body 를 1025MB 까지 허용해 인증 사용자만으로 메모리 DoS 가 가능하다.
# export 는 이미지 없는 소형 payload 라 타이트하게, corrections 는 문서 이미지 총량(≈40MB) 위로,
# 나머지(멀티파트 업로드)는 스트리밍 상한(_read_upload) 위의 coarse 백스톱으로 건다.
_MAX_EXPORT_BODY_BYTES = 32 * 1024 * 1024
_MAX_CORRECTIONS_BODY_BYTES = 64 * 1024 * 1024
_DEFAULT_MAX_BODY_BYTES = service.MAX_TOTAL_UPLOAD_BYTES + 16 * 1024 * 1024

# endpoint 함수 → 허용 body 상한. 라우터가 workspace prefix 하위로 include 되어도 endpoint 함수
# 식별자는 그대로라(경로는 바뀜) 함수 기준으로 매핑한다. 함수 정의 후 모듈 하단에서 채운다.
_BODY_LIMIT_BY_ENDPOINT: dict[Callable[..., object], int] = {}


def _content_length_missing_or_invalid(header_value: str | None) -> bool:
    return not header_value or not header_value.isdigit()


def _content_length_exceeds(header_value: str | None, limit: int) -> bool:
    """content-length 헤더가 한도를 초과하면 True(정수로 파싱 가능할 때만)."""
    if _content_length_missing_or_invalid(header_value):
        return False
    return int(header_value) > limit


class _BodySizeLimitRoute(APIRoute):
    """typed body 를 파싱(=전체 buffering)하기 전에 content-length 로 요청을 거절하는 라우트.

    FastAPI 는 body 를 dependency 해석보다 먼저 읽으므로, 상위 핸들러(body 읽음)를 호출하기 전에
    헤더만으로 막는다. include_router 는 route class(type(route))를 보존하므로 합성 후에도 적용된다.
    """

    def get_route_handler(self) -> Callable[[Request], object]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            limit = _BODY_LIMIT_BY_ENDPOINT.get(self.endpoint, _DEFAULT_MAX_BODY_BYTES)
            content_length = request.headers.get("content-length")
            if self.endpoint in _BODY_LIMIT_BY_ENDPOINT and _content_length_missing_or_invalid(
                content_length
            ):
                raise localized_http_exception(
                    status_code=413, code="meal_invoice_ocr.upload_too_large"
                )
            if _content_length_exceeds(content_length, limit):
                raise localized_http_exception(
                    status_code=413, code="meal_invoice_ocr.upload_too_large"
                )
            return await original(request)

        return handler


require_meal_invoice_ocr_app_enabled = require_workspace_app_enabled(
    MEAL_INVOICE_OCR_WORKSPACE_APP.app_id,
    error_code="meal_invoice_ocr.app_disabled",
)


def require_meal_invoice_ocr_admin(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> None:
    """공유·관리 데이터(학습 교정, 기준 카탈로그)를 바꾸는 작업은 워크스페이스 관리자로 제한한다.

    교정/카탈로그는 워크스페이스 전체 OCR 동작을 좌우하는 공유 상태라, 일반 멤버가 임의로
    전량 삭제하거나 교체하지 못하게 한다(권한 상승성 데이터 무결성 보호).
    """
    role = resolve_workspace_role(db, current_user, current_workspace.id)
    if not workspace_role_allows(role, "admin"):
        raise localized_http_exception(status_code=403, code="meal_invoice_ocr.admin_required")


router = APIRouter(
    prefix="/meal-invoice-ocr",
    tags=["meal-invoice-ocr"],
    dependencies=[Depends(require_meal_invoice_ocr_app_enabled)],
    route_class=_BodySizeLimitRoute,
)


async def _read_upload(
    file: UploadFile, *, current_total: int
) -> tuple[service.MealInvoiceUpload, int]:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        size += len(chunk)
        if size > service.MAX_UPLOAD_BYTES or current_total + size > service.MAX_TOTAL_UPLOAD_BYTES:
            raise localized_http_exception(
                status_code=413, code="meal_invoice_ocr.upload_too_large"
            )
        chunks.append(chunk)
    return (
        service.MealInvoiceUpload(
            filename=file.filename or "invoice.bin",
            content_type=file.content_type or "application/octet-stream",
            content=b"".join(chunks),
        ),
        current_total + size,
    )


@router.post("/extract", response_model=MealInvoiceExtractResponse)
async def extract_invoices(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceExtractResponse:
    if len(files) > service.MAX_FILES_PER_REQUEST:
        raise localized_http_exception(status_code=413, code="meal_invoice_ocr.too_many_files")
    uploads: list[service.MealInvoiceUpload] = []
    total = 0
    for file in files:
        upload, total = await _read_upload(file, current_total=total)
        # 확장자·선언 MIME 이 아니라 실제 콘텐츠(매직바이트)로 PDF/이미지만 허용한다.
        if not service.is_supported_invoice_upload(upload.content):
            raise localized_http_exception(
                status_code=415, code="meal_invoice_ocr.unsupported_file_type"
            )
        uploads.append(upload)
    if not uploads:
        raise localized_http_exception(status_code=400, code="meal_invoice_ocr.empty_upload")

    # ORM 스칼라는 스레드풀에 넘기기 전에 미리 뽑아 둔다(요청 세션에 스레드 밖 접근 방지).
    workspace_id = workspace.id
    actor_user_id = current_user.id

    def _run() -> MealInvoiceExtractResponse:
        # 과거 교정은 두 갈래로 쓴다: (1) few-shot 소프트 힌트(오독 완화), (2) 자동 교정·검수 후보.
        # 자동 교정은 거래처별로 격리한다. 상호가 정확히 일치하지 않으면 적용하지 않는다.
        try:
            vocab_list = vocab.load_vocab(workspace_id)
        except Exception:  # noqa: BLE001
            vocab_list = []
        try:
            catalog_map = catalog.load_catalog(workspace_id)
        except Exception:  # noqa: BLE001
            catalog_map = {}
        try:
            correction_records = corrections.load_corrections(workspace_id)
            # 실재 품목 이름은 오독 예시에서 빼야 프롬프트가 정답 이름들로 오염되지 않는다.
            fewshot = corrections.build_fewshot(
                correction_records,
                known_names=set(vocab_list) | set(catalog_map),
            )
            aliases = service.build_vendor_aliases(correction_records)
        except Exception:  # noqa: BLE001 - 저장소 접근 실패가 OCR 자체를 막지 않게.
            fewshot = ""
            aliases = {}
        # gateway(LLM 호출)용 DB 세션은 extract_documents가 페이지마다 자체적으로 열고 순차 처리한다.
        # 요청 세션은 스레드 안전하지 않으므로 worker thread와 공유하지 않는다.
        return service.extract_documents(
            uploads,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            fewshot=fewshot,
            vocab=vocab_list,
            catalog=catalog_map,
            aliases=aliases,
        )

    # 렌더 + vLLM 호출은 블로킹이라 스레드풀에서 실행해 이벤트 루프를 막지 않는다.
    return await run_in_threadpool(_run)


@router.post(
    "/corrections",
    response_model=MealInvoiceCorrectionSaveResponse,
    dependencies=[Depends(require_meal_invoice_ocr_admin)],
)
async def save_corrections(
    payload: MealInvoiceCorrectionSaveRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCorrectionSaveResponse:
    records = corrections.records_from_items(payload.items)
    doc_images = dict(payload.문서이미지)

    def _save() -> int:
        try:
            total = corrections.append_corrections(workspace.id, records, doc_images)
        except corrections.CorrectionImageQuotaExceeded as exc:
            raise localized_http_exception(
                status_code=413, code="meal_invoice_ocr.upload_too_large"
            ) from exc
        # 확인된 교정 품명을 사전에 추가해 다음 인식의 자동 매칭에 활용한다(학습 루프).
        names = [str((r.get("교정") or {}).get("품명", "")).strip() for r in records]
        names = [n for n in names if n]
        if names:
            try:
                vocab.add_names(workspace.id, names)
            except Exception:  # noqa: BLE001
                pass
        return total

    total = await run_in_threadpool(_save)
    return MealInvoiceCorrectionSaveResponse(saved=len(records), total_stored=total)


@router.get("/corrections", response_model=MealInvoiceCorrectionListResponse)
async def list_corrections(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCorrectionListResponse:
    records = await run_in_threadpool(corrections.list_corrections, workspace.id)
    items = [
        MealInvoiceCorrectionRecord(
            id=str(r.get("id", "")),
            거래처=str(r.get("거래처", "")),
            거래일=str(r.get("거래일", "")),
            원본={k: str(v) for k, v in (r.get("원본") or {}).items()},
            교정={k: str(v) for k, v in (r.get("교정") or {}).items()},
            created_at=str(r.get("created_at", "")),
            이미지있음=bool(r.get("image_ref")),
        )
        for r in reversed(records)  # 최근 저장이 위로.
    ]
    return MealInvoiceCorrectionListResponse(items=items, total=len(items))


@router.get(
    "/corrections/{correction_id}/image",
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def get_correction_image(
    correction_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    data_url = await run_in_threadpool(
        corrections.get_correction_image, workspace.id, correction_id
    )
    if not data_url or "," not in data_url:
        raise localized_http_exception(status_code=404, code="meal_invoice_ocr.image_not_found")
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
    except (ValueError, IndexError):
        raise localized_http_exception(status_code=404, code="meal_invoice_ocr.image_not_found")
    return Response(content=raw, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.delete(
    "/corrections/{correction_id}",
    response_model=MealInvoiceCorrectionSaveResponse,
    dependencies=[Depends(require_meal_invoice_ocr_admin)],
)
async def delete_correction(
    correction_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCorrectionSaveResponse:
    total = await run_in_threadpool(corrections.delete_correction, workspace.id, correction_id)
    return MealInvoiceCorrectionSaveResponse(saved=0, total_stored=total)


@router.delete(
    "/corrections",
    response_model=MealInvoiceCorrectionSaveResponse,
    dependencies=[Depends(require_meal_invoice_ocr_admin)],
)
async def clear_corrections(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCorrectionSaveResponse:
    await run_in_threadpool(corrections.clear_corrections, workspace.id)
    return MealInvoiceCorrectionSaveResponse(saved=0, total_stored=0)


@router.post(
    "/catalog",
    response_model=MealInvoiceCatalogInfoResponse,
    dependencies=[Depends(require_meal_invoice_ocr_admin)],
)
async def upload_catalog(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCatalogInfoResponse:
    """영양사 납품 대장 엑셀을 올려 품목별 기준 카탈로그(단위·단가·원산지)를 적재한다."""
    upload, _ = await _read_upload(file, current_total=0)
    if not upload.content:
        raise localized_http_exception(status_code=400, code="meal_invoice_ocr.empty_upload")
    # openpyxl 에 넘기기 전에 실제 xlsx(ZIP) 인지 매직바이트로 확인한다.
    if not catalog.is_xlsx_upload(upload.content):
        raise localized_http_exception(
            status_code=415, code="meal_invoice_ocr.unsupported_file_type"
        )

    def _ingest() -> tuple[int, list[str]]:
        try:
            parsed, units = catalog.parse_catalog_xlsx(upload.content)
        except catalog.CatalogArchiveTooLarge as exc:
            raise localized_http_exception(
                status_code=413, code="meal_invoice_ocr.upload_too_large"
            ) from exc
        except Exception:  # noqa: BLE001 - 파싱 실패는 사용자 오류(형식)로 취급.
            raise localized_http_exception(
                status_code=400, code="meal_invoice_ocr.catalog_parse_failed"
            )
        catalog.save_catalog_with_units(workspace.id, parsed, units)
        return (len(parsed), units)

    count, units = await run_in_threadpool(_ingest)
    return MealInvoiceCatalogInfoResponse(items=count, units=units)


@router.get("/catalog", response_model=MealInvoiceCatalogInfoResponse)
async def catalog_info(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCatalogInfoResponse:
    def _info() -> tuple[int, list[str]]:
        return (len(catalog.load_catalog(workspace.id)), catalog.load_units(workspace.id))

    count, units = await run_in_threadpool(_info)
    return MealInvoiceCatalogInfoResponse(items=count, units=units)


@router.delete(
    "/catalog",
    response_model=MealInvoiceCatalogInfoResponse,
    dependencies=[Depends(require_meal_invoice_ocr_admin)],
)
async def clear_catalog(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MealInvoiceCatalogInfoResponse:
    await run_in_threadpool(catalog.clear_catalog, workspace.id)
    return MealInvoiceCatalogInfoResponse(items=0)


_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "/export.xlsx",
    response_class=StreamingResponse,
    responses={
        200: {"content": {_XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def export_invoices(
    payload: MealInvoiceExportRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    body = await run_in_threadpool(export_documents_xlsx, payload.documents)
    return StreamingResponse(
        BytesIO(body),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": "attachment; filename=meal-invoice-ocr.xlsx",
            "Cache-Control": "no-store",
        },
    )


# JSON body 엔드포인트별 파싱-전 body 상한(위 _BodySizeLimitRoute 가 참조). export 는 이미지 없는
# 소형 payload, corrections 는 문서 이미지 총량 위. 나머지는 _DEFAULT_MAX_BODY_BYTES 백스톱.
_BODY_LIMIT_BY_ENDPOINT[export_invoices] = _MAX_EXPORT_BODY_BYTES
_BODY_LIMIT_BY_ENDPOINT[save_corrections] = _MAX_CORRECTIONS_BODY_BYTES
