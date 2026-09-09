"""Run a privacy-safe Files retrieval E2E against the shared development runtime.

The command is intentionally fail-closed. It never accepts credentials on the
command line and it requires an explicit live-execution acknowledgement.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import importlib.util
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
import time
from typing import Any, Protocol, Sequence
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx

from open_work_hub_api.core.settings import is_production_like_environment


EXECUTION_ACK = "live-e2e-development"
NON_PRODUCTION_PROFILES = frozenset({"dev", "development", "local", "test", "testing"})
MAX_LIVE_CANARIES = 12
MAX_LIVE_TOTAL_BYTES = 120 * 1024 * 1024
_CONTENT_PROBE_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,64}")
HASHED_UPLOAD_NAME_RE = re.compile(r"^[0-9a-f]{64}\.[a-z0-9]{1,10}$")


class LiveE2EContractError(Exception):
    """A stable error code that is safe to print."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LiveCanary:
    """A validated source handle retained only in process memory."""

    candidate: object
    source_id: str
    content_sha256: str
    extension: str
    size_bytes: int
    upload_name: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_readonly_harness():
    path = Path(__file__).with_name("files_rag_readonly_harness.py")
    module_name = "open_work_hub_files_rag_readonly_harness_for_live_e2e"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise LiveE2EContractError("readonly_harness_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise LiveE2EContractError("readonly_harness_unavailable") from error
    return module


def _resolve_source_root(source: Path) -> Path:
    try:
        source_lstat = source.lstat()
        source_root = source.resolve(strict=True)
    except OSError as error:
        raise LiveE2EContractError("invalid_source") from error
    if stat.S_ISLNK(source_lstat.st_mode) or not source_root.is_dir():
        raise LiveE2EContractError("invalid_source")
    return source_root


def select_live_canaries(
    source: Path,
    *,
    max_canaries: int,
    max_total_bytes: int,
    workers: int,
    run_nonce: bytes | None = None,
) -> tuple[LiveCanary, ...]:
    """Select a deterministic, bounded stratum sample without serializing paths."""

    if (
        not 1 <= max_canaries <= MAX_LIVE_CANARIES
        or not 1 <= max_total_bytes <= MAX_LIVE_TOTAL_BYTES
        or not 1 <= workers <= 32
    ):
        raise LiveE2EContractError("invalid_live_limits")
    source_root = _resolve_source_root(source)
    harness = _load_readonly_harness()
    candidates, *_ = harness._scan_source(source_root)
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="files-rag-live-select"
    ) as pool:
        inspections = tuple(pool.map(harness._inspect_candidate, candidates))

    strata: dict[tuple[str, str], list[object]] = defaultdict(list)
    for inspection in inspections:
        if inspection.exclusion_reason is None and inspection.content_sha256 is not None:
            candidate = inspection.candidate
            strata[(candidate.extension, harness._size_bucket(candidate.size_bytes))].append(
                inspection
            )

    ordered_strata: list[list[object]] = []
    for key in sorted(strata):
        ordered_strata.append(
            sorted(
                strata[key],
                key=lambda item: _sha256_bytes(
                    b"open-work-hub-files-live-canary-v1\0"
                    + item.candidate.source_id.encode("ascii")
                    + item.content_sha256.encode("ascii")
                ),
            )
        )

    nonce = run_nonce if run_nonce is not None else secrets.token_bytes(32)
    run_tag = _sha256_bytes(b"open-work-hub-files-live-run-tag-v1\0" + nonce)[:16]
    selected: list[LiveCanary] = []
    total_bytes = 0
    round_index = 0
    max_rounds = max((len(items) for items in ordered_strata), default=0)
    while len(selected) < max_canaries and round_index < max_rounds:
        for items in ordered_strata:
            if round_index >= len(items):
                continue
            inspection = items[round_index]
            candidate = inspection.candidate
            if total_bytes + candidate.size_bytes > max_total_bytes:
                continue
            item_digest = _sha256_bytes(
                b"open-work-hub-files-live-upload-name-v1\0"
                + nonce
                + candidate.source_id.encode("ascii")
                + inspection.content_sha256.encode("ascii")
            )
            selected.append(
                LiveCanary(
                    candidate=candidate,
                    source_id=candidate.source_id,
                    content_sha256=inspection.content_sha256,
                    extension=candidate.extension,
                    size_bytes=candidate.size_bytes,
                    upload_name=f"{run_tag}{item_digest[:48]}.{candidate.extension}",
                )
            )
            total_bytes += candidate.size_bytes
            if len(selected) >= max_canaries:
                break
        round_index += 1
    if not selected:
        raise LiveE2EContractError("no_canaries_within_live_limits")
    return tuple(selected)


def select_private_content_probe(rows: Sequence[tuple[str, str]]) -> tuple[str, str]:
    """Choose a body-derived query and target without serializing either body."""

    token_rows: list[tuple[str, list[str]]] = []
    document_frequency: Counter[str] = Counter()
    for resource_id, text in rows:
        tokens = [
            token.casefold()
            for token in _CONTENT_PROBE_TOKEN_RE.findall(text[:120_000])
            if not token.isdecimal() and not re.fullmatch(r"[0-9a-fA-F]{16,}", token)
        ]
        if tokens:
            token_rows.append((resource_id, tokens))
            document_frequency.update(set(tokens))
    if not token_rows:
        raise LiveE2EContractError("content_probe_unavailable")

    candidates: list[tuple[tuple[int, int, int, int], str, str]] = []
    for resource_id, tokens in token_rows:
        for window_size in (6, 5, 4, 3):
            stop = min(max(len(tokens) - window_size + 1, 0), 2_000)
            for index in range(stop):
                window = tokens[index : index + window_size]
                query = " ".join(window)
                if len(query) < 16 or len(query) > 320 or len(set(window)) < 2:
                    continue
                unique_tokens = sum(document_frequency[token] == 1 for token in set(window))
                candidates.append(
                    (
                        (unique_tokens, len(set(window)), len(query), -index),
                        resource_id,
                        query,
                    )
                )
            if candidates:
                break
    if not candidates:
        raise LiveE2EContractError("content_probe_unavailable")
    _score, target_resource_id, query = max(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    )
    return query, target_resource_id


def _resolve_report_output(source: Path, output: Path) -> Path:
    source_root = _resolve_source_root(source)
    try:
        resolved_parent = output.parent.resolve(strict=True)
    except OSError as error:
        raise LiveE2EContractError("invalid_report_output") from error
    resolved_output = resolved_parent / output.name
    if resolved_output == source_root or source_root in resolved_output.parents:
        raise LiveE2EContractError("report_output_inside_source")
    try:
        resolved_output.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise LiveE2EContractError("invalid_report_output") from error
    else:
        raise LiveE2EContractError("invalid_report_output")
    return resolved_output


