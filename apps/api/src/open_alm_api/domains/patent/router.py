from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import resolve_workspace_enabled_app_ids
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.patent import service
from open_alm_api.domains.patent.app_catalog import (
    PATENT_ANALYSIS_WORKSPACE_APP,
    PATENT_COMPOSE_WORKSPACE_APP,
)
from open_alm_api.domains.patent.schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AiSearchRequest,
    AiSearchResponse,
    AskBrainyRequest,
    AskBrainyResponse,
    ClaimsExplainRequest,
    ClaimsExplainResponse,
    DescriptionMappingRequest,
    DescriptionMappingResponse,
    ExtractResponse,
    FetchRequest,
    FetchResponse,
    FilingAssistRequest,
    FilingAssistResponse,
    InfringeCheckRequest,
    InfringeCheckResponse,
    PatentTranslateRequest,
    PatentTranslateResponse,
    PdfUrlRequest,
    PdfUrlResponse,
    ReportRequest,
    ReportResponse,
    RightsScopeRequest,
    RightsScopeResponse,
    SearchQueryRequest,
    SearchQueryResponse,
)

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024

router = APIRouter(prefix="/patent", tags=["patent"])

require_patent_compose_app_enabled = require_workspace_app_enabled(
    PATENT_COMPOSE_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)
require_patent_analysis_app_enabled = require_workspace_app_enabled(
    PATENT_ANALYSIS_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)


def require_any_patent_interactive_app_enabled(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> None:
    enabled_app_ids = set(resolve_workspace_enabled_app_ids(db, workspace.id))
    interactive_app_ids = {
        PATENT_COMPOSE_WORKSPACE_APP.app_id,
        PATENT_ANALYSIS_WORKSPACE_APP.app_id,
    }
    if enabled_app_ids.isdisjoint(interactive_app_ids):
        raise localized_http_exception(status_code=403, code="workspace.app_disabled")


@router.post(
    "/ai-search",
    response_model=AiSearchResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def ai_search(
    body: AiSearchRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> AiSearchResponse:
    return service.ai_search(
        db,
        workspace=workspace,
        user=current_user,
        query=body.query,
        page=body.page,
        applicant_filter=body.applicant_filter,
    )


@router.post(
    "/fetch",
    response_model=FetchResponse,
    dependencies=[Depends(require_any_patent_interactive_app_enabled)],
)
def fetch(
    body: FetchRequest,
    _user: User = Depends(require_current_user),
    _workspace: Workspace = Depends(require_current_workspace),
) -> FetchResponse:
    return service.fetch_patent(body.patent_number)


@router.post(
    "/translate",
    response_model=PatentTranslateResponse,
    dependencies=[Depends(require_patent_analysis_app_enabled)],
)
def translate(
    body: PatentTranslateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentTranslateResponse:
    return service.translate_texts(db, workspace=workspace, user=current_user, texts=body.texts)


@router.post(
    "/search-query",
    response_model=SearchQueryResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def search_query(
    body: SearchQueryRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SearchQueryResponse:
    return service.generate_search_query(
        db, workspace=workspace, user=current_user, tech_description=body.technology_description
    )


@router.post(
    "/report",
    response_model=ReportResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def report(
    body: ReportRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ReportResponse:
    return service.generate_report(
        db,
        workspace=workspace,
        user=current_user,
        content=body.content,
        report_type=body.report_type,
        patent_context=body.patent_context,
    )


@router.post(
    "/filing-assist",
    response_model=FilingAssistResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def filing_assist(
    body: FilingAssistRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> FilingAssistResponse:
    return service.filing_assist(
        db, workspace=workspace, user=current_user, invention=body.invention, mode=body.mode
    )


@router.post(
    "/agent-chat",
    response_model=AgentChatResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def agent_chat(
    body: AgentChatRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> AgentChatResponse:
    return service.agent_chat(
        db,
        workspace=workspace,
        user=current_user,
        message=body.message,
        context=body.context,
        history=body.history,
        conversation_id=body.conversation_id,
    )


@router.post(
    "/ask-brainy",
    response_model=AskBrainyResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def ask_brainy(
    body: AskBrainyRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> AskBrainyResponse:
    return service.ask_brainy(
        db,
        workspace=workspace,
        user=current_user,
        patent_context=body.patent_context,
        messages=body.messages,
        question=body.question,
        conversation_id=body.conversation_id,
    )


@router.post(
    "/claims-explain",
    response_model=ClaimsExplainResponse,
    dependencies=[Depends(require_patent_analysis_app_enabled)],
)
def claims_explain(
    body: ClaimsExplainRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ClaimsExplainResponse:
    return service.claims_explain(
        db,
        workspace=workspace,
        user=current_user,
        claims=body.claims,
        abstract=body.abstract,
        title=body.title,
    )


@router.post(
    "/rights-scope",
    response_model=RightsScopeResponse,
    dependencies=[Depends(require_patent_analysis_app_enabled)],
)
def rights_scope(
    body: RightsScopeRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RightsScopeResponse:
    return service.rights_scope(
        db, workspace=workspace, user=current_user, claims=body.claims, title=body.title
    )


@router.post(
    "/description-mapping",
    response_model=DescriptionMappingResponse,
    dependencies=[Depends(require_patent_analysis_app_enabled)],
)
def description_mapping(
    body: DescriptionMappingRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DescriptionMappingResponse:
    return service.description_mapping(
        db,
        workspace=workspace,
        user=current_user,
        claims=body.claims,
        description=body.description,
        abstract=body.abstract,
    )


@router.post(
    "/infringe-check",
    response_model=InfringeCheckResponse,
    dependencies=[Depends(require_patent_analysis_app_enabled)],
)
def infringe_check(
    body: InfringeCheckRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> InfringeCheckResponse:
    return service.infringe_check(
        db,
        workspace=workspace,
        user=current_user,
        claims=body.claims,
        title=body.title,
        tech_description=body.tech_description,
    )


@router.post(
    "/pdf-url",
    response_model=PdfUrlResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
def pdf_url(
    body: PdfUrlRequest,
    _user: User = Depends(require_current_user),
    _workspace: Workspace = Depends(require_current_workspace),
) -> PdfUrlResponse:
    return service.pdf_url(body.app_no, body.reg_no)


@router.post(
    "/extract",
    response_model=ExtractResponse,
    dependencies=[Depends(require_patent_compose_app_enabled)],
)
async def extract(
    file: UploadFile = File(...),
    _user: User = Depends(require_current_user),
    _workspace: Workspace = Depends(require_current_workspace),
) -> ExtractResponse:
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise localized_http_exception(status_code=413, code="patent.file_too_large")
    return await run_in_threadpool(
        service.extract_text,
        filename=file.filename or "",
        mime_type=file.content_type or "",
        content=bytes(data),
    )
