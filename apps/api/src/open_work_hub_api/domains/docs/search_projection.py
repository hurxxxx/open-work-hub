from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.domains.auth.models import Team, Workspace
from open_work_hub_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP
from open_work_hub_api.domains.docs.content_text import extract_page_text
from open_work_hub_api.domains.docs.models import DocMeetingAccess, NativeDoc, NativeDocPage
from open_work_hub_api.domains.pms.models import TaskList
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    DOCS_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.search.index_document import (
    build_search_document,
    extract_blocks_text,
    search_person,
    trim_search_text,
)
from open_work_hub_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    SearchIndexLifecycleHooks,
)
from open_work_hub_api.domains.search.schemas import SearchEntityType
from open_work_hub_api.domains.source_access.resource_types import NATIVE_DOC_RESOURCE_TYPE


def load_docs_search_document(db: Session, source_id: str) -> dict[str, Any] | None:
    doc = db.scalar(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.targets),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.meeting_access_grants),
        )
        .where(NativeDoc.id == source_id, NativeDoc.trashed_at.is_(None))
    )
    if doc is None:
        return None
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == doc.workspace_id, Workspace.active.is_(True))
    )
    if workspace is None:
        return None
    return _doc_row(db, workspace=workspace, doc=doc)


def load_workspace_docs_search_documents(
    db: Session, *, workspace: Workspace
) -> list[dict[str, Any]]:
    docs = db.scalars(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.targets),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.meeting_access_grants),
        )
        .where(NativeDoc.workspace_id == workspace.id, NativeDoc.trashed_at.is_(None))
    ).all()
    return [_doc_row(db, workspace=workspace, doc=doc) for doc in docs]


def load_docs_search_document_for_entity(
    db: Session,
    *,
    entity_type: SearchEntityType,
    entity_id: str,
) -> dict[str, Any] | None:
    if entity_type != SearchEntityType.DOC:
        return None
    return load_docs_search_document(db, entity_id)


def _doc_row(db: Session, *, workspace: Workspace, doc: NativeDoc) -> dict[str, Any]:
    task_list_team_ids = _task_list_team_lookup(db, workspace)
    active_link_shares = [share for share in doc.link_shares if share.active]
    body_parts = []
    active_pages = sorted(
        (page for page in doc.pages if page.trashed_at is None),
        key=_doc_page_sort_key,
    )
    doc_pages = []
    for page in active_pages:
        page_text = extract_page_text(
            content_format=page.content_format,
            content_blocks=page.content_blocks,
            content_text=page.content_text,
            block_extractor=extract_blocks_text,
        )
        body_parts.append(page.title)
        body_parts.append(page_text)
        doc_pages.append({"id": page.id, "title": page.title, "text": page_text})
    targets = [
        {
            "app": target.target_app,
            "type": target.target_type,
            "id": target.target_id,
            "label": _target_label(
                target.target_app,
                target.target_type,
                target.target_id,
            ),
        }
        for target in doc.targets
    ]
    row = build_search_document(
        workspace_id=workspace.id,
        entity_type=SearchEntityType.DOC,
        entity_id=doc.id,
        title=doc.title,
        summary=trim_search_text(" ".join(part for part in body_parts if part), 240),
        body="\n".join(part for part in body_parts if part),
        keywords=" ".join(
            [doc.source_kind, doc.source_app, getattr(doc.owner, "full_name", "") or ""]
        ),
        status=None,
        status_label=None,
        visibility="shared" if doc.user_shares or active_link_shares else "private",
        people=[search_person("owner", doc.owner_id, getattr(doc.owner, "full_name", None))],
        targets=targets,
        owner_user_id=doc.owner_id,
        team_ids=_target_team_ids(targets, task_list_team_ids),
        participant_user_ids=[],
        shared_user_ids=[share.user_id for share in doc.user_shares],
        granted_user_ids=_active_doc_grant_user_ids(doc.meeting_access_grants),
        date_markers={},
        deep_link=_with_query_param(
            f"/w/{workspace.key}/docs/{doc.id}",
            "page",
            doc_pages[0]["id"] if doc_pages else None,
        ),
        metadata={"source_kind": doc.source_kind, "source_ref": doc.source_ref},
        source_updated_at=doc.updated_at,
    )
    row["doc_pages"] = doc_pages
    return row


def _doc_page_sort_key(page: NativeDocPage) -> tuple[int, datetime, str]:
    return (page.sort_order, page.created_at, page.id)


def _with_query_param(url: str, key: str, value: str | None) -> str:
    if not value:
        return url
    parts = urlsplit(url)
    query = [
        (item_key, item_value)
        for item_key, item_value in parse_qsl(parts.query, keep_blank_values=True)
        if item_key != key
    ]
    query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _task_list_team_lookup(db: Session, workspace: Workspace) -> dict[str, str]:
    rows = db.execute(
        select(TaskList.id, TaskList.team_id)
        .join(Team, TaskList.team_id == Team.id)
        .where(Team.workspace_id == workspace.id, TaskList.team_id.is_not(None))
    ).all()
    return {list_id: team_id for list_id, team_id in rows if team_id}


def _target_team_ids(
    targets: list[dict[str, str]], task_list_team_ids: dict[str, str]
) -> list[str]:
    team_ids: list[str] = []
    for target in targets:
        target_app = target.get("app")
        target_type = target.get("type")
        target_id = target.get("id")
        if not target_id:
            continue
        if target_app == "pms" and target_type == "space":
            team_ids.append(target_id)
        if target_app == "pms" and target_type == "list" and target_id in task_list_team_ids:
            team_ids.append(task_list_team_ids[target_id])
    return team_ids


def _active_doc_grant_user_ids(grants: list[DocMeetingAccess]) -> list[str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    return [
        grant.user_id
        for grant in grants
        if grant.revoked_at is None and (grant.expires_at is None or grant.expires_at > now)
    ]


def _target_label(app: str, kind: str, item_id: str) -> str:
    return f"{app}:{kind}:{item_id}"


DOCS_WORKSPACE_KEYWORD_SEARCH_ADAPTER = SearchEntityAdapter(
    owner_app=DOCS_WORKSPACE_APP,
    entity_type=SearchEntityType.DOC.value,
    resource_type=NATIVE_DOC_RESOURCE_TYPE,
    label="문서",
    label_key="ai.search.entityDoc",
    workspace_loader=load_workspace_docs_search_documents,
    document_loader=load_docs_search_document_for_entity,
    partition_adapter_id=DOCS_RETRIEVAL_PARTITION_ADAPTER_ID,
    index_hooks=SearchIndexLifecycleHooks(
        create=("docs.enqueue_doc_search_index",),
        update=(
            "docs.enqueue_doc_search_index",
            "docs.enqueue_doc_search_index_by_id",
        ),
        delete=("docs.enqueue_doc_search_index",),
    ),
    person_roles=("owner", "participant"),
)


__all__ = [
    "DOCS_WORKSPACE_KEYWORD_SEARCH_ADAPTER",
    "load_docs_search_document",
    "load_docs_search_document_for_entity",
    "load_workspace_docs_search_documents",
]