def write_safe_report(*, source: Path, output: Path, report: dict[str, object]) -> str:
    """Atomically create an ASCII JSON report with owner-only permissions."""

    resolved_output = _resolve_report_output(source, output)
    payload = (_canonical_json(report) + "\n").encode("ascii")
    digest = _sha256_bytes(payload)
    temporary_name: str | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=resolved_output.parent,
            prefix=f".{resolved_output.name}.",
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_name, resolved_output, follow_symlinks=False)
        os.unlink(temporary_name)
        temporary_name = None
        os.chmod(resolved_output, 0o600)
        directory_descriptor = os.open(resolved_output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return digest
    except OSError as error:
        raise LiveE2EContractError("report_write_failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


class LiveFilesApi(Protocol):
    def validate_acl_group(self, group_id: str) -> None: ...
    def replace_acl_group_members(self, group_id: str, user_ids: Sequence[str]) -> None: ...
    def assert_app_denied(self) -> None: ...

    def identity(self) -> dict[str, object]: ...

    def preflight(self) -> None: ...

    def create_corpus(self, name: str) -> dict[str, object]: ...

    def upload(self, corpus_id: str, canary: LiveCanary) -> dict[str, object]: ...

    def wait_ready(
        self,
        file_ids: Sequence[str],
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, str]: ...

    def search(
        self,
        *,
        query: str,
        strategy: str,
        page: int,
        page_size: int,
    ) -> dict[str, object]: ...

    def fresh_download(self, file_id: str) -> tuple[str, str, int]: ...

    def assert_stale_download_denied(self, url: str) -> None: ...

    def bulk_delete(self, file_ids: Sequence[str]) -> None: ...


class ProjectionInspector(Protocol):
    def content_probe(self, *, file_ids: Sequence[str]) -> tuple[str, str]: ...

    def cleanup_target(self, *, corpus_id: str) -> tuple[str, ...]: ...

    def wait_projected(
        self,
        *,
        corpus_id: str,
        file_ids: Sequence[str],
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, object]: ...

    def snapshot(self, *, corpus_id: str, file_ids: Sequence[str]) -> dict[str, object]: ...

    def wait_removed(
        self,
        *,
        corpus_id: str,
        file_ids: Sequence[str],
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, object]: ...


_CONTENT_TYPES = {
    "csv": "text/csv",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "md": "text/markdown",
    "pdf": "application/pdf",
    "png": "image/png",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "rst": "text/plain",
    "text": "text/plain",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "txt": "text/plain",
    "webp": "image/webp",
    "xls": "application/vnd.ms-excel",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def assert_development_api_origin(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise LiveE2EContractError("loopback_development_api_required")
    return value.rstrip("/")


class HttpFilesApi:
    """Minimal public Files API client with sanitized failure codes."""

    def __init__(self, *, base_url: str, token: str, timeout_seconds: float = 60) -> None:
        if not token:
            raise LiveE2EContractError("auth_token_required")
        self._base_url = assert_development_api_origin(base_url)
        self._origin = urlparse(self._base_url)
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def _files_path(self, suffix: str) -> str:
        return f"/api/v1/files{suffix}"

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        error_code: str,
        **kwargs: Any,
    ) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise LiveE2EContractError(error_code) from error
        if response.status_code != expected_status:
            raise LiveE2EContractError(error_code)
        try:
            return response.json() if response.content else None
        except (UnicodeError, ValueError) as error:
            raise LiveE2EContractError(error_code) from error

    def identity(self) -> dict[str, object]:
        payload = self._json_request(
            "GET",
            "/api/v1/auth/me",
            expected_status=200,
            error_code="identity_preflight_failed",
        )
        if not isinstance(payload, dict):
            raise LiveE2EContractError("invalid_identity_response")
        return payload

    def validate_acl_group(self, group_id: str) -> None:
        policy = self._json_request(
            "GET",
            "/api/v1/admin/apps/files/access-policy",
            expected_status=200,
            error_code="acl_fixture_unavailable",
        )
        members = self._json_request(
            "GET",
            f"/api/v1/admin/groups/{quote(group_id, safe='')}/members",
            expected_status=200,
            error_code="acl_fixture_unavailable",
        )
        if (
            not isinstance(policy, dict)
            or policy.get("enabled") is not True
            or policy.get("audience") != "selected"
            or group_id not in policy.get("group_ids", [])
            or not isinstance(members, dict)
            or members.get("user_ids") != []
        ):
            raise LiveE2EContractError("dedicated_empty_admission_group_required")

    def replace_acl_group_members(self, group_id: str, user_ids: Sequence[str]) -> None:
        payload = self._json_request(
            "PUT",
            f"/api/v1/admin/groups/{quote(group_id, safe='')}/members",
            expected_status=200,
            error_code="acl_group_mutation_failed",
            json={"user_ids": list(user_ids)},
        )
        if not isinstance(payload, dict) or set(payload.get("user_ids", [])) != set(user_ids):
            raise LiveE2EContractError("acl_group_mutation_failed")

    def assert_app_denied(self) -> None:
        self._json_request(
            "GET",
            self._files_path(""),
            expected_status=403,
            error_code="app_grant_revocation_failed",
        )

    def preflight(self) -> None:
        browse = self._json_request(
            "GET",
            self._files_path(""),
            expected_status=200,
            error_code="files_app_preflight_failed",
        )
        if not isinstance(browse, dict) or not isinstance(browse.get("files"), list):
            raise LiveE2EContractError("files_app_preflight_failed")
        query = _sha256_bytes(b"open-work-hub-files-live-preflight-v1\0" + secrets.token_bytes(16))[
            :16
        ]
        search = self._json_request(
            "POST",
            self._files_path("/search"),
            expected_status=200,
            error_code="files_search_not_active",
            json={"query": query, "strategy": "hybrid", "page": 1, "page_size": 1},
        )
        if not isinstance(search, dict) or search.get("query") != query:
            raise LiveE2EContractError("files_search_not_active")

    def create_corpus(self, name: str) -> dict[str, object]:
        payload = self._json_request(
            "POST",
            self._files_path("/corpora"),
            expected_status=201,
            error_code="corpus_create_failed",
            json={"name": name},
        )
        if not isinstance(payload, dict):
            raise LiveE2EContractError("invalid_corpus_response")
        return payload

    def upload(self, corpus_id: str, canary: LiveCanary) -> dict[str, object]:
        harness = _load_readonly_harness()
        candidate = canary.candidate
        try:
            with harness._open_candidate(candidate) as stream:
                payload = self._json_request(
                    "POST",
                    self._files_path("/upload"),
                    expected_status=201,
                    error_code="canary_upload_failed",
                    data={
                        "visibility": "company",
                        "company_admin_read_acknowledged": "true",
                        "corpus_id": corpus_id,
                    },
                    files={
                        "file": (
                            canary.upload_name,
                            stream,
                            _CONTENT_TYPES.get(canary.extension, "application/octet-stream"),
                        )
                    },
                )
                final_stat = os.fstat(stream.fileno())
                identity = (
                    final_stat.st_dev,
                    final_stat.st_ino,
                    final_stat.st_size,
                    final_stat.st_mtime_ns,
                )
                expected = (
                    candidate.device,
                    candidate.inode,
                    candidate.size_bytes,
                    candidate.modified_ns,
                )
                if identity != expected or harness._hash_stream(stream) != canary.content_sha256:
                    raise LiveE2EContractError("source_changed_during_upload")
        except LiveE2EContractError:
            raise
        except Exception as error:
            raise LiveE2EContractError("canary_upload_failed") from error
        if not isinstance(payload, dict):
            raise LiveE2EContractError("invalid_upload_response")
        return payload

    def wait_ready(
        self,
        file_ids: Sequence[str],
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, str]:
        expected = set(file_ids)
        deadline = time.monotonic() + timeout_seconds
        while True:
            payload = self._json_request(
                "GET",
                self._files_path(""),
                expected_status=200,
                error_code="projection_status_poll_failed",
            )
            rows = payload.get("files") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise LiveE2EContractError("projection_status_poll_failed")
            statuses = {
                str(row.get("id")): str(row.get("rag_status"))
                for row in rows
                if isinstance(row, dict) and str(row.get("id")) in expected
            }
            if any(status in {"failed", "unsupported", "disabled"} for status in statuses.values()):
                raise LiveE2EContractError("projection_failed")
            if statuses == {file_id: "ready" for file_id in file_ids}:
                return statuses
            if time.monotonic() >= deadline:
                raise LiveE2EContractError("projection_ready_timeout")
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def search(
        self,
        *,
        query: str,
        strategy: str,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        payload = self._json_request(
            "POST",
            self._files_path("/search"),
            expected_status=200,
            error_code="files_search_failed",
            json={
                "query": query,
                "strategy": strategy,
                "page": page,
                "page_size": page_size,
            },
        )
        if not isinstance(payload, dict):
            raise LiveE2EContractError("invalid_search_contract")
        return payload

    def _validated_content_url(self, raw_url: object) -> tuple[str, str]:
        if not isinstance(raw_url, str) or not raw_url:
            raise LiveE2EContractError("invalid_download_url")
        absolute = urljoin(f"{self._base_url}/", raw_url)
        parsed = urlparse(absolute)
        try:
            fragment = parse_qs(
                parsed.fragment,
                keep_blank_values=True,
                strict_parsing=True,
            )
        except ValueError as error:
            raise LiveE2EContractError("invalid_download_url") from error
        if (
            parsed.scheme != self._origin.scheme
            or parsed.hostname != self._origin.hostname
            or parsed.port != self._origin.port
            or parsed.path != "/api/v1/content"
            or parsed.query
            or set(fragment) != {"grant"}
            or len(fragment["grant"]) != 1
            or not fragment["grant"][0]
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise LiveE2EContractError("invalid_download_url")
        return parsed._replace(fragment="").geturl(), fragment["grant"][0]

    def fresh_download(self, file_id: str) -> tuple[str, str, int]:
        payload = self._json_request(
            "GET",
            self._files_path(f"/{quote(file_id, safe='')}/download"),
            expected_status=200,
            error_code="download_url_request_failed",
        )
        if not isinstance(payload, dict):
            raise LiveE2EContractError("invalid_download_url")
        raw_url = payload.get("url")
        url, grant = self._validated_content_url(raw_url)
        digest = hashlib.sha256()
        byte_count = 0
        try:
            with self._client.stream(
                "GET",
                url,
                headers={"X-Open-Work-Hub-Content-Grant": grant},
            ) as response:
                if response.status_code != 200:
                    raise LiveE2EContractError("fresh_download_failed")
                if response.headers.get("cache-control") != "private, no-store":
                    raise LiveE2EContractError("invalid_download_cache_control")
                for chunk in response.iter_bytes():
                    byte_count += len(chunk)
                    if byte_count > MAX_LIVE_TOTAL_BYTES:
                        raise LiveE2EContractError("download_size_limit_exceeded")
                    digest.update(chunk)
        except LiveE2EContractError:
            raise
        except httpx.HTTPError as error:
            raise LiveE2EContractError("fresh_download_failed") from error
        return str(raw_url), digest.hexdigest(), byte_count

    def assert_stale_download_denied(self, url: str) -> None:
        validated, grant = self._validated_content_url(url)
        try:
            with self._client.stream(
                "GET",
                validated,
                headers={"X-Open-Work-Hub-Content-Grant": grant},
            ) as response:
                if response.status_code not in {403, 404}:
                    raise LiveE2EContractError("stale_download_still_valid")
        except LiveE2EContractError:
            raise
        except httpx.HTTPError as error:
            raise LiveE2EContractError("stale_download_check_failed") from error

    def bulk_delete(self, file_ids: Sequence[str]) -> None:
        self._json_request(
            "POST",
            self._files_path("/bulk-delete"),
            expected_status=204,
            error_code="canary_cleanup_failed",
            json={"file_ids": list(file_ids), "folder_ids": []},
        )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(mode="json"))
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _jsonable(tolist())
    return str(value)


class DevelopmentProjectionInspector:
    """Read-only, selected-resource proof across PostgreSQL/OpenSearch/Qdrant."""

    def __init__(self, settings: object) -> None:
        from qdrant_client import QdrantClient

        from open_work_hub_api.core.db import get_session_factory
        from open_work_hub_api.core.storage import get_minio_client

        self._settings = settings
        self._session_factory = get_session_factory()
        self._opensearch = httpx.Client(
            base_url=str(getattr(settings, "opensearch_url")).rstrip("/"),
            timeout=30,
        )
        self._qdrant = QdrantClient(
            url=str(getattr(settings, "rag_qdrant_url")),
            api_key=str(getattr(settings, "rag_qdrant_api_key", "") or "") or None,
            timeout=30,
        )
        self._minio = get_minio_client()
        self._minio_bucket = str(getattr(settings, "minio_bucket"))

    def close(self) -> None:
        self._opensearch.close()
        self._qdrant.close()

    def _active_physical_names(self, db: Any) -> tuple[str, str]:
        from sqlalchemy import select

        from open_work_hub_api.domains.retrieval.models import RetrievalProjectionGeneration

        rows = tuple(
            db.scalars(
                select(RetrievalProjectionGeneration).where(
                    RetrievalProjectionGeneration.state == "active",
                    RetrievalProjectionGeneration.backend.in_(("opensearch", "qdrant")),
                )
            ).all()
        )
        names: dict[str, str] = {}
        for backend in ("opensearch", "qdrant"):
            matches = [
                row
                for row in rows
                if row.backend == backend
                and row.validation_state == "passed"
                and row.validated_at is not None
            ]
            if len(matches) != 1:
                raise LiveE2EContractError("active_generation_required")
            names[backend] = str(matches[0].physical_name)
        return names["opensearch"], names["qdrant"]

    def _opensearch_records(self, physical_name: str, file_ids: Sequence[str]) -> list[Any]:
        from open_work_hub_api.domains.retrieval.projection_identity import (
            canonical_search_document_id,
        )
        from open_work_hub_api.domains.source_access.resource_types import (
            FILE_MANAGER_FILE_RESOURCE_TYPE,
        )

        document_ids = [
            canonical_search_document_id(
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id=file_id,
            )
            for file_id in file_ids
        ]
        try:
            response = self._opensearch.post(
                f"/{quote(physical_name, safe='')}/_mget",
                json={"ids": document_ids},
            )
        except httpx.HTTPError as error:
            raise LiveE2EContractError("projection_inspection_failed") from error
        if response.status_code != 200:
            raise LiveE2EContractError("projection_inspection_failed")
        try:
            payload = response.json()
        except ValueError as error:
            raise LiveE2EContractError("projection_inspection_failed") from error
        docs = payload.get("docs") if isinstance(payload, dict) else None
        if not isinstance(docs, list):
            raise LiveE2EContractError("projection_inspection_failed")
        return sorted(
            (
                {
                    "id": str(doc.get("_id") or ""),
                    "version": doc.get("_version"),
                    "source": doc.get("_source"),
                }
                for doc in docs
                if isinstance(doc, dict) and doc.get("found") is True
            ),
            key=lambda item: item["id"],
        )

    def _qdrant_records(self, physical_name: str, file_ids: Sequence[str]) -> list[Any]:
        from qdrant_client import models

        from open_work_hub_api.domains.source_access.resource_types import (
            FILE_MANAGER_FILE_RESOURCE_TYPE,
        )

        records: list[Any] = []
        for file_id in file_ids:
            offset: Any = None
            resource_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="resource_type",
                        match=models.MatchValue(value=FILE_MANAGER_FILE_RESOURCE_TYPE),
                    ),
                    models.FieldCondition(
                        key="resource_id",
                        match=models.MatchValue(value=file_id),
                    ),
                ]
            )
            while True:
                try:
                    page, offset = self._qdrant.scroll(
                        collection_name=physical_name,
                        scroll_filter=resource_filter,
                        limit=128,
                        offset=offset,
                        with_payload=True,
                        with_vectors=True,
                    )
                except Exception as error:
                    raise LiveE2EContractError("projection_inspection_failed") from error
                records.extend(
                    {
                        "id": str(record.id),
                        "payload": _jsonable(record.payload),
                        "vector": _jsonable(record.vector),
                    }
                    for record in page
                )
                if offset is None:
                    break
        return sorted(records, key=lambda item: item["id"])

    def _state(self, *, corpus_id: str, file_ids: Sequence[str]) -> dict[str, object]:
        from sqlalchemy import select

        from open_work_hub_api.domains.files.models import FileManagerCorpus, FileManagerFile
        from open_work_hub_api.domains.rag.models import RagSyncJob
        from open_work_hub_api.domains.retrieval.models import (
            RetrievalProjectionEvent,
            RetrievalProjectionHead,
        )
        from open_work_hub_api.domains.search.models import SearchIndexJob
        from open_work_hub_api.domains.source_access.resource_types import (
            FILE_MANAGER_FILE_RESOURCE_TYPE,
        )

        expected_ids = tuple(dict.fromkeys(file_ids))
        with self._session_factory() as db:
            corpus = db.get(FileManagerCorpus, corpus_id)
            if corpus is None:
                raise LiveE2EContractError("projection_inspection_failed")
            files = tuple(
                db.scalars(
                    select(FileManagerFile)
                    .where(FileManagerFile.id.in_(expected_ids))
                    .order_by(FileManagerFile.id.asc())
                ).all()
            )
            heads = tuple(
                db.scalars(
                    select(RetrievalProjectionHead)
                    .where(
                        RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RetrievalProjectionHead.resource_id.in_(expected_ids),
                    )
                    .order_by(RetrievalProjectionHead.resource_id.asc())
                ).all()
            )
            events = tuple(
                db.scalars(
                    select(RetrievalProjectionEvent)
                    .where(
                        RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RetrievalProjectionEvent.resource_id.in_(expected_ids),
                    )
                    .order_by(RetrievalProjectionEvent.event_sequence.asc())
                ).all()
            )
            search_jobs = tuple(
                db.scalars(
                    select(SearchIndexJob)
                    .where(
                        SearchIndexJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        SearchIndexJob.entity_id.in_(expected_ids),
                    )
                    .order_by(SearchIndexJob.created_at.asc(), SearchIndexJob.id.asc())
                ).all()
            )
            rag_jobs = tuple(
                db.scalars(
                    select(RagSyncJob)
                    .where(
                        RagSyncJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RagSyncJob.resource_id.in_(expected_ids),
                    )
                    .order_by(RagSyncJob.created_at.asc(), RagSyncJob.id.asc())
                ).all()
            )
            opensearch_name, qdrant_name = self._active_physical_names(db)

        if len(files) != len(expected_ids) or any(file.corpus_id != corpus_id for file in files):
            raise LiveE2EContractError("projection_inspection_failed")
        opensearch_records = self._opensearch_records(opensearch_name, expected_ids)
        qdrant_records = self._qdrant_records(qdrant_name, expected_ids)
        head_by_id = {head.resource_id: head for head in heads}
        active_source = all(
            file.deleted_at is None
            and file.extraction_status == "ready"
            and file.retrieval_partition_id == corpus.retrieval_partition_id
            for file in files
        )

        def current_job_succeeded(file_id: str, jobs: Sequence[Any], *, rag: bool) -> bool:
            head = head_by_id.get(file_id)
            if head is None:
                return False
            matching = [
                job
                for job in jobs
                if (job.resource_id if rag else job.entity_id) == file_id
                and job.projection_version == head.projection_version
                and str(job.retrieval_partition_id) == str(head.retrieval_partition_id)
                and job.desired_state == head.desired_state
                and (
                    job.operation in {"upsert", "visibility_update"}
                    if rag
                    else job.operation == "upsert"
                )
            ]
            return bool(matching) and matching[-1].status == "succeeded"

        ready = (
            active_source
            and len(heads) == len(expected_ids)
            and all(head.desired_state == "active" for head in heads)
            and all(
                current_job_succeeded(file_id, search_jobs, rag=False) for file_id in expected_ids
            )
            and all(current_job_succeeded(file_id, rag_jobs, rag=True) for file_id in expected_ids)
            and len(opensearch_records) == len(expected_ids)
            and len(qdrant_records) >= len(expected_ids)
        )
        stable_payload = {
            "files": [
                (
                    file.id,
                    str(file.retrieval_partition_id),
                    file.corpus_id,
                    file.extraction_status,
                    file.extraction_content_checksum,
                    file.deleted_at is not None,
                )
                for file in files
            ],
            "heads": [
                (
                    head.resource_id,
                    head.projection_version,
                    str(head.retrieval_partition_id),
                    head.desired_state,
                    head.content_checksum,
                    head.visibility_checksum,
                )
                for head in heads
            ],
            "events": [
                (
                    event.event_sequence,
                    event.resource_id,
                    event.projection_version,
                    str(event.retrieval_partition_id),
                    event.change_kind,
                    event.desired_state,
                    event.content_checksum,
                    event.visibility_checksum,
                )
                for event in events
            ],
            "search_jobs": [
                (
                    job.id,
                    job.entity_id,
                    job.operation,
                    job.status,
                    job.projection_version,
                    str(job.retrieval_partition_id),
                    job.desired_state,
                )
                for job in search_jobs
            ],
            "rag_jobs": [
                (
                    job.id,
                    job.resource_id,
                    job.operation,
                    job.status,
                    job.projection_version,
                    str(job.retrieval_partition_id),
                    job.desired_state,
                )
                for job in rag_jobs
            ],
            "opensearch": opensearch_records,
            "qdrant": qdrant_records,
        }
        fingerprint = _sha256_bytes(_canonical_json(_jsonable(stable_payload)).encode("ascii"))
        return {
            "retrieval_partition_id": str(corpus.retrieval_partition_id),
            "resource_count": len(files),
            "head_count": len(heads),
            "event_count": len(events),
            "search_job_count": len(search_jobs),
            "rag_job_count": len(rag_jobs),
            "opensearch_record_count": len(opensearch_records),
            "qdrant_record_count": len(qdrant_records),
            "fingerprint_sha256": fingerprint,
            "projection_ready": ready,
        }

    def snapshot(self, *, corpus_id: str, file_ids: Sequence[str]) -> dict[str, object]:
        return self._state(corpus_id=corpus_id, file_ids=file_ids)

    def content_probe(self, *, file_ids: Sequence[str]) -> tuple[str, str]:
        from sqlalchemy import select

        from open_work_hub_api.domains.files.models import FileManagerFile

        expected_ids = tuple(dict.fromkeys(file_ids))
        with self._session_factory() as db:
            rows = tuple(
                db.execute(
                    select(FileManagerFile.id, FileManagerFile.extraction_text)
                    .where(
                        FileManagerFile.id.in_(expected_ids),
                        FileManagerFile.deleted_at.is_(None),
                        FileManagerFile.extraction_status == "ready",
                    )
                    .order_by(FileManagerFile.id.asc())
                ).all()
            )
        if len(rows) != len(expected_ids):
            raise LiveE2EContractError("content_probe_unavailable")
        return select_private_content_probe(
            [(str(resource_id), str(text or "")) for resource_id, text in rows]
        )

    def cleanup_target(self, *, corpus_id: str) -> tuple[str, ...]:
        from sqlalchemy import select
        from open_work_hub_api.domains.files.models import FileManagerCorpus, FileManagerFile

        with self._session_factory() as db:
            corpus = db.get(FileManagerCorpus, corpus_id)
            if corpus is None or corpus.access_scope_kind != "company":
                raise LiveE2EContractError("cleanup_target_unavailable")
            return tuple(
                db.scalars(
                    select(FileManagerFile.id)
                    .where(
                        FileManagerFile.corpus_id == corpus_id, FileManagerFile.deleted_at.is_(None)
                    )
                    .order_by(FileManagerFile.id)
                ).all()
            )

    def wait_projected(
        self,
        *,
        corpus_id: str,
        file_ids: Sequence[str],
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            state = self.snapshot(corpus_id=corpus_id, file_ids=file_ids)
            if state.get("projection_ready") is True:
                return state
            if time.monotonic() >= deadline:
                raise LiveE2EContractError("physical_projection_timeout")
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def _removed_state(self, *, corpus_id: str, file_ids: Sequence[str]) -> dict[str, object]:
        from minio.error import S3Error
        from sqlalchemy import select

        from open_work_hub_api.domains.files.models import FileManagerFile
        from open_work_hub_api.domains.rag.models import RagSyncJob
        from open_work_hub_api.domains.retrieval.models import RetrievalProjectionHead
        from open_work_hub_api.domains.search.models import SearchIndexJob
        from open_work_hub_api.domains.source_access.resource_types import (
            FILE_MANAGER_FILE_RESOURCE_TYPE,
        )

        expected_ids = tuple(dict.fromkeys(file_ids))
        with self._session_factory() as db:
            files = tuple(
                db.scalars(
                    select(FileManagerFile).where(FileManagerFile.id.in_(expected_ids))
                ).all()
            )
            heads = tuple(
                db.scalars(
                    select(RetrievalProjectionHead).where(
                        RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RetrievalProjectionHead.resource_id.in_(expected_ids),
                    )
                ).all()
            )
            search_jobs = tuple(
                db.scalars(
                    select(SearchIndexJob).where(
                        SearchIndexJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        SearchIndexJob.entity_id.in_(expected_ids),
                        SearchIndexJob.operation == "delete",
                        SearchIndexJob.status == "succeeded",
                    )
                ).all()
            )
            rag_jobs = tuple(
                db.scalars(
                    select(RagSyncJob).where(
                        RagSyncJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RagSyncJob.resource_id.in_(expected_ids),
                        RagSyncJob.operation == "delete",
                        RagSyncJob.status == "succeeded",
                    )
                ).all()
            )
            opensearch_name, qdrant_name = self._active_physical_names(db)
        opensearch_count = len(self._opensearch_records(opensearch_name, expected_ids))
        qdrant_count = len(self._qdrant_records(qdrant_name, expected_ids))
        storage_object_count = 0
        for file in files:
            try:
                self._minio.stat_object(self._minio_bucket, file.storage_key)
            except S3Error as error:
                if error.code not in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                    raise LiveE2EContractError("storage_cleanup_inspection_failed") from error
            except Exception as error:
                raise LiveE2EContractError("storage_cleanup_inspection_failed") from error
            else:
                storage_object_count += 1
        return {
            "resource_count": len(files),
            "deleted_source_count": sum(file.deleted_at is not None for file in files),
            "deleted_head_count": sum(head.desired_state == "deleted" for head in heads),
            "opensearch_record_count": opensearch_count,
            "qdrant_record_count": qdrant_count,
            "storage_object_count": storage_object_count,
            "search_delete_succeeded_count": len({job.entity_id for job in search_jobs}),
            "rag_delete_succeeded_count": len({job.resource_id for job in rag_jobs}),
        }

    def wait_removed(
        self,
        *,
        corpus_id: str,
        file_ids: Sequence[str],
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_seconds
        expected = len(set(file_ids))
        while True:
            state = self._removed_state(corpus_id=corpus_id, file_ids=file_ids)
            if (
                state.get("resource_count") == expected
                and state.get("deleted_source_count") == expected
                and state.get("deleted_head_count") == expected
                and state.get("search_delete_succeeded_count") == expected
                and state.get("rag_delete_succeeded_count") == expected
                and state.get("opensearch_record_count") == 0
                and state.get("qdrant_record_count") == 0
                and state.get("storage_object_count") == 0
            ):
                return state
            if time.monotonic() >= deadline:
                raise LiveE2EContractError("backend_cleanup_timeout")
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))


def _validate_identity_matrix(
    *, actor: dict[str, object], observer_a: dict[str, object], observer_b: dict[str, object]
) -> tuple[str, str, str]:
    identities = (actor, observer_a, observer_b)
    user_ids = tuple(str(identity.get("id") or "") for identity in identities)
    if any(not user_id for user_id in user_ids) or len(set(user_ids)) != 3:
        raise LiveE2EContractError("distinct_dev_identities_required")
    if "platform_admin" not in actor.get("system_roles", []):
        raise LiveE2EContractError("company_platform_admin_required")
    if any(
        "platform_admin" in identity.get("system_roles", [])
        for identity in (observer_a, observer_b)
    ):
        raise LiveE2EContractError("non_admin_observers_required")
    return user_ids


def _validated_search_pages(
    *,
    api: LiveFilesApi,
    query: str,
    strategy: str,
    page_size: int,
    require_strategy_methods: bool = True,
    required_highlight_file_id: str | None = None,
) -> tuple[set[str], dict[str, object]]:
    first = api.search(
        query=query,
        strategy=strategy,
        page=1,
        page_size=page_size,
    )
    second = api.search(
        query=query,
        strategy=strategy,
        page=2,
        page_size=page_size,
    )
    repeated = api.search(
        query=query,
        strategy=strategy,
        page=1,
        page_size=page_size,
    )
    pages = (first, second)
    rows: list[dict[str, object]] = []
    for expected_page, payload in enumerate(pages, start=1):
        if (
            payload.get("query") != query
            or payload.get("strategy") != strategy
            or payload.get("page") != expected_page
            or payload.get("page_size") != page_size
            or payload.get("max_ranked_results") != 100
            or not isinstance(payload.get("hits"), list)
        ):
            raise LiveE2EContractError("invalid_search_contract")
        rows.extend(payload["hits"])  # type: ignore[arg-type]
    if repeated.get("hits") != first.get("hits"):
        raise LiveE2EContractError("unstable_search_ranking")

    expected_rank = 1
    previous_score = float("inf")
    file_ids: set[str] = set()
    method_union: set[str] = set()
    highlighted_file_ids: set[str] = set()
    max_snippet_chars = 0
    max_snippet_words = 0
    max_highlights = 0
    for row in rows:
        rank = row.get("rank")
        score = row.get("score")
        file_id = row.get("file_id")
        methods = row.get("methods")
        snippet = row.get("snippet")
        if (
            rank != expected_rank
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or float(score) > previous_score
            or not isinstance(file_id, str)
            or not file_id
            or file_id in file_ids
            or not isinstance(methods, list)
            or not isinstance(snippet, dict)
        ):
            raise LiveE2EContractError("invalid_search_ranking")
        text = snippet.get("text")
        highlights = snippet.get("highlights")
        if not isinstance(text, str) or len(text) > 4_000 or not isinstance(highlights, list):
            raise LiveE2EContractError("invalid_search_snippet")
        for highlight in highlights:
            if (
                not isinstance(highlight, dict)
                or not isinstance(highlight.get("start"), int)
                or not isinstance(highlight.get("end"), int)
                or not 0 <= highlight["start"] < highlight["end"] <= len(text)
            ):
                raise LiveE2EContractError("invalid_search_snippet")
        word_count = len(re.findall(r"\S+", text))
        if "bm25" in methods and word_count > 101:
            raise LiveE2EContractError("invalid_search_snippet")
        expected_rank += 1
        previous_score = float(score)
        file_ids.add(file_id)
        method_union.update(str(method) for method in methods)
        if highlights:
            highlighted_file_ids.add(file_id)
        max_snippet_chars = max(max_snippet_chars, len(text))
        max_snippet_words = max(max_snippet_words, word_count)
        max_highlights = max(max_highlights, len(highlights))

    required_methods = {
        "keyword": {"bm25"},
        "semantic": {"dense_vector"},
        "hybrid": {"bm25", "dense_vector", "rrf"},
    }[strategy]
    if require_strategy_methods and rows and not required_methods <= method_union:
        raise LiveE2EContractError("search_method_missing")
    if (
        required_highlight_file_id is not None
        and required_highlight_file_id not in highlighted_file_ids
    ):
        raise LiveE2EContractError("content_search_snippet_missing")
    latency_values = [payload.get("latency_ms") for payload in pages]
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) for value in latency_values
    ):
        raise LiveE2EContractError("invalid_search_contract")
    return file_ids, {
        "page_count": 2,
        "returned_count": len(rows),
        "matched_method_count": len(method_union),
        "max_snippet_chars": max_snippet_chars,
        "max_snippet_words": max_snippet_words,
        "max_highlights": max_highlights,
        "latency_ms": round(sum(float(value) for value in latency_values), 3),
    }


