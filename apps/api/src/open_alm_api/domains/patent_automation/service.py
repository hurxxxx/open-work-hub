"""Service layer: import 특허현황관리 workbook → DB, CRUD, progress, export.

The canonical import maps by **column position** (field_defs column letters)
because the workbook's 3-row merged header (group / blank / label) doesn't fit
the 2-row ``combine_header_rows`` helper. A round-trip export (record_id +
field columns, single header row) re-imports by header key instead.
"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.patent_automation import disclosure_form
from open_alm_api.domains.patent_automation import field_defs as fd
from open_alm_api.domains.patent_automation import history
from open_alm_api.domains.patent_automation.models import (
    PatentCostLine,
    PatentProgressEvent,
    PatentRecord,
)


INVALID_FILE_CODE = "patent_automation.invalid_file"
RECORD_NOT_FOUND_CODE = "patent_automation.record_not_found"
EXPORT_RECORD_ID_HEADER = "record_id"
OVERSEAS_SHEET_TITLE = "해외출원"
DATA_START_ROW = 5  # rows 1-4 are title/merged-header band

# Lifecycle phases derived from record state + progress.
PHASE_DISCLOSURE = "발명신고"
PHASE_PRIOR_ART = "선행조사"
PHASE_FILING_DECISION = "출원결정"
PHASE_FILED = "출원"
PHASE_EXAM_REQUEST = "심사청구"
PHASE_EXAM = "심사"
PHASE_REGISTERED = "등록"
PHASE_MAINTAINED = "유지"
PHASE_EXTINCT = "소멸"


# ── helpers ───────────────────────────────────────────────────────────────────
def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _derive_lifecycle_phase(values: dict[str, str]) -> str:
    if _clean(values.get("extinction_date")) or _clean(values.get("extinction_reason")):
        return PHASE_EXTINCT
    if _clean(values.get("annuity_payment_date")) or _clean(values.get("annuity_year")):
        return PHASE_MAINTAINED
    if _clean(values.get("registration_no")):
        return PHASE_REGISTERED
    if _clean(values.get("exam_progress_log")) or _clean(values.get("exam_in_progress")):
        return PHASE_EXAM
    if _clean(values.get("exam_request_date")) or _clean(values.get("exam_request_log")):
        return PHASE_EXAM_REQUEST
    if _clean(values.get("application_no")):
        return PHASE_FILED
    if _clean(values.get("review_result")):
        return PHASE_FILING_DECISION
    if _clean(values.get("draft_spec_log")) or _clean(values.get("draft_request_date")):
        return PHASE_PRIOR_ART
    return PHASE_DISCLOSURE


def _latest_stage(values: dict[str, str]) -> str | None:
    """current_stage = the last step of the invention-review (검토현황) log."""
    steps = fd.parse_progress_log(values.get("invention_review_log"))
    if steps:
        return steps[-1][1]
    return None


def _progress_events_from_values(values: dict[str, str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for field_key, kind in fd.PROGRESS_LOG_FIELDS.items():
        for seq, (event_date, stage) in enumerate(fd.parse_progress_log(values.get(field_key))):
            events.append({"kind": kind, "seq": seq, "event_date": event_date, "stage": stage})
    return events


def _trim(value: str, limit: int) -> str | None:
    """Promoted columns are length-bounded; never let a mis-mapped long cell
    (e.g. a progress log landing in registration_no) crash the insert."""
    cleaned = _clean(value)
    return cleaned[:limit] or None if cleaned else None


def _apply_promoted(record: PatentRecord, values: dict[str, str]) -> None:
    record.application_no = _trim(values.get("application_no", ""), 80)
    record.application_no_norm = (fd.normalize_app_no(values.get("application_no")) or "")[
        :40
    ] or None
    record.registration_no = _trim(values.get("registration_no", ""), 80)
    record.invention_title = _trim(values.get("invention_title", ""), 512)
    record.inventors = _clean(values.get("inventors")) or None
    record.application_date = fd.parse_mixed_date(values.get("application_date"))
    record.patent_status = _trim(values.get("patent_status", ""), 40)
    app_year = _clean(values.get("application_year"))
    record.application_year = int(app_year) if app_year.isdigit() else None
    disclosure = fd.extract_disclosure_date(values.get("invention_review_log"))
    record.disclosure_date = disclosure
    record.disclosure_year = fd.year_from_iso(disclosure)
    record.current_stage = _latest_stage(values)
    record.lifecycle_phase = _derive_lifecycle_phase(values)


def _sync_progress_events(
    db: Session, workspace: Workspace, record: PatentRecord, values: dict[str, str]
) -> int:
    """Replace the record's progress events from the accumulated log columns."""
    for existing in list(record.progress_events):
        db.delete(existing)
    record.progress_events.clear()
    count = 0
    for event in _progress_events_from_values(values):
        db.add(
            PatentProgressEvent(
                id=new_id(),
                workspace_id=workspace.id,
                record_id=record.id,
                kind=event["kind"],
                seq=event["seq"],
                event_date=event["event_date"],
                stage=event["stage"][:200],
            )
        )
        count += 1
    return count


