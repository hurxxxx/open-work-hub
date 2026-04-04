from fastapi import APIRouter
from pydantic import BaseModel


class DraftTemplate(BaseModel):
    template_id: str
    title: str
    status: str


class DraftRecord(BaseModel):
    draft_id: str
    title: str
    export_status: str


router = APIRouter(tags=["drafts"])


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
