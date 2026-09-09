from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from dev_accounts import auth_headers, dev_login

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.mail import clients as mail_clients
from open_work_hub_api.domains.mail.clients import (
    FetchedAttachment,
    FetchedMessage,
    MailboxInfo,
    MailboxSyncBatch,
    MailConnectionSettings,
)
from open_work_hub_api.domains.mail.models import (
    MailAccount,
    MailAttachment,
    MailDraft,
    MailMailbox,
    MailMessage,
    MailMessageBody,
    MailSyncJob,
    MailSyncState,
)
from open_work_hub_api.domains.mail import service as mail_service


class FakeMailClient:
    sent: list[dict]

    def __init__(self) -> None:
        self.sent = []

    def test_incoming(self, settings: MailConnectionSettings) -> None:
        assert settings.incoming_password == "mail-password"

    def test_smtp(self, settings: MailConnectionSettings) -> None:
        assert settings.smtp_password == "mail-password"

    def fetch_recent(
        self,
        settings: MailConnectionSettings,
        *,
        folder: str = "INBOX",
        limit: int = 50,
    ) -> list[FetchedMessage]:
        assert settings.incoming_password == "mail-password"
        assert folder == "INBOX"
        assert limit >= 1
        return [
            FetchedMessage(
                provider_uid="uid-001",
                provider_message_id="<message-001@example.test>",
                thread_key="<message-001@example.test>",
                subject="Quarterly report",
                from_text="sender@example.test",
                to_text="admin@example.test",
                cc_text="",
                text_body="Please review the quarterly report by Friday.",
                html_body="",
                snippet="Please review the quarterly report by Friday.",
                received_at=datetime(2026, 5, 12, 9, 0, 0),
                sent_at=datetime(2026, 5, 12, 9, 0, 0),
                is_read=False,
                attachments=(
                    FetchedAttachment(
                        filename="report.pdf",
                        content_type="application/pdf",
                        size_bytes=128,
                    ),
                ),
                remote_identity="imap:10:uid-001",
                remote_flags={"provider": "imap", "flags": []},
            )
        ]

    def sync_mailbox(
        self,
        settings: MailConnectionSettings,
        *,
        mailbox: str = "INBOX",
        cursor: dict | None = None,
        initial_limit: int = 50,
    ) -> MailboxSyncBatch:
        assert settings.incoming_password == "mail-password"
        assert mailbox == "INBOX"
        assert initial_limit >= 1
        return MailboxSyncBatch(
            messages=tuple(self.fetch_recent(settings, folder=mailbox, limit=initial_limit)),
            cursor={"uidvalidity": "10", "highest_seen_uid": 1, "uidnext": "2"},
        )

    def send_draft(
        self,
        settings: MailConnectionSettings,
        *,
        to_text: str,
        cc_text: str,
        bcc_text: str,
        subject: str,
        text_body: str,
        html_body: str = "",
    ) -> str | None:
        assert settings.smtp_password == "mail-password"
        self.sent.append(
            {
                "to_text": to_text,
                "subject": subject,
                "text_body": text_body,
            }
        )
        return "<sent-message@example.test>"


class SequenceMailClient(FakeMailClient):
    def __init__(self, batches: list[MailboxSyncBatch]) -> None:
        super().__init__()
        self.batches = batches

    def sync_mailbox(
        self,
        settings: MailConnectionSettings,
        *,
        mailbox: str = "INBOX",
        cursor: dict | None = None,
        initial_limit: int = 50,
    ) -> MailboxSyncBatch:
        del settings, mailbox, cursor, initial_limit
        assert self.batches
        return self.batches.pop(0)