def _stable_id_for(values: dict[str, str]) -> str:
    norm = fd.normalize_app_no(values.get("application_no"))
    if norm:
        return f"app:{norm}"
    title = _clean(values.get("invention_title"))
    disclosure = fd.extract_disclosure_date(values.get("invention_review_log")) or ""
    if title:
        return f"title:{disclosure}:{title}"[:36]
    return new_id()


def _row_is_empty(values: dict[str, str]) -> bool:
    return not any(
        _clean(values.get(k))
        for k in ("application_no", "invention_title", "submit_date", "registration_no")
    )


# ── import ────────────────────────────────────────────────────────────────────
def _load_workbook(filename: str, content: bytes) -> Workbook:
    if not filename.lower().endswith(".xlsx"):
        raise localized_http_exception(status_code=400, code=INVALID_FILE_CODE)
    try:
        return load_workbook(BytesIO(content), data_only=True)
    except Exception as error:  # noqa: BLE001
        raise localized_http_exception(status_code=400, code=INVALID_FILE_CODE) from error


_APPNO_DETECT = re.compile(r"^\s*\d{2}-\d{4}-\d{7}\s*$")
_NAMES_DETECT = re.compile(
    r"^[가-힣]{2,4}(?:\s*\([^)]*\))?(?:\s*,\s*[가-힣]{2,4}(?:\s*\([^)]*\))?)*$"
)


def _looks_like_appno(value: str) -> bool:
    return bool(_APPNO_DETECT.match(value))


def _looks_like_names(value: str) -> bool:
    return bool(value) and len(value) <= 40 and bool(_NAMES_DETECT.match(value.strip()))


def _looks_like_abstract(value: str) -> bool:
    return value.startswith("본 발명") or len(value) > 80


def _detect_sheet_offset(data_rows: list[tuple[Any, ...]], position: dict[str, int]) -> int:
    """Historical year-sheets are sometimes uniformly column-shifted vs the 2026
    layout (e.g. 2013 = −1) while others (2022) align. A naive 출원번호 scan is
    fooled by 원출원번호 (분할/우선권) columns that also match, so score several
    candidate offsets against multiple anchors (출원번호 + 발명자 names + 발명의
    명칭 + 요약) and pick the best; ties favour the canonical offset 0.
    """
    app_i = position["application_no"]
    inv_i = position["inventors"]
    title_i = position["invention_title"]
    abs_i = position["abstract"]

    def cell(row: tuple[Any, ...], idx: int) -> str:
        return _clean(row[idx]) if 0 <= idx < len(row) else ""

    best_offset, best_score = 0, -1
    for offset in (0, -1, -2, 1, 2, -3):
        score = 0
        for row in data_rows[:60]:
            if not row:
                continue
            if _looks_like_appno(cell(row, app_i + offset)):
                score += 3
            if _looks_like_names(cell(row, inv_i + offset)):
                score += 3
            title = cell(row, title_i + offset)
            if title and not _looks_like_names(title) and not _looks_like_abstract(title):
                score += 1
            if _looks_like_abstract(cell(row, abs_i + offset)):
                score += 1
        # Prefer canonical 0 on ties.
        if score > best_score or (score == best_score and offset == 0):
            best_offset, best_score = offset, score
    return best_offset if best_score > 0 else 0


