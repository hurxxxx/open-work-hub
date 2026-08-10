from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.principal import user_principal
from open_alm_api.domains.auth.access import load_user_graph
from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.docs import service as docs_service
from open_alm_api.domains.docs.models import NativeDocPage
from open_alm_api.domains.docs.page_mutations import (
    CreateNativePageCommand,
    DeleteNativePageCommand,
    UpdateNativePageCommand,
    create_native_page,
    delete_native_page,
    update_native_page,
)
from dev_accounts import dev_login


def test_create_native_page_module_creates_html_page(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user, workspace = _load_user_and_workspace(db, session["user"]["id"])
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Page mutation doc",
        )
        db.commit()

        result = create_native_page(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.docs.page_mutations.create",
            ),
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="Uploaded HTML",
                content_format="html",
                content_text="<h1>HTML</h1>",
                content_text_present=True,
            ),
        )

    assert result.created is True
    assert result.doc_id == doc.id
    assert result.page["title"] == "Uploaded HTML"
    assert result.page["content_format"] == "html"
    assert result.page["content_text"] == "<h1>HTML</h1>"
    assert result.page["content_blocks"] is None
    assert result.page["realtime_collab"] is False


def test_create_native_page_module_rejects_content_format_mismatch(
    client: TestClient,
) -> None:
    session = dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user, workspace = _load_user_and_workspace(db, session["user"]["id"])
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Mismatch doc",
        )
        db.commit()

        with pytest.raises(HTTPException) as exc:
            create_native_page(
                db,
                workspace=workspace,
                principal=user_principal(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    source="test.docs.page_mutations.mismatch",
                ),
                user=user,
                command=CreateNativePageCommand(
                    item_id=doc.id,
                    title="Bad block page",
                    content_format="block",
                    content_text="# Should fail",
                    content_text_present=True,
                ),
            )

    assert exc.value.status_code == 400


def test_create_native_page_module_preserves_approved_call_id_idempotency(
    client: TestClient,
) -> None:
    session = dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user, workspace = _load_user_and_workspace(db, session["user"]["id"])
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Idempotent doc",
        )
        db.commit()
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="test.docs.page_mutations.idempotent",
        )

        created = create_native_page(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="Created once",
                content_format="block",
                content_blocks=[{"type": "paragraph", "content": "hello"}],
                content_blocks_present=True,
                page_id="approved-page-1",
            ),
        )
        replayed = create_native_page(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="Created once",
                content_format="block",
                content_blocks=[{"type": "paragraph", "content": "hello"}],
                content_blocks_present=True,
                page_id="approved-page-1",
            ),
        )
        rows = list(db.scalars(select(NativeDocPage).where(NativeDocPage.id == "approved-page-1")))

    assert created.created is True
    assert replayed.created is False
    assert replayed.page_id == created.page_id
    assert len(rows) == 1


def test_update_native_page_module_updates_metadata(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user, workspace = _load_user_and_workspace(db, session["user"]["id"])
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Mutable doc",
        )
        db.commit()
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="test.docs.page_mutations.update",
        )
        parent = create_native_page(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="New parent",
            ),
        )
        child = create_native_page(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="Child",
            ),
        )

        result = update_native_page(
            db,
            user=user,
            command=UpdateNativePageCommand(
                page_id=child.page_id,
                parent_id=parent.page_id,
                parent_id_present=True,
                title="Renamed child",
            ),
        )

    assert result.changed is True
    assert result.metadata_changed is True
    assert result.page["title"] == "Renamed child"
    assert result.page["parent_id"] == parent.page_id


def test_delete_native_page_module_trashes_subtree(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user, workspace = _load_user_and_workspace(db, session["user"]["id"])
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Delete subtree doc",
        )
        db.commit()
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="test.docs.page_mutations.delete",
        )
        parent = create_native_page(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="Parent",
            ),
        )
        child = create_native_page(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            command=CreateNativePageCommand(
                item_id=doc.id,
                title="Child",
                parent_id=parent.page_id,
            ),
        )

        result = delete_native_page(
            db,
            user=user,
            command=DeleteNativePageCommand(page_id=parent.page_id),
        )
        trashed_parent = db.get(NativeDocPage, parent.page_id)
        trashed_child = db.get(NativeDocPage, child.page_id)

        with pytest.raises(HTTPException) as read_error:
            docs_service.read_page(db, user=user, page_id=parent.page_id)
        with pytest.raises(HTTPException) as update_error:
            update_native_page(
                db,
                user=user,
                command=UpdateNativePageCommand(page_id=parent.page_id, title="Blocked"),
            )

    assert result.doc_id == doc.id
    assert result.page_id == parent.page_id
    assert result.media_keys == []
    assert read_error.value.status_code == 403
    assert read_error.value.detail.code == "docs.page_access_required"
    assert update_error.value.status_code == 403
    assert update_error.value.detail.code == "docs.doc_edit_access_required"
    assert trashed_parent is not None
    assert trashed_child is not None
    assert trashed_parent.trashed_at is not None
    assert trashed_child.trashed_at is not None


def test_create_native_page_module_rejects_doc_prefixed_parent_id(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user, workspace = _load_user_and_workspace(db, session["user"]["id"])
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Bad parent prefix doc",
        )
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            create_native_page(
                db,
                workspace=workspace,
                principal=user_principal(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    source="test.docs.page_mutations.bad_parent_prefix",
                ),
                user=user,
                command=CreateNativePageCommand(
                    item_id=doc.id,
                    title="Bad child",
                    parent_id=f"native_doc__{doc.id}",
                ),
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail.code == "docs.page_not_found"


def _load_user_and_workspace(db, user_id: str):
    user = load_user_graph(db, user_id)
    workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
    assert user is not None
    assert workspace is not None
    return user, workspace
