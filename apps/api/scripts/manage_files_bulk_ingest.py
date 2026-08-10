"""Inventory, ingest, pause, purge, and verify operator-managed Files runs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import stat
import sys
from typing import Any


_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ai_do_api.core.db import get_session_factory  # noqa: E402
from ai_do_api.core.settings import get_settings, is_production_environment  # noqa: E402
from ai_do_api.core.storage import get_minio_client  # noqa: E402
from ai_do_api.domains.auth.models import User, Workspace  # noqa: E402
from ai_do_api.domains.files import bulk_ingest  # noqa: E402
from ai_do_api.domains.files.models import (  # noqa: E402
    FileManagerBulkIngestEntry,
    FileManagerFile,
)
from ai_do_api.domains.retrieval.files_generation_backends import (  # noqa: E402
    FilesPhysicalGenerationBackends,
)
from ai_do_api.domains.retrieval.files_generation_runner import (  # noqa: E402
    FilesGenerationPairSpec,
)
from ai_do_api.domains.retrieval.models import (  # noqa: E402
    RetrievalProjectionBackend,
    RetrievalProjectionGeneration,
)
from files_rag_readonly_harness import (  # noqa: E402
    HarnessContractError,
    MAX_SOURCE_BYTES,
    inspect_source_tree,
)


MANIFEST_VERSION = 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            return _inventory(args)
        settings = get_settings()
        if _is_mutating(args.command) and not args.dry_run:
            _require_production_confirmation(args=args, settings=settings)
        if args.command == "create-run":
            return _create_run(args)
        if args.command == "ingest":
            return _ingest(args)
        if args.command == "status":
            return _status(args)
        if args.command == "pause":
            return _pause(args)
        if args.command == "purge":
            return _purge(args)
        if args.command == "verify-clean":
            return _verify_clean(args, settings=settings)
        raise bulk_ingest.FilesBulkIngestError("unsupported_command")
    except bulk_ingest.FilesBulkIngestError as error:
        print(f"status=failed reason={error.code}", file=sys.stderr)
        return 1
    except Exception:
        print("status=failed reason=files_bulk_ingest_operation_failed", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage resumable operator-owned Files ingestion. Manifest files contain "
            "source paths and therefore must be regular mode-0600 files."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    inventory = subcommands.add_parser("inventory")
    inventory.add_argument("--source-root", required=True)
    inventory.add_argument("--manifest", required=True)
    inventory.add_argument(
        "--include-extension",
        action="append",
        default=[],
        help="Case-insensitive extension including or excluding the leading dot; repeatable.",
    )
    inventory.add_argument(
        "--max-file-bytes",
        type=int,
        default=MAX_SOURCE_BYTES,
    )
    inventory.add_argument("--workers", type=int, default=4)

    create_run = subcommands.add_parser("create-run")
    _manifest_argument(create_run)
    create_run.add_argument("--workspace-key", required=True)
    create_run.add_argument("--actor-login-id", required=True)
    create_run.add_argument(
        "--owner-login-id",
        help=(
            "Optional workspace member who owns the root folder. Use the same login "
            "as ingest --actor-login-id when uploaded files must share that owner; "
            "the create-run actor remains the workspace-admin control-plane creator."
        ),
    )
    create_run.add_argument(
        "--run-key",
        required=True,
        help="Operator-chosen idempotency key; reuse to resume creation, change after purge.",
    )
    create_run.add_argument("--corpus-name", required=True)
    create_run.add_argument("--root-folder-name", required=True)
    _mutation_arguments(create_run)

    ingest = subcommands.add_parser("ingest")
    _manifest_argument(ingest)
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--actor-login-id", required=True)
    ingest.add_argument("--limit", type=int, default=bulk_ingest.INGEST_BATCH_LIMIT)
    _mutation_arguments(ingest)

    status_parser = subcommands.add_parser("status")
    status_parser.add_argument("--run-id", required=True)

    pause = subcommands.add_parser("pause")
    pause.add_argument("--run-id", required=True)
    _mutation_arguments(pause)

    purge = subcommands.add_parser("purge")
    purge.add_argument("--run-id", required=True)
    purge.add_argument("--actor-login-id", required=True)
    purge.add_argument("--limit", type=int, default=bulk_ingest.PURGE_BATCH_LIMIT)
    _mutation_arguments(purge)

    verify = subcommands.add_parser("verify-clean")
    verify.add_argument("--run-id", required=True)
    return parser


def _manifest_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True)


def _mutation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--confirm-production",
        help=(
            "On production, create-run requires 'workspace:<workspace-key>'; "
            "other commands require 'run:<run-id>'."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")


def _inventory(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root).resolve(strict=True)
    if not source_root.is_dir():
        raise bulk_ingest.FilesBulkIngestError("source_root_not_directory")
    max_file_bytes = int(args.max_file_bytes)
    if max_file_bytes < 0 or max_file_bytes > MAX_SOURCE_BYTES:
        raise bulk_ingest.FilesBulkIngestError("inventory_max_file_bytes_invalid")
    extensions = {
        f".{str(value).strip().lower().lstrip('.')}"
        for value in args.include_extension
        if str(value).strip()
    }
    try:
        inspection = inspect_source_tree(source_root, workers=int(args.workers))
    except HarnessContractError as error:
        raise bulk_ingest.FilesBulkIngestError("source_inventory_failed") from error
    entries: list[dict[str, Any]] = []
    filtered_eligible = 0
    normalized_extensions = {value.removeprefix(".") for value in extensions}
    for eligible in inspection.eligible:
        candidate = eligible.candidate
        if candidate.size_bytes > max_file_bytes or (
            normalized_extensions and candidate.extension not in normalized_extensions
        ):
            filtered_eligible += 1
            continue
        relative_path = candidate.path.relative_to(inspection.source_root).as_posix()
        if eligible.content_sha256 is None:
            raise bulk_ingest.FilesBulkIngestError("source_inventory_failed")
        entries.append(
            {
                "source_path": bulk_ingest.normalize_source_path(relative_path),
                "size_bytes": candidate.size_bytes,
                "content_sha256": eligible.content_sha256,
                "content_type": (
                    mimetypes.guess_type(candidate.path.name, strict=False)[0]
                    or "application/octet-stream"
                ),
            }
        )
    skipped = inspection.excluded_entry_count + filtered_eligible
    payload = {
        "version": MANIFEST_VERSION,
        "source_root": str(source_root),
        "source_root_sha256": bulk_ingest.source_root_identity(source_root),
        "entries": entries,
    }
    manifest_bytes = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
    _write_private_manifest(Path(args.manifest), manifest_bytes)
    print(
        f"status=ok entries={len(entries)} skipped={skipped} "
        f"total_bytes={sum(int(entry['size_bytes']) for entry in entries)} "
        f"manifest_sha256={hashlib.sha256(manifest_bytes).hexdigest()}"
    )
    return 0


def _create_run(args: argparse.Namespace) -> int:
    manifest, manifest_sha256 = _load_manifest(Path(args.manifest))
    if args.dry_run:
        print(
            f"status=ok state=planned dry_run=1 entries={len(manifest['entries'])} "
            f"total_bytes={sum(int(entry['size_bytes']) for entry in manifest['entries'])} "
            f"manifest_sha256={manifest_sha256}"
        )
        return 0
    with get_session_factory().begin() as db:
        workspace = _require_workspace(db, args.workspace_key)
        actor = _require_actor(db, args.actor_login_id)
        owner = _require_actor(db, args.owner_login_id or args.actor_login_id)
        run = bulk_ingest.create_run(
            db,
            workspace=workspace,
            actor=actor,
            owner=owner,
            corpus_name=args.corpus_name,
            root_folder_name=args.root_folder_name,
            idempotency_key=args.run_key,
            manifest_sha256=manifest_sha256,
            source_root_sha256=str(manifest["source_root_sha256"]),
            entries=_manifest_entries(manifest),
        )
        run_id = run.id
    print(
        f"status=ok run_id={run_id} state=planned entries={len(manifest['entries'])} "
        f"manifest_sha256={manifest_sha256}"
    )
    return 0


def _ingest(args: argparse.Namespace) -> int:
    manifest, manifest_sha256 = _load_manifest(Path(args.manifest))
    source_root = Path(str(manifest["source_root"]))
    if bulk_ingest.source_root_identity(source_root) != manifest["source_root_sha256"]:
        raise bulk_ingest.FilesBulkIngestError("source_root_identity_mismatch")
    if args.dry_run:
        with get_session_factory()() as db:
            status = bulk_ingest.load_status(db, run_id=args.run_id)
        print(
            f"status=ok run_id={status.run_id} state={status.state} dry_run=1 "
            f"candidate_limit={args.limit}"
        )
        return 0

    factory = get_session_factory()
    with factory.begin() as db:
        bulk_ingest.start_or_resume_run(
            db,
            run_id=args.run_id,
            manifest_sha256=manifest_sha256,
            source_root_sha256=str(manifest["source_root_sha256"]),
        )
        candidate_ids = [
            entry.id
            for entry in bulk_ingest.list_ingest_candidates(
                db,
                run_id=args.run_id,
                limit=args.limit,
            )
        ]
    uploaded = 0
    for entry_id in candidate_ids:
        try:
            with factory.begin() as db:
                actor = _require_actor(db, args.actor_login_id)
                if bulk_ingest.ingest_entry(
                    db,
                    run_id=args.run_id,
                    entry_id=entry_id,
                    source_root=source_root,
                    actor=actor,
                ):
                    uploaded += 1
        except Exception as error:
            error_code = (
                error.code
                if isinstance(error, bulk_ingest.FilesBulkIngestError)
                else "entry_upload_failed"
            )
            with factory.begin() as db:
                bulk_ingest.mark_ingest_failure(
                    db,
                    run_id=args.run_id,
                    entry_id=entry_id,
                    error_code=error_code,
                )
            raise bulk_ingest.FilesBulkIngestError(error_code) from error
    with factory.begin() as db:
        bulk_ingest.finish_ingest_batch(db, run_id=args.run_id)
        status = bulk_ingest.load_status(db, run_id=args.run_id)
    print(f"{status.status_line()} batch_uploaded={uploaded}")
    return 0


def _status(args: argparse.Namespace) -> int:
    with get_session_factory()() as db:
        status = bulk_ingest.load_status(db, run_id=args.run_id)
    print(status.status_line())
    return 0


def _pause(args: argparse.Namespace) -> int:
    if args.dry_run:
        print(f"status=ok run_id={args.run_id} state=pause-planned dry_run=1")
        return 0
    with get_session_factory().begin() as db:
        run = bulk_ingest.pause_run(db, run_id=args.run_id)
        state = run.status
    print(f"status=ok run_id={args.run_id} state={state}")
    return 0


def _purge(args: argparse.Namespace) -> int:
    if args.dry_run:
        print(
            f"status=ok run_id={args.run_id} state=purge-planned dry_run=1 batch_limit={args.limit}"
        )
        return 0
    factory = get_session_factory()
    with factory.begin() as db:
        bulk_ingest.begin_purge(db, run_id=args.run_id)
    with factory.begin() as db:
        actor = _require_actor(db, args.actor_login_id)
        result = bulk_ingest.purge_batch(
            db,
            run_id=args.run_id,
            actor=actor,
            limit=args.limit,
        )
    print(f"status=ok run_id={result.run_id} state={result.state} batch_purged={result.processed}")
    return 0


def _verify_clean(args: argparse.Namespace, *, settings) -> int:
    factory = get_session_factory()
    backends = None
    try:
        with factory() as db:
            resource_ids = tuple(
                db.scalars(
                    select(FileManagerBulkIngestEntry.target_file_id).where(
                        FileManagerBulkIngestEntry.run_id == args.run_id
                    )
                )
            )
            storage_objects = _count_storage_objects(
                db,
                run_id=args.run_id,
                bucket=settings.minio_bucket,
            )
            spec = _active_files_generation_spec(db)
        backends = FilesPhysicalGenerationBackends(settings)
        presence = backends.count_resource_presence(
            spec,
            resource_ids=resource_ids,
        )
        with factory() as db:
            result = bulk_ingest.verify_clean(
                db,
                run_id=args.run_id,
                storage_objects=storage_objects,
                opensearch_documents=presence.opensearch_documents,
                qdrant_points=presence.qdrant_points,
            )
    finally:
        if backends is not None:
            backends.close()
    print(result.status_line(), file=sys.stdout if result.clean else sys.stderr)
    return 0 if result.clean else 1


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    _require_private_regular_file(path)
    try:
        manifest_bytes = path.read_bytes()
        payload = json.loads(manifest_bytes)
    except (OSError, ValueError, TypeError) as error:
        raise bulk_ingest.FilesBulkIngestError("manifest_invalid") from error
    if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
        raise bulk_ingest.FilesBulkIngestError("manifest_version_invalid")
    source_root = payload.get("source_root")
    source_root_sha256 = payload.get("source_root_sha256")
    entries = payload.get("entries")
    if (
        not isinstance(source_root, str)
        or not isinstance(source_root_sha256, str)
        or not isinstance(entries, list)
    ):
        raise bulk_ingest.FilesBulkIngestError("manifest_invalid")
    normalized_entries = _manifest_entries(payload)
    if len(normalized_entries) != len(entries):
        raise bulk_ingest.FilesBulkIngestError("manifest_invalid")
    return payload, hashlib.sha256(manifest_bytes).hexdigest()


def _manifest_entries(manifest: dict[str, Any]) -> list[bulk_ingest.ManifestEntry]:
    entries: list[bulk_ingest.ManifestEntry] = []
    try:
        for row in manifest["entries"]:
            if not isinstance(row, dict):
                raise TypeError
            entries.append(
                bulk_ingest.ManifestEntry(
                    source_path=str(row["source_path"]),
                    size_bytes=int(row["size_bytes"]),
                    content_sha256=str(row["content_sha256"]),
                    content_type=str(row["content_type"]),
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        raise bulk_ingest.FilesBulkIngestError("manifest_invalid") from error
    return entries


def _write_private_manifest(path: Path, content: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise bulk_ingest.FilesBulkIngestError("manifest_target_invalid")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as target:
                target.write(content)
                target.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise bulk_ingest.FilesBulkIngestError("manifest_write_failed") from error


def _require_private_regular_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise bulk_ingest.FilesBulkIngestError("manifest_unavailable") from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise bulk_ingest.FilesBulkIngestError("manifest_permissions_invalid")


def _require_workspace(db: Session, workspace_key: str) -> Workspace:
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.key == str(workspace_key or "").strip(),
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise bulk_ingest.FilesBulkIngestError("workspace_not_found")
    return workspace


def _require_actor(db: Session, login_id: str) -> User:
    actor = db.scalar(
        select(User).where(
            User.login_id == str(login_id or "").strip(),
            User.status == "active",
            User.login_blocked.is_(False),
        )
    )
    if actor is None:
        raise bulk_ingest.FilesBulkIngestError("actor_not_found")
    return actor


def _count_storage_objects(db: Session, *, run_id: str, bucket: str) -> int:
    keys = list(
        db.scalars(
            select(FileManagerFile.storage_key)
            .join(
                FileManagerBulkIngestEntry,
                FileManagerBulkIngestEntry.target_file_id == FileManagerFile.id,
            )
            .where(FileManagerBulkIngestEntry.run_id == run_id)
        )
    )
    client = get_minio_client()
    count = 0
    for storage_key in keys:
        try:
            client.stat_object(bucket, storage_key)
            count += 1
        except Exception as error:
            if str(getattr(error, "code", "")) not in {
                "NoSuchKey",
                "NoSuchObject",
            }:
                raise bulk_ingest.FilesBulkIngestError("storage_verification_failed") from error
    return count


def _active_files_generation_spec(db: Session) -> FilesGenerationPairSpec:
    rows = tuple(
        db.scalars(
            select(RetrievalProjectionGeneration)
            .where(RetrievalProjectionGeneration.state == "active")
            .order_by(RetrievalProjectionGeneration.backend.asc())
        )
    )
    if len(rows) != 2 or len({row.generation_key for row in rows}) != 1:
        raise bulk_ingest.FilesBulkIngestError("active_generation_pair_invalid")
    by_backend = {row.backend: row for row in rows}
    opensearch = by_backend.get(RetrievalProjectionBackend.OPENSEARCH.value)
    qdrant = by_backend.get(RetrievalProjectionBackend.QDRANT.value)
    if opensearch is None or qdrant is None:
        raise bulk_ingest.FilesBulkIngestError("active_generation_pair_invalid")
    return FilesGenerationPairSpec(
        generation_key=opensearch.generation_key,
        opensearch_physical_name=opensearch.physical_name,
        opensearch_alias_name=opensearch.alias_name,
        qdrant_physical_name=qdrant.physical_name,
        qdrant_alias_name=qdrant.alias_name,
    )


def _require_production_confirmation(*, args: argparse.Namespace, settings) -> None:
    if not is_production_environment(settings.environment):
        return
    if args.command == "create-run":
        expected = f"workspace:{args.workspace_key}"
    else:
        expected = f"run:{args.run_id}"
    if str(args.confirm_production or "").strip() != expected:
        raise bulk_ingest.FilesBulkIngestError("production_confirmation_required")


def _is_mutating(command: str) -> bool:
    return command in {"create-run", "ingest", "pause", "purge"}


if __name__ == "__main__":
    raise SystemExit(main())