def _values_from_year_row(row: tuple[Any, ...], offset: int = 0) -> dict[str, str]:
    """Map a year-sheet data row to {field_key: cleaned value} by column position.

    Historical sheets are shifted **non-uniformly**: NO. (col B) is always the
    leftmost data column, but older sheets omit the 제출실명 column so everything
    from 제출팀명 onward shifts left (offset < 0). So NO. keeps offset 0, the
    missing 제출실명 is left empty when shifted, and every other field uses the
    detected offset.
    """
    position = fd.column_position_mapping()
    values: dict[str, str] = {}
    for key, idx in position.items():
        if key == "no":
            shifted = idx  # row-number column is always leftmost; never shift
        elif key == "submitter_name" and offset < 0:
            continue  # 제출실명 column is absent in shifted historical sheets
        else:
            shifted = idx + offset
        cell = row[shifted] if 0 <= shifted < len(row) else None
        cleaned = _clean(cell)
        if cleaned:
            values[key] = _normalize_numeric(key, cleaned)
    return values


_YYYYMM_DOT = re.compile(r"^(\d{4})\.(\d{1,2})$")


def _values_from_overseas_row(row: tuple[Any, ...]) -> dict[str, str]:
    """Map a 해외출원 data row (row 15+) to {field_key: cleaned value} by the
    overseas column-letter positions (row-14 labels)."""
    position = fd.overseas_column_position_mapping()
    values: dict[str, str] = {}
    for key, idx in position.items():
        cell = row[idx] if 0 <= idx < len(row) else None
        cleaned = _clean(cell)
        if cleaned:
            values[key] = _normalize_numeric(key, cleaned, fd.OVERSEAS_FIELD_LOOKUP)
    return values


def _normalize_numeric(
    key: str, value: str, lookup: dict[str, "fd.PatentFieldDefinition"] | None = None
) -> str:
    """Round money/int fields to integers — the source stores Excel floats with
    binary noise (e.g. 254099.99999999997 → 254100).

    실적(_metric)·년월(_ym) 코드는 과거 시트에서 ``YYYY.MM`` 형식으로 들어올 수
    있는데(예: 제출실적 ``2007.02``), 단순 int 반올림하면 ``2007``로 잘려 '월'이
    사라진다. 이런 값은 현행 시트와 동일한 6자리 ``YYYYMM``(200702)으로 정규화한다.
    """
    definition = (lookup or fd.PATENT_FIELD_LOOKUP).get(key)
    if not (definition and definition.type in ("money", "int")):
        return value
    if key.endswith("_metric") or key.endswith("_ym"):
        m = _YYYYMM_DOT.match(value.strip())
        if m:
            return f"{int(m.group(1)):04d}{int(m.group(2)):02d}"
    try:
        return str(int(round(float(value.replace(",", "")))))
    except (ValueError, TypeError):
        return value


# Reverse map for round-trip re-import: export writes Korean labels as headers.
_LABEL_TO_KEY: dict[str, str] = {d.label_ko: d.key for d in fd.PATENT_FIELD_DEFINITIONS}


def _values_from_roundtrip_row(
    headers: list[str], row: tuple[Any, ...]
) -> tuple[str | None, dict[str, str]]:
    """Map a round-trip export row (record_id + label/key headers) to field keys."""
    values: dict[str, str] = {}
    stable: str | None = None
    for idx, header in enumerate(headers):
        cell = row[idx] if idx < len(row) else None
        cleaned = _clean(cell)
        if header == EXPORT_RECORD_ID_HEADER:
            stable = cleaned or None
            continue
        key = header if header in fd.PATENT_FIELD_LOOKUP else _LABEL_TO_KEY.get(header)
        if key and cleaned:
            values[key] = cleaned
    return stable, values