def _assert_acl_visibility(
    *,
    api: LiveFilesApi,
    query: str,
    expected_file_ids: set[str],
    visible: bool,
) -> None:
    observed, _metrics = _validated_search_pages(
        api=api,
        query=query,
        strategy="hybrid",
        page_size=50,
        # ACL probes can legitimately return unrelated semantic-only rows. The
        # main strategy probes above still enforce the full hybrid method set.
        require_strategy_methods=False,
    )
    matched = observed & expected_file_ids
    if (visible and matched != expected_file_ids) or (not visible and matched):
        raise LiveE2EContractError("acl_matrix_failed")


def _assert_projections_stable(
    baseline: dict[str, object], current: dict[str, object], *, partition_id: str
) -> None:
    if current != baseline or current.get("retrieval_partition_id") != partition_id:
        raise LiveE2EContractError("admission_reindexed_projection")


def _recover_live_files(
    *,
    actor_api: LiveFilesApi,
    inspector: ProjectionInspector,
    corpus_id: str,
    known_file_ids: Sequence[str],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, object] | None:
    active_file_ids = inspector.cleanup_target(corpus_id=corpus_id)
    all_file_ids = tuple(dict.fromkeys((*known_file_ids, *active_file_ids)))
    if active_file_ids:
        try:
            actor_api.bulk_delete(active_file_ids)
        except Exception:
            pass
    if not all_file_ids:
        return None
    return inspector.wait_removed(
        corpus_id=corpus_id,
        file_ids=all_file_ids,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def run_live_e2e(
    *,
    source: Path,
    canaries: Sequence[LiveCanary],
    acl_group_id: str,
    actor_api: LiveFilesApi,
    observer_a_api: LiveFilesApi,
    observer_b_api: LiveFilesApi,
    inspector: ProjectionInspector,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, object]:
    """Use a dedicated empty Files-admission group; preserve all company policy settings."""
    if not canaries or not acl_group_id or timeout_seconds <= 0 or poll_interval_seconds <= 0:
        raise LiveE2EContractError("invalid_live_limits")
    user_ids = _validate_identity_matrix(
        actor=actor_api.identity(),
        observer_a=observer_a_api.identity(),
        observer_b=observer_b_api.identity(),
    )
    actor_api.preflight()
    actor_api.validate_acl_group(acl_group_id)
    observer_a_api.assert_app_denied()
    observer_b_api.assert_app_denied()
    query = canaries[0].upload_name.split(".", 1)[0][:16]
    query_id = _sha256_bytes(b"open-work-hub-files-live-query-v1\0" + query.encode("ascii"))
    corpus = actor_api.create_corpus(f"rag-e2e-{_sha256_bytes(query.encode('ascii'))[:16]}")
    corpus_id = str(corpus.get("id") or "")
    partition_id = str(corpus.get("retrieval_partition_id") or "")
    if (
        not corpus_id
        or not partition_id
        or corpus.get("metadata_version") != 1
        or corpus.get("access_scope_kind") != "company"
    ):
        raise LiveE2EContractError("invalid_corpus_response")
    file_ids = []
    cleanup_complete = False
    try:
        actor_api.replace_acl_group_members(acl_group_id, [user_ids[1]])
        observer_a_api.preflight()
        observer_b_api.assert_app_denied()
        for canary in canaries:
            uploaded = actor_api.upload(corpus_id, canary)
            file_id = str(uploaded.get("id") or "")
            if not file_id or file_id in file_ids or uploaded.get("filename") != canary.upload_name:
                raise LiveE2EContractError("invalid_upload_response")
            file_ids.append(file_id)
        expected_file_ids = set(file_ids)
        statuses = actor_api.wait_ready(
            file_ids, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds
        )
        if statuses != {file_id: "ready" for file_id in file_ids}:
            raise LiveE2EContractError("projection_not_ready")
        baseline = inspector.wait_projected(
            corpus_id=corpus_id,
            file_ids=file_ids,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        if baseline.get("retrieval_partition_id") != partition_id:
            raise LiveE2EContractError("projection_partition_mismatch")
        content_query, content_target_file_id = inspector.content_probe(file_ids=file_ids)
        if content_target_file_id not in expected_file_ids:
            raise LiveE2EContractError("content_probe_unavailable")
        content_query_id = _sha256_bytes(
            b"open-work-hub-files-live-content-query-v1\0" + content_query.encode("utf-8")
        )
        search_metrics = {}
        for label, probe in (("", query), ("content_", content_query)):
            for strategy in ("keyword", "semantic", "hybrid"):
                observed, metrics = _validated_search_pages(
                    api=actor_api,
                    query=probe,
                    strategy=strategy,
                    page_size=5,
                    required_highlight_file_id=content_target_file_id
                    if label and strategy == "keyword"
                    else None,
                )
                if not (observed & expected_file_ids) or (
                    label and content_target_file_id not in observed
                ):
                    raise LiveE2EContractError(
                        "content_search_miss" if label else "canary_search_miss"
                    )
                search_metrics[label + strategy] = metrics
        _assert_acl_visibility(
            api=observer_a_api, query=query, expected_file_ids=expected_file_ids, visible=True
        )
        stale_urls = []
        for canary, file_id in zip(canaries, file_ids, strict=True):
            url, digest, size = observer_a_api.fresh_download(file_id)
            stale_urls.append(url)
            if digest != canary.content_sha256 or size != canary.size_bytes:
                raise LiveE2EContractError("download_content_mismatch")
        actor_api.replace_acl_group_members(acl_group_id, [user_ids[1], user_ids[2]])
        _assert_acl_visibility(
            api=observer_b_api,
            query=content_query,
            expected_file_ids={content_target_file_id},
            visible=True,
        )
        actor_api.replace_acl_group_members(acl_group_id, [user_ids[2]])
        observer_a_api.assert_app_denied()
        for url in stale_urls:
            observer_a_api.assert_stale_download_denied(url)
        _assert_projections_stable(
            baseline,
            inspector.snapshot(corpus_id=corpus_id, file_ids=file_ids),
            partition_id=partition_id,
        )
        final_urls = []
        for canary, file_id in zip(canaries, file_ids, strict=True):
            url, digest, size = observer_b_api.fresh_download(file_id)
            final_urls.append(url)
            if digest != canary.content_sha256 or size != canary.size_bytes:
                raise LiveE2EContractError("download_content_mismatch_after_revocation")
        actor_api.bulk_delete(file_ids)
        cleanup = inspector.wait_removed(
            corpus_id=corpus_id,
            file_ids=file_ids,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        for url in final_urls:
            observer_b_api.assert_stale_download_denied(url)
        _assert_acl_visibility(
            api=observer_b_api, query=query, expected_file_ids=expected_file_ids, visible=False
        )
        actor_api.replace_acl_group_members(acl_group_id, [])
        observer_b_api.assert_app_denied()
        cleanup_complete = True
        return {
            "schema_version": "open-work-hub.files-rag-live-e2e.v2",
            "status": "passed",
            "source_root_id": _sha256_bytes(
                b"open-work-hub-files-live-source-root-v1\0"
                + os.fsencode(str(_resolve_source_root(source)))
            ),
            "query_id": query_id,
            "content_query_id": content_query_id,
            "identity_ids": [_sha256_bytes(value.encode("utf-8")) for value in user_ids],
            "corpus_id": corpus_id,
            "retrieval_partition_id": partition_id,
            "canaries": [
                {
                    "source_id": canary.source_id,
                    "content_sha256": canary.content_sha256,
                    "file_id": file_id,
                    "extension": canary.extension,
                    "size_bytes": canary.size_bytes,
                }
                for canary, file_id in zip(canaries, file_ids, strict=True)
            ],
            "search": search_metrics,
            "acl": {"company_group_admission_and_revocation": True},
            "download": {"sha256_match": True, "byte_count_match": True},
            "admission_changes": {
                "count": 4,
                "partition_unchanged": True,
                "projection_unchanged": True,
                "baseline": baseline,
            },
            "cleanup": cleanup,
            "corpus_retained": True,
        }
    finally:
        if not cleanup_complete:
            cleanup_error = None
            try:
                _recover_live_files(
                    actor_api=actor_api,
                    inspector=inspector,
                    corpus_id=corpus_id,
                    known_file_ids=file_ids,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                )
            except Exception as error:
                cleanup_error = error
            try:
                actor_api.replace_acl_group_members(acl_group_id, [])
            except Exception as error:
                cleanup_error = error
            if cleanup_error is not None:
                raise LiveE2EContractError("canary_cleanup_failed_after_error") from cleanup_error


def assert_development_runtime(settings: object) -> None:
    environment = str(getattr(settings, "environment", "") or "").strip().lower()
    profile = str(getattr(settings, "env_profile", "") or "").strip().lower()
    if is_production_like_environment(environment) or profile not in NON_PRODUCTION_PROFILES:
        raise LiveE2EContractError("development_runtime_required")


def assert_development_data_plane(settings: object) -> None:
    """Require the project's loopback development data-plane identity."""

    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    def require_loopback(value: object) -> None:
        raw = str(value or "").strip()
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        hostname = parsed.hostname
        if hostname == "localhost":
            return
        try:
            address = ipaddress.ip_address(hostname or "")
        except ValueError as error:
            raise LiveE2EContractError("development_data_plane_required") from error
        if not address.is_loopback:
            raise LiveE2EContractError("development_data_plane_required")

    try:
        database_url = make_url(str(getattr(settings, "postgres_dsn", "") or ""))
    except Exception as error:
        raise LiveE2EContractError("development_data_plane_required") from error
    if database_url.database != "open_work_hub_dev":
        raise LiveE2EContractError("development_data_plane_required")
    require_loopback(database_url.host)
    require_loopback(getattr(settings, "opensearch_url", ""))
    require_loopback(getattr(settings, "rag_qdrant_url", ""))
    require_loopback(getattr(settings, "minio_endpoint", ""))
    expected_names = {
        "minio_bucket": "open-work-hub-dev",
        "opensearch_index_prefix": "open-work-hub-dev",
        "rag_qdrant_collection_prefix": "open-work-hub-dev-rag",
    }
    if any(
        str(getattr(settings, attribute, "") or "").strip() != expected
        for attribute, expected in expected_names.items()
    ):
        raise LiveE2EContractError("development_data_plane_required")

    workspace_root = Path(__file__).resolve().parents[3]
    production_env = workspace_root.parent / "prod" / ".env"
    if not production_env.exists():
        return
    values = dotenv_values(production_env)
    bindings = (
        ("OPEN_WORK_HUB_POSTGRES_DSN", "postgres_dsn"),
        ("OPEN_WORK_HUB_OPENSEARCH_URL", "opensearch_url"),
        ("OPEN_WORK_HUB_RAG_QDRANT_URL", "rag_qdrant_url"),
        ("OPEN_WORK_HUB_MINIO_ENDPOINT", "minio_endpoint"),
    )
    for environment_key, attribute in bindings:
        production_value = str(values.get(environment_key) or "").rstrip("/")
        selected_value = str(getattr(settings, attribute, "") or "").rstrip("/")
        if production_value and selected_value and production_value == selected_value:
            raise LiveE2EContractError("production_data_plane_refused")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--acl-group-id")
    parser.add_argument("--actor-token-env")
    parser.add_argument("--observer-a-token-env")
    parser.add_argument("--observer-b-token-env")
    parser.add_argument("--max-canaries", type=int, default=8)
    parser.add_argument("--max-total-mib", type=int, default=50)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--poll-interval-seconds", type=float, default=2)
    parser.add_argument("--execute-live-e2e", action="store_true")
    parser.add_argument("--acknowledge-development")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report_written = False
    try:
        if not args.execute_live_e2e:
            raise LiveE2EContractError("execution_flag_required")
        if args.acknowledge_development != EXECUTION_ACK:
            raise LiveE2EContractError("development_acknowledgement_required")
        # Prevent dependency request logging from serializing signed URLs or
        # Authorization-bearing request metadata in an operator terminal.
        logging.getLogger("httpx").disabled = True
        logging.getLogger("httpcore").disabled = True
        from open_work_hub_api.core.settings import get_settings

        settings = get_settings()
        assert_development_runtime(settings)
        assert_development_data_plane(settings)
        assert_development_api_origin(args.api_base_url)
        if not bool(getattr(settings, "files_retrieval_enabled", False)):
            raise LiveE2EContractError("files_retrieval_not_enabled")
        _resolve_report_output(args.source, args.report_out)
        if not 1 <= args.max_total_mib <= 120:
            raise LiveE2EContractError("invalid_live_limits")
        token_environment_names = (
            args.actor_token_env,
            args.observer_a_token_env,
            args.observer_b_token_env,
        )
        if not args.acl_group_id or any(
            not isinstance(name, str) or not name for name in token_environment_names
        ):
            raise LiveE2EContractError("live_scope_required")
        if len(set(token_environment_names)) != 3:
            raise LiveE2EContractError("distinct_token_environment_names_required")
        tokens = tuple(str(os.environ.get(name) or "") for name in token_environment_names)
        if any(not token for token in tokens) or len(set(tokens)) != 3:
            raise LiveE2EContractError("distinct_auth_tokens_required")
        canaries = select_live_canaries(
            args.source,
            max_canaries=args.max_canaries,
            max_total_bytes=args.max_total_mib * 1024 * 1024,
            workers=args.workers,
        )
        apis = tuple(
            HttpFilesApi(
                base_url=args.api_base_url,
                token=token,
                timeout_seconds=min(max(args.timeout_seconds, 1), 120),
            )
            for token in tokens
        )
        inspector = DevelopmentProjectionInspector(settings)
        try:
            report = run_live_e2e(
                source=args.source,
                canaries=canaries,
                acl_group_id=args.acl_group_id,
                actor_api=apis[0],
                observer_a_api=apis[1],
                observer_b_api=apis[2],
                inspector=inspector,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        finally:
            inspector.close()
            for api in apis:
                api.close()
        report_digest = write_safe_report(
            source=args.source,
            output=args.report_out,
            report=report,
        )
        report_written = True
        print(_canonical_json({"status": "passed", "report_sha256": report_digest}))
        return 0
    except LiveE2EContractError as error:
        if args.execute_live_e2e and not report_written:
            try:
                write_safe_report(
                    source=args.source,
                    output=args.report_out,
                    report={
                        "schema_version": "open-work-hub.files-rag-live-e2e.v2",
                        "status": "failed",
                        "code": error.code,
                    },
                )
            except Exception:  # noqa: BLE001 - stdout retains the authoritative safe code.
                pass
        print(_canonical_json({"status": "error", "code": error.code}))
        return 2
    except Exception:  # noqa: BLE001 - never expose source or credential details.
        if args.execute_live_e2e and not report_written:
            try:
                write_safe_report(
                    source=args.source,
                    output=args.report_out,
                    report={
                        "schema_version": "open-work-hub.files-rag-live-e2e.v2",
                        "status": "failed",
                        "code": "unexpected_error",
                    },
                )
            except Exception:  # noqa: BLE001 - never replace the sanitized failure.
                pass
        print(_canonical_json({"status": "error", "code": "unexpected_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
