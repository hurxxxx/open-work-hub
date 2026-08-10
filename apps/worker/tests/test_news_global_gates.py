from __future__ import annotations

from types import SimpleNamespace

from ai_do_worker.tasks import industry_report, news_aggregator


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        raise AssertionError("disabled task must not need rollback")


def test_forced_news_collection_rechecks_platform_gate(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(
        news_aggregator,
        "get_settings",
        lambda: SimpleNamespace(news_crawl_enabled=False),
    )
    monkeypatch.setattr(news_aggregator, "_db_session", lambda: session)
    monkeypatch.setattr(news_aggregator, "is_platform_app_enabled", lambda *_args: False)
    monkeypatch.setattr(
        news_aggregator.service,
        "run_full_collection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("external news collection must not run")
        ),
    )

    assert news_aggregator.collect_all.run(force=True) == "cancelled:app-disabled"
    assert session.closed is True


def test_forced_industry_report_collection_rechecks_platform_gate(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(
        industry_report,
        "get_settings",
        lambda: SimpleNamespace(industry_report_crawl_enabled=False),
    )
    monkeypatch.setattr(industry_report, "_db_session", lambda: session)
    monkeypatch.setattr(industry_report, "is_platform_app_enabled", lambda *_args: False)
    monkeypatch.setattr(
        industry_report.service,
        "run_full_collection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("external report collection must not run")
        ),
    )

    assert industry_report.collect_all.run(force=True) == "cancelled:app-disabled"
    assert session.closed is True
