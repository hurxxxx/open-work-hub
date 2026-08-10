from __future__ import annotations

from types import SimpleNamespace

from open_alm_api.domains.spec_compare.artifacts import (
    DEFAULT_CONTENT_TYPE,
    SpecCompareArtifactStore,
    SpecCompareUpload,
    input_storage_key,
    result_json_key,
    result_markdown_key,
    safe_artifact_filename,
)
from open_alm_api.domains.spec_compare.dispatch import (
    RUN_JOB_QUEUE,
    RUN_JOB_TASK_NAME,
    SpecCompareJobDispatcher,
)


class FakeStorageObject:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeStorageClient:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []
        self.objects: dict[tuple[str, str], FakeStorageObject] = {}

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data,
        *,
        length: int,
        content_type: str,
    ) -> object:
        self.puts.append(
            {
                "bucket": bucket_name,
                "key": object_name,
                "content": data.read(),
                "length": length,
                "content_type": content_type,
            }
        )
        return object()

    def get_object(self, bucket_name: str, object_name: str) -> FakeStorageObject:
        return self.objects[(bucket_name, object_name)]


def test_artifact_store_upload_inputs_writes_safe_keys_and_metadata() -> None:
    client = FakeStorageClient()
    ensure_calls: list[bool] = []
    store = SpecCompareArtifactStore(
        bucket_name="bucket",
        client=client,
        ensure_bucket_exists=lambda: ensure_calls.append(True),
    )

    artifacts = store.upload_inputs(
        workspace_id="workspace-1",
        job_id="job-1",
        base=SpecCompareUpload(
            filename="../base deck.pptx",
            mime_type="application/pptx",
            content=b"base bytes",
        ),
        target=SpecCompareUpload(
            filename="target.pptx",
            mime_type="",
            content=b"target bytes",
        ),
    )

    assert ensure_calls == [True]
    assert artifacts.base.filename == "base deck.pptx"
    assert artifacts.base.mime_type == "application/pptx"
    assert artifacts.base.size_bytes == len(b"base bytes")
    assert artifacts.base.storage_key == (
        "spec-compare/workspace-1/job-1/inputs/base-base deck.pptx"
    )
    assert artifacts.target.mime_type == DEFAULT_CONTENT_TYPE
    assert client.puts == [
        {
            "bucket": "bucket",
            "key": artifacts.base.storage_key,
            "content": b"base bytes",
            "length": len(b"base bytes"),
            "content_type": "application/pptx",
        },
        {
            "bucket": "bucket",
            "key": artifacts.target.storage_key,
            "content": b"target bytes",
            "length": len(b"target bytes"),
            "content_type": DEFAULT_CONTENT_TYPE,
        },
    ]


def test_artifact_store_read_result_payload_closes_response() -> None:
    client = FakeStorageClient()
    response = FakeStorageObject(
        b'{"report_markdown":"ok","comparison_rows":[],"evidence_blocks":[]}'
    )
    client.objects[("bucket", "result.json")] = response
    store = SpecCompareArtifactStore(
        bucket_name="bucket",
        client=client,
        ensure_bucket_exists=lambda: None,
    )

    payload = store.read_result_payload("result.json")

    assert payload["report_markdown"] == "ok"
    assert response.closed is True
    assert response.released is True


def test_spec_compare_artifact_key_helpers_keep_existing_layout() -> None:
    assert safe_artifact_filename("/tmp/base.pptx") == "base.pptx"
    assert input_storage_key("workspace-1", "job-1", "base", "base.pptx") == (
        "spec-compare/workspace-1/job-1/inputs/base-base.pptx"
    )
    assert result_json_key("workspace-1", "job-1") == (
        "spec-compare/workspace-1/job-1/result/result.json"
    )
    assert result_markdown_key("workspace-1", "job-1") == (
        "spec-compare/workspace-1/job-1/result/report.md"
    )


def test_job_dispatcher_sends_existing_task_to_spec_compare_queue() -> None:
    class FakePublisher:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def send_task(self, name: str, *, args: list[str], queue: str) -> object:
            self.calls.append({"name": name, "args": args, "queue": queue})
            return SimpleNamespace(id="celery-task-1")

    publisher = FakePublisher()
    dispatcher = SpecCompareJobDispatcher(publisher=publisher)

    task_id = dispatcher.dispatch("job-1")

    assert task_id == "celery-task-1"
    assert publisher.calls == [
        {"name": RUN_JOB_TASK_NAME, "args": ["job-1"], "queue": RUN_JOB_QUEUE}
    ]
