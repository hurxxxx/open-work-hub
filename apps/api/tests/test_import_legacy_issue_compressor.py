from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from open_alm_api.domains.legacy_issues.dataset_records import (
    build_dataset_import_rows,
    get_dataset_definition,
    validate_mapping,
)


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "import_legacy_issue_compressor.py"
    spec = importlib.util.spec_from_file_location(
        "test_import_legacy_issue_compressor_script", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_curated_csv(path: Path, *, check_plan: str) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "source_file",
                "source_sha256",
                "source_sheet",
                "source_row",
                "source_no",
                "symptom",
                "check_plan",
                "evidence_legacy_issue",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_file": "source.xlsx",
                "source_sha256": "approved-sha",
                "source_sheet": "전동컴프 과거차 문제",
                "source_row": "6",
                "source_no": "1",
                "symptom": "여러 줄\n현상",
                "check_plan": check_plan,
                "evidence_legacy_issue": "등재",
            }
        )


def test_curated_electric_input_preserves_reviewed_multiline_check_plan(
    tmp_path: Path, monkeypatch
) -> None:
    loader = _load_script_module()
    filename = loader.ELECTRIC_LISTED_CSV
    reviewed = "점검 항목: 확인\n\n[설계]\n설계\n\n[평가]\n평가\n\n[제조]\n제조"
    _write_curated_csv(tmp_path / filename, check_plan=reviewed)
    monkeypatch.setitem(
        loader.EXPECTED_INPUTS,
        filename,
        {"rows": 1, "source_sha256": "approved-sha", "master_status": "등재"},
    )

    curated = loader._read_curated_input(tmp_path, filename)

    assert curated.rows[0]["check_plan"] == reviewed
    parsed = build_dataset_import_rows(
        get_dataset_definition("common-master"),
        filename=filename,
        content=curated.import_content,
    )
    assert len(parsed.data_rows) == 1
    validate_mapping(
        get_dataset_definition("common-master"),
        headers=parsed.headers,
        mapping=curated.mapping,
    )


def test_curated_electric_input_rejects_unreviewed_check_plan(tmp_path: Path, monkeypatch) -> None:
    loader = _load_script_module()
    filename = loader.ELECTRIC_LISTED_CSV
    _write_curated_csv(tmp_path / filename, check_plan="자동 결합되지 않은 텍스트")
    monkeypatch.setitem(
        loader.EXPECTED_INPUTS,
        filename,
        {"rows": 1, "source_sha256": "approved-sha", "master_status": "등재"},
    )

    with pytest.raises(ValueError, match="invalid reviewed check-plan format"):
        loader._read_curated_input(tmp_path, filename)
