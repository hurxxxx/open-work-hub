from fastapi.testclient import TestClient

from dev_accounts import dev_login

from open_alm_api.domains.docs.collab import make_page_ref
from open_alm_api.domains.docs.content_text import extract_page_text


def test_block_doc_rejects_initial_content_text(
    client: TestClient,
) -> None:
    session = dev_login(client)
    token = session["token"]
    workspace_slug = session["user"]["workspaces"][0]["slug"]

    create_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(token),
        json={
            "title": "Block Doc",
            "content_format": "block",
            "first_page_content_text": "# Should not be accepted",
        },
    )
    assert create_response.status_code == 400
    assert create_response.json()["code"] == "docs.content_format_mismatch"


def test_doc_pages_own_content_format_and_allow_mixed_docs(
    client: TestClient,
) -> None:
    session = dev_login(client)
    token = session["token"]
    workspace_slug = session["user"]["workspaces"][0]["slug"]
    html = "<!doctype html><html><body><h1>HTML Guide</h1><script>hidden()</script></body></html>"

    create_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(token),
        json={
            "title": "Mixed Doc",
            "content_format": "block",
        },
    )
    assert create_response.status_code == 201, create_response.text
    doc = create_response.json()
    assert doc["content_format"] == "block"

    pages_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(token),
    )
    assert pages_response.status_code == 200, pages_response.text
    block_page = pages_response.json()["items"][0]
    assert block_page["content_format"] == "block"
    assert block_page["realtime_collab"] is True

    create_html_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(token),
        json={"title": "Uploaded HTML", "content_format": "html", "content_text": html},
    )
    assert create_html_response.status_code == 201, create_html_response.text
    html_page = create_html_response.json()
    assert html_page["content_format"] == "html"
    assert html_page["content_text"] == html
    assert html_page["content_blocks"] is None
    assert html_page["realtime_collab"] is False

    mixed_doc_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}",
        headers=_auth_headers(token),
    )
    assert mixed_doc_response.status_code == 200, mixed_doc_response.text
    assert mixed_doc_response.json()["content_format"] == "mixed"

    block_patch_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/pages/{html_page['id']}",
        headers=_auth_headers(token),
        json={"content_blocks": [{"type": "paragraph", "content": "blocked"}]},
    )
    assert block_patch_response.status_code == 400
    assert block_patch_response.json()["code"] == "docs.content_format_mismatch"

    html_patch_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/pages/{html_page['id']}",
        headers=_auth_headers(token),
        json={"content_text": html},
    )
    assert html_patch_response.status_code == 200, html_patch_response.text
    assert html_patch_response.json()["content_text"] == html

    block_text_patch_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/pages/{block_page['id']}",
        headers=_auth_headers(token),
        json={"content_text": html},
    )
    assert block_text_patch_response.status_code == 400
    assert block_text_patch_response.json()["code"] == "docs.content_format_mismatch"

    page_ref = make_page_ref(html_page["source_type"], html_page["source_page_id"])
    collab_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session",
        headers=_auth_headers(token),
    )
    assert collab_response.status_code == 404


def test_markdown_doc_format_is_rejected(
    client: TestClient,
) -> None:
    session = dev_login(client)
    token = session["token"]
    workspace_slug = session["user"]["workspaces"][0]["slug"]

    create_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(token),
        json={
            "title": "Markdown Doc",
            "content_format": "markdown",
        },
    )
    assert create_response.status_code == 422


def test_content_text_extracts_indexable_html_and_block_content() -> None:
    assert extract_page_text(
        content_format="html",
        content_blocks=None,
        content_text="<h1>Visible</h1><script>hidden</script><style>.x{}</style><p>Body</p>",
        block_extractor=lambda _blocks: "unused",
    ) == "Visible Body"
    assert extract_page_text(
        content_format="block",
        content_blocks=[{"type": "paragraph"}],
        content_text=None,
        block_extractor=lambda blocks: f"blocks:{len(blocks or [])}",
    ) == "blocks:1"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
