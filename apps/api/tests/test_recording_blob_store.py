from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_do_api.domains.recording.blob_store import (
    RecordingArtifactStore,
    RecordingSpoolStore,
    build_recording_storage_key,
)


class _FakeMinioObject:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.chunk_sizes: list[int] = []
        self.closed = False
        self.released = False

    def stream(self, chunk_size: int):
        self.chunk_sizes.append(chunk_size)
        for offset in range(0, len(self.data), chunk_size):
            yield self.data[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeMinioClient:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, str, bytes, int, str]] = []
        self.fput_calls: list[tuple[str, str, str, str | None]] = []
        self.objects: dict[str, _FakeMinioObject] = {}

    def put_object(self, bucket: str, key: str, data, length: int, content_type: str) -> None:
        self.put_calls.append((bucket, key, data.read(), length, content_type))

    def fput_object(self, bucket: str, key: str, path: str, content_type: str | None = None) -> None:
        self.fput_calls.append((bucket, key, path, content_type))

    def get_object(self, bucket: str, key: str) -> _FakeMinioObject:
        del bucket
        return self.objects[key]


def test_build_recording_storage_key_preserves_current_layout() -> None:
    key = build_recording_storage_key(
        workspace_id="workspace-1",
        user_id="user-1",
        recording_id="recording-1",
        started_at=datetime(2026, 5, 30, 9, 8, 7),
        file_extension=".webm",
    )

    assert key == (
        "recordings/workspace-1/user-1/2026/05/30/"
        "20260530T090807Z-recording-1.webm"
    )


def test_artifact_store_put_bytes_uses_configured_bucket_and_metadata() -> None:
    client = _FakeMinioClient()
    store = RecordingArtifactStore(bucket_name="recordings", client=client)

    store.put_bytes(
        storage_key="recordings/workspace-1/file.webm",
        data=b"audio",
        content_type="audio/webm",
    )

    assert client.put_calls == [
        ("recordings", "recordings/workspace-1/file.webm", b"audio", 5, "audio/webm")
    ]


def test_artifact_store_put_file_uses_configured_bucket(tmp_path: Path) -> None:
    client = _FakeMinioClient()
    store = RecordingArtifactStore(bucket_name="recordings", client=client)
    source = tmp_path / "assembled.bin"
    source.write_bytes(b"audio")

    store.put_file(
        storage_key="recordings/workspace-1/file.webm",
        path=source,
        content_type="audio/webm",
    )

    assert client.fput_calls == [
        ("recordings", "recordings/workspace-1/file.webm", str(source), "audio/webm")
    ]


def test_artifact_store_stream_closes_and_releases_response() -> None:
    client = _FakeMinioClient()
    obj = _FakeMinioObject(b"abcdef")
    client.objects["recordings/workspace-1/file.webm"] = obj
    store = RecordingArtifactStore(bucket_name="recordings", client=client)

    chunks = list(
        store.open_stream(
            storage_key="recordings/workspace-1/file.webm",
            chunk_size=2,
        )
    )

    assert chunks == [b"ab", b"cd", b"ef"]
    assert obj.chunk_sizes == [2]
    assert obj.closed is True
    assert obj.released is True


def test_spool_store_allocates_staging_dir_under_root(tmp_path: Path) -> None:
    store = RecordingSpoolStore(root=tmp_path)

    spool_dir = store.allocate("staging-1")

    assert spool_dir == tmp_path / "staging-1"
    assert spool_dir.is_dir()


def test_spool_store_writes_zero_padded_chunk_files_atomically(tmp_path: Path) -> None:
    store = RecordingSpoolStore(root=tmp_path)
    spool_dir = store.allocate("staging-1")

    store.write_chunk(spool_path=str(spool_dir), seq=2, data=b"first")
    store.write_chunk(spool_path=str(spool_dir), seq=2, data=b"second")

    assert (spool_dir / "00000002.chunk").read_bytes() == b"second"
    assert not list(spool_dir.glob("*.tmp"))


def test_spool_store_assembles_chunks_in_requested_order(tmp_path: Path) -> None:
    store = RecordingSpoolStore(root=tmp_path)
    spool_dir = store.allocate("staging-1")
    store.write_chunk(spool_path=str(spool_dir), seq=0, data=b"zero")
    store.write_chunk(spool_path=str(spool_dir), seq=1, data=b"one")
    store.write_chunk(spool_path=str(spool_dir), seq=2, data=b"two")

    assembled = store.assemble_chunks(spool_path=str(spool_dir), sequences=[2, 0, 1])

    assert assembled == spool_dir / "assembled.bin"
    assert assembled.read_bytes() == b"twozeroone"


def test_spool_store_cleanup_removes_dir_and_tolerates_missing_paths(tmp_path: Path) -> None:
    store = RecordingSpoolStore(root=tmp_path)
    spool_dir = store.allocate("staging-1")
    store.write_chunk(spool_path=str(spool_dir), seq=0, data=b"data")

    store.cleanup(str(spool_dir))
    store.cleanup(str(spool_dir))
    store.cleanup(None)

    assert not spool_dir.exists()
