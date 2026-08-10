from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.writing_assistant.app_catalog import DRAFTING_WORKSPACE_APP


class DraftTemplate(BaseModel):
    template_id: str
    title: str
    status: str


class DraftRecord(BaseModel):
    draft_id: str
    title: str
    export_status: str


require_drafting_app_enabled = require_workspace_app_enabled(
    DRAFTING_WORKSPACE_APP.app_id,
    error_code="writing_assistant.app_disabled",
)

router = APIRouter(
    tags=["drafts"],
    dependencies=[Depends(require_drafting_app_enabled)],
)


@router.get("/templates", response_model=list[DraftTemplate])
def list_templates() -> list[DraftTemplate]:
    return [
        DraftTemplate(
            template_id="tpl-project-summary",
            title="Project Summary",
            status="ready",
        ),
        DraftTemplate(
            template_id="tpl-risk-review",
            title="Risk Review Memo",
            status="needs-fields",
        ),
    ]


@router.get("/drafts", response_model=list[DraftRecord])
def list_drafts() -> list[DraftRecord]:
    return [
        DraftRecord(draft_id="draft-001", title="Project A Summary", export_status="queued"),
    ]
