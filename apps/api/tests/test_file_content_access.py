from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.exceptions import HTTPException

from open_work_hub_api.domains.content_access import grants
from open_work_hub_api.domains.content_access.grants import (
    ContentGrantIssuer,
    InvalidContentGrant,
    decode_content_grant,
)
from open_work_hub_api.domains.files import content_access
from open_work_hub_api.domains.files.content_access import (
    build_file_content_url,
    is_previewable_image,
    open_file_content_grant,
)
from open_work_hub_api.domains.files.models import FileManagerCorpus, FileManagerFile


_USER_ID = "user-1"
_SESSION_ID = "session-1"
_WORKSPACE_ID = "workspace-1"


def _settings() -> SimpleNamespace:
    return SimpleNamespace(api_prefix="/api/v1", minio_secret_key="test-secret")


def _file(**overrides: object) -> FileManagerFile:
    values = {
        "id": "file-1",
        "workspace_id": _WORKSPACE_ID,
        "folder_id": None,
        "owner_id": _USER_ID,
        "filename": "diagram final.png",
        "content_type": "image/png; charset=binary",
        "size_bytes": 9,
        "storage_key": "objects/file-1",
        "visibility": "private",
    }
    values.update(overrides)
    return FileManagerFile(**values)


def _corpus(*, scope: str = "company", metadata_version: int = 1) -> FileManagerCorpus:
    return FileManagerCorpus(
        id="corpus-1",
        name="Company handbook",
        managed_workspace_id=_WORKSPACE_ID,
        access_scope_kind=scope,
        retrieval_partition_id="11111111-1111-1111-1111-111111111111",
        created_by_id=_USER_ID,
        metadata_version=metadata_version,
    )


class _FakeDb:
    def __init__(self, file: FileManagerFile | None) -> None:
        self.file = file
        self.user = SimpleNamespace(id=_USER_ID, status="active", login_blocked=False)
        self.workspace = SimpleNamespace(id=_WORKSPACE_ID, active=True)

    def scalar(self, _statement: object) -> FileManagerFile | None:
        return self.file

    def get(self, model, identity):
        if model is content_access.User and identity == _USER_ID:
            return self.user
        if model is content_access.Workspace and identity == _WORKSPACE_ID:
            return self.workspace
        return None


class _FakeObject:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.closed = False
        self.released = False

    def stream(self, _chunk_size: int):
        yield from self.chunks

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


def _claims(monkeypatch, file: FileManagerFile, *, disposition="attachment"):
    monkeypatch.setattr(grants, "get_settings", _settings)
    url = build_file_content_url(
        file,
        issuer=ContentGrantIssuer(user_id=_USER_ID, session_id=_SESSION_ID),
        execution_workspace_id=_WORKSPACE_ID,
        disposition=disposition,
        now=100,
        expires_seconds=60,
    )
    token = parse_qs(urlparse(url).fragment)["grant"][0]
    return url, decode_content_grant(token, now=100)


def _allow_source(monkeypatch, file: FileManagerFile) -> None:
    monkeypatch.setattr(
        content_access.files_service,
        "require_file_access",
        lambda db, *, workspace, user, file_id: file,
    )


def test_file_content_url_uses_single_grant_route_and_bound_claims(monkeypatch) -> None:
    file = _file()
    url, claims = _claims(monkeypatch, file, disposition="inline")

    assert urlparse(url).path == "/api/v1/content"
    assert claims.resource_kind == "files.file"
    assert claims.owner_app_id == "files"
    assert claims.issuer_session_id == _SESSION_ID
    assert claims.execution_context_kind == "workspace"
    assert claims.execution_workspace_id == _WORKSPACE_ID
    assert claims.disposition == "inline"
    assert claims.expires == 160


def test_previewable_image_accepts_only_safe_raster_types() -> None:
    for content_type in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        assert is_previewable_image(_file(content_type=content_type))
    for content_type in ("image/svg+xml", "image/avif", "application/pdf"):
        assert not is_previewable_image(_file(content_type=content_type))


