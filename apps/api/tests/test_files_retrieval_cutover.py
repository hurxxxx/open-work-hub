from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from open_alm_api.domains.retrieval import files_cutover
from open_alm_api.domains.retrieval.files_cutover import (
    FilesRetrievalCutoverError,
    check_files_retrieval_cutover,
)
from open_alm_api.domains.retrieval.files_generation_runner import FilesGenerationError
from open_alm_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
)
from open_alm_api.domains.retrieval.models import RetrievalProjectionGeneration


_CHECKER_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "check_files_retrieval_cutover.py"
)


def _load_checker_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "test_check_files_retrieval_cutover_script",
        _CHECKER_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ScalarRows:
    def __init__(self, rows: list[RetrievalProjectionGeneration]) -> None:
        self._rows = rows

    def all(self) -> list[RetrievalProjectionGeneration]:
        return list(self._rows)


class _GenerationSession:
    def __init__(self, rows: list[RetrievalProjectionGeneration]) -> None:
        self._rows = rows

    def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self._rows)


def test_disabled_files_retrieval_cutover_does_not_touch_runtime_or_backends() -> None:
    result = check_files_retrieval_cutover(
        object(),  # type: ignore[arg-type]
        settings=SimpleNamespace(files_retrieval_enabled=False),  # type: ignore[arg-type]
        qdrant_collection_exists=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled Files retrieval must not probe Qdrant")
        ),
    )

    assert result.deployment_enabled is False
    assert result.ready is False
    assert result.status_line() == "status=ok deployment_enabled=0 ready=0"


def test_enabled_files_retrieval_cutover_verifies_bound_backend_existence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class KeywordIndexProbe:
        calls = 0

        def index_exists(self) -> bool:
            self.calls += 1
            return True

    keyword = KeywordIndexProbe()
    runtime = SimpleNamespace(
        release_cohort="release_20260723",
        keyword_search_client=keyword,
        rag_collection="open-alm-rag-v1-release_20260723",
    )
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: runtime,
        raising=False,
    )
    qdrant_calls: list[str] = []

    def qdrant_collection_exists(settings, collection: str) -> bool:
        del settings
        qdrant_calls.append(collection)
        return True

    result = check_files_retrieval_cutover(
        object(),  # type: ignore[arg-type]
        settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
        qdrant_collection_exists=qdrant_collection_exists,
    )

    assert keyword.calls == 1
    assert qdrant_calls == [runtime.rag_collection]
    assert result.deployment_enabled is True
    assert result.ready is True
    assert result.release_cohort == "release_20260723"
    assert result.status_line() == (
        "status=ok deployment_enabled=1 ready=1 release_cohort=release_20260723"
        " opensearch_index_present=1 qdrant_collection_present=1"
    )


def test_files_retrieval_cutover_preserves_safe_runtime_failure_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: (_ for _ in ()).throw(
            PartitionedRetrievalRuntimeUnavailable(reason="release_cohort_mismatch")
        ),
    )

    with pytest.raises(FilesRetrievalCutoverError) as caught:
        check_files_retrieval_cutover(
            object(),  # type: ignore[arg-type]
            settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
            qdrant_collection_exists=lambda *_args: pytest.fail(
                "invalid DB/runtime generation must stop before backend probes"
            ),
        )

    assert caught.value.code == "runtime_release_cohort_mismatch"


def test_files_retrieval_cutover_sanitizes_unknown_runtime_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "runtime-secret-value"
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: (_ for _ in ()).throw(
            PartitionedRetrievalRuntimeUnavailable(reason=secret)
        ),
    )

    with pytest.raises(FilesRetrievalCutoverError) as caught:
        check_files_retrieval_cutover(
            object(),  # type: ignore[arg-type]
            settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
        )

    assert caught.value.code == "runtime_unavailable"
    assert secret not in str(caught.value)


def test_files_retrieval_cutover_does_not_fallback_from_partial_active_pair() -> None:
    opensearch = RetrievalProjectionGeneration(
        id="opensearch-release_20260723",
        backend="opensearch",
        generation_key="release_20260723",
        physical_name="open-alm-test_keyword_search_documents_v3_release_20260723",
        alias_name="open-alm-test_keyword_search_documents",
        schema_version=3,
        state="active",
        validation_state="passed",
        validation_details={"release_cohort": "release_20260723"},
        validated_at=datetime(2026, 7, 23, 1, 0, 0),
    )

    with pytest.raises(FilesRetrievalCutoverError) as caught:
        check_files_retrieval_cutover(
            _GenerationSession([opensearch]),  # type: ignore[arg-type]
            settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
            qdrant_collection_exists=lambda *_args: pytest.fail(
                "partial active pair must not fall back to legacy backends"
            ),
        )

    assert caught.value.code == "runtime_missing_active_generation"


