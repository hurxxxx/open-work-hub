from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from typing import Protocol

from sqlalchemy import select

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.auth.access import resolve_workspace_enabled_app_ids
from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.search.backend_contracts import KeywordSearchClient, KeywordSearchQuery
from open_alm_api.domains.search.entity_adapter_registry import (
    resolve_workspace_keyword_search_scope,
)
from open_alm_api.domains.search.projections import all_workspace_search_documents
from open_alm_api.domains.search.service import _search_client


class WorkspaceLike(Protocol):
    id: str
    key: str


def verify_workspace_keyword_index(
    client: KeywordSearchClient,
    *,
    workspace: WorkspaceLike,
    allowed_entity_types: tuple[str, ...],
    expected_active_document_counts: Mapping[str, int],
) -> int:
    if not client.index_exists():
        raise RuntimeError("Keyword search index is not initialized.")

    document_count = client.count_workspace_documents(workspace_id=workspace.id)
    for entity_type in allowed_entity_types:
        expected_count = expected_active_document_counts.get(entity_type, 0)
        indexed_count = client.count_workspace_documents(
            workspace_id=workspace.id,
            entity_types=(entity_type,),
        )
        if indexed_count != expected_count:
            raise RuntimeError(
                f"keyword smoke failed for {workspace.key}: active entity {entity_type} "
                f"expected {expected_count} projection document(s), "
                f"but the workspace index has {indexed_count}"
            )
    expected_active_document_count = sum(expected_active_document_counts.values())
    if expected_active_document_count == 0:
        return document_count

    result = client.search(
        KeywordSearchQuery(
            workspace_id=workspace.id,
            entity_types=allowed_entity_types,
            size=1,
        )
    )
    if not result.hits:
        raise RuntimeError(
            f"keyword smoke failed for {workspace.key}: expected "
            f"{expected_active_document_count} active projection document(s), "
            "but search returned no active entity hits"
        )
    source = result.hits[0].document
    if str(source.get("workspace_id") or "") != workspace.id:
        raise RuntimeError(
            f"keyword smoke failed for {workspace.key}: search returned a different workspace"
        )
    if str(source.get("entity_type") or "") not in allowed_entity_types:
        raise RuntimeError(
            f"keyword smoke failed for {workspace.key}: search returned a disabled entity type"
        )
    return document_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test workspace-scoped keyword search documents."
    )
    parser.add_argument(
        "--workspace-key",
        action="append",
        default=[],
        help="Workspace key to verify. Can be passed more than once.",
    )
    parser.add_argument(
        "--all-active",
        action="store_true",
        help="Verify all active workspaces.",
    )
    args = parser.parse_args()
    workspace_keys = [key.strip() for key in args.workspace_key if key.strip()]
    if args.all_active and workspace_keys:
        raise SystemExit("Use either --all-active or --workspace-key, not both.")
    if not args.all_active and not workspace_keys:
        raise SystemExit("Pass at least one --workspace-key or use --all-active.")

    client = _search_client()
    with get_session_factory()() as db:
        query = select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.key.asc())
        if not args.all_active:
            query = query.where(Workspace.key.in_(workspace_keys))
        workspaces = list(db.scalars(query))
        if not workspaces:
            raise SystemExit("No matching active workspaces found.")
        if not args.all_active:
            missing = sorted(set(workspace_keys) - {workspace.key for workspace in workspaces})
            if missing:
                raise SystemExit(f"No matching active workspaces: {', '.join(missing)}")
        for workspace in workspaces:
            scope = resolve_workspace_keyword_search_scope(
                resolve_workspace_enabled_app_ids(db, workspace.id)
            )
            allowed_entity_types = frozenset(scope.entity_types)
            expected_active_document_counts = Counter(
                str(document.get("entity_type") or "")
                for document in all_workspace_search_documents(db, workspace=workspace)
                if str(document.get("entity_type") or "") in allowed_entity_types
            )
            try:
                document_count = verify_workspace_keyword_index(
                    client,
                    workspace=workspace,
                    allowed_entity_types=scope.entity_types,
                    expected_active_document_counts=expected_active_document_counts,
                )
            except RuntimeError as error:
                raise SystemExit(str(error)) from error
            print(
                f"Verified keyword search for workspace {workspace.key}: "
                f"{document_count} indexed document(s)."
            )


if __name__ == "__main__":
    main()
