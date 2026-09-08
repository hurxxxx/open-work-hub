from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "files_rag_readonly_harness.py"
    spec = importlib.util.spec_from_file_location("test_files_rag_readonly_harness_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="urn:test"><w:body><w:p/></w:body></w:document>',
        )


def _write_encrypted_flag_docx(path: Path) -> None:
    _write_docx(path)
    content = bytearray(path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        cursor = 0
        while True:
            position = content.find(signature, cursor)
            if position < 0:
                break
            flags = int.from_bytes(
                content[position + flag_offset : position + flag_offset + 2], "little"
            )
            content[position + flag_offset : position + flag_offset + 2] = (flags | 0x1).to_bytes(
                2, "little"
            )
            cursor = position + len(signature)
    path.write_bytes(content)


def _write_png(path: Path) -> None:
    Image.new("RGB", (2, 2), color=(12, 34, 56)).save(path, format="PNG")


def _exclusions(manifest: dict[str, object]) -> dict[str, int]:
    inventory = manifest["inventory"]
    assert isinstance(inventory, dict)
    exclusions = inventory["exclusions"]
    assert isinstance(exclusions, list)
    return {str(item["reason"]): int(item["file_count"]) for item in exclusions}


def _source_snapshot(source: Path) -> dict[str, str]:
    return {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_manifest_is_deterministic_and_never_serializes_names_or_bodies(tmp_path: Path) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    secret_name = "OMEGA_PRIVATE_customer_record.txt"
    secret_body = "TOP SECRET BODY MUST NEVER APPEAR"
    (source / secret_name).write_text(secret_body, encoding="utf-8")
    _write_docx(source / "valid.docx")
    _write_png(source / "valid.png")
    companion = source / "generated" / "support" / "lib" / "images"
    companion.mkdir(parents=True)
    _write_png(companion / "companion.png")
    (source / "looks-like-image.png").write_text(
        "<!doctype html><html><body>private portal</body></html>", encoding="utf-8"
    )
    (source / "broken.docx").write_bytes(b"PK\x03\x04not-a-valid-archive")
    _write_encrypted_flag_docx(source / "encrypted.docx")
    _write_docx(source / "~$draft.docx")
    (source / "page.html").write_text("<html>private page</html>", encoding="utf-8")

    first = harness.build_manifest(source, canaries_per_stratum=1, workers=2)
    second = harness.build_manifest(source, canaries_per_stratum=1, workers=1)

    assert first == second
    serialized = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert secret_name not in serialized
    assert secret_body not in serialized
    assert "private portal" not in serialized
    assert "private page" not in serialized
    inventory = first["inventory"]
    assert inventory["regular_file_count"] == 9
    assert inventory["eligible_file_count"] == 3
    assert _exclusions(first) == {
        "corrupt_office_archive": 1,
        "encrypted_office_archive": 1,
        "html_companion_asset": 1,
        "html_visible_text_below_minimum": 1,
        "html_like_image": 1,
        "office_temporary_file": 1,
    }
    assert len(first["strata"]) == 3
    for stratum in first["strata"]:
        assert len(stratum["canaries"]) == 1
        assert len(stratum["canaries"][0]["source_id"]) == 64
        assert len(stratum["canaries"][0]["content_sha256"]) == 64

    manifest_without_digest = dict(first)
    manifest_sha256 = manifest_without_digest.pop("manifest_sha256")
    expected_digest = hashlib.sha256(
        harness._canonical_json(manifest_without_digest).encode("ascii")
    ).hexdigest()
    assert manifest_sha256 == expected_digest


def test_manifest_output_must_be_outside_source_and_source_stays_unchanged(
    tmp_path: Path, capsys
) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    secret_name = "NEVER_PRINT_THIS_FILENAME.txt"
    secret_body = "NEVER PRINT THIS BODY"
    (source / secret_name).write_text(secret_body, encoding="utf-8")
    before = _source_snapshot(source)

    inside = source / "manifest.json"
    assert harness.main(["--source", str(source), "--manifest-out", str(inside)]) == 2
    error_output = capsys.readouterr().out
    assert json.loads(error_output) == {
        "status": "error",
        "code": "manifest_output_inside_source",
    }
    assert not inside.exists()

    outside = tmp_path / "manifest.json"
    assert harness.main(["--source", str(source), "--manifest-out", str(outside)]) == 0
    stdout = capsys.readouterr().out
    from_stdout = json.loads(stdout)
    from_disk = json.loads(outside.read_text(encoding="ascii"))
    assert from_stdout == from_disk
    assert secret_name not in stdout
    assert secret_body not in stdout
    assert _source_snapshot(source) == before


def test_ingest_is_fail_closed_behind_explicit_scope(tmp_path: Path, capsys) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()

    assert harness.main(["--source", str(source), "--execute-ingest"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "ingest_scope_required"

    assert (
        harness.main(
            [
                "--source",
                str(source),
                "--execute-ingest",
                "--corpus-id",
                "corpus-01",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["code"] == "ingest_adapter_not_connected"

    assert harness.main(["--source", str(source), "--corpus-id", "corpus-01"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "ingest_flag_required"


def test_hashed_evaluation_reports_quality_and_acl_without_query_or_ranked_ids(
    tmp_path: Path,
) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    (source / "evidence.txt").write_text("safe evidence", encoding="utf-8")
    source_id = harness._source_id(Path("evidence.txt"))
    disallowed_id = hashlib.sha256(b"disallowed").hexdigest()
    secret_query = "Confidential gearbox failure phrase"
    query_id = harness._query_id(secret_query)
    evaluation_input = tmp_path / "queries.json"
    evaluation_input.write_text(
        json.dumps(
            {
                "k": 5,
                "queries": [
                    {
                        "query": secret_query,
                        "relevant_source_ids": [source_id],
                        "allowed_source_ids": [source_id],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evaluation_results = tmp_path / "results.json"
    evaluation_results.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "query_id": query_id,
                        "mode": "hybrid",
                        "returned_source_ids": [source_id, disallowed_id],
                        "latency_ms": 12.3456,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = harness.build_manifest(
        source,
        workers=1,
        evaluation_input=evaluation_input,
        evaluation_results=evaluation_results,
    )

    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    assert secret_query not in serialized
    assert "returned_source_ids" not in serialized
    report = manifest["evaluation"]
    assert report["query_count"] == 1
    assert report["queries"][0]["query_id"] == query_id
    hybrid = report["queries"][0]["modes"]["hybrid"]
    assert hybrid == {
        "mrr": 1.0,
        "ndcg_at_k": 1.0,
        "recall_at_k": 1.0,
        "returned_count": 2,
        "latency_ms": 12.346,
        "acl_violation_count": 1,
    }
    assert report["queries"][0]["modes"]["keyword"] is None
    assert report["aggregate"]["hybrid"]["acl_violation_count"] == 1


def test_symlinks_and_oversize_files_are_excluded_before_content_inspection(tmp_path: Path) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    valid = source / "valid.txt"
    valid.write_text("ordinary content", encoding="utf-8")
    (source / "linked.txt").symlink_to(valid)
    oversize = source / "oversize.pdf"
    with oversize.open("wb") as stream:
        stream.truncate(harness.MAX_SOURCE_BYTES + 1)

    manifest = harness.build_manifest(source, workers=1)

    assert manifest["inventory"]["eligible_file_count"] == 1
    assert _exclusions(manifest) == {
        "source_size_limit_exceeded": 1,
        "symlink_file": 1,
    }


def test_unexpected_parser_failures_are_sanitized(tmp_path: Path, monkeypatch) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    secret_name = "LEAK_FROM_EXCEPTION.txt"
    secret_body = "LEAK FROM EXCEPTION BODY"
    (source / secret_name).write_text(secret_body, encoding="utf-8")

    def fail_with_sensitive_message(_stream, _candidate) -> None:
        raise RuntimeError(f"parser failed for {secret_name}: {secret_body}")

    monkeypatch.setattr(harness, "_validate_candidate_content", fail_with_sensitive_message)
    manifest = harness.build_manifest(source, workers=1)

    serialized = json.dumps(manifest, ensure_ascii=False)
    assert _exclusions(manifest) == {"inspection_error": 1}
    assert secret_name not in serialized
    assert secret_body not in serialized


def test_evaluation_validation_errors_do_not_echo_plaintext(tmp_path: Path, capsys) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    secret_query = "DO NOT ECHO THIS QUERY"
    evaluation_input = tmp_path / "queries.json"
    evaluation_input.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": secret_query,
                        "relevant_source_ids": ["not-a-sha"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert harness.main(["--source", str(source), "--evaluation-input", str(evaluation_input)]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["code"] == "invalid_evaluation_input"
    assert secret_query not in output


def test_html_reports_are_eligible_but_short_helpers_and_active_text_are_not(
    tmp_path: Path,
) -> None:
    harness = _load_script_module()
    source = tmp_path / "source"
    source.mkdir()
    visible_report = "열관리 시험 결과 정상 범위를 확인했습니다. " * 12
    (source / "report.html").write_text(
        "<!doctype html><html><head><title>시험 보고서</title></head><body>"
        f"<h1>결과</h1><p>{visible_report}</p>"
        "<script>이 내용은 검색되면 안 됩니다.</script>"
        "</body></html>",
        encoding="utf-8",
    )
    (source / "blank.html").write_text(
        "<!doctype html><html><body><script>"
        + ("실행 전용 콘텐츠 " * 100)
        + "</script><p>helper</p></body></html>",
        encoding="utf-8",
    )

    manifest = harness.build_manifest(source, workers=1)

    assert manifest["inventory"]["eligible_file_count"] == 1
    assert _exclusions(manifest) == {"html_visible_text_below_minimum": 1}
    html_extension = next(
        row for row in manifest["inventory"]["extensions"] if row["extension"] == "html"
    )
    assert html_extension["file_count"] == 2
    assert html_extension["eligible_file_count"] == 1
