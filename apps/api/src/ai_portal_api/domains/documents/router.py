from fastapi import APIRouter
from pydantic import BaseModel, Field


class SearchDocumentsRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)


class SearchHit(BaseModel):
    document_id: str
    title: str
    summary: str
    source_type: str
    score: float


class SearchDocumentsResponse(BaseModel):
    scenario_id: str = "documents-rag"
    hits: list[SearchHit]
    next_actions: list[str]


router = APIRouter(prefix="/search", tags=["documents"])


@router.post("/documents", response_model=SearchDocumentsResponse)
def search_documents(payload: SearchDocumentsRequest) -> SearchDocumentsResponse:
    query = payload.query.strip()
    hit = SearchHit(
        document_id="doc-spec-001",
        title="KX-21 Compressor Specification",
        summary=f"Scaffold hit for query '{query}'. Replace with OpenSearch + Qdrant retrieval.",
        source_type="spec",
        score=0.94,
    )
    return SearchDocumentsResponse(
        hits=[hit],
        next_actions=[
            "wire hybrid retrieval",
            "attach citation blocks",
            "add reranker and ACL filter",
        ],
    )