class MultiMailboxMailClient(FakeMailClient):
    def __init__(self) -> None:
        super().__init__()
        self.synced_mailboxes: list[str] = []

    def list_mailboxes(self, settings: MailConnectionSettings) -> list[MailboxInfo]:
        assert settings.incoming_password == "mail-password"
        return [
            MailboxInfo(provider_mailbox_id="INBOX", display_name="INBOX", role="inbox"),
            MailboxInfo(
                provider_mailbox_id="Projects",
                display_name="Projects",
                role="folder",
            ),
            MailboxInfo(
                provider_mailbox_id="[Gmail]/Sent Mail",
                display_name="Sent Mail",
                role="sent",
                sync_enabled=False,
            ),
        ]

    def sync_mailbox(
        self,
        settings: MailConnectionSettings,
        *,
        mailbox: str = "INBOX",
        cursor: dict | None = None,
        initial_limit: int = 50,
    ) -> MailboxSyncBatch:
        del cursor
        assert settings.incoming_password == "mail-password"
        assert initial_limit >= 1
        self.synced_mailboxes.append(mailbox)
        subject = "Inbox report" if mailbox == "INBOX" else "Project report"
        uid = "uid-inbox" if mailbox == "INBOX" else "uid-projects"
        return MailboxSyncBatch(
            messages=(
                FetchedMessage(
                    provider_uid=uid,
                    provider_message_id=f"<{uid}@example.test>",
                    thread_key=f"<{uid}@example.test>",
                    subject=subject,
                    from_text="sender@example.test",
                    to_text="admin@example.test",
                    cc_text="",
                    text_body=subject,
                    html_body="",
                    snippet=subject,
                    received_at=datetime(2026, 5, 12, 9, 0, 0),
                    sent_at=datetime(2026, 5, 12, 9, 0, 0),
                    is_read=False,
                    attachments=(),
                    remote_identity=f"imap:{mailbox}:10:{uid}",
                    remote_flags={"provider": "imap", "folder": mailbox},
                ),
            ),
            cursor={"uidvalidity": "10", "highest_seen_uid": 1, "uidnext": "2"},
        )


def _payload() -> dict:
    return {
        "email_address": "admin@example.test",
        "display_name": "Admin Mail",
        "protocol": "imap",
        "incoming_host": "imap.example.test",
        "incoming_port": 993,
        "incoming_security": "ssl",
        "incoming_username": "admin@example.test",
        "incoming_password": "mail-password",
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "admin@example.test",
        "smtp_password": "mail-password",
    }


def _settings(protocol: str = "imap") -> MailConnectionSettings:
    return MailConnectionSettings(
        protocol=protocol,
        incoming_host="imap.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="admin@example.test",
        incoming_password="mail-password",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="admin@example.test",
        smtp_password="mail-password",
        email_address="admin@example.test",
        provider_kind=protocol,
    )


def test_mail_connection_validation_blocks_private_hosts() -> None:
    payload = {**_payload(), "incoming_host": "127.0.0.1"}

    result = mail_service.test_connection(
        mail_service.MailAccountConnectionRequest.model_validate(payload),
        client=FakeMailClient(),
    )

    assert result.incoming_ok is False
    assert result.incoming_error == "Mail host resolves to a blocked network."
    assert result.smtp_ok is True
    assert result.smtp_error is None


def test_mail_connection_validation_blocks_cgnat_hosts() -> None:
    payload = {**_payload(), "incoming_host": "100.64.0.1"}

    result = mail_service.test_connection(
        mail_service.MailAccountConnectionRequest.model_validate(payload),
        client=FakeMailClient(),
    )

    assert result.incoming_ok is False
    assert result.incoming_error == "Mail host resolves to a blocked network."
    assert result.smtp_ok is True
    assert result.smtp_error is None


def test_mail_connection_validation_blocks_insecure_transport() -> None:
    payload = {**_payload(), "incoming_security": "none"}

    result = mail_service.test_connection(
        mail_service.MailAccountConnectionRequest.model_validate(payload),
        client=FakeMailClient(),
    )

    assert result.incoming_ok is False
    assert result.incoming_error == "Insecure mail transport is not allowed."
    assert result.smtp_ok is True
    assert result.smtp_error is None


@pytest.mark.slow
def test_stored_account_sync_revalidates_mail_egress_policy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]

    with get_session_factory()() as db:
        account = db.get(MailAccount, account_id)
        assert account is not None
        account.incoming_host = "127.0.0.1"
        db.add(account)
        db.commit()

        with pytest.raises(mail_clients.MailConnectionPolicyError):
            mail_service.sync_account(db, account_id=account.id, client=fake)
        db.refresh(account)
        assert account.last_error == "Mail host resolves to a blocked network."


@pytest.mark.slow
def test_send_draft_revalidates_stored_smtp_policy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]
    with get_session_factory()() as db:
        account = db.get(MailAccount, account_id)
        assert account is not None
        account.smtp_security = "none"
        draft = MailDraft(
            id="mail-policy-draft",
            account_id=account.id,
            to_text="receiver@example.test",
            cc_text="",
            bcc_text="",
            subject="Policy check",
            text_body="Hello",
            html_body="",
            ai_generated=False,
            status="draft",
        )
        db.add_all([account, draft])
        db.commit()

    send_response = client.post(
        "/api/v1/mail/drafts/mail-policy-draft/send",
        headers=headers,
    )

    assert send_response.status_code == 502, send_response.text
    assert fake.sent == []


