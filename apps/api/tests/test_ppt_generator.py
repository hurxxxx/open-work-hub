from __future__ import annotations

import asyncio
import io
import os
import re
import sys
import zipfile
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from open_alm_api.core.db import get_db_session
from open_alm_api.domains.auth.dependencies import require_current_workspace
from open_alm_api.domains.document_processing.pptx import archive_exceeds_limits
from open_alm_api.domains.media.models import MediaFile  # noqa: F401
from open_alm_api.domains.ppt_generator.families import FAMILIES
from open_alm_api.domains.ppt_generator import router, service, source_images
from open_alm_api.domains.ppt_generator.design import corporate_templates, html_to_pptx
from open_alm_api.domains.ppt_generator.models import PptJob, PptTemplatePreviewImage


def _zip_info(name: str, *, size: int, compressed: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.file_size = size
    info.compress_size = compressed
    return info


class _FakeDb:
    def __init__(self) -> None:
        self.job = None
        self.commits = 0

    def add(self, job) -> None:
        self.job = job

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, job) -> None:
        self.job = job


class _FakeGetDb:
    def __init__(self, job) -> None:
        self.job = job

    def get(self, model, job_id: str):
        return self.job if self.job.id == job_id else None


def test_archive_exceeds_limits_accepts_normal_pptx_directory() -> None:
    infos = [
        _zip_info("ppt/slides/slide1.xml", size=4_096, compressed=1_024),
        _zip_info("ppt/media/image1.png", size=100_000, compressed=80_000),
    ]

    assert archive_exceeds_limits(infos) is False


def test_archive_exceeds_limits_rejects_suspicious_expansion_ratio() -> None:
    infos = [_zip_info("ppt/media/image1.png", size=101_000, compressed=1_000)]

    assert archive_exceeds_limits(infos) is True


def test_family_catalog_exposes_corporate_report_templates() -> None:
    assert FAMILIES["corporate-seminar"]["design"] == "corporate-seminar"
    assert FAMILIES["corporate-education"]["design"] == "corporate-education"


def test_meeting_minutes_renderer_keeps_missing_date_blank() -> None:
    html = corporate_templates.render_meeting_minutes_deck(
        {
            "title": "품질 회의",
            "team": "품질팀",
            "date": "",
            "body": ["결정 사항을 정리한다."],
        }
    )

    match = re.search(r">회의일</td><td[^>]*>(.*?)</td>", html)

    assert match is not None
    assert match.group(1) == ""


def test_html_to_pptx_find_browser_prefers_configured_path(monkeypatch, tmp_path) -> None:
    browser = tmp_path / "chrome"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setenv("OPEN_ALM_PPT_BROWSER_PATH", str(browser))
    monkeypatch.setattr(html_to_pptx.shutil, "which", lambda _name: None)

    assert html_to_pptx._find_browser() == str(browser)