def test_files_retrieval_cutover_default_qdrant_probe_is_read_only_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = SimpleNamespace(
        release_cohort="release_20260723",
        keyword_search_client=SimpleNamespace(index_exists=lambda: True),
        rag_collection="open-alm-rag-v1-release_20260723",
    )
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: runtime,
    )
    observed: dict[str, object] = {}

    class QdrantProbeClient:
        def __init__(self, *, url: str, api_key: str | None, timeout: int) -> None:
            observed.update(url=url, api_key=api_key, timeout=timeout, closed=False)

        def collection_exists(self, *, collection_name: str) -> bool:
            observed["collection_name"] = collection_name
            return True

        def close(self) -> None:
            observed["closed"] = True

    monkeypatch.setattr(files_cutover, "QdrantClient", QdrantProbeClient, raising=False)
    settings = SimpleNamespace(
        files_retrieval_enabled=True,
        rag_vector_index_provider="qdrant",
        rag_qdrant_url="http://qdrant.internal:6333",
        rag_qdrant_api_key="test-secret-must-not-appear-in-status",
    )

    result = check_files_retrieval_cutover(
        object(),  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )

    assert observed == {
        "url": settings.rag_qdrant_url,
        "api_key": settings.rag_qdrant_api_key,
        "timeout": 5,
        "closed": True,
        "collection_name": runtime.rag_collection,
    }
    assert settings.rag_qdrant_api_key not in result.status_line()


def test_files_retrieval_cutover_fails_closed_when_physical_index_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = SimpleNamespace(
        release_cohort="release_20260723",
        keyword_search_client=SimpleNamespace(index_exists=lambda: False),
        rag_collection="open-alm-rag-v1-release_20260723",
    )
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: runtime,
    )

    with pytest.raises(FilesRetrievalCutoverError) as caught:
        check_files_retrieval_cutover(
            object(),  # type: ignore[arg-type]
            settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
            qdrant_collection_exists=lambda *_args: pytest.fail(
                "missing OpenSearch index must stop before Qdrant"
            ),
        )

    assert caught.value.code == "opensearch_index_missing"


def test_files_retrieval_cutover_fails_closed_when_physical_collection_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = SimpleNamespace(
        release_cohort="release_20260723",
        keyword_search_client=SimpleNamespace(index_exists=lambda: True),
        rag_collection="open-alm-rag-v1-release_20260723",
    )
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: runtime,
    )

    with pytest.raises(FilesRetrievalCutoverError) as caught:
        check_files_retrieval_cutover(
            object(),  # type: ignore[arg-type]
            settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
            qdrant_collection_exists=lambda *_args: False,
        )

    assert caught.value.code == "qdrant_collection_missing"


def test_files_retrieval_cutover_sanitizes_backend_probe_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "backend-secret-value"
    runtime = SimpleNamespace(
        release_cohort="release_20260723",
        keyword_search_client=SimpleNamespace(index_exists=lambda: True),
        rag_collection="open-alm-rag-v1-release_20260723",
    )
    monkeypatch.setattr(
        files_cutover,
        "resolve_partitioned_files_query_runtime",
        lambda db, *, settings: runtime,
    )

    with pytest.raises(FilesRetrievalCutoverError) as caught:
        check_files_retrieval_cutover(
            object(),  # type: ignore[arg-type]
            settings=SimpleNamespace(files_retrieval_enabled=True),  # type: ignore[arg-type]
            qdrant_collection_exists=lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
        )

    assert caught.value.code == "qdrant_probe_failed"
    assert secret not in str(caught.value)


def test_files_retrieval_cutover_script_sanitizes_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = _load_checker_script()
    secret = "database-secret-value"

    backends = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(checker, "get_settings", lambda: object())
    monkeypatch.setattr(checker, "get_session_factory", lambda: object())
    monkeypatch.setattr(checker, "FilesPhysicalGenerationBackends", lambda _settings: backends)
    monkeypatch.setattr(
        checker,
        "FilesCachedProjectionMaterializer",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        checker,
        "FilesGenerationRunner",
        lambda **_kwargs: SimpleNamespace(
            verify_active=lambda: (_ for _ in ()).throw(RuntimeError(secret))
        ),
    )

    assert checker.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "status=failed reason=cutover_check_failed"
    assert secret not in captured.err


@pytest.mark.parametrize(
    "reason",
    ["active_alias_mismatch", "stored_validation_evidence_invalid"],
)
def test_files_retrieval_cutover_script_runs_full_generation_evidence_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reason: str,
) -> None:
    checker = _load_checker_script()
    closed: list[bool] = []
    monkeypatch.setattr(checker, "get_settings", lambda: object())
    monkeypatch.setattr(checker, "get_session_factory", lambda: object())
    monkeypatch.setattr(
        checker,
        "FilesPhysicalGenerationBackends",
        lambda _settings: SimpleNamespace(close=lambda: closed.append(True)),
    )
    monkeypatch.setattr(
        checker,
        "FilesCachedProjectionMaterializer",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        checker,
        "FilesGenerationRunner",
        lambda **_kwargs: SimpleNamespace(
            verify_active=lambda: (_ for _ in ()).throw(FilesGenerationError(reason))
        ),
    )

    assert checker.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"status=failed reason={reason}"
    assert closed == [True]