@pytest.mark.slow
def test_mail_sync_enqueue_dedupes_processing_and_reclaims_expired_jobs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    published: list[str] = []
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    monkeypatch.setattr(
        mail_service, "_publish_sync_job", lambda *, job_id: published.append(job_id)
    )
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]

    first = client.post(
        f"/api/v1/mail/accounts/{account_id}/sync",
        headers=headers,
    )
    assert first.status_code == 202, first.text
    job_id = first.json()["job_id"]
    assert published == [job_id]

    second = client.post(
        f"/api/v1/mail/accounts/{account_id}/sync",
        headers=headers,
    )
    assert second.status_code == 202, second.text
    assert second.json()["job_id"] == job_id
    assert published == [job_id]

    with get_session_factory()() as db:
        job = db.get(MailSyncJob, job_id)
        assert job is not None
        job.status = "processing"
        job.lease_expires_at = mail_service.utcnow_naive() + timedelta(minutes=5)
        db.add(job)
        db.commit()

    third = client.post(
        f"/api/v1/mail/accounts/{account_id}/sync",
        headers=headers,
    )
    assert third.status_code == 202, third.text
    assert third.json()["job_id"] == job_id
    assert published == [job_id]
    with get_session_factory()() as db:
        active_count = (
            db.query(MailSyncJob)
            .filter(
                MailSyncJob.account_id == account_id,
                MailSyncJob.status.in_(("pending", "processing")),
            )
            .count()
        )
        assert active_count == 1
        job = db.get(MailSyncJob, job_id)
        assert job is not None
        job.lease_expires_at = mail_service.utcnow_naive() - timedelta(seconds=1)
        db.add(job)
        db.commit()

    fourth = client.post(
        f"/api/v1/mail/accounts/{account_id}/sync",
        headers=headers,
    )
    assert fourth.status_code == 202, fourth.text
    assert fourth.json()["job_id"] == job_id
    assert published == [job_id, job_id]
    with get_session_factory()() as db:
        job = db.get(MailSyncJob, job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.lease_expires_at is None


@pytest.mark.slow
def test_mail_sync_dispatcher_claims_visibility_before_publish(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[str] = []
    monkeypatch.setattr(mail_service, "_mail_client", lambda: FakeMailClient())
    monkeypatch.setattr(
        mail_service, "_publish_sync_job", lambda *, job_id: published.append(job_id)
    )
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]
    sync_response = client.post(
        f"/api/v1/mail/accounts/{account_id}/sync",
        headers=headers,
    )
    assert sync_response.status_code == 202, sync_response.text
    job_id = sync_response.json()["job_id"]
    assert published == [job_id]

    with get_session_factory()() as db:
        job = db.get(MailSyncJob, job_id)
        assert job is not None
        job.last_published_at = mail_service.utcnow_naive() - timedelta(minutes=10)
        db.add(job)
        db.commit()

        assert mail_service.publish_due_mail_sync_jobs(db) == 1
        assert mail_service.publish_due_mail_sync_jobs(db) == 0

    assert published == [job_id, job_id]


@pytest.mark.slow
def test_mail_sync_dispatcher_clears_publish_claim_on_broker_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[str] = []
    fail_publish = False

    def fake_publish(*, job_id: str) -> None:
        if fail_publish:
            raise RuntimeError("broker down")
        published.append(job_id)

    monkeypatch.setattr(mail_service, "_mail_client", lambda: FakeMailClient())
    monkeypatch.setattr(mail_service, "_publish_sync_job", fake_publish)
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]
    sync_response = client.post(
        f"/api/v1/mail/accounts/{account_id}/sync",
        headers=headers,
    )
    assert sync_response.status_code == 202, sync_response.text
    job_id = sync_response.json()["job_id"]

    with get_session_factory()() as db:
        job = db.get(MailSyncJob, job_id)
        assert job is not None
        job.last_published_at = mail_service.utcnow_naive() - timedelta(minutes=10)
        db.add(job)
        db.commit()

        fail_publish = True
        assert mail_service.publish_due_mail_sync_jobs(db) == 0
        db.refresh(job)
        assert job.last_published_at is None

        fail_publish = False
        assert mail_service.publish_due_mail_sync_jobs(db) == 1

    assert published == [job_id, job_id]


