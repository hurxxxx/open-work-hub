from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook

from ai_do_api.domains.legacy_issues.dataset_records import (
    clean_dataset_values,
    get_dataset_definition,
)
from ai_do_api.domains.legacy_issues.tabular_import import parse_tabular_upload


def test_xlsx_date_and_datetime_cells_are_normalized_by_date_fields() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["접수일", "접수일시", "빈 값"])
    sheet.append([date(2026, 7, 24), datetime(2026, 7, 25, 13, 45), None])
    content = BytesIO()
    workbook.save(content)

    rows, file_kind = parse_tabular_upload(
        filename="legacy-issues.xlsx",
        content=content.getvalue(),
        invalid_code="legacy_issues.dataset_import_file_invalid",
    )

    assert file_kind == "xlsx"
    assert rows == [
        ["접수일", "접수일시", "빈 값"],
        ["2026-07-24 00:00:00", "2026-07-25 13:45:00", ""],
    ]
    definition = get_dataset_definition("common-master")
    assert clean_dataset_values(
        definition,
        {"received_date": rows[1][0]},
    ) == {"received_date": "2026-07-24"}
    assert clean_dataset_values(
        definition,
        {"received_date": rows[1][1]},
    ) == {"received_date": "2026-07-25"}
