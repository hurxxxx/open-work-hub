from fastapi import APIRouter
from pydantic import BaseModel, Field


class SearchPlmRequest(BaseModel):
    query: str = Field(..., min_length=1)
    preview_only: bool = True


class PlmRow(BaseModel):
    item_code: str
    status: str
    owner: str


class SearchPlmResponse(BaseModel):
    scenario_id: str = "plm-query"
    sql_preview: str
    result_summary: str
    result_table: list[PlmRow]
    warnings: list[str]


router = APIRouter(prefix="/search", tags=["plm"])


@router.post("/plm", response_model=SearchPlmResponse)
def search_plm(payload: SearchPlmRequest) -> SearchPlmResponse:
    return SearchPlmResponse(
        sql_preview=(
            "select item_code, status, owner from vw_release_delay "
            "where status = 'Delayed' order by owner"
        ),
        result_summary=f"Scaffold preview for '{payload.query}'. Replace with template match + validator.",
        result_table=[
            PlmRow(item_code="ECO-991", status="Delayed", owner="Kim"),
            PlmRow(item_code="BOM-214", status="Open", owner="Lee"),
        ],
        warnings=["preview_only route", "validator not wired yet"],
    )