def build_import_preview(filename: str, content: bytes) -> dict[str, Any]:
    workbook = _load_workbook(filename, content)
    sheet_names = [ws.title for ws in workbook.worksheets]
    target = _first_year_sheet(workbook)
    columns: list[dict[str, Any]] = []
    preview_rows: list[list[str]] = []
    if target is not None:
        for d in fd.PATENT_FIELD_DEFINITIONS:
            columns.append(
                {
                    "index": fd.column_index_from_string(d.column_letter) - 1,
                    "header": f"{d.group_ko} - {d.label_ko}",
                    "sample_values": [],
                }
            )
        rows = list(target.iter_rows(min_row=DATA_START_ROW, values_only=True))
        for row in rows[:5]:
            preview_rows.append([_clean(c) for c in row])
    return {
        "columns": columns,
        "preview_rows": preview_rows,
        "suggested_mapping": {
            d.key: fd.column_index_from_string(d.column_letter) - 1
            for d in fd.PATENT_FIELD_DEFINITIONS
        },
        "sheet_names": sheet_names,
        "total_preview_rows": len(preview_rows),
    }


def _first_year_sheet(workbook: Workbook):
    for ws in workbook.worksheets:
        if ws.title.strip().isdigit() and len(ws.title.strip()) == 4:
            return ws
    return None


def _in_import_scope(
    source_sheet: str | None, *, imported_domestic: bool, imported_overseas: bool
) -> bool:
    """레코드(source_sheet 기준)가 이번 업로드 scope에 속해 미러 삭제 대상이 되는지 판정.
    해외 레코드는 해외 시트가 업로드됐을 때만, 국내(연도시트/수기=None) 레코드는 국내 시트가
    업로드됐을 때만 삭제 대상. 부분 업로드가 다른 scope의 공유 레코드를 지우지 못하게 한다."""
    if source_sheet == fd.OVERSEAS_SOURCE_SHEET:
        return imported_overseas
    return imported_domestic


