from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.qna.router import _qna_conversation_workspace
from dev_accounts import auth_headers, create_workspace_user_session, dev_login


def test_qna_conversation_workspace_uses_payload_workspace_key(
    client: TestClient,
) -> None:
    session = create_workspace_user_session(
        client,
        workspace_key="qna-history-workspace",
        login_id="qnahistory",
        email="qna-history@open-alm.local",
        full_name="QNA History",
    )
    with get_session_factory()() as db:
        user = db.get(User, session["user"]["id"])
        assert user is not None

        workspace = _qna_conversation_workspace(
            db,
            user,
            workspace_key="qna-history-workspace",
        )

    assert workspace is not None
    assert workspace.key == "qna-history-workspace"


def test_qna_conversation_workspace_rejects_unjoined_workspace(
    client: TestClient,
) -> None:
    admin = dev_login(client)
    create_response = client.post(
        "/api/v1/admin/workspaces",
        headers=auth_headers(admin["token"]),
        json={"key": "qna-other-workspace", "name": "QNA Other Workspace"},
    )
    assert create_response.status_code == 201, create_response.text
    session = create_workspace_user_session(
        client,
        workspace_key="qna-member-workspace",
        login_id="qnamemberonly",
        email="qna-member-only@open-alm.local",
        full_name="QNA Member Only",
    )

    with get_session_factory()() as db:
        user = db.get(User, session["user"]["id"])
        assert user is not None
        with pytest.raises(HTTPException) as exc_info:
            _qna_conversation_workspace(
                db,
                user,
                workspace_key="qna-other-workspace",
            )

    assert exc_info.value.status_code == 403
