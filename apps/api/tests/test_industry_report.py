"""Tests for the industry-report aggregator domain.

Crawler tests are pure/offline (no network). Service tests run against an
in-memory SQLite session with just the two industry-report tables created.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.domains.industry_report import config_data as cfg
from ai_do_api.domains.industry_report import crawler, report_curator, service, storage
from ai_do_api.domains.industry_report.models import (
    IndustryReportAiEvaluation,
    IndustryReportFile,
    IndustryReportItem,
    IndustryReportRecommended,
    IndustryReportScrap,
)
from ai_do_api.domains.news.models import NewsFilterSetting

report_router = importlib.import_module("ai_do_api.domains.industry_report.router")
report_dispatch = importlib.import_module("ai_do_api.domains.industry_report.dispatch")


# ── Autojournal parser (offline) ─────────────────────────────
def test_parse_autojournal_bookcase_extracts_and_sorts_issues() -> None:
    html = (
        'a={"title":"오토저널 2026.03","bLink":"auto48-03","description":"봄호",'
        '"pages":50,"coverimg":"http://c/3.jpg"} '
        'b={"title":"오토저널 2026.02","bLink":"auto48-02","pages":40} '
        'dup={"title":"again","bLink":"auto48-03"}'
    )
    issues = crawler.parse_autojournal_bookcase(html)
    assert len(issues) == 2  # bLink dedup
    assert issues[0]["extra"]["issue_id"] == "auto48-03"  # newest first
    assert issues[0]["published_date"] == "2026-03"
    assert issues[0]["source"] == cfg.AUTOJOURNAL_SOURCE


def test_parse_autojournal_bookcase_handles_empty() -> None:
    assert crawler.parse_autojournal_bookcase("no objects here") == []


def test_parse_autojournal_issue_text_builds_toc_skipping_blanks() -> None:
    js = 'window.x=1; var textForPages =["제1장 서론입니다\\n본문", "", "제2장 본론입니다\\n상세"]; var y=2;'
    data = crawler.parse_autojournal_issue_text(js, "auto48-03")
    assert data is not None
    assert data["total_pages"] == 3
    assert [t["page"] for t in data["toc"]] == [1, 3]  # blank page 2 skipped


def test_parse_autojournal_issue_text_returns_none_without_marker() -> None:
    assert crawler.parse_autojournal_issue_text("no pages var", "x") is None


def test_known_autojournal_issues_count() -> None:
    issues = crawler.known_autojournal_issues(datetime(2026, 6, 8))
    assert len(issues) == 36
    assert all(i["extra"]["issue_id"].startswith("auto") for i in issues)


# ── KDI parsers (offline) ────────────────────────────────────
def test_parse_nara_list_dedups_and_dates() -> None:
    html = (
        '<a href="/publish/naraView.do?fcode=F1&cidx=123">자동차 산업 동향 분석 보고서</a>'
        '<a href="/publish/naraView.do?fcode=F1&cidx=123">중복 항목</a>'
    )
    items = crawler.parse_nara_list(html, "2026", "06")
    assert len(items) == 1
    assert items[0]["published_date"] == "2026년 06월호"
    assert items[0]["source"] == cfg.KDI_NARA_SOURCE


def test_parse_material_list_extracts_org_and_date() -> None:
    html = (
        "x materialView.do?num=999 <p>모빌리티 정책 자료</p>"
        "<span>한국교통연구원</span> <span>2026.05.01</span>"
    )
    items = crawler.parse_material_list(html, "모빌리티")
    assert len(items) == 1
    assert items[0]["org"] == "한국교통연구원"
    assert items[0]["published_date"] == "2026.05.01"
    assert items[0]["extra"]["num"] == "999"
    assert items[0]["keyword"] == "모빌리티"


def test_parse_domestic_list_extracts_id() -> None:
    html = "domesticView.do?ac=77 <strong>국내 연구 자료</strong> <span>KDI</span> <span>2026.04.02</span>"
    items = crawler.parse_domestic_list(html, "자동차")
    assert len(items) == 1
    assert items[0]["extra"]["ac"] == "77"
    assert items[0]["source"] == cfg.KDI_DOMESTIC_SOURCE


def test_is_kdi_url_validates_host_not_substring() -> None:
    assert crawler.is_kdi_url("https://eiec.kdi.re.kr/publish/naraView.do?cidx=1")
    assert crawler.is_kdi_url("http://eiec.kdi.re.kr/x")
    # SSRF guards: substring matches must NOT pass.
    assert not crawler.is_kdi_url("http://attacker.example/?x=eiec.kdi.re.kr")
    assert not crawler.is_kdi_url("https://eiec.kdi.re.kr.evil.com/x")
    assert not crawler.is_kdi_url("not a url")
    assert not crawler.is_kdi_url("")


def test_resolve_kdi_pdf_url_only_returns_kdi_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        text = '<a href="https://attacker.example/file.pdf">bad</a><a href="/publish/file.pdf">good</a>'

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url: str) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(crawler, "_kdi_client", lambda: FakeClient())

    assert (
        crawler.resolve_kdi_pdf_url("https://eiec.kdi.re.kr/publish/naraView.do?cidx=1")
        == "https://eiec.kdi.re.kr/publish/file.pdf"
    )


# ── KATECH crawler parsers (offline) ─────────────────────────
def test_parse_katech_list_skips_header_and_notice() -> None:
    html = """
    <table>
      <tr><th>no</th><th>title</th><th>date</th></tr>
      <tr data-post_key="pk-1"><td>공지</td><td>공지글</td><td>2026-01-01</td></tr>
      <tr data-post_key="pk-2"><td>167</td><td>대형 트럭 전동화</td><td>2026-06-08</td></tr>
      <tr><td>168</td><td>키 없는 행</td><td>2026-06-09</td></tr>
    </table>
    """
    items = crawler.parse_katech_list(html)
    assert len(items) == 1  # notice + keyless row dropped
    assert items[0]["post_key"] == "pk-2"
    assert items[0]["date"] == "2026-06-08"


def test_parse_katech_list_extracts_tls_valid_biz_board_rows() -> None:
    html = """
    <table class="tbl_list">
      <tr>
        <td class="col_num">465</td>
        <td class="col_tit">
          <a href="./?cid=28&uid=844&page=1&role=view">
            <strong class="tit">
              [한자연] (산업분석 Vol. 167) 대형 트럭 전동화의 서막을 여는 Semi
            </strong>
            <span class="new">N</span>
          </a>
        </td>
        <td class="col_date">2026-06-17</td>
        <td class="col_hit">17</td>
        <td class="col_file">
          <a href="/bb/down.html?bid=5&fid=1017&file=202606/a.pdf&force=1">
            (산업분석 Vol. 167) 대형 트럭 전동화의 서막을 여는 Semi.pdf
          </a>
        </td>
      </tr>
    </table>
    """
    items = crawler.parse_katech_list(html)
    assert items == [
        {
            "post_key": "biz:844",
            "no": "465",
            "title": "[한자연] (산업분석 Vol. 167) 대형 트럭 전동화의 서막을 여는 Semi",
            "date": "2026-06-17",
            "download_path": "/bb/down.html?bid=5&fid=1017&file=202606/a.pdf&force=1",
            "filename": "(산업분석 Vol. 167) 대형 트럭 전동화의 서막을 여는 Semi.pdf",
        }
    ]


def test_parse_katech_list_ignores_non_pdf_biz_downloads() -> None:
    html = """
    <table class="tbl_list">
      <tr>
        <td class="col_num">1</td>
        <td class="col_tit">
          <a href="./?cid=28&uid=1&role=view"><strong class="tit">통계 파일</strong></a>
        </td>
        <td class="col_date">2026-06-17</td>
        <td class="col_hit">17</td>
        <td class="col_file">
          <a href="/bb/down.html?bid=5&fid=1&file=202606/a.xlsx&force=1">a.xlsx</a>
        </td>
      </tr>
    </table>
    """
    items = crawler.parse_katech_list(html)
    assert items[0]["post_key"] == "biz:1"
    assert items[0]["download_path"] == ""
    assert items[0]["filename"] == ""


def test_parse_katech_detail_extracts_download_and_strips_size() -> None:
    html = (
        '<a class="download" href="/download/abc;jsessionid=XYZ">'
        "(산업분석 Vol. 167) 대형 트럭 전동화.pdf(1.2MB)</a>"
    )
    path, filename = crawler.parse_katech_detail(html)
    assert path == "/download/abc"
    assert filename == "(산업분석 Vol. 167) 대형 트럭 전동화.pdf"


def test_parse_katech_detail_returns_none_without_download() -> None:
    assert crawler.parse_katech_detail("<a href='/foo'>x</a>") == (None, None)


def test_crawlers_keep_tls_verification_enabled_by_default() -> None:
    source = inspect.getsource(crawler)
    assert "verify=False" not in source
    assert "verify=" not in source
    assert "KATECH_VERIFY_TLS" not in inspect.getsource(cfg)


def test_iter_katech_skips_oversized_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(
            self,
            *,
            text: str = "",
            chunks: list[bytes] | None = None,
        ) -> None:
            self.text = text
            self.headers: dict[str, str] = {}
            self.chunks = chunks or []
            self.chunks_read = 0

        def raise_for_status(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def iter_bytes(self, *, chunk_size: int):
            del chunk_size
            for chunk in self.chunks:
                self.chunks_read += 1
                yield chunk

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.stream_response = FakeResponse(chunks=[b"%PDF-", b"xxxx", b"unread"])
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, url: str, params: dict[str, str] | None = None) -> FakeResponse:
            if params == {"cid": cfg.KATECH_BOARD_CID, "page": "1"}:
                return FakeResponse(
                    text=(
                        '<table class="tbl_list"><tr><td class="col_num">1</td>'
                        '<td class="col_tit"><a href="./?cid=28&uid=1&role=view">'
                        '<strong class="tit">큰 PDF</strong></a></td>'
                        '<td class="col_date">2026-06-09</td><td class="col_hit">1</td>'
                        '<td class="col_file"><a href="/bb/down.html?file=pk-1.pdf">'
                        "r.pdf</a></td></tr></table>"
                    )
                )
            raise AssertionError(f"unexpected request: {url} {params}")

        def stream(self, method: str, url: str) -> FakeResponse:
            assert method == "GET"
            assert url.endswith("/bb/down.html?file=pk-1.pdf")
            return self.stream_response

    clients: list[FakeClient] = []

    def fake_client(*args, **kwargs) -> FakeClient:
        client = FakeClient(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(crawler.httpx, "Client", fake_client)

    existing: set[str] = set()
    reports = list(
        crawler.iter_katech(
            existing,
            max_pages=1,
            max_new=1,
            max_file_bytes=8,
        )
    )

    assert reports == []
    assert existing == set()
    assert clients[0].stream_response.chunks_read == 2


# ── Service (in-memory SQLite) ───────────────────────────────
def _session() -> Session:
    engine = create_engine("sqlite://")
    NewsFilterSetting.__table__.create(engine)
    IndustryReportFile.__table__.create(engine)
    IndustryReportItem.__table__.create(engine)
    IndustryReportRecommended.__table__.create(engine)
    IndustryReportScrap.__table__.create(engine)
    IndustryReportAiEvaluation.__table__.create(engine)
    return Session(engine)


def test_replace_items_dedups_by_url_and_replaces() -> None:
    db = _session()
    batch = [
        {
            "source": cfg.KDI_NARA_SOURCE,
            "title": "A",
            "url": "u1",
            "published_date": "2026년 06월호",
        },
        {"source": cfg.KDI_NARA_SOURCE, "title": "A-dup", "url": "u1"},
        {"source": cfg.KDI_NARA_SOURCE, "title": "B", "url": "u2"},
        {"source": cfg.KDI_NARA_SOURCE, "title": "skip", "url": ""},
    ]
    assert service.replace_items(db, cfg.KDI_NARA_SOURCE, batch) == 2

    rows, collected_at = service.list_items(db, cfg.KDI_NARA_SOURCE)
    assert {r.url for r in rows} == {"u1", "u2"}
    assert collected_at is not None

    # A second replace wipes the prior rows.
    assert (
        service.replace_items(
            db, cfg.KDI_NARA_SOURCE, [{"source": cfg.KDI_NARA_SOURCE, "title": "C", "url": "u3"}]
        )
        == 1
    )
    rows, _ = service.list_items(db, cfg.KDI_NARA_SOURCE)
    assert {r.url for r in rows} == {"u3"}


def test_replace_items_empty_batch_preserves_cache() -> None:
    db = _session()
    service.replace_items(
        db, cfg.KDI_NARA_SOURCE, [{"source": cfg.KDI_NARA_SOURCE, "title": "A", "url": "u1"}]
    )
    # An empty batch (transient upstream failure) must NOT wipe existing rows.
    assert service.replace_items(db, cfg.KDI_NARA_SOURCE, []) == 0
    rows, _ = service.list_items(db, cfg.KDI_NARA_SOURCE)
    assert {r.url for r in rows} == {"u1"}


def test_list_items_keyword_filter() -> None:
    db = _session()
    service.replace_items(
        db,
        cfg.KDI_MATERIAL_SOURCE,
        [
            {"source": cfg.KDI_MATERIAL_SOURCE, "title": "전기차 배터리 동향", "url": "a"},
            {"source": cfg.KDI_MATERIAL_SOURCE, "title": "조선업 수출", "url": "b"},
        ],
    )
    rows, _ = service.list_items(db, cfg.KDI_MATERIAL_SOURCE, keyword="배터리")
    assert [r.url for r in rows] == ["a"]


def test_existing_source_keys_tracks_crawled_only() -> None:
    db = _session()
    db.add(
        IndustryReportFile(
            id="u1",
            company="KATECH",
            title="manual",
            filename="m.pdf",
            storage_key="k/u1/m.pdf",
            content_type="application/pdf",
            size_bytes=1,
            source="upload",
            source_key=None,
        )
    )
    db.add(
        IndustryReportFile(
            id="c1",
            company="KATECH",
            title="crawled",
            filename="c.pdf",
            storage_key="k/c1/c.pdf",
            content_type="application/pdf",
            size_bytes=1,
            source="katech",
            source_key="pk-99",
        )
    )
    db.commit()
    assert service.existing_source_keys(db, "KATECH") == {"pk-99"}


def test_collect_katech_persists_each_file_before_next_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    stored: list[str] = []
    observed: dict[str, object] = {}

    def item(source_key: str) -> dict[str, object]:
        return {
            "source_key": source_key,
            "title": f"report {source_key}",
            "filename": f"{source_key}.pdf",
            "data": b"%PDF-1.7\n",
            "content_type": "application/pdf",
            "published_date": "2026-06-09",
        }

    def fake_iter(existing_keys: set[str], **kwargs):
        observed["existing_keys"] = set(existing_keys)
        observed["kwargs"] = kwargs
        yield item("pk-1")
        assert stored == ["pk-1"]
        yield item("pk-2")

    def fake_create_crawled_file(_db: Session, **kwargs):
        stored.append(str(kwargs["source_key"]))
        return SimpleNamespace(id=kwargs["source_key"])

    monkeypatch.setattr(service.crawler, "iter_katech", fake_iter)
    monkeypatch.setattr(service, "create_crawled_file", fake_create_crawled_file)

    assert service.collect_katech(db, max_pages=2, max_new=7, max_file_bytes=123) == 2
    assert stored == ["pk-1", "pk-2"]
    assert observed["existing_keys"] == set()
    assert observed["kwargs"] == {
        "max_pages": 2,
        "max_new": 7,
        "max_file_bytes": 123,
    }


def test_collect_katech_treats_unique_race_as_already_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()

    def fake_iter(existing_keys: set[str], **_kwargs):
        assert existing_keys == set()
        yield {
            "source_key": "biz:844",
            "title": "report",
            "filename": "report.pdf",
            "data": b"%PDF-1.7\n",
            "content_type": "application/pdf",
            "published_date": "2026-06-17",
        }

    def fake_create_crawled_file(_db: Session, **_kwargs):
        raise IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(service.crawler, "iter_katech", fake_iter)
    monkeypatch.setattr(service, "create_crawled_file", fake_create_crawled_file)

    assert service.collect_katech(db, max_pages=1, max_new=1, max_file_bytes=123) == 0


def test_list_companies_counts_files() -> None:
    db = _session()
    db.add(
        IndustryReportFile(
            id="f1",
            company="KATECH",
            title="t",
            filename="t.pdf",
            storage_key="industry-reports/f1/t.pdf",
            content_type="application/pdf",
            size_bytes=10,
        )
    )
    db.commit()
    companies = {c["code"]: c for c in service.list_companies(db)}
    # 자동 수집(KATECH)만 노출한다. 메이커 버킷은 제거됨.
    assert set(companies) == {"KATECH"}
    assert companies["KATECH"]["file_count"] == 1
    assert companies["KATECH"]["label"] == cfg.COMPANY_MAP["KATECH"]


def test_recommended_and_scraps_are_separate_user_scoped_lists() -> None:
    db = _session()
    recommended = service.recommend_report(
        db,
        kind=cfg.KDI_NARA_SOURCE,
        title="추천 리포트",
        org="KDI",
        published_date="2026년 06월호",
        url="https://eiec.kdi.re.kr/a",
        file_id=None,
        company="",
        user_id="admin",
    )
    first_scrap = service.scrap_report(
        db,
        kind=cfg.KDI_NARA_SOURCE,
        title="스크랩 리포트",
        org="KDI",
        published_date="2026년 06월호",
        url="https://eiec.kdi.re.kr/a",
        file_id=None,
        company="",
        user_id="user-1",
    )
    service.scrap_report(
        db,
        kind=cfg.KDI_NARA_SOURCE,
        title="스크랩 리포트",
        org="KDI",
        published_date="2026년 06월호",
        url="https://eiec.kdi.re.kr/a",
        file_id=None,
        company="",
        user_id="user-2",
    )

    assert service.recommended_refs(db) == {"https://eiec.kdi.re.kr/a"}
    assert [r.id for r in service.list_recommended_reports(db)] == [recommended.id]
    assert [r.id for r in service.list_scrap_reports(db, user_id="user-1")] == [first_scrap.id]
    assert not service.delete_scrap_report(db, first_scrap.id, user_id="user-2")
    assert service.delete_scrap_report(db, first_scrap.id, user_id="user-1")
    assert service.list_scrap_reports(db, user_id="user-1") == []


def test_report_curate_records_non_relevant_verdicts_to_avoid_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    service.replace_items(
        db,
        cfg.KDI_NARA_SOURCE,
        [
            {
                "source": cfg.KDI_NARA_SOURCE,
                "title": "일반 경제 동향",
                "url": "https://eiec.kdi.re.kr/neutral",
                "published_date": "2026년 06월호",
            }
        ],
    )
    calls: list[str] = []

    def fake_execute_llm(workload_id, context, _db, **kwargs):
        del workload_id, context
        calls.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(
            completion=SimpleNamespace(
                text='[{"index": 0, "relevant": false, "reason": "", "detail": ""}]'
            )
        )

    monkeypatch.setattr(report_curator, "execute_llm", fake_execute_llm)

    first = report_curator.curate_recent(db, limit=1)
    second = report_curator.curate_recent(db, limit=1)

    assert first["evaluated"] == 1
    assert first["saved"] == 0
    assert second["evaluated"] == 0
    assert len(calls) == 1
    assert service.ai_evaluated_report_refs(db) == {"https://eiec.kdi.re.kr/neutral"}
    assert service.list_recommended_reports(db, origin="ai") == []


# ── API/dispatch contracts ──────────────────────────────────
def test_dispatch_collect_all_passes_force_kwarg(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeClient:
        def send_task(self, name: str, **kwargs):
            calls.append({"name": name, **kwargs})
            return SimpleNamespace(id="task-1")

    monkeypatch.setattr(report_dispatch, "_news_app_enabled", lambda: True)
    monkeypatch.setattr(report_dispatch, "get_celery_client", lambda: FakeClient())

    assert report_dispatch.dispatch_collect_all(force=True) == "task-1"
    assert calls == [
        {
            "name": report_dispatch.INDUSTRY_REPORT_COLLECT_TASK_NAME,
            "kwargs": {"force": True},
            "queue": report_dispatch.INDUSTRY_REPORT_COLLECT_QUEUE,
        }
    ]


def test_dispatch_collect_all_does_not_publish_while_app_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(report_dispatch, "_news_app_enabled", lambda: False)
    monkeypatch.setattr(
        report_dispatch,
        "get_celery_client",
        lambda: (_ for _ in ()).throw(AssertionError("broker client must not be created")),
    )

    assert report_dispatch.dispatch_collect_all(force=True) is None


def test_background_curation_rechecks_platform_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSessionContext:
        def __enter__(self):
            return "curation-db"

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

    monkeypatch.setattr(report_router, "get_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(report_router, "is_platform_app_enabled", lambda *_args: False)
    monkeypatch.setattr(
        report_router.report_curator,
        "curate_recent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("LLM curation must not run while News is disabled")
        ),
    )

    report_router._run_curation_background(None)


def test_trigger_fetch_enqueues_worker_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, bool]] = []

    def fake_dispatch(*, force: bool = False) -> str:
        calls.append({"force": force})
        return "task-1"

    monkeypatch.setattr(report_router, "dispatch_collect_all", fake_dispatch)
    response = report_router.trigger_fetch(_admin=object())  # type: ignore[arg-type]

    assert response.status == "success"
    assert calls == [{"force": True}]


def test_download_file_serves_non_pdf_as_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    db.add(
        IndustryReportFile(
            id="html-1",
            company="KATECH",
            title="Legacy HTML",
            filename="legacy.html",
            storage_key="industry-reports/html-1/legacy.html",
            content_type="text/html",
            size_bytes=20,
        )
    )
    db.commit()
    monkeypatch.setattr(
        report_router.storage,
        "open_report_stream",
        lambda _storage_key: iter([b"<script>alert(1)</script>"]),
    )

    response = report_router.download_file("html-1", db=db)

    assert response.media_type == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_pdf_upload_validation_requires_pdf_signature() -> None:
    assert storage.is_pdf_upload(
        filename="report.pdf",
        content_type="application/octet-stream",
        data=b"%PDF-1.7\n...",
    )
    assert not storage.is_pdf_upload(
        filename="report.pdf",
        content_type="application/pdf",
        data=b"<html></html>",
    )


def test_upload_file_rejects_fake_pdf_bytes() -> None:
    class FakeUpload:
        filename = "legacy.pdf"
        content_type = "application/pdf"
        read_called = False
        chunks = [b"<html></html>"]

        async def read(self, _size: int = -1) -> bytes:
            self.read_called = True
            if not self.chunks:
                return b""
            return self.chunks.pop(0)

    upload = FakeUpload()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            report_router.upload_file(
                "KATECH",
                file=upload,  # type: ignore[arg-type]
                title="",
                published_date="",
                db=_session(),
                admin=SimpleNamespace(id="admin"),
            )
        )

    assert exc.value.status_code == 415
    assert upload.read_called


def test_upload_file_rejects_oversized_pdf_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUpload:
        filename = "large.pdf"
        content_type = "application/pdf"

        def __init__(self) -> None:
            self.chunks = [b"%PDF-", b"too-large"]

        async def read(self, _size: int = -1) -> bytes:
            if not self.chunks:
                return b""
            return self.chunks.pop(0)

    monkeypatch.setattr(
        report_router,
        "get_settings",
        lambda: SimpleNamespace(industry_report_upload_max_bytes=8),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            report_router.upload_file(
                "KATECH",
                file=FakeUpload(),  # type: ignore[arg-type]
                title="",
                published_date="",
                db=_session(),
                admin=SimpleNamespace(id="admin"),
            )
        )

    assert exc.value.status_code == 413
