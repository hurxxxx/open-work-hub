from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.exceptions import HTTPException

from open_alm_api.domains.files import content_access
from open_alm_api.domains.files.content_access import (
    build_file_content_url,
    is_previewable_image,
    open_file_content,
    sign_file_content_url,
)
from open_alm_api.domains.files.models import FileManagerCorpus, FileManagerFile


_ISSUER_USER_ID = "user-1"
_EXECUTION_WORKSPACE_ID = "workspace-1"
_SIGNING_CONTEXT = {
    "issuer_user_id": _ISSUER_USER_ID,
    "execution_workspace_id": _EXECUTION_WORKSPACE_ID,
}


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        api_prefix="/api/v1",
        minio_bucket="files-bucket",
        minio_secret_key="test-secret",
    )


def _file(**overrides: object) -> FileManagerFile:
    values = {
        "id": "file-1",
        "workspace_id": "workspace-1",
        "folder_id": None,
        "owner_id": "user-1",
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
        managed_workspace_id="workspace-1",
        access_scope_kind=scope,
        retrieval_partition_id="11111111-1111-1111-1111-111111111111",
        created_by_id="user-1",
        metadata_version=metadata_version,
    )


class _FakeDb:
    def __init__(
        self,
        file: FileManagerFile | None,
        *,
        user: object | None = None,
        workspace: object | None = None,
    ) -> None:
        self.file = file
        self.user = user or SimpleNamespace(
            id=_ISSUER_USER_ID,
            status="active",
            login_blocked=False,
        )
        self.workspace = workspace or SimpleNamespace(
            id=_EXECUTION_WORKSPACE_ID,
            active=True,
        )

    def scalar(self, _statement: object) -> FileManagerFile | None:
        return self.file

    def get(self, model, identity):
        if model is content_access.User and identity == _ISSUER_USER_ID:
            return self.user
        if model is content_access.Workspace and identity == _EXECUTION_WORKSPACE_ID:
            return self.workspace
        return None


class _FakeObject:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.chunk_size: int | None = None
        self.closed = False
        self.released = False

    def stream(self, chunk_size: int):
        self.chunk_size = chunk_size
        yield from self.chunks

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