def test_html_to_pptx_find_browser_uses_path_commands(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_ALM_PPT_BROWSER_PATH", raising=False)
    monkeypatch.setattr(html_to_pptx, "_BROWSER_PATHS", ())

    def fake_which(name: str) -> str | None:
        return "/usr/bin/google-chrome" if name == "google-chrome" else None

    monkeypatch.setattr(html_to_pptx.shutil, "which", fake_which)

    assert html_to_pptx._find_browser() == "/usr/bin/google-chrome"


def test_html_to_pptx_find_browser_prefers_system_chrome_over_snap_wrapper(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPEN_ALM_PPT_BROWSER_PATH", raising=False)
    monkeypatch.setattr(
        html_to_pptx,
        "_BROWSER_PATHS",
        ("/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable"),
    )
    monkeypatch.setattr(
        html_to_pptx.os.path,
        "exists",
        lambda path: path in {"/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable"},
    )
    monkeypatch.setattr(html_to_pptx.shutil, "which", lambda _name: None)

    assert html_to_pptx._find_browser() == "/usr/bin/google-chrome-stable"


def test_extract_geometry_reports_early_browser_exit_and_uses_isolated_profile(
    monkeypatch,
    tmp_path,
) -> None:
    commands: list[list[str]] = []
    popen_kwargs: list[dict] = []

    class FakeProc:
        def poll(self) -> int:
            return 1

        def wait(self, timeout: int | None = None) -> int:  # noqa: ARG002
            return 1

    def fake_popen(command, **kwargs):
        commands.append(command)
        popen_kwargs.append(kwargs)
        stderr = kwargs.get("stderr")
        if hasattr(stderr, "write"):
            stderr.write(b"snap-confine refused to start")
            stderr.flush()
        return FakeProc()

    monkeypatch.setattr(html_to_pptx.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        html_to_pptx.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("CDP must not be polled")),
    )

    html_path = tmp_path / "deck.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"exit=1.*snap-confine refused to start"):
        asyncio.run(html_to_pptx._extract_geometry(str(html_path), "/snap/bin/chromium"))

    assert len(commands) == 1
    assert popen_kwargs[0]["env"]["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/dev/null"
    profile_args = [arg for arg in commands[0] if arg.startswith("--user-data-dir=")]
    assert len(profile_args) == 1
    assert not os.path.exists(profile_args[0].split("=", 1)[1])


def test_run_browser_isolates_headless_chrome_from_desktop_session_bus(
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    monkeypatch.setattr(html_to_pptx.subprocess, "run", fake_run)

    html_to_pptx._run_browser(
        ["/usr/bin/google-chrome", "--headless=new"],
        timeout=10,
        operation="test",
    )

    assert captured["env"]["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/dev/null"


def test_editable_pptx_cleans_temporary_html_directory_on_failure(
    monkeypatch,
    tmp_path,
) -> None:
    async def fail_extract(*_args, **_kwargs):
        raise RuntimeError("browser failed")

    monkeypatch.setattr(html_to_pptx, "_find_browser", lambda: "/usr/bin/google-chrome")
    monkeypatch.setattr(html_to_pptx, "_extract_geometry", fail_extract)
    monkeypatch.setattr(html_to_pptx.tempfile, "tempdir", str(tmp_path))

    with pytest.raises(RuntimeError, match="browser failed"):
        html_to_pptx.html_deck_to_editable_pptx_bytes("<html></html>")

    assert not list(tmp_path.glob("pptedit_*"))


def test_ppt_generator_router_blocks_disabled_app() -> None:
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from open_alm_api.app import localized_http_exception_handler
    from open_alm_api.core.i18n import localized_http_exception

    app = FastAPI()
    app.include_router(router.router, prefix="/api/v1/workspaces/{workspace_slug}")
    app.add_exception_handler(StarletteHTTPException, localized_http_exception_handler)

    def disabled() -> None:
        raise localized_http_exception(status_code=403, code="ppt_generator.app_disabled")

    app.dependency_overrides[router.require_ppt_generator_app_enabled] = disabled
    app.dependency_overrides[require_current_workspace] = lambda: SimpleNamespace(id="ws-1")
    app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()

    response = TestClient(app).get("/api/v1/workspaces/acme/ppt-generator/families")

    assert response.status_code == 403
    assert response.json()["code"] == "ppt_generator.app_disabled"


def test_template_preview_without_media_is_not_renderable() -> None:
    preview = PptTemplatePreviewImage(
        id="preview-1",
        workspace_id="workspace-1",
        family_id="corporate-house",
        media_id="media-1",
        sort_order=1,
        uploaded_by_id="user-1",
    )

    assert service.template_preview_url(preview) is None


def test_extract_uploaded_files_merges_txt_and_rejects_unknown_extension() -> None:
    merged, succeeded, failed = service.extract_uploaded_files(
        [
            ("brief.txt", "핵심 내용".encode("utf-8"), "text/plain"),
            ("archive.exe", b"nope", "application/octet-stream"),
        ]
    )

    assert "[brief.txt]" in merged
    assert "핵심 내용" in merged
    assert succeeded == ["brief.txt"]
    assert failed == [{"name": "archive.exe", "reason": "지원되지 않는 확장자 (.exe)"}]


def test_generate_form_topic_limit_is_enforced_server_side() -> None:
    with pytest.raises(HTTPException) as exc_info:
        router._clean_limited_text(
            "x" * 101,
            max_chars=100,
            code="ppt_generator.topic_too_long",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.headers["X-Open ALM-Error-Code"] == "ppt_generator.topic_too_long"


def test_generate_form_reference_url_limit_is_enforced_server_side() -> None:
    with pytest.raises(HTTPException) as exc_info:
        router._clean_limited_text(
            "x" * (router._MAX_REFERENCE_URL_CHARS + 1),
            max_chars=router._MAX_REFERENCE_URL_CHARS,
            code="ppt_generator.form_field_too_long",
        )

    assert exc_info.value.status_code == 422
    assert (
        exc_info.value.headers["X-Open ALM-Error-Code"]
        == "ppt_generator.form_field_too_long"
    )


def test_create_job_stores_external_context_in_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "_enqueue", lambda _task_name, _job_id: "task-1")
    db = _FakeDb()

    external_context = {
        "purpose": "임원 보고용",
        "audience": "경영진",
        "reference_url": "https://example.com/article",
    }
    job = service.create_job(
        db,  # type: ignore[arg-type]
        SimpleNamespace(id="user-1"),
        SimpleNamespace(id="workspace-1"),
        # content(=내부 Qwen 입력)에는 기밀 첨부/기타 참고사항이 합쳐져 들어온다.
        content="주제\n\n[기타 참고사항]\n비공개 매출 수치",
        topic="주제",
        external_context=external_context,
        family="corporate-house",
        slide_range=None,
        language="Korean",
        tone="default",
        instructions=None,
        include_title_slide=True,
        include_toc=False,
        attached_files=[],
        failed_files=[],
    )

    stored = (job.params or {}).get("external_context")
    assert stored == external_context
    # 불변식: 외부로 나갈 수 있는 external_context 에는 기밀 본문이 절대 섞이지 않는다.
    assert "비공개" not in str(stored)


def test_create_job_sets_fixed_cover_author_label(monkeypatch: pytest.MonkeyPatch) -> None:
    # 표지 하단 작성자는 로그인 사용자의 개인 이름이 아니라 소속(팀) 고정 문구여야 한다.
    monkeypatch.setattr(service, "_enqueue", lambda _task_name, _job_id: "task-1")
    db = _FakeDb()

    job = service.create_job(
        db,  # type: ignore[arg-type]
        SimpleNamespace(id="user-1", display_name="주승근", full_name="주승근"),
        SimpleNamespace(id="workspace-1"),
        content="주제",
        topic="주제",
        external_context=None,
        family="corporate-house",
        slide_range=None,
        language="Korean",
        tone="default",
        instructions=None,
        include_title_slide=True,
        include_toc=False,
        attached_files=[],
        failed_files=[],
    )

    assert (job.params or {}).get("author_name") == service._COVER_AUTHOR_LABEL
    assert "주승근" not in str((job.params or {}).get("author_name"))


def test_create_job_marks_error_when_enqueue_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_enqueue(task_name: str, job_id: str) -> str:
        raise RuntimeError("broker password leaked in exception")

    monkeypatch.setattr(service, "_enqueue", fail_enqueue)
    db = _FakeDb()

    with pytest.raises(service.PptGeneratorEnqueueError):
        service.create_job(
            db,  # type: ignore[arg-type]
            SimpleNamespace(id="user-1"),
            SimpleNamespace(id="workspace-1"),
            content="주제",
            topic="주제",
            family="corporate-house",
            slide_range=None,
            language="Korean",
            tone="default",
            instructions=None,
            include_title_slide=True,
            include_toc=False,
            attached_files=[],
            failed_files=[],
        )

    assert db.job is not None
    assert db.job.status == "error"
    assert db.job.message == "생성 실패"
    assert "broker" not in (db.job.error or "")
    assert db.commits >= 2


def test_create_job_stores_bounded_template_preview_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "_enqueue", lambda _task_name, _job_id: "task-1")
    db = _FakeDb()
    refs = [
        {
            "storage_key": f"media/template/{idx}.png",
            "filename": f"template-{idx}.png",
            "content_type": "image/png",
            "size_bytes": 1000 + idx,
            "sort_order": idx,
        }
        for idx in range(6)
    ]

    job = service.create_job(
        db,  # type: ignore[arg-type]
        SimpleNamespace(id="user-1"),
        SimpleNamespace(id="workspace-1"),
        content="주제",
        topic="주제",
        family="corporate-house",
        slide_range=None,
        language="Korean",
        tone="default",
        instructions=None,
        include_title_slide=True,
        include_toc=False,
        attached_files=[],
        failed_files=[],
        template_preview_images=refs,
    )

    stored_refs = (job.params or {}).get("template_preview_images")
    assert stored_refs == refs[:4]


def test_public_job_title_uses_topic_only() -> None:
    job = PptJob(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        status="completed",
        message="완료",
        family="corporate-house",
        aspect="A4",
        n_slides=2,
        content="[첨부 문서 내용]\n[secret.docx]\n대외비 본문",
        params={"topic": "월간 품질 보고"},
    )

    assert service.public_job_title(job) == "월간 품질 보고"


def test_public_job_title_does_not_fallback_to_attachment_text() -> None:
    job = PptJob(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        status="completed",
        message="완료",
        family="corporate-house",
        aspect="A4",
        n_slides=2,
        content="[첨부 문서 내용]\n[secret.docx]\n대외비 본문",
        params={},
    )

    assert service.public_job_title(job) is None


def test_get_job_ignores_soft_deleted_jobs() -> None:
    job = PptJob(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        status="completed",
        message="완료",
        family="corporate-house",
        aspect="A4",
        n_slides=2,
        deleted_at=service.utcnow_naive(),
    )

    assert (
        service.get_job(
            _FakeGetDb(job),  # type: ignore[arg-type]
            "workspace-1",
            "job-1",
            "user-1",
        )
        is None
    )


def test_start_finalize_restores_previous_pptx_key_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_enqueue(task_name: str, job_id: str) -> str:
        raise RuntimeError("redis://secret")

    monkeypatch.setattr(service, "_enqueue", fail_enqueue)
    db = _FakeDb()
    job = PptJob(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        status="completed",
        message="완료",
        family="corporate-house",
        aspect="A4",
        n_slides=2,
        content="주제",
        params={},
        slides_spec={"family": "corporate-house", "slides": []},
        pptx_key="ppt-generator/workspace-1/job-1/output.pptx",
    )

    with pytest.raises(service.PptGeneratorEnqueueError):
        service.start_finalize(db, job)  # type: ignore[arg-type]

    assert job.pptx_key == "ppt-generator/workspace-1/job-1/output.pptx"
    assert job.message == "변환 실패"
    assert "redis" not in (job.error or "")


def test_request_cancel_revokes_task_and_marks_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revoked: list[tuple[str, bool]] = []

    class _FakeControl:
        def revoke(self, task_id: str, terminate: bool = False) -> None:
            revoked.append((task_id, terminate))

    monkeypatch.setattr(
        service,
        "_get_celery_client",
        lambda: SimpleNamespace(control=_FakeControl()),
    )
    db = _FakeDb()
    job = PptJob(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        status="running",
        message="슬라이드 구조 생성 중...",
        family="corporate-house",
        aspect="A4",
        n_slides=0,
        content="주제",
        params={},
        celery_task_id="task-xyz",
    )

    service.request_cancel(db, job)  # type: ignore[arg-type]

    assert job.status == "cancelled"
    assert job.error is None
    # 실행 중인 워커를 죽이지 않도록 terminate=False 로 revoke 해야 한다.
    assert revoked == [("task-xyz", False)]


def test_request_cancel_without_task_id_still_marks_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom() -> object:
        raise AssertionError("celery client should not be needed without a task id")

    monkeypatch.setattr(service, "_get_celery_client", _boom)
    db = _FakeDb()
    job = PptJob(
        id="job-2",
        workspace_id="workspace-1",
        user_id="user-1",
        status="pending",
        message="작업 큐 등록됨",
        family="corporate-house",
        aspect="A4",
        n_slides=0,
        content="주제",
        params={},
        celery_task_id=None,
    )

    service.request_cancel(db, job)  # type: ignore[arg-type]

    assert job.status == "cancelled"


def test_start_chat_edit_marks_chat_error_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_enqueue(task_name: str, job_id: str) -> str:
        raise RuntimeError("redis://secret")

    monkeypatch.setattr(service, "_enqueue", fail_enqueue)
    db = _FakeDb()
    job = PptJob(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        status="completed",
        message="완료",
        family="corporate-house",
        aspect="A4",
        n_slides=2,
        content="주제",
        params={},
        slides_spec={"family": "corporate-house", "slides": []},
        chat_result={"rev": 4},
    )

    with pytest.raises(service.PptGeneratorEnqueueError):
        service.start_chat_edit(db, job, "1번 슬라이드 수정", [])  # type: ignore[arg-type]

    assert job.chat_result is not None
    assert job.chat_result["status"] == "error"
    assert job.chat_result["rev"] == 5
    assert "redis" not in job.chat_result["answer"]


def test_pdf_image_extraction_stops_at_page_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded_pages: list[int] = []

    class FakePage:
        def get_text(self, kind: str) -> str:
            return ""

        def get_images(self, full: bool) -> list:
            return []

    class FakeDoc:
        page_count = source_images._MAX_PDF_PAGES + 25

        def load_page(self, page_number: int) -> FakePage:
            loaded_pages.append(page_number)
            return FakePage()

        def close(self) -> None:
            pass

    fake_doc = FakeDoc()
    fake_fitz = SimpleNamespace(open=lambda **kwargs: fake_doc)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    assert source_images._extract_pdf_images(b"%PDF") == []
    assert loaded_pages == list(range(source_images._MAX_PDF_PAGES))


def test_find_browser_returns_none_when_no_browser_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # env override·표준 경로·PATH 어디에도 브라우저가 없으면 None. (env override 최우선과 PATH
    # 탐색은 test_html_to_pptx_find_browser_* 가 커버한다.)
    import os as _os
    import shutil

    from open_alm_api.domains.ppt_generator.design import html_to_pptx

    monkeypatch.delenv("OPEN_ALM_PPT_BROWSER_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(_os.path, "exists", lambda _p: False)

    assert html_to_pptx._find_browser() is None


def test_render_seminar_report_appends_merged_trip() -> None:
    # 출장 일정 병합: slide["trip"] 이 있으면 report 본문 하단에 '■ 출장 일정' + 표를 이어 붙인다.
    from open_alm_api.domains.ppt_generator.design import corporate_templates

    slide = {
        "pattern": "seminar_report",
        "page_role": "single",
        "meta": {},
        "sections": [{"no": "1", "topic": "행사", "points": ["핵심 내용"]}],
        "conclusion": ["소감"],
        "trip": {
            "days": [
                {"date": "5/27", "rows": [{"group": "이동", "content": ["인천→상해"], "attendees": "홍길동"}]}
            ]
        },
    }

    html = corporate_templates.render_seminar_report(slide)

    assert "출장 일정" in html
    assert "인천→상해" in html


def test_render_seminar_report_without_trip_has_no_trip_heading() -> None:
    from open_alm_api.domains.ppt_generator.design import corporate_templates

    slide = {
        "pattern": "seminar_report",
        "page_role": "single",
        "meta": {},
        "sections": [{"no": "1", "topic": "행사", "points": ["핵심 내용"]}],
        "conclusion": ["소감"],
    }

    html = corporate_templates.render_seminar_report(slide)

    assert "출장 일정" not in html


def test_seminar_remark_renders_ole_icon_when_ole_src_present() -> None:
    # 비고칸 항목에 ole_src(똑딱이 아이콘)가 있으면 아이콘 이미지 + 캡션을 렌더.
    slide = {
        "pattern": "seminar_report",
        "page_role": "single",
        "meta": {},
        "sections": [
            {
                "no": "1",
                "topic": "행사",
                "points": ["핵심"],
                "remark": {"items": [{"ole_src": "data:image/png;base64,IC", "caption": "첨부 일정표"}]},
            }
        ],
        "conclusion": ["소감"],
    }

    html = corporate_templates.render_seminar_report(slide)

    assert '<img src="data:image/png;base64,IC"' in html
    assert "첨부 일정표" in html


def test_render_schedule_images_returns_empty_without_libreoffice(monkeypatch) -> None:
    # LibreOffice 가 없으면 렌더 없이 빈 리스트(폴백) — 다른 파이프라인은 그대로 동작.
    monkeypatch.setattr(source_images, "_find_soffice", lambda: None)

    out = source_images.render_schedule_images([("a.xlsx", b"PK\x03\x04", "")])

    assert out == []


def test_render_schedule_images_skips_non_spreadsheet(monkeypatch) -> None:
    called = {"pdf": 0}

    def _boom(*_a, **_k):
        called["pdf"] += 1
        return None

    monkeypatch.setattr(source_images, "_find_soffice", lambda: "soffice")
    monkeypatch.setattr(source_images, "_office_to_pdf", _boom)

    out = source_images.render_schedule_images([("note.txt", b"hi", ""), ("pic.png", b"x", "")])

    assert out == []
    assert called["pdf"] == 0  # 스프레드시트가 아니면 변환을 시도하지 않는다.


def test_render_schedule_images_skips_workbook_when_sheet_surgery_fails(monkeypatch) -> None:
    # 회귀: eligible 시트를 알았지만 시트 서저리가 전부 실패하면, 전체 워크북을 통째로 변환하지
    # 않고 이 파일을 건너뛴다(무관한 시트가 '일정표'로 삽입되는 것을 방지).
    called = {"pdf": 0}

    def _boom(*_a, **_k):
        called["pdf"] += 1
        return None

    monkeypatch.setattr(source_images, "_find_soffice", lambda: "soffice")
    # archive 안전 게이트는 통과시켜(무효 zip 로 조기 종료되지 않게) 실제 서저리-실패 경로를 검증.
    monkeypatch.setattr(source_images, "_xlsx_archive_safe", lambda _d: True)
    monkeypatch.setattr(
        source_images,
        "_sheet_render_meta",
        lambda _d: [{"visible": True, "eligible": True, "tokens": set()}],
    )
    surgery = {"n": 0}

    def _surgery_fail(*_a, **_k):
        surgery["n"] += 1
        return None

    monkeypatch.setattr(source_images, "_xlsx_keep_only_sheet", _surgery_fail)
    monkeypatch.setattr(source_images, "_office_to_pdf", _boom)

    out = source_images.render_schedule_images([("plan.xlsx", b"PK\x03\x04", "")])

    assert out == []
    assert surgery["n"] >= 1  # 실제 서저리 시도(→ 실패) 경로를 탔다
    assert called["pdf"] == 0  # 전체 워크북 폴백 없음


def test_resolve_family_keeps_legacy_a4_resolvable() -> None:
    # 회귀(Codex): 카탈로그에서 뺀 레거시 A4 양식도 finalize/build 가 계속 해석해야 한다.
    # (안 그러면 옛 a4-exec-kpi 작업이 house 빌더로 잘못 빌드돼 깨짐.) 목록엔 안 보이되 resolve 됨.
    from open_alm_api.domains.ppt_generator.families import resolve_family

    for legacy in ("a4-exec-kpi", "a4-scorecard", "a4-minutes"):
        assert legacy not in FAMILIES  # 카탈로그(템플릿 목록)엔 노출 안 됨
        key, fam = resolve_family(legacy)
        assert key == legacy  # house 로 떨어지지 않고 그대로 해석
        assert fam["build_fn"].__name__ == "build_slide_a4"
        assert fam.get("hidden") is True
    # 알 수 없는 값은 여전히 기본 양식으로 보정.
    assert resolve_family("no-such-family")[0] == "corporate-house"


def test_render_schedule_images_skips_archive_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    # 회귀(Codex): 업로드 xlsx(zip)가 압축폭탄 한도를 넘으면 열기/시트 복사/변환 전에 건너뛴다.
    called = {"pdf": 0, "meta": 0}

    def _boom_pdf(*_a, **_k):
        called["pdf"] += 1
        return None

    def _boom_meta(*_a, **_k):
        called["meta"] += 1
        return []

    monkeypatch.setattr(source_images, "_find_soffice", lambda: "soffice")
    monkeypatch.setattr(source_images, "_office_to_pdf", _boom_pdf)
    monkeypatch.setattr(source_images, "_sheet_render_meta", _boom_meta)
    monkeypatch.setattr(source_images, "archive_exceeds_limits", lambda _infos: True)

    # 열 수 있는 정상 zip 이어야 archive 한도 검사까지 도달한다.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")

    out = source_images.render_schedule_images([("bomb.xlsx", buf.getvalue(), "")])

    assert out == []
    assert called["pdf"] == 0  # 변환 시도 안 함
    assert called["meta"] == 0  # 시트 메타 파싱(시트 복사)도 안 함 — 한도 검사에서 조기 차단


def test_create_job_stores_schedule_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_enqueue", lambda _task_name, _job_id: "task-1")
    stored: dict[str, bytes] = {}
    monkeypatch.setattr(
        service, "_put_object_bytes", lambda key, data, ct: stored.__setitem__(key, data)
    )
    db = _FakeDb()

    job = service.create_job(
        db,  # type: ignore[arg-type]
        SimpleNamespace(id="user-1", display_name="주승근"),
        SimpleNamespace(id="workspace-1"),
        content="주제",
        topic="주제",
        external_context=None,
        family="corporate-seminar",
        slide_range=None,
        language="Korean",
        tone="default",
        instructions=None,
        include_title_slide=True,
        include_toc=False,
        attached_files=[],
        failed_files=[],
        schedule_images=[
            {"data": b"PNG0", "ext": "png", "w": 100, "h": 60, "text": "표", "sheet": "s.xlsx"},
        ],
    )

    refs = (job.params or {}).get("schedule_images")
    assert refs and len(refs) == 1
    assert refs[0]["key"].endswith("/sched-images/0.png")
    assert refs[0]["sheet"] == "s.xlsx"
    # 바이트는 params(DB)가 아니라 MinIO 로만 저장한다.
    assert refs[0]["key"] in stored
    assert "data" not in refs[0]