def test_mail_account_sync_and_message_access(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])

    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_payload = response.json()
    assert "incoming_password" not in account_payload
    assert "smtp_password" not in account_payload
    assert account_payload["status"] == "ready"

    sync_response = client.post(
        f"/api/v1/mail/accounts/{account_payload['id']}/sync",
        headers=headers,
    )
    assert sync_response.status_code == 202, sync_response.text
    sync_payload = sync_response.json()
    assert sync_payload["queued"] is True
    assert sync_payload["job_id"]
    assert sync_payload["task_id"] == sync_payload["job_id"]

    duplicate_sync_response = client.post(
        f"/api/v1/mail/accounts/{account_payload['id']}/sync",
        headers=headers,
    )
    assert duplicate_sync_response.status_code == 202, duplicate_sync_response.text
    assert duplicate_sync_response.json()["job_id"] == sync_payload["job_id"]

    with get_session_factory()() as db:
        account = db.get(MailAccount, account_payload["id"])
        assert account is not None
        pending_jobs = (
            db.query(MailSyncJob)
            .filter(MailSyncJob.account_id == account.id, MailSyncJob.status == "pending")
            .all()
        )
        assert len(pending_jobs) == 1
        assert account.incoming_password_encrypted != "mail-password"
        assert mail_service.process_mail_sync_job(db, pending_jobs[0].id, client=fake) == "synced:1"
        db.refresh(pending_jobs[0])
        assert pending_jobs[0].status == "succeeded"
        second_result = mail_service.sync_account(db, account_id=account.id, client=fake)
        assert second_result.new_count == 0
        assert second_result.updated_count == 1
        assert (
            db.query(MailMessage)
            .filter(MailMessage.account_id == account.id, MailMessage.remote_deleted_at.is_(None))
            .count()
            == 1
        )

    list_response = client.get(
        "/api/v1/mail/messages",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    messages = list_response.json()["items"]
    assert len(messages) == 1
    assert messages[0]["subject"] == "Quarterly report"
    assert messages[0]["has_attachments"] is True

    detail_response = client.get(
        f"/api/v1/mail/messages/{messages[0]['id']}",
        headers=headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["body"]["text_body"] == "Please review the quarterly report by Friday."
    assert detail["attachments"][0]["filename"] == "report.pdf"

    flag_response = client.patch(
        f"/api/v1/mail/messages/{messages[0]['id']}/flags",
        headers=headers,
        json={"is_read": True},
    )
    assert flag_response.status_code == 200, flag_response.text
    assert flag_response.json()["is_read"] is True
    with get_session_factory()() as db:
        mail_service.sync_account(db, account_id=account_payload["id"], client=fake)
        message = db.get(MailMessage, messages[0]["id"])
        assert message is not None
        assert message.is_read is True

    duplicate_response = client.post("/api/v1/mail/accounts", headers=headers, json=_payload())
    assert duplicate_response.status_code == 409, duplicate_response.text
    assert duplicate_response.json()["code"] == "mail.account_duplicate"
    second_response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json={**_payload(), "email_address": "archive@example.test"},
    )
    assert second_response.status_code == 201, second_response.text
    duplicate_account_id = second_response.json()["id"]
    assert duplicate_account_id != account_payload["id"]

    delete_response = client.delete(
        f"/api/v1/mail/accounts/{account_payload['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text
    with get_session_factory()() as db:
        assert db.get(MailAccount, account_payload["id"]) is None
        assert db.get(MailAccount, duplicate_account_id) is not None
        assert (
            db.query(MailMessage).filter(MailMessage.account_id == account_payload["id"]).count()
            == 0
        )
        assert (
            db.query(MailSyncJob).filter(MailSyncJob.account_id == account_payload["id"]).count()
            == 0
        )
    hidden_response = client.get(
        "/api/v1/mail/messages",
        headers=headers,
    )
    assert hidden_response.status_code == 200, hidden_response.text
    assert hidden_response.json()["items"] == []

    reconnect_response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert reconnect_response.status_code == 201, reconnect_response.text
    assert reconnect_response.json()["id"] != account_payload["id"]


def test_imap_account_sync_discovers_and_syncs_enabled_mailboxes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = MultiMailboxMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]

    with get_session_factory()() as db:
        result = mail_service.sync_account(db, account_id=account_id, client=fake)
        assert result.new_count == 2
        assert fake.synced_mailboxes == ["INBOX", "Projects"]
        mailbox_rows = (
            db.query(MailMailbox)
            .filter(MailMailbox.account_id == account_id)
            .order_by(MailMailbox.provider_mailbox_id.asc())
            .all()
        )
        assert {(row.provider_mailbox_id, row.role, row.sync_enabled) for row in mailbox_rows} == {
            ("[Gmail]/Sent Mail", "sent", False),
            ("INBOX", "inbox", True),
            ("Projects", "folder", True),
        }
        messages = (
            db.query(MailMessage)
            .filter(
                MailMessage.account_id == account_id,
                MailMessage.remote_deleted_at.is_(None),
            )
            .order_by(MailMessage.folder.asc())
            .all()
        )
        assert [(message.folder, message.subject) for message in messages] == [
            ("INBOX", "Inbox report"),
            ("Projects", "Project report"),
        ]


@pytest.mark.slow
def test_mail_account_update_reuses_existing_passwords_and_resets_sync_on_incoming_change(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])

    create_response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    account_id = create_response.json()["id"]

    with get_session_factory()() as db:
        assert mail_service.sync_account(db, account_id=account_id, client=fake).new_count == 1
        assert db.query(MailMessage).filter(MailMessage.account_id == account_id).count() == 1
        account = db.get(MailAccount, account_id)
        assert account is not None
        incoming_ciphertext = account.incoming_password_encrypted
        smtp_ciphertext = account.smtp_password_encrypted

    update_response = client.patch(
        f"/api/v1/mail/accounts/{account_id}",
        headers=headers,
        json={
            "display_name": "Updated Mail",
            "incoming_host": "imap2.example.test",
            "incoming_password": "",
            "smtp_password": "",
        },
    )
    assert update_response.status_code == 200, update_response.text
    payload = update_response.json()
    assert payload["display_name"] == "Updated Mail"
    assert payload["incoming_host"] == "imap2.example.test"
    assert payload["status"] == "ready"
    assert payload["last_sync_at"] is None
    assert "incoming_password" not in payload
    assert "smtp_password" not in payload

    with get_session_factory()() as db:
        account = db.get(MailAccount, account_id)
        assert account is not None
        assert account.incoming_host == "imap2.example.test"
        assert account.incoming_password_encrypted == incoming_ciphertext
        assert account.smtp_password_encrypted == smtp_ciphertext
        assert db.query(MailMessage).filter(MailMessage.account_id == account_id).count() == 0
        assert db.query(MailSyncState).filter(MailSyncState.account_id == account_id).count() == 1


