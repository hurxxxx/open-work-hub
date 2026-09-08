from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.app_availability import resolve_company_enabled_app_ids
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordSearchClient,
    KeywordSearchQuery,
)
from open_work_hub_api.domains.search.entity_adapter_registry import (
    resolve_keyword_search_scope,
)
from open_work_hub_api.domains.search.projections import all_search_documents
from open_work_hub_api.domains.search.service import _search_client


def verify_keyword_index(
    client: KeywordSearchClient,
    *,
    allowed_entity_types: tuple[str, ...],
    expected_active_document_counts: Mapping[str, int],
) -> int:
    if not client.index_exists():
        raise RuntimeError("Keyword search index is not initialized.")

    document_count = client.count_company_documents()
    for entity_type in allowed_entity_types:
        expected_count = expected_active_document_counts.get(entity_type, 0)
        indexed_count = client.count_company_documents(
            entity_types=(entity_type,),
        )
        if indexed_count != expected_count:
            raise RuntimeError(
                f"keyword smoke failed for company sources: active entity {entity_type} "
                f"expected {expected_count} projection document(s), "
                f"but the index has {indexed_count}"
            )
    expected_active_document_count = sum(expected_active_document_counts.values())
    if expected_active_document_count == 0:
        return document_count

    result = client.search(
        KeywordSearchQuery(
            entity_types=allowed_entity_types,
            size=1,
        )
    )
    if not result.hits:
        raise RuntimeError(
            f"keyword smoke failed for company sources: expected "
            f"{expected_active_document_count} active projection document(s), "
            "but search returned no active entity hits"
        )
    source = result.hits[0].document
    if str(source.get("entity_type") or "") not in allowed_entity_types:
        raise RuntimeError(
            "keyword smoke failed for company sources: search returned a disabled entity type"
        )
    return document_count


def main() -> None:
    argparse.ArgumentParser(
        description="Verify registered company keyword source documents."
    ).parse_args()
    with get_session_factory()() as db:
        scope = resolve_keyword_search_scope(resolve_company_enabled_app_ids(db))
        counts = Counter(
            str(row.get("entity_type") or "")
            for row in all_search_documents(db)
            if str(row.get("entity_type") or "") in scope.entity_types
        )
        count = verify_keyword_index(
            _search_client(),
            allowed_entity_types=scope.entity_types,
            expected_active_document_counts=counts,
        )
        print(f"Verified keyword index: {count} document(s).")


if __name__ == "__main__":
    main()
