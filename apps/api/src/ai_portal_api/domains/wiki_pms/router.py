from fastapi import APIRouter
from pydantic import BaseModel


class WikiPage(BaseModel):
    page_id: str
    title: str
    status: str


router = APIRouter(prefix="/wiki", tags=["wiki-pms"])


@router.get("/pages", response_model=list[WikiPage])
def list_pages() -> list[WikiPage]:
    return [
        WikiPage(page_id="wiki-001", title="Release Policy", status="published"),
        WikiPage(page_id="wiki-002", title="Supplier Risk Review", status="draft"),
    ]
