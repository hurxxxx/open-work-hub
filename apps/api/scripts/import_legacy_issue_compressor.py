"""Load the curated compressor legacy-issue records into one workspace.

The input directory must contain the three normalized CSV files prepared from
the approved source workbooks.  In particular, this loader never opens or
groups rows from the electric-compressor workbook; its 36 check plans are
already human-reviewed, single-cell values in ``electric_listed_rev36.csv``.

The import is intentionally all-or-nothing.  A clean target receives a
published mechanical Rev.1 and electric Rev.36 in one transaction.  Re-running
against the exact completed state is a no-op; any partial or conflicting state
is rejected for manual review.

Usage::

    apps/api/.venv/bin/python apps/api/scripts/import_legacy_issue_compressor.py \
        --workspace 기술연구소 \
        --input-dir samples/legacy_issue/compressor \
        --dry-run
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path

from sqlalchemy import func, or_, select

# Allow running as a plain script: add apps/api/src to the path.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from open_alm_api.core.db import get_session_factory  # noqa: E402
from open_alm_api.domains.auth.access import is_platform_admin_user  # noqa: E402
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive  # noqa: E402
from open_alm_api.domains.auth.security import new_id  # noqa: E402
from open_alm_api.domains.legacy_issues.ai_search import (  # noqa: E402
    reindex_legacy_issue_revision_ai_chunks,
)
from open_alm_api.domains.legacy_issues.dataset_records import (  # noqa: E402
    COMMON_MASTER_DATASET_KEY,
    get_dataset_definition_with_all_module_fields,
    import_dataset_records,
)
from open_alm_api.domains.legacy_issues.models import (  # noqa: E402
    LegacyIssueAttachment,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from open_alm_api.domains.legacy_issues.partitioning import (  # noqa: E402
    ensure_revision_partition,
)
from open_alm_api.domains.legacy_issues.revisioning import (  # noqa: E402
    REVISION_STATUS_PUBLISHED,
    add_revision_event,
    legacy_issue_dataset_revision_key,
)


MECHANICAL_MODULE_KEY = "compressor-mechanical"
ELECTRIC_MODULE_KEY = "compressor-electric"
MECHANICAL_REVISION_NO = 1
ELECTRIC_REVISION_NO = 36

XLSX_SOURCE_SHA256 = "394a1417e907273c143aa1897192c1477e9c892988282aeb3d7897ff8a2860c8"
XLS_SOURCE_SHA256 = "6955b423372f1bac337f507d71efff34d247bfe142a1cf4c906ae8af47e84b89"

MECHANICAL_CSV = "mechanical_unlisted.csv"
ELECTRIC_LISTED_CSV = "electric_listed_rev36.csv"
ELECTRIC_UNLISTED_CSV = "electric_unlisted.csv"

EXPECTED_INPUTS = {
    MECHANICAL_CSV: {
        "rows": 50,
        "source_sha256": XLS_SOURCE_SHA256,
        "master_status": "미등재",
    },
    ELECTRIC_LISTED_CSV: {
        "rows": 36,
        "source_sha256": XLSX_SOURCE_SHA256,
        "master_status": "등재",
    },
    ELECTRIC_UNLISTED_CSV: {
        "rows": 14,
        "source_sha256": XLS_SOURCE_SHA256,
        "master_status": "미등재",
    },
}

PROVENANCE_HEADERS = frozenset(
    {
        "source_file",
        "source_sha256",
        "source_sheet",
        "source_row",
        "source_no",
        "source_past_vehicle_master",
    }
)
IMPORT_FIELD_ALIASES = {
    "evidence_design_guide": "evidence_design_standard_guide",
}


@dataclass(frozen=True)
class CuratedInput:
    filename: str
    path: Path
    content: bytes
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]

    @property
    def mapping(self) -> dict[str, int]:
        return {
            IMPORT_FIELD_ALIASES.get(header, header): index
            for index, header in enumerate(self.headers)
            if header not in PROVENANCE_HEADERS
        }

    @property
    def import_content(self) -> bytes:
        # common-master has a two-row grouped spreadsheet header.  The curated
        # CSV uses one ordinary header, so supply an empty group row in memory
        # for the generic importer without changing the reviewed artifact.
        empty_group_row = "," * (len(self.headers) - 1)
        decoded = self.content.decode("utf-8-sig")
        return f"{empty_group_row}\n{decoded}".encode("utf-8")


def _read_curated_input(input_dir: Path, filename: str) -> CuratedInput:
    path = input_dir / filename
    if not path.is_file():
        raise ValueError(f"required curated input is missing: {path}")
    content = path.read_bytes()
    decoded = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(decoded, newline=""))
    headers = tuple(reader.fieldnames or ())
    rows = tuple(dict(row) for row in reader)
    expected = EXPECTED_INPUTS[filename]
    if len(rows) != expected["rows"]:
        raise ValueError(f"{filename}: expected {expected['rows']} rows, found {len(rows)}")
    required_headers = {
        "source_file",
        "source_sha256",
        "source_sheet",
        "source_row",
        "source_no",
        "evidence_legacy_issue",
    }
    missing_headers = sorted(required_headers.difference(headers))
    if missing_headers:
        raise ValueError(f"{filename}: missing headers: {', '.join(missing_headers)}")
    for index, row in enumerate(rows, start=2):
        if row["source_sha256"] != expected["source_sha256"]:
            raise ValueError(f"{filename}:{index}: unexpected source SHA-256")
        if row["evidence_legacy_issue"] != expected["master_status"]:
            raise ValueError(f"{filename}:{index}: unexpected master status")
    provenance = {(row["source_sheet"], row["source_row"], row["source_no"]) for row in rows}
    if len(provenance) != len(rows):
        raise ValueError(f"{filename}: duplicate source provenance")
    if filename == ELECTRIC_LISTED_CSV:
        for index, row in enumerate(rows, start=2):
            check_plan = row.get("check_plan", "")
            if not (
                check_plan.startswith("점검 항목: ")
                and "\n\n[설계]\n" in check_plan
                and "\n\n[평가]\n" in check_plan
                and "\n\n[제조]\n" in check_plan
            ):
                raise ValueError(f"{filename}:{index}: invalid reviewed check-plan format")
    return CuratedInput(
        filename=filename,
        path=path,
        content=content,
        headers=headers,
        rows=rows,
    )


def load_curated_inputs(input_dir: Path) -> dict[str, CuratedInput]:
    return {filename: _read_curated_input(input_dir, filename) for filename in EXPECTED_INPUTS}


def _resolve_workspace(db, target: str) -> Workspace:
    matches = list(
        db.scalars(
            select(Workspace).where(
                Workspace.active.is_(True),
                or_(Workspace.key == target, Workspace.name == target),
            )
        )
    )
    unique_matches = {workspace.id: workspace for workspace in matches}
    if len(unique_matches) != 1:
        raise ValueError(
            f"workspace target must resolve to exactly one active workspace: {target!r}"
        )
    return next(iter(unique_matches.values()))


def _resolve_actor(db, login_id: str) -> User:
    actor = db.scalar(
        select(User).where(
            User.login_id == login_id,
            User.status == "active",
            User.login_blocked.is_(False),
        )
    )
    if actor is None:
        raise ValueError(f"active actor not found: {login_id!r}")
    if not is_platform_admin_user(actor, db):
        raise ValueError(f"actor must be a platform administrator: {login_id!r}")
    return actor


def _revision_key(module_key: str) -> str:
    return legacy_issue_dataset_revision_key(COMMON_MASTER_DATASET_KEY, module_key)


def _module_revisions(db, *, workspace: Workspace, module_key: str):
    return list(
        db.scalars(
            select(LegacyIssueDataRevision).where(
                LegacyIssueDataRevision.workspace_id == workspace.id,
                LegacyIssueDataRevision.dataset_key == _revision_key(module_key),
            )
        )
    )


def _module_records(db, *, workspace: Workspace, module_key: str):
    return list(
        db.scalars(
            select(LegacyIssueRecord).where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.dataset_key == COMMON_MASTER_DATASET_KEY,
                LegacyIssueRecord.module_key == module_key,
            )
        )
    )


def _completed_state_matches(db, *, workspace: Workspace) -> bool:
    mechanical_revisions = _module_revisions(
        db, workspace=workspace, module_key=MECHANICAL_MODULE_KEY
    )
    electric_revisions = _module_revisions(db, workspace=workspace, module_key=ELECTRIC_MODULE_KEY)
    mechanical_records = _module_records(db, workspace=workspace, module_key=MECHANICAL_MODULE_KEY)
    electric_records = _module_records(db, workspace=workspace, module_key=ELECTRIC_MODULE_KEY)
    if not any([mechanical_revisions, electric_revisions, mechanical_records, electric_records]):
        return False
    if len(mechanical_revisions) != 1 or len(electric_revisions) != 1:
        raise ValueError("conflicting compressor revision state; import aborted")
    mechanical_revision = mechanical_revisions[0]
    electric_revision = electric_revisions[0]
    revisions_match = (
        mechanical_revision.status == REVISION_STATUS_PUBLISHED
        and mechanical_revision.revision_no == MECHANICAL_REVISION_NO
        and electric_revision.status == REVISION_STATUS_PUBLISHED
        and electric_revision.revision_no == ELECTRIC_REVISION_NO
    )
    if not revisions_match or len(mechanical_records) != 50 or len(electric_records) != 50:
        raise ValueError("partial or conflicting compressor data; import aborted")
    if any(record.revision_id != mechanical_revision.id for record in mechanical_records):
        raise ValueError("mechanical records are linked to an unexpected revision")
    if any(record.revision_id != electric_revision.id for record in electric_records):
        raise ValueError("electric records are linked to an unexpected revision")

    def source_signature(record: LegacyIssueRecord) -> tuple[str, str]:
        raw = record.raw_fields or {}
        values = record.field_values or {}
        return str(raw.get("source_sha256") or ""), str(values.get("evidence_legacy_issue") or "")

    mechanical_signatures = [source_signature(record) for record in mechanical_records]
    electric_signatures = [source_signature(record) for record in electric_records]
    expected_mechanical = [(XLS_SOURCE_SHA256, "미등재")] * 50
    expected_electric = [(XLSX_SOURCE_SHA256, "등재")] * 36 + [(XLS_SOURCE_SHA256, "미등재")] * 14
    if sorted(mechanical_signatures) != sorted(expected_mechanical):
        raise ValueError("mechanical source/status metadata does not match the approved import")
    if sorted(electric_signatures) != sorted(expected_electric):
        raise ValueError("electric source/status metadata does not match the approved import")
    revision_ids = [mechanical_revision.id, electric_revision.id]
    attachment_count = db.scalar(
        select(func.count())
        .select_from(LegacyIssueAttachment)
        .where(
            LegacyIssueAttachment.workspace_id == workspace.id,
            LegacyIssueAttachment.revision_id.in_(revision_ids),
        )
    )
    if attachment_count:
        raise ValueError("compressor revisions unexpectedly contain attachments")
    return True


def _create_published_revision(
    db,
    *,
    workspace: Workspace,
    actor: User,
    module_key: str,
    revision_no: int,
    now: datetime,
) -> LegacyIssueDataRevision:
    revision = LegacyIssueDataRevision(
        id=new_id(),
        workspace_id=workspace.id,
        dataset_key=_revision_key(module_key),
        revision_no=revision_no,
        status=REVISION_STATUS_PUBLISHED,
        note="Initial compressor source import",
        created_by_id=actor.id,
        published_by_id=actor.id,
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    ensure_revision_partition(db, revision)
    db.add(revision)
    db.flush()
    add_revision_event(
        db,
        workspace=workspace,
        revision=revision,
        user=actor,
        action="initial_publish",
        note=revision.note,
        details={"module_key": module_key, "source": "compressor-curated-import"},
    )
    return revision


def _import_file(
    db,
    *,
    workspace: Workspace,
    actor: User,
    revision: LegacyIssueDataRevision,
    module_key: str,
    curated_input: CuratedInput,
):
    definition = get_dataset_definition_with_all_module_fields(
        db,
        workspace=workspace,
        dataset_key=COMMON_MASTER_DATASET_KEY,
    )
    return import_dataset_records(
        db,
        definition,
        workspace=workspace,
        user=actor,
        revision=revision,
        filename=curated_input.filename,
        content=curated_input.import_content,
        mapping=curated_input.mapping,
        module_key=module_key,
    )


def import_compressor_data(
    db,
    *,
    workspace: Workspace,
    actor: User,
    inputs: dict[str, CuratedInput],
) -> dict[str, int]:
    if _completed_state_matches(db, workspace=workspace):
        return {"created": 0, "mechanical": 50, "electric": 50, "already_loaded": 1}

    now = utcnow_naive()
    mechanical_revision = _create_published_revision(
        db,
        workspace=workspace,
        actor=actor,
        module_key=MECHANICAL_MODULE_KEY,
        revision_no=MECHANICAL_REVISION_NO,
        now=now,
    )
    electric_revision = _create_published_revision(
        db,
        workspace=workspace,
        actor=actor,
        module_key=ELECTRIC_MODULE_KEY,
        revision_no=ELECTRIC_REVISION_NO,
        now=now,
    )
    mechanical_result = _import_file(
        db,
        workspace=workspace,
        actor=actor,
        revision=mechanical_revision,
        module_key=MECHANICAL_MODULE_KEY,
        curated_input=inputs[MECHANICAL_CSV],
    )
    electric_listed_result = _import_file(
        db,
        workspace=workspace,
        actor=actor,
        revision=electric_revision,
        module_key=ELECTRIC_MODULE_KEY,
        curated_input=inputs[ELECTRIC_LISTED_CSV],
    )
    electric_unlisted_result = _import_file(
        db,
        workspace=workspace,
        actor=actor,
        revision=electric_revision,
        module_key=ELECTRIC_MODULE_KEY,
        curated_input=inputs[ELECTRIC_UNLISTED_CSV],
    )
    definition = get_dataset_definition_with_all_module_fields(
        db,
        workspace=workspace,
        dataset_key=COMMON_MASTER_DATASET_KEY,
    )
    reindex_legacy_issue_revision_ai_chunks(
        db,
        definition,
        workspace=workspace,
        revision=mechanical_revision,
        embed=False,
    )
    reindex_legacy_issue_revision_ai_chunks(
        db,
        definition,
        workspace=workspace,
        revision=electric_revision,
        embed=False,
    )
    db.flush()
    created = (
        mechanical_result.created
        + electric_listed_result.created
        + electric_unlisted_result.created
    )
    if created != 100:
        raise ValueError(f"expected to create 100 records, created {created}")
    if not _completed_state_matches(db, workspace=workspace):
        raise ValueError("post-import compressor state verification failed")
    return {"created": created, "mechanical": 50, "electric": 50, "already_loaded": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Active workspace key or exact name")
    parser.add_argument("--actor", default="administrator", help="Platform-admin login id")
    parser.add_argument("--input-dir", type=Path, required=True, help="Curated CSV directory")
    parser.add_argument("--dry-run", action="store_true", help="Execute fully, then roll back")
    args = parser.parse_args()

    try:
        inputs = load_curated_inputs(args.input_dir)
        db = get_session_factory()()
        try:
            workspace = _resolve_workspace(db, args.workspace)
            actor = _resolve_actor(db, args.actor)
            result = import_compressor_data(
                db,
                workspace=workspace,
                actor=actor,
                inputs=inputs,
            )
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as exc:
        print(f"compressor import failed: {exc}", file=sys.stderr)
        return 1

    mode = "dry-run (rolled back)" if args.dry_run else "committed"
    print(
        f"compressor import {mode}: workspace={args.workspace!r} "
        f"created={result['created']} mechanical={result['mechanical']} "
        f"electric={result['electric']} already_loaded={bool(result['already_loaded'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
