from __future__ import annotations

from fastapi import APIRouter

from open_alm_api.domains.documents.search_projection import (
    SearchDocumentsRequest,
    SearchDocumentsResponse,
    build_search_documents_response,
)

router = APIRouter(prefix="/search", tags=["documents"])


@router.post("/documents", response_model=SearchDocumentsResponse)
def search_documents(payload: SearchDocumentsRequest) -> SearchDocumentsResponse:
    return build_search_documents_response(payload)