def test_mail_sync_remote_delete_purges_body_and_attachments(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mail_service, "_mail_client", lambda: FakeMailClient())
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]
    message = FakeMailClient().fetch_recent(_settings())[0]
    sequence = SequenceMailClient(
        [
            MailboxSyncBatch(
                messages=(message,),
                cursor={"uidvalidity": "10", "highest_seen_uid": 1, "known_uids": ["uid-001"]},
            ),
            MailboxSyncBatch(
                messages=(),
                cursor={"uidvalidity": "10", "highest_seen_uid": 1, "known_uids": []},
                deleted_remote_identities=("imap:10:uid-001",),
            ),
        ]
    )

    with get_session_factory()() as db:
        first = mail_service.sync_account(db, account_id=account_id, client=sequence)
        assert first.new_count == 1
        row = db.query(MailMessage).filter(MailMessage.account_id == account_id).one()
        message_id = row.id
        assert (
            db.query(MailMessageBody).filter(MailMessageBody.message_id == message_id).count() == 1
        )
        assert db.query(MailAttachment).filter(MailAttachment.message_id == message_id).count() == 1

        second = mail_service.sync_account(db, account_id=account_id, client=sequence)
        assert second.deleted_count == 1
        row = db.get(MailMessage, message_id)
        assert row is not None
        assert row.remote_deleted_at is not None
        assert row.has_attachments is False
        assert row.body_status == "remote_deleted"
        assert (
            db.query(MailMessageBody).filter(MailMessageBody.message_id == message_id).count() == 0
        )
        assert db.query(MailAttachment).filter(MailAttachment.message_id == message_id).count() == 0

    list_response = client.get(
        "/api/v1/mail/messages",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["items"] == []


def test_mail_ai_reply_draft_and_manual_send(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    monkeypatch.setattr(
        mail_service,
        "execute_llm",
        lambda *args, **kwargs: SimpleNamespace(
            completion=SimpleNamespace(text="검토 후 금요일까지 회신드리겠습니다.")
        ),
    )
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    account_response = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json=_payload(),
    )
    assert account_response.status_code == 201, account_response.text
    with get_session_factory()() as db:
        account = db.get(MailAccount, account_response.json()["id"])
        assert account is not None
        mail_service.sync_account(db, account_id=account.id, client=fake)

    message_id = client.get(
        "/api/v1/mail/messages",
        headers=headers,
    ).json()["items"][0]["id"]

    draft_response = client.post(
        f"/api/v1/mail/messages/{message_id}/reply-draft",
        headers=headers,
        json={"instruction": "짧게 답장"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    assert draft["status"] == "draft"
    assert draft["ai_generated"] is True

    send_response = client.post(
        f"/api/v1/mail/drafts/{draft['id']}/send",
        headers=headers,
    )
    assert send_response.status_code == 200, send_response.text
    sent = send_response.json()
    assert sent["status"] == "sent"
    assert fake.sent[0]["subject"] == "Re: Quarterly report"

    with get_session_factory()() as db:
        row = db.get(MailDraft, draft["id"])
        assert row is not None
        assert row.sent_message_id == "<sent-message@example.test>"


def test_mail_account_uniqueness_is_per_owner_and_reconnect_is_allowed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMailClient()
    monkeypatch.setattr(mail_service, "_mail_client", lambda: fake)
    owner = dev_login(client, "administrator")
    other = dev_login(client, "delivery-hub-member")
    owner_headers = auth_headers(owner["token"])
    first = client.post("/api/v1/mail/accounts", headers=owner_headers, json=_payload())
    assert first.status_code == 201, first.text
    foreign = client.post(
        "/api/v1/mail/accounts", headers=auth_headers(other["token"]), json=_payload()
    )
    assert foreign.status_code == 201, foreign.text
    assert first.json()["id"] != foreign.json()["id"]
    assert (
        client.delete(
            f"/api/v1/mail/accounts/{foreign.json()['id']}", headers=owner_headers
        ).status_code
        == 404
    )
    deleted = client.delete(f"/api/v1/mail/accounts/{first.json()['id']}", headers=owner_headers)
    assert deleted.status_code == 204
    reconnected = client.post("/api/v1/mail/accounts", headers=owner_headers, json=_payload())
    assert reconnected.status_code == 201, reconnected.text
    assert reconnected.json()["id"] != first.json()["id"]


def test_duplicate_mail_create_and_email_update_fail_before_provider_io(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mail_service, "_mail_client", lambda: FakeMailClient())
    headers = auth_headers(dev_login(client)["token"])
    first = client.post("/api/v1/mail/accounts", headers=headers, json=_payload())
    second = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json={**_payload(), "email_address": "archive@example.test"},
    )
    assert first.status_code == second.status_code == 201
    monkeypatch.setattr(
        mail_service,
        "_mail_client",
        lambda: pytest.fail("Duplicate account must be rejected before provider I/O"),
    )
    duplicate = client.post(
        "/api/v1/mail/accounts",
        headers=headers,
        json={**_payload(), "email_address": "ADMIN@example.test"},
    )
    changed = client.patch(
        f"/api/v1/mail/accounts/{second.json()['id']}", headers=headers, json=_payload()
    )
    for response in (duplicate, changed):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "mail.account_duplicate"
    listing = client.get("/api/v1/mail/accounts", headers=headers)
    assert listing.status_code == 200
    assert {row["email_address"] for row in listing.json()} == {
        "admin@example.test",
        "archive@example.test",
    }


def test_mail_account_unique_constraint_race_returns_conflict_without_partial_audit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import func, select
    from open_work_hub_api.domains.auth.models import AuditLog

    monkeypatch.setattr(mail_service, "_mail_client", lambda: FakeMailClient())
    headers = auth_headers(dev_login(client)["token"])
    first = client.post("/api/v1/mail/accounts", headers=headers, json=_payload())
    assert first.status_code == 201, first.text
    with get_session_factory()() as db:
        before = db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "mail.account.create")
        )
    # A concurrent writer can commit after preflight; the real database constraint remains authoritative.
    monkeypatch.setattr(mail_service, "_ensure_email_available", lambda *_args, **_kwargs: None)
    raced = client.post("/api/v1/mail/accounts", headers=headers, json=_payload())
    assert raced.status_code == 409, raced.text
    assert raced.json()["code"] == "mail.account_duplicate"
    with get_session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(MailAccount)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "mail.account.create")
            )
            == before
        )
