"""Prepare and cut over Files partitioned retrieval generations safely."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
import sys


_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from open_work_hub_api.core.db import get_session_factory  # noqa: E402
from open_work_hub_api.core.settings import get_settings, is_production_environment  # noqa: E402
from open_work_hub_api.domains.files.extraction_bootstrap import (  # noqa: E402
    OcrOnlyFileExtractionRuntime,
    bootstrap_file_extraction_artifacts,
)
from open_work_hub_api.domains.files.rag_sync import (  # noqa: E402
    adopt_legacy_file_retrieval_heads,
)
from open_work_hub_api.domains.rag.provider_factory import RagProviderFactory  # noqa: E402
from open_work_hub_api.domains.retrieval.evaluation import (  # noqa: E402
    RetrievalQualityGateArtifact,
)
from open_work_hub_api.domains.retrieval.files_generation_backends import (  # noqa: E402
    FilesPhysicalGenerationBackends,
)
from open_work_hub_api.domains.retrieval.files_generation_materializer import (  # noqa: E402
    FilesCachedProjectionMaterializer,
)
from open_work_hub_api.domains.retrieval.files_generation_runner import (  # noqa: E402
    FilesGenerationBaselineMode,
    FilesGenerationError,
    FilesGenerationRunner,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    generation_key = str(getattr(args, "generation", "") or "").strip().lower()
    dry_run = bool(getattr(args, "dry_run", False))
    if args.command == "reconcile-source":
        production_confirmation = (
            str(getattr(args, "confirm_production_adoption", "") or "").strip().lower()
        )
        expected_confirmation = "adopt-legacy-files"
    elif args.command == "bootstrap-extraction":
        production_confirmation = (
            str(getattr(args, "confirm_production_extraction", "") or "").strip().lower()
        )
        expected_confirmation = "bootstrap-files-extraction"
    elif args.command == "attest-active":
        production_confirmation = (
            str(getattr(args, "confirm_production_attestation", "") or "").strip().lower()
        )
        expected_confirmation = "attest-active-files-quality"
    else:
        production_confirmation = (
            str(getattr(args, "confirm_production_generation", "") or "").strip().lower()
        )
        expected_confirmation = generation_key
    if (
        args.command != "verify-active"
        and is_production_environment(settings.environment)
        and not dry_run
        and production_confirmation != expected_confirmation
    ):
        print("status=failed reason=production_confirmation_required", file=sys.stderr)
        return 1
    empty_bootstrap_confirmation = (
        str(getattr(args, "confirm_empty_production_bootstrap", "") or "").strip().lower()
    )
    if (
        args.command == "validate"
        and is_production_environment(settings.environment)
        and not dry_run
        and empty_bootstrap_confirmation
        and empty_bootstrap_confirmation != "bootstrap-empty-files-retrieval"
    ):
        print(
            "status=failed reason=empty_production_bootstrap_confirmation_required",
            file=sys.stderr,
        )
        return 1

    if args.command == "reconcile-source":
        return _reconcile_source(args=args, settings=settings)
    if args.command == "bootstrap-extraction":
        return _bootstrap_extraction(args=args, settings=settings)

    backends = None
    try:
        backends = FilesPhysicalGenerationBackends(settings)
        runner = FilesGenerationRunner(
            session_factory=get_session_factory(),
            settings=settings,
            backends=backends,
            materializer=FilesCachedProjectionMaterializer(
                session_factory=get_session_factory(),
                settings=settings,
            ),
        )
        if args.command == "prepare":
            result = runner.prepare(
                generation_key=generation_key,
                baseline_mode=FilesGenerationBaselineMode(args.baseline_mode),
                dry_run=dry_run,
            )
            print(result.status_line())
            return 0
        if args.command == "validate":
            artifact, corpus_bytes = _quality_inputs(
                quality_report=args.quality_report,
                quality_corpus=args.quality_corpus,
            )
            result = runner.validate(
                generation_key=generation_key,
                writes_quiesced=bool(args.confirm_writes_quiesced),
                reconciliation_watermark=args.reconciliation_watermark,
                quality_artifact=artifact,
                quality_corpus_bytes=corpus_bytes,
                allow_empty_non_production=bool(args.allow_empty_non_production),
                allow_empty_production_bootstrap=(
                    empty_bootstrap_confirmation == "bootstrap-empty-files-retrieval"
                ),
                dry_run=dry_run,
            )
            print(result.status_line())
            return 0
        if args.command == "attest-active":
            artifact, corpus_bytes = _quality_inputs(
                quality_report=args.quality_report,
                quality_corpus=args.quality_corpus,
            )
            result = runner.attest_active(
                generation_key=generation_key,
                writes_quiesced=bool(args.confirm_writes_quiesced),
                quality_artifact=artifact,
                quality_corpus_bytes=corpus_bytes,
                scope_coverage=args.scope_coverage,
                dry_run=dry_run,
            )
            print(result.status_line())
            return 0
        if args.command in {"materialize", "replay"}:
            operation = runner.materialize if args.command == "materialize" else runner.replay
            result = operation(
                generation_key=generation_key,
                after_event_sequence=args.after_event_sequence,
                through_event_sequence=args.through_event_sequence,
                limit=args.limit,
                writes_quiesced=bool(args.confirm_writes_quiesced),
                workers_stopped=bool(args.confirm_workers_stopped),
                dry_run=dry_run,
            )
            print(result.status_line())
            return 0
        if args.command == "cutover":
            corpus_bytes = _quality_corpus_input(args.quality_corpus)
            result = runner.cutover(
                generation_key=generation_key,
                writes_quiesced=bool(args.confirm_writes_quiesced),
                rollback_window=timedelta(hours=args.rollback_window_hours),
                quality_corpus_bytes=corpus_bytes,
                dry_run=dry_run,
            )
            print(result.status_line())
            return 0
        if args.command == "verify-active":
            print(runner.verify_active().status_line())
            return 0
        raise FilesGenerationError("unsupported_command")
    except FilesGenerationError as error:
        print(f"status=failed reason={error.code}", file=sys.stderr)
        return 1
    except Exception:
        print("status=failed reason=files_generation_operation_failed", file=sys.stderr)
        return 1
    finally:
        if backends is not None:
            backends.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage an isolated Files OpenSearch v3/Qdrant v1 generation pair. "
            "No command stops writers or runs automatically during production deployment."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    prepare = subcommands.add_parser("prepare")
    _generation_arguments(prepare)
    prepare.add_argument(
        "--baseline-mode",
        required=True,
        choices=[mode.value for mode in FilesGenerationBaselineMode],
    )
    prepare.add_argument("--dry-run", action="store_true")

    reconcile_source = subcommands.add_parser("reconcile-source")
    reconcile_source.add_argument("--after-file-id")
    reconcile_source.add_argument("--limit", type=int, default=500)
    reconcile_source.add_argument("--confirm-writes-quiesced", action="store_true")
    reconcile_source.add_argument("--confirm-operator-gate-disabled", action="store_true")
    reconcile_source.add_argument("--confirm-production-adoption")
    reconcile_source.add_argument("--dry-run", action="store_true")

    bootstrap_extraction = subcommands.add_parser("bootstrap-extraction")
    bootstrap_extraction.add_argument("--after-file-id")
    bootstrap_extraction.add_argument("--limit", type=int, default=25)
    bootstrap_extraction.add_argument("--confirm-writes-quiesced", action="store_true")
    bootstrap_extraction.add_argument("--confirm-workers-stopped", action="store_true")
    bootstrap_extraction.add_argument("--confirm-operator-gate-disabled", action="store_true")
    bootstrap_extraction.add_argument("--confirm-production-extraction")
    bootstrap_extraction.add_argument("--dry-run", action="store_true")

    for command in ("materialize", "replay"):
        materialize = subcommands.add_parser(command)
        _generation_arguments(materialize)
        materialize.add_argument("--after-event-sequence", type=int, required=True)
        materialize.add_argument("--through-event-sequence", type=int, required=True)
        materialize.add_argument("--limit", type=int, default=100)
        materialize.add_argument("--confirm-writes-quiesced", action="store_true")
        materialize.add_argument("--confirm-workers-stopped", action="store_true")
        materialize.add_argument("--dry-run", action="store_true")

    validate = subcommands.add_parser("validate")
    _generation_arguments(validate)
    validate.add_argument("--confirm-writes-quiesced", action="store_true")
    validate.add_argument("--reconciliation-watermark", type=int)
    validate.add_argument("--quality-report")
    validate.add_argument("--quality-corpus")
    validate.add_argument("--allow-empty-non-production", action="store_true")
    validate.add_argument(
        "--confirm-empty-production-bootstrap",
        help=(
            "Allows an initial empty production pair only when set exactly to "
            "'bootstrap-empty-files-retrieval'."
        ),
    )
    validate.add_argument("--dry-run", action="store_true")

    attest = subcommands.add_parser("attest-active")
    _generation_arguments(attest, production_confirmation=False)
    attest.add_argument("--confirm-writes-quiesced", action="store_true")
    attest.add_argument("--quality-report", required=True)
    attest.add_argument("--quality-corpus", required=True)
    attest.add_argument(
        "--scope-coverage",
        action="append",
        required=True,
        choices=("company", "personal"),
        help="Repeat for every access scope represented by the judged corpus.",
    )
    attest.add_argument(
        "--confirm-production-attestation",
        help=("Required in production and must equal 'attest-active-files-quality'."),
    )
    attest.add_argument("--dry-run", action="store_true")

    cutover = subcommands.add_parser("cutover")
    _generation_arguments(cutover)
    cutover.add_argument("--confirm-writes-quiesced", action="store_true")
    cutover.add_argument("--rollback-window-hours", type=int, default=168)
    cutover.add_argument(
        "--quality-corpus",
        help="The same judged corpus used for validation; required for a non-empty pair.",
    )
    cutover.add_argument("--dry-run", action="store_true")

    subcommands.add_parser("verify-active")
    return parser


def _generation_arguments(
    parser: argparse.ArgumentParser,
    *,
    production_confirmation: bool = True,
) -> None:
    parser.add_argument("--generation", required=True)
    if production_confirmation:
        parser.add_argument(
            "--confirm-production-generation",
            help=(
                "Required for a mutating production command and must exactly match --generation."
            ),
        )


def _quality_inputs(
    *,
    quality_report: str | None,
    quality_corpus: str | None,
) -> tuple[RetrievalQualityGateArtifact | None, bytes | None]:
    if quality_report is None and quality_corpus is None:
        return None, None
    if quality_report is None or quality_corpus is None:
        raise FilesGenerationError("quality_evidence_incomplete")
    try:
        artifact = RetrievalQualityGateArtifact.model_validate_json(
            Path(quality_report).read_bytes()
        )
        corpus_bytes = Path(quality_corpus).read_bytes()
    except (OSError, ValueError) as error:
        raise FilesGenerationError("quality_evidence_invalid") from error
    return artifact, corpus_bytes


def _quality_corpus_input(quality_corpus: str | None) -> bytes | None:
    if quality_corpus is None:
        return None
    try:
        return Path(quality_corpus).read_bytes()
    except OSError as error:
        raise FilesGenerationError("quality_evidence_invalid") from error


def _reconcile_source(*, args: argparse.Namespace, settings) -> int:
    if not args.confirm_writes_quiesced:
        print(
            "status=failed reason=source_reconciliation_requires_quiesced_writers", file=sys.stderr
        )
        return 1
    if not args.confirm_operator_gate_disabled or settings.files_retrieval_enabled:
        print("status=failed reason=source_reconciliation_requires_disabled_gate", file=sys.stderr)
        return 1
    if args.limit < 1 or args.limit > 1_000:
        print("status=failed reason=source_reconciliation_limit_invalid", file=sys.stderr)
        return 1
    if args.dry_run:
        print("status=ok state=source-reconciliation-planned dry_run=1")
        return 0
    try:
        with get_session_factory().begin() as db:
            batch = adopt_legacy_file_retrieval_heads(
                db,
                after_file_id=args.after_file_id,
                limit=args.limit,
            )
    except Exception:
        print("status=failed reason=source_reconciliation_failed", file=sys.stderr)
        return 1
    next_file_id = batch.next_file_id or "none"
    print(
        "status=ok state=source-reconciled dry_run=0"
        f" scanned_files={batch.scanned_files} recorded_events={batch.recorded_events}"
        f" complete={int(batch.complete)} event_watermark={batch.event_watermark}"
        f" next_file_id={next_file_id}"
    )
    return 0


def _bootstrap_extraction(*, args: argparse.Namespace, settings) -> int:
    if not args.confirm_writes_quiesced:
        print("status=failed reason=extraction_requires_quiesced_writers", file=sys.stderr)
        return 1
    if not args.confirm_workers_stopped:
        print("status=failed reason=extraction_requires_stopped_workers", file=sys.stderr)
        return 1
    if not args.confirm_operator_gate_disabled or settings.files_retrieval_enabled:
        print("status=failed reason=extraction_requires_disabled_gate", file=sys.stderr)
        return 1
    if args.limit < 1 or args.limit > 1_000:
        print("status=failed reason=extraction_limit_invalid", file=sys.stderr)
        return 1
    if args.dry_run:
        print("status=ok state=extraction-planned dry_run=1")
        return 0

    runtime = None
    try:
        runtime = OcrOnlyFileExtractionRuntime(RagProviderFactory(settings).build_ocr())
        with get_session_factory().begin() as db:
            batch = bootstrap_file_extraction_artifacts(
                db,
                after_file_id=args.after_file_id,
                limit=args.limit,
                extraction_runtime=runtime,
            )
    except Exception:
        print("status=failed reason=files_extraction_bootstrap_failed", file=sys.stderr)
        return 1
    finally:
        if runtime is not None:
            runtime.close()

    next_file_id = batch.next_file_id or "none"
    batch_details = (
        f" scanned_files={batch.scanned_files} ready_files={batch.ready_files}"
        f" unsupported_files={batch.unsupported_files} failed_files={batch.failed_files}"
        f" recorded_events={batch.recorded_events} complete={int(batch.complete)}"
        f" next_file_id={next_file_id}"
    )
    if batch.failed_files:
        print(
            f"status=failed reason=extraction_batch_incomplete{batch_details}",
            file=sys.stderr,
        )
        return 1
    print(f"status=ok state=extraction-bootstrapped dry_run=0{batch_details}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
