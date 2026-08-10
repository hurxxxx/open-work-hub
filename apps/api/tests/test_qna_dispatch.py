from __future__ import annotations

from open_alm_api.domains.qna import dispatch


def test_qna_dispatch_stops_before_broker_when_platform_app_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(dispatch, "_qna_app_enabled", lambda: False)

    def fail_client():
        raise AssertionError("disabled Q&A dispatch must not publish to the broker")

    monkeypatch.setattr(dispatch, "_get_celery_client", fail_client)

    assert dispatch.dispatch_board_sync() is None
