from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from io import BytesIO
import json
import logging
import re
from typing import BinaryIO, Protocol

from open_alm_api.core.settings import get_settings
from open_alm_api.core.storage import ensure_bucket, get_minio_client


_SAFE_KEY_SEGMENT = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")
_MAX_INPUT_OBJECT_BYTES = 2 * 1024 * 1024
_MAX_RESULT_OBJECT_BYTES = 20 * 1024 * 1024
_MAX_JOB_OBJECTS = 1_000

logger = logging.getLogger(__name__)


class PatentPriorArtStorageObject(Protocol):
    def read(self, amount: int | None = None) -> bytes: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


class PatentPriorArtListedObject(Protocol):
    object_name: str | None


class PatentPriorArtStorageClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        *,
        length: int,
        content_type: str,
    ) -> object: ...

    def get_object(self, bucket_name: str, object_name: str) -> PatentPriorArtStorageObject: ...

    def list_objects(
        self,
        bucket_name: str,
        *,
        prefix: str,
        recursive: bool,
    ) -> Iterable[PatentPriorArtListedObject]: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


@dataclass(frozen=True)
class StoredArtifact:
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_key: str


@dataclass(frozen=True)
class PatentPriorArtArtifactStore:
    bucket_name: str
    client: PatentPriorArtStorageClient
    ensure_bucket_exists: Callable[[], None] = ensure_bucket

    def put_input_payload(
        self,
        *,
        workspace_id: str,
        job_id: str,
        payload: dict[str, object],
    ) -> str:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(content) > _MAX_INPUT_OBJECT_BYTES:
            raise ValueError("prior-art input object exceeds storage limit")
        key = input_storage_key(workspace_id, job_id)
        self._put(key, content, "application/json; charset=utf-8")
        return key

    def read_input_payload(self, storage_key: str) -> dict[str, object]:
        content = self._read_bounded(storage_key, _MAX_INPUT_OBJECT_BYTES)
        payload = json.loads(content.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("prior-art input payload must be an object")
        return payload

    def put_result_artifacts(
        self,
        *,
        workspace_id: str,
        job_id: str,
        execution_id: str,
        result_json: str,
        report_markdown: str,
    ) -> tuple[StoredArtifact, StoredArtifact]:
        result_bytes = result_json.encode("utf-8")
        markdown_bytes = report_markdown.encode("utf-8")
        if (
            len(result_bytes) > _MAX_RESULT_OBJECT_BYTES
            or len(markdown_bytes) > _MAX_RESULT_OBJECT_BYTES
        ):
            raise ValueError("prior-art result object exceeds storage limit")

        result = StoredArtifact(
            kind="result_json",
            filename="prior-art-result.json",
            mime_type="application/json; charset=utf-8",
            size_bytes=len(result_bytes),
            storage_key=result_json_storage_key(workspace_id, job_id, execution_id),
        )
        report = StoredArtifact(
            kind="report_markdown",
            filename="prior-art-report.md",
            mime_type="text/markdown; charset=utf-8",
            size_bytes=len(markdown_bytes),
            storage_key=report_markdown_storage_key(
                workspace_id,
                job_id,
                execution_id,
            ),
        )
        self._put(result.storage_key, result_bytes, result.mime_type)
        try:
            self._put(report.storage_key, markdown_bytes, report.mime_type)
        except Exception:
            try:
                self.client.remove_object(self.bucket_name, result.storage_key)
            except Exception:
                logger.exception("patent_prior_art.artifacts: partial result compensation failed")
            raise
        return result, report

    def read_artifact(self, storage_key: str, *, expected_size: int) -> bytes:
        if expected_size < 0 or expected_size > _MAX_RESULT_OBJECT_BYTES:
            raise ValueError("invalid prior-art artifact size")
        content = self._read_bounded(storage_key, _MAX_RESULT_OBJECT_BYTES)
        if len(content) != expected_size:
            raise ValueError("prior-art artifact size does not match metadata")
        return content

    def remove_objects(self, storage_keys: Iterable[str]) -> None:
        for storage_key in dict.fromkeys(storage_keys):
            if storage_key:
                self.client.remove_object(self.bucket_name, storage_key)

    def remove_job_objects(
        self,
        *,
        workspace_id: str,
        job_id: str,
        recorded_storage_keys: Iterable[str] = (),
    ) -> None:
        """Remove every object under a job, including unrecorded executions."""

        prefix = f"{job_storage_prefix(workspace_id, job_id)}/"
        listed_keys: list[str] = []
        for index, item in enumerate(
            self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True,
            ),
            start=1,
        ):
            if index > _MAX_JOB_OBJECTS:
                raise ValueError("prior-art job object count exceeds cleanup limit")
            object_name = str(item.object_name or "")
            if not object_name:
                continue
            if not object_name.startswith(prefix):
                raise ValueError("object listing escaped prior-art job prefix")
            listed_keys.append(object_name)

        explicit_keys = [
            input_storage_key(workspace_id, job_id),
            *recorded_storage_keys,
        ]
        if any(not str(key).startswith(prefix) for key in explicit_keys):
            raise ValueError("recorded object escaped prior-art job prefix")
        self.remove_objects([*explicit_keys, *listed_keys])

    def remove_stale_execution_objects(
        self,
        *,
        workspace_id: str,
        job_id: str,
        keep_execution_id: str,
    ) -> None:
        """Remove crashed execution objects while preserving the fenced winner."""

        executions_prefix = f"{job_storage_prefix(workspace_id, job_id)}/executions/"
        keep_prefix = f"{execution_storage_prefix(workspace_id, job_id, keep_execution_id)}/"
        stale_keys: list[str] = []
        for index, item in enumerate(
            self.client.list_objects(
                self.bucket_name,
                prefix=executions_prefix,
                recursive=True,
            ),
            start=1,
        ):
            if index > _MAX_JOB_OBJECTS:
                raise ValueError("prior-art execution object count exceeds cleanup limit")
            object_name = str(item.object_name or "")
            if not object_name:
                continue
            if not object_name.startswith(executions_prefix):
                raise ValueError("object listing escaped prior-art execution prefix")
            if not object_name.startswith(keep_prefix):
                stale_keys.append(object_name)
        self.remove_objects(stale_keys)

    def _put(self, storage_key: str, content: bytes, mime_type: str) -> None:
        self.ensure_bucket_exists()
        self.client.put_object(
            self.bucket_name,
            storage_key,
            BytesIO(content),
            length=len(content),
            content_type=mime_type,
        )

    def _read_bounded(self, storage_key: str, maximum: int) -> bytes:
        response = self.client.get_object(self.bucket_name, storage_key)
        try:
            content = response.read(maximum + 1)
        finally:
            response.close()
            response.release_conn()
        if len(content) > maximum:
            raise ValueError("prior-art stored object exceeds read limit")
        return content


