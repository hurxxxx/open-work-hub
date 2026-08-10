"""One-off importer for legacy Trend (자동차 리서치 자료) report files.

The industry-report feature stores Trend reports in the DB + object storage and
starts empty. This script back-fills the existing legacy files from the old
Flask portal's ``static/trend/<COMPANY>/`` directories into MinIO + the
``industry_report_files`` table via the normal service path.

For each company directory whose name matches a known ``COMPANY_MAP`` code, it
uploads every ``*.pdf`` / ``*.html`` file. Legacy HTML is stored as a download,
not an inline browser preview. Clean ``title`` and ``published_date`` come from
the company's ``_index.json`` when present (keyed by filename); files not in the
index fall back to a title derived from the filename and a date parsed from a
leading ``YYMMDD`` / ``YYYYMMDD`` prefix when present.

Idempotent: a file is skipped when a row with the same ``company`` + ``filename``
already exists, so re-runs only add what is missing.

Usage (load .env.local first so OPEN_ALM_POSTGRES_DSN / MinIO settings resolve;
remote infra → run with the Claude Code sandbox disabled)::

    python apps/api/scripts/import_industry_report_trend.py \
        --source "C:\\server\\static\\trend" [--company KATECH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow running as a plain script: add apps/api/src to the path.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sqlalchemy import select  # noqa: E402

from open_alm_api.core.db import get_session_factory  # noqa: E402
from open_alm_api.domains.industry_report import config_data as cfg  # noqa: E402
from open_alm_api.domains.industry_report import service, storage  # noqa: E402
from open_alm_api.domains.industry_report.models import IndustryReportFile  # noqa: E402

_DEFAULT_SOURCE = r"C:\server\static\trend"
_DATE_PREFIX_RE = re.compile(r"^(\d{6}|\d{8})[ _]")
_SUPPORTED_SUFFIXES = {".pdf", ".html", ".htm"}
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".html": "application/octet-stream",
    ".htm": "application/octet-stream",
}


def _load_index(company_dir: Path) -> dict[str, dict]:
    """Map filename -> metadata entry from ``_index.json`` (if any)."""
    index_path = company_dir / "_index.json"
    if not index_path.is_file():
        return {}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {entry["filename"]: entry for entry in raw.values() if entry.get("filename")}


def _derive_date_from_name(name: str) -> str:
    match = _DATE_PREFIX_RE.match(name)
    if not match:
        return ""
    digits = match.group(1)
    if len(digits) == 6:  # YYMMDD
        yy, mm, dd = digits[0:2], digits[2:4], digits[4:6]
        year = f"20{yy}"
    else:  # YYYYMMDD
        year, mm, dd = digits[0:4], digits[4:6], digits[6:8]
    if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
        return ""
    return f"{year}-{mm}-{dd}"


def _derive_title(filename: str) -> str:
    stem = Path(filename).stem
    return _DATE_PREFIX_RE.sub("", stem).strip() or stem


def _resolve_meta(filename: str, index: dict[str, dict]) -> tuple[str, str]:
    entry = index.get(filename)
    if entry:
        return (entry.get("title") or _derive_title(filename), entry.get("date") or "")
    return (_derive_title(filename), _derive_date_from_name(filename))


def import_company(session, company_dir: Path, company: str, *, dry_run: bool) -> tuple[int, int]:
    index = _load_index(company_dir)
    existing = {
        row.filename
        for row in session.scalars(
            select(IndustryReportFile).where(IndustryReportFile.company == company)
        )
    }
    imported = skipped = 0
    for path in sorted(company_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        if path.name in existing:
            skipped += 1
            continue
        title, published_date = _resolve_meta(path.name, index)
        if dry_run:
            print(f"  [dry-run] {company} <- {path.name}  (title={title!r} date={published_date!r})")
            imported += 1
            continue
        data = path.read_bytes()
        content_type = _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        if content_type == storage.DEFAULT_REPORT_CONTENT_TYPE and not storage.has_pdf_signature(data):
            print(f"  [skip] {company} <- {path.name}  (not a PDF)")
            skipped += 1
            continue
        service.create_file(
            session,
            company=company,
            title=title,
            filename=path.name,
            data=data,
            content_type=content_type,
            uploaded_by_id=None,
            published_date=published_date,
        )
        imported += 1
        print(f"  {company} <- {path.name}")
    return imported, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=_DEFAULT_SOURCE, help="Legacy trend root directory")
    parser.add_argument("--company", default=None, help="Import only this company code (e.g. KATECH)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be imported; no writes")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_dir():
        print(f"source directory not found: {source}", file=sys.stderr)
        return 2

    session = get_session_factory()()
    total_imported = total_skipped = 0
    try:
        for company in cfg.COMPANY_MAP:
            if args.company and company != args.company:
                continue
            company_dir = source / company
            if not company_dir.is_dir():
                continue
            print(f"== {company} ({cfg.COMPANY_MAP[company]}) ==")
            imported, skipped = import_company(session, company_dir, company, dry_run=args.dry_run)
            total_imported += imported
            total_skipped += skipped
    finally:
        session.close()

    print(f"\nDone. imported={total_imported} skipped(existing)={total_skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
