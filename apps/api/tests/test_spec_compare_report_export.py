from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.spec_compare import report_export, service
from open_work_hub_api.domains.spec_compare import router as spec_compare_router
from open_work_hub_api.domains.spec_compare.models import SpecCompareJob


SAMPLE_PAYLOAD: dict[str, object] = {
    "report_markdown": "# r\n\n## AI 분석 요약\n\n- 전압 사양이 상이합니다.\n\n## 상세 비교표\n",
    "summary": {
        "total_rows": 2,
        "same": 1,
        "different": 1,
        "base_only": 0,
        "target_only": 0,
        "unknown": 0,
    },
    "comparison_rows": [
        {
            "spec_name": "정격 전압",
            "base_value": "220V",
            "target_value": "380V",
            "status": "different",
            "summary": "전압이 다릅니다",
            "base_evidence_ids": ["b1"],
            "target_evidence_ids": ["t1"],
        },
        {
            "spec_name": "무게",
            "base_value": "10 kg",
            "target_value": "10 kg",
            "status": "same",
            "summary": "동일",
            "base_evidence_ids": ["b2"],
            "target_evidence_ids": ["t2"],
        },
    ],
}


def _render(fmt: str, payload: dict[str, object], title: str = "제목") -> report_export.RenderedReport:
    return report_export.render_report(
        fmt,
        title=title,
        base_filename="base.pptx",
        target_filename="target.pdf",
        summary=payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {},
        payload=payload,
    )


def test_render_report_docx_and_pdf_produce_valid_magic_bytes() -> None:
    docx = _render("docx", SAMPLE_PAYLOAD)
    pdf = _render("pdf", SAMPLE_PAYLOAD)
    assert docx.content[:4] == b"PK\x03\x04"
    assert docx.media_type.endswith("wordprocessingml.document")
    assert docx.extension == "docx"
    assert pdf.content[:5] == b"%PDF-"
    assert pdf.media_type == "application/pdf"
    assert pdf.extension == "pdf"


def test_render_report_survives_xml_special_characters() -> None:
    payload: dict[str, object] = {
        "report_markdown": "## AI 분석 요약\n\n- R&D 항목 <검토> 필요 & 확인",
        "summary": {"total_rows": 1, "different": 1},
        "comparison_rows": [
            {
                "spec_name": "전압 < 5V & 안전",
                "base_value": "A & B",
                "target_value": "x<y>z",
                "status": "different",
                "summary": "R&D <표기> 차이",
                "base_evidence_ids": ["b1"],
                "target_evidence_ids": [],
            }
        ],
    }
    # reportlab's Paragraph mini-XML parser would raise on unescaped & < >.
    assert _render("pdf", payload, title='2024/01 "final" & <비교>').content[:5] == b"%PDF-"
    assert _render("docx", payload).content[:4] == b"PK\x03\x04"


def test_render_report_with_empty_rows_and_summary() -> None:
    payload: dict[str, object] = {"report_markdown": "", "summary": {}, "comparison_rows": []}
    assert _render("docx", payload, title="").content[:4] == b"PK\x03\x04"
    assert _render("pdf", payload, title="").content[:5] == b"%PDF-"


def test_render_report_rejects_unknown_format() -> None:
    with pytest.raises(ValueError):
        _render("xlsx", SAMPLE_PAYLOAD)


def test_pdf_font_falls_back_to_builtin_cid_when_no_ttf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No TTF candidate exists (Linux production image without CJK packages):
    # the built-in Korean CID fonts must be used, never Latin-only Helvetica.
    monkeypatch.setattr(report_export.os.path, "exists", lambda _path: False)
    regular, bold = report_export._register_pdf_korean_font()
    assert regular == "HYSMyeongJo-Medium"
    assert bold == "HYGothic-Medium"


def _succeeded_job(**overrides: object) -> SpecCompareJob:
    row = SpecCompareJob(
        id="job-1",
        workspace_id="workspace-1",
        owner_id="user-1",
        title="검증 보고서",
        status="succeeded",
        progress=100,
        status_message="succeeded",
        base_file_name="base.pptx",
        base_mime_type="application/pptx",
        base_size_bytes=1,
        base_storage_key="base-key",
        target_file_name="target.pdf",
        target_mime_type="application/pdf",
        target_size_bytes=1,
        target_storage_key="target-key",
        result_json_storage_key="result-key",
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


class _FakeGetDb:
    def __init__(self, row: SpecCompareJob | None) -> None:
        self.row = row

    def get(self, _model: type, _job_id: str) -> SpecCompareJob | None:
        return self.row


def test_get_report_document_returns_rendered_docx(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStore:
        def read_result_payload(self, storage_key: str) -> dict[str, object]:
            assert storage_key == "result-key"
            return dict(SAMPLE_PAYLOAD)

    monkeypatch.setattr(service, "spec_compare_artifact_store", lambda: FakeStore())
    db = _FakeGetDb(_succeeded_job())

    content, media_type, filename = service.get_report_document(
        db,  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        job_id="job-1",
        fmt="docx",
    )

    assert content[:4] == b"PK\x03\x04"
    assert media_type.endswith("wordprocessingml.document")
    assert filename == "검증 보고서.docx"


def test_get_report_document_rejects_unfinished_job() -> None:
    db = _FakeGetDb(_succeeded_job(status="running", result_json_storage_key=None))

    with pytest.raises(HTTPException) as exc_info:
        service.get_report_document(
            db,  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-1"),
            user=SimpleNamespace(id="user-1"),
            job_id="job-1",
            fmt="docx",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail.code == "spec_compare.not_ready"


def test_get_report_document_enforces_workspace_and_owner() -> None:
    db = _FakeGetDb(_succeeded_job())

    with pytest.raises(HTTPException) as other_workspace:
        service.get_report_document(
            db,  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-2"),
            user=SimpleNamespace(id="user-1"),
            job_id="job-1",
            fmt="pdf",
        )
    assert other_workspace.value.status_code == 404

    with pytest.raises(HTTPException) as other_user:
        service.get_report_document(
            db,  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-1"),
            user=SimpleNamespace(id="user-2"),
            job_id="job-1",
            fmt="pdf",
        )
    assert other_user.value.status_code == 403


def test_report_response_sanitizes_content_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nasty_filename = '2024/01 "final"\n비교.docx'
    monkeypatch.setattr(
        spec_compare_router.service,
        "get_report_document",
        lambda *_args, **_kwargs: (b"PK\x03\x04", "application/test", nasty_filename),
    )

    response = spec_compare_router._report_response(
        None,  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        job_id="job-1",
        fmt="docx",
    )

    disposition = response.headers["content-disposition"]
    # The quoted ASCII fallback must not smuggle quotes, newlines, or slashes.
    ascii_part = disposition.split('filename="', 1)[1].split('"', 1)[0]
    assert '"' not in ascii_part
    assert "\n" not in ascii_part
    assert "/" not in ascii_part
    # The RFC 5987 part must percent-encode every reserved byte, including '/'.
    star_part = disposition.split("filename*=UTF-8''", 1)[1]
    assert "/" not in star_part
    assert "\n" not in star_part
    assert '"' not in star_part
    assert response.headers["content-type"].startswith("application/test")
