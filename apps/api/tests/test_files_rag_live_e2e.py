from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import urlparse


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "files_rag_live_e2e.py"
    spec = importlib.util.spec_from_file_location("test_files_rag_live_e2e_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_e2e_requires_explicit_execution_and_refuses_production_like(
    tmp_path: Path,
    capsys,
) -> None:
    live = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    (source / "canary.txt").write_text("private body", encoding="utf-8")
    report = tmp_path / "report.json"

    assert live.main(["--source", str(source), "--report-out", str(report)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "code": "execution_flag_required",
    }
    assert not report.exists()

    settings = SimpleNamespace(
        environment="production",
        env_profile="prod",
        files_retrieval_enabled=True,
    )
    try:
        live.assert_development_runtime(settings)
    except live.LiveE2EContractError as error:
        assert error.code == "development_runtime_required"
    else:
        raise AssertionError("production-like runtime was accepted")

    settings.environment = "preview"
    settings.env_profile = "dev"
    try:
        live.assert_development_runtime(settings)
    except live.LiveE2EContractError as error:
        assert error.code == "development_runtime_required"
    else:
        raise AssertionError("preview runtime was accepted")


def test_live_e2e_requires_positive_loopback_development_data_plane_identity() -> None:
    live = _load_script_module()
    settings = SimpleNamespace(
        postgres_dsn="postgresql+psycopg://dev:dev@127.0.0.1:5432/open_work_hub_dev",
        opensearch_url="http://127.0.0.1:59210",
        rag_qdrant_url="http://localhost:16333",
        minio_endpoint="127.0.0.1:59000",
        minio_bucket="open-work-hub-dev",
        opensearch_index_prefix="open-work-hub-dev",
        rag_qdrant_collection_prefix="open-work-hub-dev-rag",
    )

    live.assert_development_data_plane(settings)

    for attribute, unsafe in (
        ("postgres_dsn", "postgresql+psycopg://dev:dev@db.example:5432/open_work_hub_prod"),
        ("opensearch_url", "https://search.example"),
        ("rag_qdrant_url", "https://vectors.example"),
        ("minio_endpoint", "objects.example:9000"),
        ("minio_bucket", "open-work-hub-prod"),
        ("opensearch_index_prefix", "open-work-hub-prod"),
        ("rag_qdrant_collection_prefix", "open-work-hub-prod-rag"),
    ):
        changed = SimpleNamespace(**{**vars(settings), attribute: unsafe})
        try:
            live.assert_development_data_plane(changed)
        except live.LiveE2EContractError as error:
            assert error.code in {
                "development_data_plane_required",
                "production_data_plane_refused",
            }
        else:
            raise AssertionError(f"unsafe development binding accepted: {attribute}")


def test_canary_selection_is_bounded_hashed_and_report_is_private(
    tmp_path: Path,
) -> None:
    live = _load_script_module()
    source = tmp_path / "private-source"
    source.mkdir()
    secret_names = [
        "CUSTOMER_ALPHA_secret.txt",
        "GEARBOX_BETA_private.md",
        "THERMAL_GAMMA_confidential.csv",
    ]
    secret_bodies = [
        "alpha private evidence",
        "beta private evidence",
        "gamma,private,evidence",
    ]
    for name, body in zip(secret_names, secret_bodies, strict=True):
        (source / name).write_text(body, encoding="utf-8")
    (source / "linked.txt").symlink_to(source / secret_names[0])

    selected = live.select_live_canaries(
        source,
        max_canaries=2,
        max_total_bytes=64,
        workers=1,
        run_nonce=b"fixed-test-nonce",
    )

    assert 0 < len(selected) <= 2
    assert sum(item.size_bytes for item in selected) <= 64
    for item in selected:
        assert live.HASHED_UPLOAD_NAME_RE.fullmatch(item.upload_name)
        assert item.candidate.path.is_relative_to(source)

    report = {
        "status": "passed",
        "canaries": [
            {
                "source_id": item.source_id,
                "content_sha256": item.content_sha256,
                "file_id": f"file-{index}",
            }
            for index, item in enumerate(selected)
        ],
    }
    report_out = tmp_path / "safe-report.json"
    digest = live.write_safe_report(source=source, output=report_out, report=report)
    serialized = report_out.read_text(encoding="ascii")

    assert len(digest) == 64
    assert os.stat(report_out).st_mode & 0o777 == 0o600
    assert all(name not in serialized for name in secret_names)
    assert all(body not in serialized for body in secret_bodies)

    try:
        live.write_safe_report(
            source=source,
            output=source / "forbidden.json",
            report=report,
        )
    except live.LiveE2EContractError as error:
        assert error.code == "report_output_inside_source"
    else:
        raise AssertionError("report was allowed inside the source tree")

    existing = tmp_path / "existing.json"
    existing.write_text("keep-me", encoding="ascii")
    try:
        live.write_safe_report(source=source, output=existing, report=report)
    except live.LiveE2EContractError as error:
        assert error.code == "invalid_report_output"
    else:
        raise AssertionError("existing report was overwritten")
    assert existing.read_text(encoding="ascii") == "keep-me"

    symlink_output = tmp_path / "report-link.json"
    symlink_output.symlink_to(tmp_path / "missing-target.json")
    try:
        live.write_safe_report(source=source, output=symlink_output, report=report)
    except live.LiveE2EContractError as error:
        assert error.code == "invalid_report_output"
    else:
        raise AssertionError("symlink report target was followed")


def test_content_probe_is_derived_from_body_and_never_requires_a_filename() -> None:
    live = _load_script_module()
    query, target = live.select_private_content_probe(
        [
            ("file-a", "common words repeat common words repeat"),
            (
                "file-b",
                "gearbox thermal calibration evidence sequence remains uniquely searchable",
            ),
        ]
    )

    assert target == "file-b"
    assert set(query.split()) <= {
        "gearbox",
        "thermal",
        "calibration",
        "evidence",
        "sequence",
        "remains",
        "uniquely",
        "searchable",
    }
    assert 16 <= len(query) <= 320


class _FakeLiveState:
    def __init__(self) -> None:
        self.scope = "workspace"
        self.workspace = "workspace-a"
        self.metadata_version = 1
        self.partition_id = "partition-stable"
        self.corpus_id = "corpus-e2e"
        self.files: dict[str, dict[str, str]] = {}
        self.deleted = False


class _FakeLiveApi:
    def __init__(self, state: _FakeLiveState, *, principal: str) -> None:
        self.state = state
        self.principal = principal

    def identity(self):
        memberships = {
            "actor": {"workspace-a": "admin", "workspace-b": "admin"},
            "observer-a": {"workspace-a": "member"},
            "observer-b": {"workspace-b": "member"},
        }[self.principal]
        return {
            "id": f"id-{self.principal}",
            "system_roles": [],
            "workspaces": [
                {"id": f"id-{slug}", "slug": slug, "role": role}
                for slug, role in memberships.items()
            ],
        }

    def preflight(self, workspace_slug: str) -> None:
        assert workspace_slug in {"workspace-a", "workspace-b"}

    def create_corpus(self, workspace_slug: str, name: str):
        assert self.principal == "actor" and workspace_slug == "workspace-a"
        assert "private" not in name
        return {
            "id": self.state.corpus_id,
            "managed_workspace_id": "id-workspace-a",
            "access_scope_kind": "workspace",
            "retrieval_partition_id": self.state.partition_id,
            "metadata_version": 1,
        }

    def upload(self, workspace_slug: str, corpus_id: str, canary):
        assert workspace_slug == "workspace-a" and corpus_id == self.state.corpus_id
        file_id = f"file-{len(self.state.files) + 1}"
        self.state.files[file_id] = {
            "sha256": canary.content_sha256,
            "upload_name": canary.upload_name,
            "size_bytes": str(canary.size_bytes),
        }
        return {"id": file_id, "filename": canary.upload_name, "rag_status": "pending"}

    def wait_ready(self, workspace_slug: str, file_ids, **_kwargs):
        assert workspace_slug == self.state.workspace
        assert set(file_ids) == set(self.state.files)
        return {file_id: "ready" for file_id in file_ids}

    def search(self, workspace_slug: str, *, query: str, strategy: str, page: int, page_size: int):
        assert query and query not in {"private body", "alpha private evidence"}
        visible = self.state.scope == "company" or workspace_slug == self.state.workspace
        ids = sorted(self.state.files) if visible and not self.state.deleted else []
        start = (page - 1) * page_size
        methods = {
            "keyword": ["bm25"],
            "semantic": ["semantic", "vector", "dense_vector"],
            "hybrid": ["bm25", "semantic", "vector", "dense_vector", "rrf"],
        }[strategy]
        hits = [
            {
                "rank": index + 1,
                "file_id": file_id,
                "score": float(len(ids) - index),
                "methods": methods,
                "snippet": {
                    "text": "bounded safe snippet",
                    "highlights": ([{"start": 0, "end": 7}] if strategy == "keyword" else []),
                },
            }
            for index, file_id in enumerate(ids)
        ][start : start + page_size]
        return {
            "query": query,
            "strategy": strategy,
            "page": page,
            "page_size": page_size,
            "hits": hits,
            "has_more": start + page_size < len(ids),
            "max_ranked_results": 100,
            "latency_ms": 7,
            "trace_id": None,
        }

    def fresh_download(self, workspace_slug: str, file_id: str):
        assert self.state.scope == "company" or workspace_slug == self.state.workspace
        row = self.state.files[file_id]
        return (
            f"http://127.0.0.1:8001/api/v1/files/content/{file_id}"
            f"?epoch={self.state.metadata_version}",
            row["sha256"],
            int(row["size_bytes"]),
        )

    def assert_stale_download_denied(self, url: str) -> None:
        epoch = int(urlparse(url).query.split("=", 1)[1])
        assert self.state.deleted or epoch < self.state.metadata_version

    def transition(
        self,
        workspace_slug: str,
        corpus_id: str,
        *,
        expected_metadata_version: int,
        access_scope_kind: str,
        target_workspace_id: str | None,
        request_id: str,
    ):
        assert self.principal == "actor" and corpus_id == self.state.corpus_id
        assert workspace_slug == self.state.workspace
        assert expected_metadata_version == self.state.metadata_version
        assert request_id
        self.state.metadata_version += 1
        self.state.scope = access_scope_kind
        if target_workspace_id is not None:
            self.state.workspace = target_workspace_id.removeprefix("id-")
        return {
            "id": corpus_id,
            "managed_workspace_id": f"id-{self.state.workspace}",
            "access_scope_kind": self.state.scope,
            "retrieval_partition_id": self.state.partition_id,
            "metadata_version": self.state.metadata_version,
        }

    def bulk_delete(self, workspace_slug: str, file_ids) -> None:
        assert workspace_slug == self.state.workspace
        assert set(file_ids) == set(self.state.files)
        self.state.deleted = True


class _FakeProjectionInspector:
    def __init__(self, state: _FakeLiveState) -> None:
        self.state = state

    def wait_projected(self, *, corpus_id: str, file_ids, **_kwargs):
        assert corpus_id == self.state.corpus_id
        return {
            "retrieval_partition_id": self.state.partition_id,
            "resource_count": len(file_ids),
            "head_count": len(file_ids),
            "event_count": len(file_ids),
            "search_job_count": len(file_ids),
            "rag_job_count": len(file_ids),
            "opensearch_record_count": len(file_ids),
            "qdrant_record_count": len(file_ids),
            "fingerprint_sha256": "a" * 64,
        }

    def snapshot(self, *, corpus_id: str, file_ids):
        return self.wait_projected(corpus_id=corpus_id, file_ids=file_ids)

    def content_probe(self, *, file_ids):
        return "do not report body content", sorted(file_ids)[0]

    def cleanup_target(self, *, corpus_id: str):
        assert corpus_id == self.state.corpus_id
        active_ids = () if self.state.deleted else tuple(sorted(self.state.files))
        return self.state.workspace, active_ids

    def wait_removed(self, *, corpus_id: str, file_ids, **_kwargs):
        assert self.state.deleted
        return {
            "resource_count": len(file_ids),
            "deleted_head_count": len(file_ids),
            "opensearch_record_count": 0,
            "qdrant_record_count": 0,
            "storage_object_count": 0,
            "search_delete_succeeded_count": len(file_ids),
            "rag_delete_succeeded_count": len(file_ids),
        }


def test_live_flow_exercises_search_acl_transitions_download_and_cleanup_without_secrets(
    tmp_path: Path,
) -> None:
    live = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    secret_name = "DO_NOT_REPORT_original.txt"
    secret_body = "DO NOT REPORT BODY CONTENT"
    (source / secret_name).write_text(secret_body, encoding="utf-8")
    canaries = live.select_live_canaries(
        source,
        max_canaries=1,
        max_total_bytes=1024,
        workers=1,
        run_nonce=b"flow-test-nonce",
    )
    state = _FakeLiveState()

    report = live.run_live_e2e(
        source=source,
        canaries=canaries,
        workspace_a="workspace-a",
        workspace_b="workspace-b",
        actor_api=_FakeLiveApi(state, principal="actor"),
        workspace_a_observer_api=_FakeLiveApi(state, principal="observer-a"),
        workspace_b_observer_api=_FakeLiveApi(state, principal="observer-b"),
        inspector=_FakeProjectionInspector(state),
        timeout_seconds=10,
        poll_interval_seconds=0.01,
    )

    assert report["status"] == "passed"
    assert report["acl"]["workspace_company_workspace_and_a_to_b"] is True
    assert report["transitions"]["projection_unchanged"] is True
    assert report["cleanup"]["opensearch_record_count"] == 0
    assert report["cleanup"]["qdrant_record_count"] == 0
    serialized = json.dumps(report, ensure_ascii=False)
    assert secret_name not in serialized
    assert secret_body not in serialized
    assert "do not report body content" not in serialized
    assert len(report["content_query_id"]) == 64
    assert "bounded safe snippet" not in serialized
    assert "Authorization" not in serialized


def test_transition_projection_drift_fails_closed_and_still_cleans_canaries(
    tmp_path: Path,
) -> None:
    live = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    (source / "private.txt").write_text("private evidence", encoding="utf-8")
    canaries = live.select_live_canaries(
        source,
        max_canaries=1,
        max_total_bytes=1024,
        workers=1,
        run_nonce=b"drift-test-nonce",
    )
    state = _FakeLiveState()

    class DriftingInspector(_FakeProjectionInspector):
        def snapshot(self, *, corpus_id: str, file_ids):
            snapshot = super().snapshot(corpus_id=corpus_id, file_ids=file_ids)
            return {**snapshot, "fingerprint_sha256": "b" * 64}

    try:
        live.run_live_e2e(
            source=source,
            canaries=canaries,
            workspace_a="workspace-a",
            workspace_b="workspace-b",
            actor_api=_FakeLiveApi(state, principal="actor"),
            workspace_a_observer_api=_FakeLiveApi(state, principal="observer-a"),
            workspace_b_observer_api=_FakeLiveApi(state, principal="observer-b"),
            inspector=DriftingInspector(state),
            timeout_seconds=10,
            poll_interval_seconds=0.01,
        )
    except live.LiveE2EContractError as error:
        assert error.code == "transition_reindexed_projection"
    else:
        raise AssertionError("projection drift was accepted")
    assert state.deleted is True


def test_upload_commit_then_client_failure_recovers_unknown_file_ids(
    tmp_path: Path,
) -> None:
    live = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    (source / "private.txt").write_text(
        "private evidence remains searchable after extraction",
        encoding="utf-8",
    )
    canaries = live.select_live_canaries(
        source,
        max_canaries=1,
        max_total_bytes=1024,
        workers=1,
        run_nonce=b"upload-loss-test-nonce",
    )
    state = _FakeLiveState()

    class ResponseLostAfterCommit(_FakeLiveApi):
        def upload(self, workspace_slug: str, corpus_id: str, canary):
            super().upload(workspace_slug, corpus_id, canary)
            raise live.LiveE2EContractError("simulated_upload_response_loss")

        def bulk_delete(self, workspace_slug: str, file_ids) -> None:
            super().bulk_delete(workspace_slug, file_ids)
            raise live.LiveE2EContractError("simulated_delete_response_loss")

    try:
        live.run_live_e2e(
            source=source,
            canaries=canaries,
            workspace_a="workspace-a",
            workspace_b="workspace-b",
            actor_api=ResponseLostAfterCommit(state, principal="actor"),
            workspace_a_observer_api=_FakeLiveApi(state, principal="observer-a"),
            workspace_b_observer_api=_FakeLiveApi(state, principal="observer-b"),
            inspector=_FakeProjectionInspector(state),
            timeout_seconds=10,
            poll_interval_seconds=0.01,
        )
    except live.LiveE2EContractError as error:
        assert error.code == "simulated_upload_response_loss"
    else:
        raise AssertionError("lost upload response was accepted")
    assert state.files
    assert state.deleted is True


def test_workspace_move_commit_then_client_failure_recovers_from_current_manager(
    tmp_path: Path,
) -> None:
    live = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    (source / "private.txt").write_text(
        "private evidence remains searchable after extraction",
        encoding="utf-8",
    )
    canaries = live.select_live_canaries(
        source,
        max_canaries=1,
        max_total_bytes=1024,
        workers=1,
        run_nonce=b"transition-loss-test-nonce",
    )
    state = _FakeLiveState()

    class MoveResponseLostAfterCommit(_FakeLiveApi):
        def transition(self, *args, **kwargs):
            response = super().transition(*args, **kwargs)
            if kwargs.get("target_workspace_id") == "id-workspace-b":
                raise live.LiveE2EContractError("simulated_move_response_loss")
            return response

    try:
        live.run_live_e2e(
            source=source,
            canaries=canaries,
            workspace_a="workspace-a",
            workspace_b="workspace-b",
            actor_api=MoveResponseLostAfterCommit(state, principal="actor"),
            workspace_a_observer_api=_FakeLiveApi(state, principal="observer-a"),
            workspace_b_observer_api=_FakeLiveApi(state, principal="observer-b"),
            inspector=_FakeProjectionInspector(state),
            timeout_seconds=10,
            poll_interval_seconds=0.01,
        )
    except live.LiveE2EContractError as error:
        assert error.code == "simulated_move_response_loss"
    else:
        raise AssertionError("lost transition response was accepted")
    assert state.workspace == "workspace-b"
    assert state.deleted is True