def import_workbook(
    db: Session,
    *,
    workspace: Workspace,
    user: User | None,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    workbook = _load_workbook(filename, content)
    created = updated = skipped = total_rows = progress_total = removed = 0
    sheets_done: list[str] = []
    warnings: list[str] = []
    seen_stable: set[str] = set()  # 완전 미러: 이번 업로드에 존재한 stable_record_id
    # 이번 업로드에 포함된 scope. 미러 삭제를 업로드 scope로 한정하기 위함(부분 국내/해외
    # 업로드가 다른 scope의 공유 레코드를 삭제하는 사고 방지). 라운드트립(전체 export
    # 재임포트)은 마스터 전체라 두 scope 모두 포함으로 본다.
    imported_domestic = False
    imported_overseas = False
    field_label_map = {**fd.field_labels(), **fd.overseas_field_labels()}

    existing_by_stable: dict[str, PatentRecord] = {
        r.stable_record_id: r
        for r in db.scalars(
            select(PatentRecord)
            .options(selectinload(PatentRecord.progress_events))
            .where(PatentRecord.workspace_id == workspace.id)
        )
        if r.stable_record_id
    }

    for ws in workbook.worksheets:
        title = ws.title.strip()
        is_year = title.isdigit() and len(title) == 4
        is_overseas = title == OVERSEAS_SHEET_TITLE
        rows = list(ws.iter_rows(min_row=1, values_only=True))

        # Round-trip export sheet: header row 1 begins with record_id.
        first_cell = _clean(rows[0][0]) if rows and rows[0] else ""
        is_roundtrip = first_cell == EXPORT_RECORD_ID_HEADER

        if not is_year and not is_roundtrip and not is_overseas:
            warnings.append(f"연도 시트가 아니라 건너뜀: {title}")
            continue

        if is_roundtrip:
            headers = [_clean(c) for c in rows[0]]
            data_rows = rows[1:]
            sheet_offset = 0
        elif is_overseas:
            # 해외출원: labels on row 14, data from row 15; separate schema.
            headers = []
            data_rows = rows[fd.OVERSEAS_DATA_START_ROW - 1 :]
            sheet_offset = 0
        else:
            headers = []
            data_rows = rows[DATA_START_ROW - 1 :]
            # Historical year-sheets are uniformly column-shifted vs 2026; detect
            # the per-sheet offset from the 출원번호 column so fields realign.
            sheet_offset = _detect_sheet_offset(data_rows, fd.column_position_mapping())
            if sheet_offset:
                warnings.append(f"{title} 시트 컬럼 오프셋 {sheet_offset} 적용")

        for row in data_rows:
            if row is None:
                continue
            if is_roundtrip:
                stable, values = _values_from_roundtrip_row(headers, row)
            elif is_overseas:
                values = _values_from_overseas_row(row)
                stable = "ov:" + _stable_id_for(values)
            else:
                values = _values_from_year_row(row, sheet_offset)
                stable = _stable_id_for(values)
            if _row_is_empty(values):
                continue
            total_rows += 1
            if not stable:
                stable = _stable_id_for(values)
            seen_stable.add(stable)

            existing = existing_by_stable.get(stable)
            if existing is not None:
                old_values = dict(existing.field_values or {})
                existing.field_values = values
                existing.raw_fields = {field_label_map.get(k, k): v for k, v in values.items()}
                if is_year:
                    existing.source_sheet = title
                elif is_overseas:
                    existing.source_sheet = fd.OVERSEAS_SOURCE_SHEET
                existing.imported_source_filename = filename
                existing.imported_at = utcnow_naive()
                _apply_promoted(existing, values)
                progress_total += _sync_progress_events(db, workspace, existing, values)
                changes = history.collect_value_changes(
                    old_values=old_values, new_values=values, field_labels=field_label_map
                )
                if changes:
                    history.add_record_history_entries(
                        db,
                        workspace=workspace,
                        user=user,
                        record_id=existing.id,
                        action="import",
                        changes=changes,
                    )
                    updated += 1
                else:
                    skipped += 1
            else:
                record = PatentRecord(
                    id=new_id(),
                    workspace_id=workspace.id,
                    stable_record_id=stable,
                    source_sheet=(
                        title if is_year else fd.OVERSEAS_SOURCE_SHEET if is_overseas else None
                    ),
                    field_values=values,
                    raw_fields={field_label_map.get(k, k): v for k, v in values.items()},
                    imported_source_filename=filename,
                    imported_at=utcnow_naive(),
                    created_by_id=user.id if user else None,
                )
                _apply_promoted(record, values)
                db.add(record)
                db.flush()
                existing_by_stable[stable] = record
                progress_total += _sync_progress_events(db, workspace, record, values)
                history.add_record_history_entries(
                    db,
                    workspace=workspace,
                    user=user,
                    record_id=record.id,
                    action="create",
                    changes=history.collect_create_changes(
                        values=values, field_labels=field_label_map
                    ),
                )
                created += 1
        if is_year or is_roundtrip or is_overseas:
            sheets_done.append(title)
            if is_overseas:
                imported_overseas = True
            if is_year:
                imported_domestic = True
            if is_roundtrip:  # 전체 export 재임포트 = 마스터 전체
                imported_domestic = imported_overseas = True

    # 미러 삭제: 업로드한 원본에 없는 기존 행은 삭제(원본 = 마스터). 단,
    #  (1) 빈/이상 파일로 전체가 지워지는 사고 방지 → 유효 행이 하나라도 있을 때만,
    #  (2) 이번 업로드에 포함된 scope(국내/해외)에 한정 → 부분 업로드가 다른 scope의
    #      공유 레코드를 삭제하지 못하게 한다.
    if total_rows > 0:
        for stable, record in existing_by_stable.items():
            if stable in seen_stable:
                continue
            if not _in_import_scope(
                record.source_sheet,
                imported_domestic=imported_domestic,
                imported_overseas=imported_overseas,
            ):
                continue  # 다른 scope의 공유 레코드는 보존
            history.add_record_history_entries(
                db,
                workspace=workspace,
                user=user,
                record_id=record.id,
                action="delete",
                changes=[
                    history.PatentHistoryChange(
                        field_key="record",
                        field_label="record",
                        old_value=record.id,
                        new_value=None,
                    )
                ],
            )
            db.delete(record)
            removed += 1

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "removed": removed,
        "total_rows": total_rows,
        "progress_events": progress_total,
        "sheets": sheets_done,
        "warnings": warnings,
    }