def patent_prior_art_artifact_store() -> PatentPriorArtArtifactStore:
    return PatentPriorArtArtifactStore(
        bucket_name=get_settings().minio_bucket,
        client=get_minio_client(),
    )


def input_storage_key(workspace_id: str, job_id: str) -> str:
    return f"{job_storage_prefix(workspace_id, job_id)}/input/request.json"


def result_json_storage_key(workspace_id: str, job_id: str, execution_id: str) -> str:
    return f"{execution_storage_prefix(workspace_id, job_id, execution_id)}/result.json"


def report_markdown_storage_key(
    workspace_id: str,
    job_id: str,
    execution_id: str,
) -> str:
    return f"{execution_storage_prefix(workspace_id, job_id, execution_id)}/report.md"


def execution_storage_prefix(
    workspace_id: str,
    job_id: str,
    execution_id: str,
) -> str:
    return (
        f"{job_storage_prefix(workspace_id, job_id)}/executions/"
        f"{_validated_segment(execution_id, label='execution_id')}"
    )


def job_storage_prefix(workspace_id: str, job_id: str) -> str:
    return (
        "patent-prior-art/"
        f"{_validated_segment(workspace_id, label='workspace_id')}/"
        f"{_validated_segment(job_id, label='job_id')}"
    )


def storage_key_belongs_to_job(storage_key: str, *, workspace_id: str, job_id: str) -> bool:
    return storage_key.startswith(f"{job_storage_prefix(workspace_id, job_id)}/")


def _validated_segment(value: str, *, label: str) -> str:
    normalized = str(value or "")
    if not _SAFE_KEY_SEGMENT.fullmatch(normalized):
        raise ValueError(f"invalid {label} for storage key")
    return normalized


__all__ = [
    "PatentPriorArtArtifactStore",
    "StoredArtifact",
    "execution_storage_prefix",
    "input_storage_key",
    "job_storage_prefix",
    "patent_prior_art_artifact_store",
    "report_markdown_storage_key",
    "result_json_storage_key",
    "storage_key_belongs_to_job",
]
