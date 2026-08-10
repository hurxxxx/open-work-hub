from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from ai_do_api.domains.images import storage


def test_put_reference_image_object_writes_to_configured_bucket(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def put_object(self, bucket, key, stream, *, length, content_type):
            captured["bucket"] = bucket
            captured["key"] = key
            captured["data"] = stream.read()
            captured["length"] = length
            captured["content_type"] = content_type

    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage, "get_minio_client", lambda: FakeClient())
    monkeypatch.setattr(storage, "ensure_bucket", lambda: captured.setdefault("ensured", True))

    storage.put_reference_image_object(
        storage_key="images/refs/generation-1/ref-1",
        data=b"png-bytes",
        content_type="image/png",
    )

    assert captured == {
        "ensured": True,
        "bucket": "bucket-1",
        "key": "images/refs/generation-1/ref-1",
        "data": b"png-bytes",
        "length": 9,
        "content_type": "image/png",
    }


def test_remove_image_objects_returns_failed_keys(monkeypatch) -> None:
    removed: list[str] = []

    class FakeClient:
        def remove_object(self, bucket, key):
            assert bucket == "bucket-1"
            if key == "bad-key":
                raise RuntimeError("boom")
            removed.append(key)

    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage, "get_minio_client", lambda: FakeClient())

    failures = storage.remove_image_objects(["ok-key", "bad-key"])

    assert [failure.storage_key for failure in failures] == ["bad-key"]
    assert isinstance(failures[0].exc, RuntimeError)
    assert removed == ["ok-key"]


def test_presign_image_object_delegates_to_minio(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def presigned_get_object(self, bucket, key, *, expires):
            captured["bucket"] = bucket
            captured["key"] = key
            captured["expires"] = expires
            return "https://download.example/image.png"

    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage, "get_minio_client", lambda: FakeClient())

    expires = timedelta(minutes=15)
    assert (
        storage.presign_image_object(storage_key="images/results/ws/gen.png", expires=expires)
        == "https://download.example/image.png"
    )
    assert captured == {
        "bucket": "bucket-1",
        "key": "images/results/ws/gen.png",
        "expires": expires,
    }


def test_read_image_object_closes_minio_response(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def read(self):
            return b"image-bytes"

        def close(self):
            captured["closed"] = True

        def release_conn(self):
            captured["released"] = True

    class FakeClient:
        def get_object(self, bucket, key):
            captured["bucket"] = bucket
            captured["key"] = key
            return FakeResponse()

    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage, "get_minio_client", lambda: FakeClient())

    assert storage.read_image_object("images/results/ws/gen.png") == b"image-bytes"
    assert captured == {
        "bucket": "bucket-1",
        "key": "images/results/ws/gen.png",
        "closed": True,
        "released": True,
    }