# ── records CRUD ───────────────────────────────────────────────────────────────
def list_records(
    db: Session,
    *,
    workspace: Workspace,
    query: str | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[PatentRecord], int]:
    base = select(PatentRecord).where(PatentRecord.workspace_id == workspace.id)
    if source == fd.OVERSEAS_SOURCE_SHEET:
        base = base.where(PatentRecord.source_sheet == fd.OVERSEAS_SOURCE_SHEET)
    elif source == "domestic":
        # year-sheets ('2025' …) and manually-added rows (source_sheet NULL)
        base = base.where(
            or_(
                PatentRecord.source_sheet.is_(None),
                PatentRecord.source_sheet != fd.OVERSEAS_SOURCE_SHEET,
            )
        )
    if query:
        like = f"%{query.strip()}%"
        base = base.where(
            or_(
                PatentRecord.invention_title.ilike(like),
                PatentRecord.application_no.ilike(like),
                PatentRecord.registration_no.ilike(like),
                PatentRecord.inventors.ilike(like),
            )
        )
    total = len(list(db.scalars(base)))
    rows = list(
        db.scalars(
            base.options(selectinload(PatentRecord.progress_events))
            .order_by(
                PatentRecord.disclosure_date.desc().nullslast(), PatentRecord.updated_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total


def get_record(db: Session, *, workspace: Workspace, record_id: str) -> PatentRecord:
    record = db.scalars(
        select(PatentRecord)
        .options(selectinload(PatentRecord.progress_events))
        .where(PatentRecord.workspace_id == workspace.id, PatentRecord.id == record_id)
    ).first()
    if record is None:
        raise localized_http_exception(status_code=404, code=RECORD_NOT_FOUND_CODE)
    return record


def create_record(
    db: Session,
    *,
    workspace: Workspace,
    user: User | None,
    values: dict[str, Any],
    stable_record_id: str | None,
) -> PatentRecord:
    clean_values = {
        k: _clean(v) for k, v in values.items() if k in fd.PATENT_FIELD_LOOKUP and _clean(v)
    }
    record = PatentRecord(
        id=new_id(),
        workspace_id=workspace.id,
        stable_record_id=stable_record_id or _stable_id_for(clean_values),
        field_values=clean_values,
        raw_fields={fd.field_labels().get(k, k): v for k, v in clean_values.items()},
        created_by_id=user.id if user else None,
    )
    _apply_promoted(record, clean_values)
    db.add(record)
    db.flush()
    _sync_progress_events(db, workspace, record, clean_values)
    history.add_record_history_entries(
        db,
        workspace=workspace,
        user=user,
        record_id=record.id,
        action="create",
        changes=history.collect_create_changes(values=clean_values, field_labels=fd.field_labels()),
    )
    db.commit()
    return get_record(db, workspace=workspace, record_id=record.id)


def create_record_from_disclosure(
    db: Session, *, workspace: Workspace, user: User | None, filename: str, content: bytes
) -> PatentRecord:
    """Parse a 직무발명신고서 form and create a new (pre-application) record.

    Sets the 직무발명기술서 접수 step to today's date so disclosure_date /
    year-sheet placement derive correctly; the rest (application/registration)
    stays empty until the patent is filed."""
    values = disclosure_form.parse_disclosure_form(content)
    if not values.get("invention_title") and not values.get("inventors"):
        # Not a recognizable disclosure form (no title and no inventors found).
        raise localized_http_exception(status_code=400, code=INVALID_FILE_CODE)
    today = datetime.now().strftime("%Y.%m.%d")
    values.setdefault("submit_date", today)
    values["invention_review_log"] = f"{today} {fd.DISCLOSURE_STAGE}"
    return create_record(db, workspace=workspace, user=user, values=values, stable_record_id=None)


def update_record(
    db: Session, *, workspace: Workspace, user: User | None, record_id: str, values: dict[str, Any]
) -> PatentRecord:
    record = get_record(db, workspace=workspace, record_id=record_id)
    old_values = dict(record.field_values or {})
    merged = dict(old_values)
    for k, v in values.items():
        if k in fd.PATENT_FIELD_LOOKUP:
            merged[k] = _clean(v)
    merged = {k: v for k, v in merged.items() if v}
    record.field_values = merged
    record.raw_fields = {fd.field_labels().get(k, k): v for k, v in merged.items()}
    _apply_promoted(record, merged)
    _sync_progress_events(db, workspace, record, merged)
    changes = history.collect_value_changes(
        old_values=old_values, new_values=merged, field_labels=fd.field_labels()
    )
    if changes:
        history.add_record_history_entries(
            db,
            workspace=workspace,
            user=user,
            record_id=record.id,
            action="update",
            changes=changes,
        )
    db.commit()
    return get_record(db, workspace=workspace, record_id=record_id)


def delete_record(db: Session, *, workspace: Workspace, user: User | None, record_id: str) -> None:
    record = get_record(db, workspace=workspace, record_id=record_id)
    db.execute(
        update(PatentCostLine)
        .where(
            PatentCostLine.workspace_id == workspace.id,
            PatentCostLine.record_id == record.id,
        )
        .values(record_id=None)
    )
    history.add_record_history_entries(
        db,
        workspace=workspace,
        user=user,
        record_id=record.id,
        action="delete",
        changes=[
            history.PatentHistoryChange(
                field_key="record", field_label="record", old_value=record.id, new_value=None
            )
        ],
    )
    db.delete(record)
    db.commit()


# ── progress ──────────────────────────────────────────────────────────────────
def add_progress_event(
    db: Session,
    *,
    workspace: Workspace,
    record_id: str,
    kind: str,
    stage: str,
    event_date: str | None,
    note: str | None,
    seq: int | None,
) -> PatentRecord:
    record = get_record(db, workspace=workspace, record_id=record_id)
    if seq is None:
        existing_seqs = [e.seq for e in record.progress_events if e.kind == kind]
        seq = (max(existing_seqs) + 1) if existing_seqs else 0
    db.add(
        PatentProgressEvent(
            id=new_id(),
            workspace_id=workspace.id,
            record_id=record.id,
            kind=kind,
            seq=seq,
            event_date=event_date,
            stage=stage[:200],
            note=note,
        )
    )
    # Refresh current_stage if this is the review log.
    if kind == fd.PROGRESS_LOG_FIELDS["invention_review_log"]:
        record.current_stage = stage[:120]
    db.commit()
    return get_record(db, workspace=workspace, record_id=record_id)


# ── export (round-trip) ─────────────────────────────────────────────────────────
def export_records(db: Session, *, workspace: Workspace) -> bytes:
    rows, _total = list_records(db, workspace=workspace, limit=100000, offset=0)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "특허현황관리"
    keys = fd.field_keys()
    headers = [EXPORT_RECORD_ID_HEADER, *(fd.PATENT_FIELD_LOOKUP[k].label_ko for k in keys)]
    sheet.append(headers)
    header_fill = PatternFill(fill_type="solid", fgColor="DDE7F6")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
    for record in rows:
        values = record.field_values or {}
        sheet.append([record.stable_record_id or record.id, *(values.get(k, "") for k in keys)])
    sheet.freeze_panes = "B2"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ── serialization ───────────────────────────────────────────────────────────────
def serialize_record(record: PatentRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "stable_record_id": record.stable_record_id,
        "application_no": record.application_no,
        "registration_no": record.registration_no,
        "invention_title": record.invention_title,
        "inventors": record.inventors,
        "disclosure_date": record.disclosure_date,
        "disclosure_year": record.disclosure_year,
        "application_date": record.application_date,
        "application_year": record.application_year,
        "patent_status": record.patent_status,
        "current_stage": record.current_stage,
        "lifecycle_phase": record.lifecycle_phase,
        "source_sheet": record.source_sheet,
        "field_values": record.field_values or {},
        "progress_events": [
            {
                "id": e.id,
                "kind": e.kind,
                "seq": e.seq,
                "event_date": e.event_date,
                "stage": e.stage,
                "note": e.note,
            }
            for e in sorted(record.progress_events, key=lambda x: (x.kind, x.seq))
        ],
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }
