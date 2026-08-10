from __future__ import annotations

from ai_do_worker.tasks import mail


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_legacy_sync_task_rechecks_platform_gate(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(mail, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(mail, "mail_background_sync_enabled", lambda _db: False)
    monkeypatch.setattr(
        mail,
        "sync_account",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider sync must not run while Mail is disabled")
        ),
    )

    assert mail.sync_mail_account.run("account-1") == "cancelled:disabled"
    assert session.closed is True
