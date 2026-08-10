"""Read-only quality evaluation for an existing Files v3/v1 physical pair."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import logging
import os
from pathlib import Path
import stat
import sys
import tempfile

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.retrieval.evaluation import evaluate_hybrid_quality_gate
from ai_do_api.domains.retrieval.files_generation_backends import (
    FilesPhysicalGenerationBackends,
)
from ai_do_api.domains.retrieval.files_quality_evaluator import (
    FilesQualityEvaluationError,
    evaluate_files_partitioned_quality,
)


_MAX_QUALITY_CORPUS_BYTES = 16 * 1024 * 1024


class _ArtifactOutputExists(RuntimeError):
    pass


class _ArtifactWriteFailed(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_path = Path(args.output)
    if output_path.exists() or output_path.is_symlink():
        print("status=failed reason=artifact_output_exists", file=sys.stderr)
        return 1
    try:
        corpus_bytes = _read_bounded_regular_file(Path(args.corpus))
    except Exception:
        print("status=failed reason=quality_corpus_read_failed", file=sys.stderr)
        return 1

    backends = None
    result = 1
    reason = "evaluation_failed"
    artifact_sha256: str | None = None
    generation = str(args.generation)
    previous_logging_threshold = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        settings = get_settings()
        backends = FilesPhysicalGenerationBackends(settings)
        artifact = evaluate_files_partitioned_quality(
            corpus_bytes=corpus_bytes,
            generation_key=generation,
            settings=settings,
            session_factory=get_session_factory(),
            backends=backends,
        )
        artifact_bytes = (artifact.model_dump_json(indent=2) + "\n").encode("utf-8")
        _write_exclusive_atomic(output_path, artifact_bytes)
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        gate = evaluate_hybrid_quality_gate(
            hybrid=artifact.hybrid,
            bm25=artifact.bm25,
            dense=artifact.dense,
        )
        if gate.passed:
            result = 0
            reason = ""
        else:
            reason = "quality_gate_failed"
    except FilesQualityEvaluationError as error:
        reason = error.code
    except _ArtifactOutputExists:
        reason = "artifact_output_exists"
    except _ArtifactWriteFailed:
        reason = "artifact_write_failed"
    except Exception:
        reason = "evaluation_failed"
    finally:
        if backends is not None:
            try:
                backends.close()
            except Exception:
                result = 1
                reason = "backend_close_failed"
        logging.disable(previous_logging_threshold)

    if result == 0:
        print(
            f"status=ok generation={generation} artifact_sha256={artifact_sha256}",
        )
        return 0
    print(f"status=failed reason={reason}", file=sys.stderr)
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate an already-materialized Files OpenSearch v3/Qdrant v1 physical "
            "generation without changing aliases, source rows, or backend content."
        )
    )
    parser.add_argument("--corpus", required=True, help="Versioned judged corpus JSON path.")
    parser.add_argument(
        "--generation",
        required=True,
        help="Exact lowercase Files generation key to evaluate.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="New artifact path. Existing files are never overwritten.",
    )
    return parser


def _read_bounded_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("quality corpus is not a regular file")
        if metadata.st_size > _MAX_QUALITY_CORPUS_BYTES:
            raise OSError("quality corpus exceeds the read limit")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(_MAX_QUALITY_CORPUS_BYTES + 1)
        if len(content) > _MAX_QUALITY_CORPUS_BYTES:
            raise OSError("quality corpus exceeds the read limit")
        return content
    finally:
        os.close(descriptor)


def _write_exclusive_atomic(path: Path, content: bytes) -> None:
    parent = path.parent
    temporary_path: Path | None = None
    linked = False
    try:
        descriptor, raw_temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary_path = Path(raw_temporary_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
            linked = True
        except FileExistsError as error:
            raise _ArtifactOutputExists from error
    except _ArtifactOutputExists:
        raise
    except Exception as error:
        raise _ArtifactWriteFailed from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        if linked:
            try:
                _fsync_directory(parent)
            except OSError as error:
                raise _ArtifactWriteFailed from error


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