def test_file_content_url_is_signed_with_expiry_and_disposition(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file()

    url = build_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        disposition="inline",
        now=100,
        expires_seconds=60,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/api/v1/files/content/file-1"
    assert query == {
        "expires": ["160"],
        "disposition": ["inline"],
        "signature": [
            sign_file_content_url(
                file,
                **_SIGNING_CONTEXT,
                expires=160,
                disposition="inline",
            ),
        ],
    }


def test_file_content_url_defaults_to_short_bearer_capability_ttl(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)

    url = build_file_content_url(
        _file(),
        **_SIGNING_CONTEXT,
        disposition="attachment",
        now=100,
    )

    assert parse_qs(urlparse(url).query)["expires"] == ["400"]


def test_previewable_image_accepts_image_content_type_parameters() -> None:
    assert is_previewable_image(_file(content_type=" Image/PNG ; charset=binary"))
    assert is_previewable_image(_file(content_type="image/jpeg"))
    assert is_previewable_image(_file(content_type="image/gif"))
    assert is_previewable_image(_file(content_type="image/webp"))
    assert not is_previewable_image(_file(content_type="image/svg+xml"))
    assert not is_previewable_image(_file(content_type="image/avif"))
    assert not is_previewable_image(_file(content_type="application/pdf"))


def test_open_file_content_verifies_signature_and_streams_object(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file()
    signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="inline",
    )
    storage_object = _FakeObject([b"\x89PNG\r\n\x1a\n", b"png-bytes"])
    monkeypatch.setattr(content_access, "open_file_object", lambda key: storage_object)
    monkeypatch.setattr(
        content_access, "resolve_workspace_role", lambda db, user, workspace_id: "member"
    )
    authorization_calls: list[tuple[str, str, str]] = []

    def require_file_access(db, *, workspace, user, file_id):
        authorization_calls.append((workspace.id, user.id, file_id))
        return file

    monkeypatch.setattr(content_access.files_service, "require_file_access", require_file_access)

    stream = open_file_content(
        _FakeDb(file),
        file_id=file.id,
        expires=200,
        signature=signature,
        disposition="inline",
        now=100,
    )

    assert stream.media_type == "image/png"
    assert stream.headers["Cache-Control"] == "private, no-store"
    assert stream.headers["Content-Disposition"].startswith("inline;")
    assert "diagram%20final.png" in stream.headers["Content-Disposition"]
    assert list(stream.body) == [b"\x89PNG\r\n\x1a\n", b"png-bytes"]
    assert storage_object.chunk_size == content_access.FILE_CONTENT_CHUNK_SIZE
    assert storage_object.closed
    assert storage_object.released
    assert authorization_calls == [(_EXECUTION_WORKSPACE_ID, _ISSUER_USER_ID, file.id)]


@pytest.mark.parametrize(
    ("content_type", "payload"),
    [
        ("image/png", b"\x89PNG\r\n\x1a\nrest"),
        ("image/jpeg", b"\xff\xd8\xff\xe0rest"),
        ("image/gif", b"GIF89arest"),
        ("image/webp", b"RIFF\x04\x00\x00\x00WEBPrest"),
    ],
)
def test_safe_inline_image_signatures_match_declared_content_type(
    content_type: str,
    payload: bytes,
) -> None:
    assert content_access._matches_inline_image_signature(
        content_type=content_type,
        prefix=payload[: content_access._INLINE_IMAGE_SIGNATURE_BYTES],
    )


def test_svg_is_never_opened_for_inline_preview(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file(filename="payload.svg", content_type="image/svg+xml")
    signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="inline",
    )
    monkeypatch.setattr(
        content_access, "resolve_workspace_role", lambda db, user, workspace_id: "member"
    )
    monkeypatch.setattr(
        content_access.files_service,
        "require_file_access",
        lambda db, *, workspace, user, file_id: file,
    )
    monkeypatch.setattr(
        content_access,
        "open_file_object",
        lambda key: pytest.fail("active image formats must be rejected before storage access"),
    )

    with pytest.raises(HTTPException) as exc:
        open_file_content(
            _FakeDb(file),
            file_id=file.id,
            expires=200,
            signature=signature,
            disposition="inline",
            now=100,
        )

    assert exc.value.status_code == 415
    assert exc.value.detail.code == "files.preview_unsupported_type"


def test_inline_preview_rejects_spoofed_raster_content_and_releases_object(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file(content_type="image/png")
    signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="inline",
    )
    storage_object = _FakeObject([b"<svg xmlns='http://www.w3.org/2000/svg'>"])
    monkeypatch.setattr(content_access, "open_file_object", lambda key: storage_object)
    monkeypatch.setattr(
        content_access, "resolve_workspace_role", lambda db, user, workspace_id: "member"
    )
    monkeypatch.setattr(
        content_access.files_service,
        "require_file_access",
        lambda db, *, workspace, user, file_id: file,
    )

    with pytest.raises(HTTPException) as exc:
        open_file_content(
            _FakeDb(file),
            file_id=file.id,
            expires=200,
            signature=signature,
            disposition="inline",
            now=100,
        )

    assert exc.value.status_code == 415
    assert exc.value.detail.code == "files.preview_unsupported_type"
    assert storage_object.closed
    assert storage_object.released


def test_spoofed_raster_content_remains_downloadable_as_attachment(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file(content_type="image/png")
    signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="attachment",
    )
    payload = b"<svg xmlns='http://www.w3.org/2000/svg'>"
    storage_object = _FakeObject([payload])
    monkeypatch.setattr(content_access, "open_file_object", lambda key: storage_object)
    monkeypatch.setattr(
        content_access, "resolve_workspace_role", lambda db, user, workspace_id: "member"
    )
    monkeypatch.setattr(
        content_access.files_service,
        "require_file_access",
        lambda db, *, workspace, user, file_id: file,
    )

    stream = open_file_content(
        _FakeDb(file),
        file_id=file.id,
        expires=200,
        signature=signature,
        disposition="attachment",
        now=100,
    )

    assert stream.headers["Content-Disposition"].startswith("attachment;")
    assert list(stream.body) == [payload]
    assert storage_object.closed
    assert storage_object.released


def test_open_file_content_rejects_invalid_signature(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)

    with pytest.raises(HTTPException) as exc:
        open_file_content(
            _FakeDb(_file()),
            file_id="file-1",
            expires=200,
            signature="invalid",
            disposition="attachment",
            now=100,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail.code == "files.proxy_url_invalid"


def test_company_corpus_transition_invalidates_existing_content_url(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    corpus = _corpus(scope="company", metadata_version=1)
    file = _file(corpus_id=corpus.id)
    file.corpus = corpus
    old_signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="attachment",
    )

    # A company -> workspace transition increments the source ACL epoch while
    # leaving the file workspace and storage object untouched.
    corpus.access_scope_kind = "workspace"
    corpus.metadata_version = 2

    with pytest.raises(HTTPException) as exc:
        open_file_content(
            _FakeDb(file),
            file_id=file.id,
            expires=200,
            signature=old_signature,
            disposition="attachment",
            now=100,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail.code == "files.proxy_url_invalid"


def test_object_replacement_invalidates_existing_content_url(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file()
    old_signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="attachment",
    )

    file.storage_key = "objects/file-1-replacement"

    with pytest.raises(HTTPException) as exc:
        open_file_content(
            _FakeDb(file),
            file_id=file.id,
            expires=200,
            signature=old_signature,
            disposition="attachment",
            now=100,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail.code == "files.proxy_url_invalid"


def test_workspace_content_fetch_rejects_revoked_membership(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    file = _file(visibility="workspace")
    signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="attachment",
    )
    monkeypatch.setattr(
        content_access, "resolve_workspace_role", lambda db, user, workspace_id: None
    )
    monkeypatch.setattr(
        content_access.files_service,
        "require_file_access",
        lambda *args, **kwargs: pytest.fail("revoked membership must fail before source access"),
    )

    with pytest.raises(HTTPException) as exc:
        open_file_content(
            _FakeDb(file),
            file_id=file.id,
            expires=200,
            signature=signature,
            disposition="attachment",
            now=100,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail.code == "files.file_access_required"


def test_company_content_fetch_rechecks_acl_without_workspace_membership(monkeypatch) -> None:
    monkeypatch.setattr(content_access, "get_settings", _settings)
    corpus = _corpus(scope="company", metadata_version=1)
    file = _file(corpus_id=corpus.id)
    file.corpus = corpus
    signature = sign_file_content_url(
        file,
        **_SIGNING_CONTEXT,
        expires=200,
        disposition="attachment",
    )
    storage_object = _FakeObject([b"company"])
    monkeypatch.setattr(content_access, "open_file_object", lambda key: storage_object)
    monkeypatch.setattr(
        content_access,
        "resolve_workspace_role",
        lambda *args, **kwargs: pytest.fail("company ACL must not require workspace membership"),
    )
    authorization_calls: list[str] = []

    def require_file_access(db, *, workspace, user, file_id):
        authorization_calls.append(file_id)
        return file

    monkeypatch.setattr(content_access.files_service, "require_file_access", require_file_access)

    stream = open_file_content(
        _FakeDb(file),
        file_id=file.id,
        expires=200,
        signature=signature,
        disposition="attachment",
        now=100,
    )

    assert list(stream.body) == [b"company"]
    assert authorization_calls == [file.id]
