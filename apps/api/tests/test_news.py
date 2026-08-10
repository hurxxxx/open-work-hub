"""Tests for the news aggregator domain.

Crawler tests are pure/offline (no network). Service tests run against an
in-memory SQLite session with just the two news tables created.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import importlib

from open_alm_api.domains.industry_report import service as report_service
from open_alm_api.domains.industry_report.models import (
    IndustryReportAiEvaluation,
    IndustryReportRecommended,
)
from open_alm_api.domains.news import config_data as cfg
from open_alm_api.domains.news import ai_curator, crawler, service
from open_alm_api.domains.news.models import (
    NewsArticle,
    NewsArticleScrap,
    NewsFilterSetting,
    NewsRecommendedArticle,
)
from open_alm_api.domains.news.schemas import NewsSnapshotRequest

# Import the router module explicitly so API architecture rules stay focused on
# the composition registry's router import.
news_router = importlib.import_module("open_alm_api.domains.news.router")
news_dispatch = importlib.import_module("open_alm_api.domains.news.dispatch")


# ── Crawler / parser (offline) ───────────────────────────────
def test_parse_article_html_uses_known_selector_and_summary() -> None:
    body = "이것은 첫 번째 문장으로 충분히 길게 작성된 본문입니다. 두 번째 문장도 동일하게 길게 작성되었습니다. 세 번째 문장."
    markup = f'<html><body><div id="dic_area">{body}</div></body></html>'
    out = crawler.parse_article_html(markup)
    assert body.split(".")[0] in out["full_text"]
    assert out["summary"]  # first 1-2 sentences extracted


def test_parse_article_html_falls_back_to_largest_paragraph() -> None:
    long_text = "문단 본문 " * 40
    markup = f"<html><body><section><p>{long_text}</p></section><p>짧음</p></body></html>"
    out = crawler.parse_article_html(markup)
    assert "문단 본문" in out["full_text"]


def test_parse_article_html_filters_small_and_logo_images() -> None:
    markup = (
        '<html><body><div id="dic_area">'
        + ("본문 문장입니다. " * 10)
        + '<img src="http://x/logo.png" width="800">'  # logo → skip
        + '<img src="http://x/tiny.jpg" width="100">'  # too small → skip
        + '<img src="http://x/photo.jpg" width="600">'  # keep
        + "</div></body></html>"
    )
    out = crawler.parse_article_html(markup)
    assert [img["url"] for img in out["images"]] == ["http://x/photo.jpg"]


def test_parse_rss_extracts_title_and_link() -> None:
    rss = (
        b"<rss><channel>"
        b"<item><title>Hello World Headline</title><link>http://a/1</link></item>"
        b"<item><title>x</title><link>http://a/2</link></item>"  # too short title → skip
        b"</channel></rss>"
    )
    assert crawler.parse_rss(rss) == [{"title": "Hello World Headline", "url": "http://a/1"}]


def test_strip_html_and_unescape() -> None:
    assert crawler.strip_html("<b>현대차</b> &amp; 기아") == "현대차 & 기아"


def test_extract_source_maps_known_domains_else_raw() -> None:
    assert crawler.extract_source("https://www.chosun.com/a/b") == "조선일보"
    assert crawler.extract_source("https://example.org/x") == "example.org"
    assert crawler.extract_source("not-a-url") == "알 수 없음"


def test_parse_date_valid_and_fallback() -> None:
    assert crawler.parse_date("Mon, 08 Jun 2026 09:30:00 +0900") == "2026-06-08"
    assert crawler.parse_date("garbage") == datetime.now().strftime("%Y-%m-%d")


def test_expand_car_keywords_brand_variants() -> None:
    assert set(crawler.expand_car_keywords("현대차")) == {"현대차", "현대자동차", "Hyundai"}
    assert crawler.expand_car_keywords("관심없는키워드") == ["관심없는키워드"]


# ── Service (in-memory SQLite) ───────────────────────────────
@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://")
    NewsArticle.__table__.create(bind=engine)
    NewsRecommendedArticle.__table__.create(bind=engine)
    NewsArticleScrap.__table__.create(bind=engine)
    NewsFilterSetting.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session


_TODAY = datetime.now().strftime("%Y-%m-%d")
_YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _article(url: str, *, title: str = "t", date: str = _TODAY) -> dict:
    return {
        "channel": "keyword",
        "keyword": "전기차",
        "source": "조선일보",
        "date": date,
        "title": title,
        "summary": "",
        "original_url": url,
    }


def test_upsert_articles_merges_and_dedupes(db: Session) -> None:
    first = service.upsert_articles(
        db, "keyword", [_article("http://a/1"), _article("http://a/1"), _article("http://a/2")]
    )
    assert first == 2  # duplicate url dropped

    # Re-collecting MERGES (does not wipe the channel): a/1, a/2 stay, a/3 added.
    second = service.upsert_articles(db, "keyword", [_article("http://a/3")])
    assert second == 1
    rows, _ = service.list_articles(db, "keyword")
    assert {r.original_url for r in rows} == {"http://a/1", "http://a/2", "http://a/3"}


def test_upsert_prunes_rows_older_than_window(db: Session) -> None:
    # Seed an aged-out row directly, then collect a fresh batch.
    db.add(
        NewsArticle(
            id="old-row",
            channel="keyword",
            title="old",
            original_url="http://a/old",
            published_date="2000-01-01",
            collected_at=datetime(2000, 1, 1),
            created_at=datetime(2000, 1, 1),
        )
    )
    db.commit()
    service.upsert_articles(db, "keyword", [_article("http://a/fresh")])
    rows, _ = service.list_articles(db, "keyword")
    assert {r.original_url for r in rows} == {"http://a/fresh"}  # aged row pruned


def test_upsert_preserves_cached_full_text(db: Session) -> None:
    service.upsert_articles(db, "keyword", [_article("http://a/1", title="orig")])
    row = next(r for r in service.list_articles(db, "keyword")[0])
    row.full_text = "cached body"
    db.add(row)
    db.commit()

    service.upsert_articles(db, "keyword", [_article("http://a/1", title="updated")])
    rows, _ = service.list_articles(db, "keyword")
    updated = next(r for r in rows if r.original_url == "http://a/1")
    assert updated.title == "updated"  # metadata refreshed
    assert updated.full_text == "cached body"  # cached body preserved


def test_list_articles_orders_by_published_date_desc(db: Session) -> None:
    service.upsert_articles(
        db,
        "car",
        [
            {**_article("http://a/old", date=_YESTERDAY), "channel": "car"},
            {**_article("http://a/new", date=_TODAY), "channel": "car"},
        ],
    )
    rows, collected_at = service.list_articles(db, "car")
    assert [r.original_url for r in rows] == ["http://a/new", "http://a/old"]
    assert collected_at is not None


def test_run_full_collection_isolates_channel_failures(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service.crawler, "collect_keyword", lambda *a, **k: [_article("http://a/kw")]
    )
    monkeypatch.setattr(
        service.crawler,
        "collect_car",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rate limit")),
    )
    monkeypatch.setattr(service.crawler, "collect_front", lambda *a, **k: [])
    counts = service.run_full_collection(db, "id", "secret")
    assert counts["keyword"] == 1  # succeeded
    assert counts["car"] == -1  # failed but did not abort the others
    assert counts["front"] == 0


def test_filter_settings_seed_defaults_then_update(db: Session) -> None:
    settings = service.get_filter_settings(db)
    assert settings["keyword_filter"] == list(cfg.SEARCH_KEYWORDS)
    assert settings["keyword_ui_filters"] == list(cfg.DEFAULT_KEYWORD_UI_FILTERS)

    updated = service.update_filter_settings(
        db,
        keyword_filter=None,  # untouched
        car_filter=["전기차", "  ", "배터리"],  # cleaned
        keyword_ui_filters=["신규필터"],
    )
    assert updated["keyword_filter"] == list(cfg.SEARCH_KEYWORDS)
    assert updated["car_filter"] == ["전기차", "배터리"]
    assert updated["keyword_ui_filters"] == ["신규필터"]


def test_get_article_detail_caches_crawl_result(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.upsert_articles(db, "keyword", [_article("http://a/1")])
    calls = {"n": 0}

    def fake_crawl(url: str) -> dict:
        calls["n"] += 1
        return {"full_text": "본문 내용", "summary": "요약", "images": [], "tables": []}

    monkeypatch.setattr(service.crawler, "crawl_article", fake_crawl)

    first = service.get_article_detail(db, "http://a/1")
    assert first["full_text"] == "본문 내용"
    # Second call serves from the cached row — no re-crawl.
    second = service.get_article_detail(db, "http://a/1")
    assert second["full_text"] == "본문 내용"
    assert calls["n"] == 1


def test_get_article_detail_falls_back_to_recommendation_snapshot(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_crawl(url: str) -> dict:
        raise AssertionError(f"unexpected crawl for {url}")

    monkeypatch.setattr(service.crawler, "crawl_article", fail_crawl)
    service.recommend_article(
        db,
        channel="keyword",
        keyword="전기차",
        source="조선일보",
        title="추천 기사",
        summary="추천 요약",
        original_url="http://a/recommended",
        published_date=_TODAY,
        user_id="admin",
    )

    detail = service.get_article_detail(db, "http://a/recommended")

    assert detail["summary"] == "추천 요약"
    assert detail["full_text"] == ""


def test_news_scraps_are_user_scoped_and_support_detail_fallback(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_crawl(url: str) -> dict:
        raise AssertionError(f"unexpected crawl for {url}")

    monkeypatch.setattr(service.crawler, "crawl_article", fail_crawl)
    first = service.scrap_article(
        db,
        channel="keyword",
        keyword="전기차",
        source="조선일보",
        title="스크랩 기사",
        summary="스크랩 요약",
        original_url="http://a/scrap",
        published_date=_TODAY,
        user_id="user-1",
    )
    second = service.scrap_article(
        db,
        channel="keyword",
        keyword="전기차",
        source="조선일보",
        title="다른 사용자 스크랩",
        summary="다른 사용자 요약",
        original_url="http://a/scrap",
        published_date=_TODAY,
        user_id="user-2",
    )

    assert first.id != second.id
    assert [row.id for row in service.list_scraps(db, user_id="user-1")] == [first.id]
    assert (
        service.get_article_detail(
            db,
            "http://a/scrap",
            user_id="user-1",
        )["summary"]
        == "스크랩 요약"
    )
    assert (
        service.get_article_detail(
            db,
            "http://a/scrap",
            user_id="user-3",
        )
        == {}
    )
    assert service.delete_scrap(db, first.id, user_id="user-2") is False
    assert service.delete_scrap(db, first.id, user_id="user-1") is True
    assert service.list_scraps(db, user_id="user-1") == []


def test_curate_recent_keeps_articles_pending_on_invalid_llm_response(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.upsert_articles(db, "keyword", [_article("http://a/ai", title="AI 후보 기사")])

    def fake_execute_llm(*_args, **_kwargs):
        return SimpleNamespace(completion=SimpleNamespace(text="not json"))

    monkeypatch.setattr(ai_curator, "execute_llm", fake_execute_llm)

    result = ai_curator.curate_recent(db, limit=1)
    row = service.list_articles(db, "keyword")[0][0]

    assert result["evaluated"] == 0
    assert result["saved"] == 0
    assert result["error"] == "invalid_verdicts"
    assert row.ai_evaluated is False


def test_profile_change_resets_ai_curation_state_across_news_and_reports(
    db: Session,
) -> None:
    bind = db.get_bind()
    IndustryReportRecommended.__table__.create(bind=bind, checkfirst=True)
    IndustryReportAiEvaluation.__table__.create(bind=bind, checkfirst=True)
    service.upsert_articles(db, "keyword", [_article("http://a/profile", title="프로필 변경 후보")])
    article = service.list_articles(db, "keyword")[0][0]
    article.ai_evaluated = True

    settings = service.get_or_create_filter_settings(db)
    settings.ai_profile = "old profile"
    settings.ai_curated_at = datetime(2026, 6, 16)
    db.add_all([article, settings])
    db.commit()

    manual_news = service.recommend_article(
        db,
        channel="keyword",
        keyword="전기차",
        source="조선일보",
        title="수동 뉴스",
        summary="",
        original_url="http://a/manual",
        published_date=_TODAY,
        user_id="admin",
        origin="manual",
    )
    service.recommend_article(
        db,
        channel="keyword",
        keyword="전기차",
        source="조선일보",
        title="AI 뉴스",
        summary="",
        original_url="http://a/ai-old",
        published_date=_TODAY,
        user_id=None,
        origin="ai",
    )
    manual_report = report_service.recommend_report(
        db,
        kind="kdi_nara",
        title="수동 리포트",
        org="KDI",
        published_date="2026년 06월호",
        url="https://eiec.kdi.re.kr/manual",
        file_id=None,
        company="",
        user_id="admin",
        origin="manual",
    )
    report_service.recommend_report(
        db,
        kind="kdi_nara",
        title="AI 리포트",
        org="KDI",
        published_date="2026년 06월호",
        url="https://eiec.kdi.re.kr/ai-old",
        file_id=None,
        company="",
        user_id=None,
        origin="ai",
    )
    report_service.record_ai_report_evaluation(
        db,
        kind="kdi_nara",
        url="https://eiec.kdi.re.kr/rejected",
        file_id=None,
        relevant=False,
    )

    payload = ai_curator.update_ai_profile(db, ai_profile="new profile")

    assert payload["ai_profile"] == "new profile"
    assert payload["ai_curated_at"] is None
    assert service.list_articles(db, "keyword")[0][0].ai_evaluated is False
    assert [r.id for r in service.list_recommended(db, origin="manual")] == [manual_news.id]
    assert service.list_recommended(db, origin="ai") == []
    assert [r.id for r in report_service.list_recommended_reports(db, origin="manual")] == [
        manual_report.id
    ]
    assert report_service.list_recommended_reports(db, origin="ai") == []
    assert report_service.ai_evaluated_report_refs(db) == set()


def test_get_article_detail_rejects_uncached_url_without_crawling(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_crawl(url: str) -> dict:
        raise AssertionError(f"unexpected crawl for {url}")

    monkeypatch.setattr(service.crawler, "crawl_article", fail_crawl)

    assert service.get_article_detail(db, "http://169.254.169.254/latest") == {}


# ── Router guards ────────────────────────────────────────────
def test_list_channel_rejects_unknown_channel(db: Session) -> None:
    with pytest.raises(HTTPException):
        news_router.list_channel("sports", db=db)


def test_require_admin_blocks_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_router, "is_platform_admin_user", lambda *_a, **_k: False)
    with pytest.raises(HTTPException):
        news_router._require_admin(current_user=object(), db=None)  # type: ignore[arg-type]


def test_require_admin_allows_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(news_router, "is_platform_admin_user", lambda *_a, **_k: True)
    assert news_router._require_admin(current_user=sentinel, db=None) is sentinel  # type: ignore[arg-type]


def test_get_article_returns_not_found_for_uncached_url(db: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        news_router.get_article(
            "http://example.test/missing",
            db=db,
            current_user=type("User", (), {"id": "user-1"})(),
        )
    assert exc.value.status_code == 404


def test_trigger_fetch_enqueues_worker_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, bool]] = []

    def fake_dispatch(*, force: bool = False) -> str:
        calls.append({"force": force})
        return "task-1"

    monkeypatch.setattr(news_router, "dispatch_collect_all", fake_dispatch)
    response = news_router.trigger_fetch(_admin=object())  # type: ignore[arg-type]

    assert response.status == "success"
    assert calls == [{"force": True}]


def test_scrap_router_restores_user_scoped_save_list_and_delete(db: Session) -> None:
    user_1 = type("User", (), {"id": "user-1"})()
    user_2 = type("User", (), {"id": "user-2"})()
    payload = NewsSnapshotRequest(
        channel="keyword",
        keyword="전기차",
        source="조선일보",
        date=_TODAY,
        title="스크랩 기사",
        summary="스크랩 요약",
        original_url="http://a/router-scrap",
    )

    saved = news_router.scrap_news(payload, db=db, current_user=user_1)

    assert saved.channel == "keyword"
    assert saved.original_url == "http://a/router-scrap"
    assert [
        row.id for row in news_router.list_news_scraps(db=db, current_user=user_1).articles
    ] == [saved.id]
    assert news_router.list_news_scraps(db=db, current_user=user_2).articles == []

    with pytest.raises(HTTPException) as exc:
        news_router.delete_news_scrap(saved.id, db=db, current_user=user_2)
    assert exc.value.status_code == 404

    assert news_router.delete_news_scrap(saved.id, db=db, current_user=user_1) == {
        "status": "deleted"
    }
    assert news_router.list_news_scraps(db=db, current_user=user_1).articles == []


def test_list_ai_recommended_enqueues_and_runs_background_curation(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeSessionContext:
        def __enter__(self):
            return "curation-db"

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

    curation_calls: list[dict[str, object | None]] = []
    list_calls: list[dict[str, object]] = []

    def fake_curate_recent(
        current_db: object, *, actor_user_id: str | None = None
    ) -> dict[str, int]:
        curation_calls.append({"db": current_db, "actor_user_id": actor_user_id})
        return {"evaluated": 1, "saved": 1}

    def fake_list_recommended(current_db: Session, *, origin: str):
        list_calls.append({"db": current_db, "origin": origin})
        return []

    monkeypatch.setattr(
        news_router.ai_curator, "needs_curation", lambda current_db: current_db is db
    )
    monkeypatch.setattr(news_router.ai_curator, "curate_recent", fake_curate_recent)
    monkeypatch.setattr(news_router.service, "list_recommended", fake_list_recommended)
    monkeypatch.setattr(news_router, "get_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(news_router, "is_platform_app_enabled", lambda *_args: True)

    background = BackgroundTasks()
    response = news_router.list_ai_recommended(background, db=db, _user=object())  # type: ignore[arg-type]

    assert response.articles == []
    assert list_calls == [{"db": db, "origin": "ai"}]
    assert len(background.tasks) == 1

    task = background.tasks[0]
    assert task.func is news_router._run_curation_background
    task.func(*task.args, **task.kwargs)

    assert curation_calls == [{"db": "curation-db", "actor_user_id": None}]


def test_dispatch_collect_all_passes_force_kwarg(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeClient:
        def send_task(self, name: str, **kwargs):
            calls.append({"name": name, **kwargs})
            return type("AsyncResult", (), {"id": "task-1"})()

    monkeypatch.setattr(news_dispatch, "_news_app_enabled", lambda: True)
    monkeypatch.setattr(news_dispatch, "get_celery_client", lambda: FakeClient())

    assert news_dispatch.dispatch_collect_all(force=True) == "task-1"
    assert calls == [
        {
            "name": news_dispatch.NEWS_COLLECT_TASK_NAME,
            "kwargs": {"force": True},
            "queue": news_dispatch.NEWS_COLLECT_QUEUE,
        }
    ]


def test_dispatch_collect_all_does_not_publish_while_app_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(news_dispatch, "_news_app_enabled", lambda: False)
    monkeypatch.setattr(
        news_dispatch,
        "get_celery_client",
        lambda: (_ for _ in ()).throw(AssertionError("broker client must not be created")),
    )

    assert news_dispatch.dispatch_collect_all(force=True) is None


def test_background_curation_rechecks_platform_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSessionContext:
        def __enter__(self):
            return "curation-db"

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

    monkeypatch.setattr(news_router, "get_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(news_router, "is_platform_app_enabled", lambda *_args: False)
    monkeypatch.setattr(
        news_router.ai_curator,
        "curate_recent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("LLM curation must not run while News is disabled")
        ),
    )

    news_router._run_curation_background(None)