def test_open_file_grant_rechecks_workspace_app_and_source_acl(monkeypatch) -> None:
    file = _file()
    _, claims = _claims(monkeypatch, file, disposition="inline")
    storage_object = _FakeObject([b"\x89PNG\r\n\x1a\n", b"png-bytes"])
    monkeypatch.setattr(content_access, "open_file_object", lambda _key: storage_object)
    monkeypatch.setattr(content_access, "is_app_enabled_for_user_context", lambda *a, **k: True)
    _allow_source(monkeypatch, file)

    stream = open_file_content_grant(_FakeDb(file), claims=claims)

    assert stream.media_type == "image/png"
    assert stream.headers["Cache-Control"] == "private, no-store"
    assert list(stream.body) == [b"\x89PNG\r\n\x1a\n", b"png-bytes"]
    assert storage_object.closed and storage_object.released


def test_workspace_app_revoke_invalidates_grant_before_source_access(monkeypatch) -> None:
    file = _file()
    _, claims = _claims(monkeypatch, file)
    monkeypatch.setattr(content_access, "is_app_enabled_for_user_context", lambda *a, **k: False)
    monkeypatch.setattr(
        content_access.files_service,
        "require_file_access",
        lambda *a, **k: pytest.fail("disabled app must fail before source ACL"),
    )

    with pytest.raises(InvalidContentGrant, match="app"):
        open_file_content_grant(_FakeDb(file), claims=claims)


def test_company_corpus_uses_company_gate_without_workspace_membership(monkeypatch) -> None:
    corpus = _corpus()
    file = _file(corpus_id=corpus.id)
    file.corpus = corpus
    _, claims = _claims(monkeypatch, file)
    storage_object = _FakeObject([b"company"])
    monkeypatch.setattr(content_access, "open_file_object", lambda _key: storage_object)
    monkeypatch.setattr(
        content_access,
        "is_company_app_enabled_for_user_context",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        content_access,
        "is_app_enabled_for_user_context",
        lambda *a, **k: pytest.fail("company corpus must not use workspace membership gate"),
    )
    _allow_source(monkeypatch, file)

    assert list(open_file_content_grant(_FakeDb(file), claims=claims).body) == [b"company"]


def test_corpus_transition_and_object_replacement_revoke_existing_grants(monkeypatch) -> None:
    corpus = _corpus(metadata_version=1)
    file = _file(corpus_id=corpus.id)
    file.corpus = corpus
    _, transition_claims = _claims(monkeypatch, file)
    corpus.access_scope_kind = "workspace"
    corpus.metadata_version = 2
    with pytest.raises(InvalidContentGrant, match="binding"):
        open_file_content_grant(_FakeDb(file), claims=transition_claims)

    replacement = _file()
    _, object_claims = _claims(monkeypatch, replacement)
    replacement.storage_key = "objects/replacement"
    with pytest.raises(InvalidContentGrant, match="binding"):
        open_file_content_grant(_FakeDb(replacement), claims=object_claims)


def test_inline_svg_and_spoofed_raster_are_rejected(monkeypatch) -> None:
    svg = _file(content_type="image/svg+xml")
    _, svg_claims = _claims(monkeypatch, svg, disposition="inline")
    monkeypatch.setattr(content_access, "is_app_enabled_for_user_context", lambda *a, **k: True)
    _allow_source(monkeypatch, svg)
    with pytest.raises(InvalidContentGrant, match="disposition"):
        open_file_content_grant(_FakeDb(svg), claims=svg_claims)

    spoofed = _file(content_type="image/png")
    _, spoofed_claims = _claims(monkeypatch, spoofed, disposition="inline")
    storage_object = _FakeObject([b"<svg xmlns='http://www.w3.org/2000/svg'>"])
    monkeypatch.setattr(content_access, "open_file_object", lambda _key: storage_object)
    _allow_source(monkeypatch, spoofed)
    with pytest.raises(HTTPException) as error:
        open_file_content_grant(_FakeDb(spoofed), claims=spoofed_claims)
    assert error.value.status_code == 415
    assert storage_object.closed and storage_object.released
