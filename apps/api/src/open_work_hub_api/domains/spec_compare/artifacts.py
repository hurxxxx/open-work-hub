from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
from typing import BinaryIO, Protocol

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import ensure_bucket, get_minio_client


DEFAULT_CONTENT_TYPE = "application/octet-stream"


class SpecCompareStorageObject(Protocol):
    def read(self) -> bytes: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


class SpecCompareStorageClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        *,
        length: int,
        content_type: str,
    ) -> object: ...

    def get_object(self, bucket_name: str, object_name: str) -> SpecCompareStorageObject: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


@dataclass(frozen=True)
class SpecCompareUpload:
    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class SpecCompareArtifactRef:
    filename: str
    mime_type: str
    size_bytes: int
    storage_key: str


@dataclass(frozen=True)
class SpecCompareInputArtifacts:
    base: SpecCompareArtifactRef
    target: SpecCompareArtifactRef


@dataclass(frozen=True)
class SpecCompareArtifactStore:
    bucket_name: str
    client: SpecCompareStorageClient
    ensure_bucket_exists: Callable[[], None] = ensure_bucket

    def upload_inputs(
        self,
        *,
        workspace_id: str,
        job_id: str,
        base: SpecCompareUpload,
        target: SpecCompareUpload,
    ) -> SpecCompareInputArtifacts:
        self.ensure_bucket_exists()
        base_ref = self._put_input(workspace_id=workspace_id, job_id=job_id, role="base", upload=base)
        target_ref = self._put_input(
            workspace_id=workspace_id,
            job_id=job_id,
            role="target",
            upload=target,
        )
        return SpecCompareInputArtifacts(base=base_ref, target=target_ref)

    def remove_job_artifacts(self, *, storage_keys: list[str | None]) -> None:
        """Best-effort removal of a job's stored objects (inputs + results)."""
        for key in storage_keys:
            if not key:
                continue
            self.client.remove_object(self.bucket_name, key)

    def read_result_payload(self, storage_key: str) -> dict[str, object]:
        response = self.client.get_object(self.bucket_name, storage_key)
        try:
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()
        if not isinstance(payload, dict):
            raise ValueError("spec_compare result payload must be a JSON object")
        return payload

    def _put_input(
        self,
        *,
        workspace_id: str,
        job_id: str,
        role: str,
        upload: SpecCompareUpload,
    ) -> SpecCompareArtifactRef:
        filename = safe_artifact_filename(upload.filename)
        mime_type = upload.mime_type or DEFAULT_CONTENT_TYPE
        storage_key = input_storage_key(workspace_id, job_id, role, filename)
        self.client.put_object(
            self.bucket_name,
            storage_key,
            BytesIO(upload.content),
            length=len(upload.content),
            content_type=mime_type,
        )
        return SpecCompareArtifactRef(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(upload.content),
            storage_key=storage_key,
        )


def spec_compare_artifact_store() -> SpecCompareArtifactStore:
    return SpecCompareArtifactStore(
        bucket_name=get_settings().minio_bucket,
        client=get_minio_client(),
    )


def safe_artifact_filename(name: str) -> str:
    raw = Path(name or "document.pptx").name.strip() or "document.pptx"
    return raw.replace("/", "_").replace("\\", "_")[:180]


def input_storage_key(workspace_id: str, job_id: str, role: str, filename: str) -> str:
    return f"spec-compare/{workspace_id}/{job_id}/inputs/{role}-{safe_artifact_filename(filename)}"


def result_json_key(workspace_id: str, job_id: str) -> str:
    return f"spec-compare/{workspace_id}/{job_id}/result/result.json"


def result_markdown_key(workspace_id: str, job_id: str) -> str:
    return f"spec-compare/{workspace_id}/{job_id}/result/report.md"
