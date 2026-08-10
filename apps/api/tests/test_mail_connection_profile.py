from __future__ import annotations

from open_work_hub_api.domains.mail.clients import MailConnectionSettings
from open_work_hub_api.domains.mail.connection_profile import (
    encrypt_connection_secrets,
    incoming_identity,
    settings_from_account,
    settings_from_account_update,
    settings_from_payload,
    validate_connection_profile,
)
from open_work_hub_api.domains.mail.models import MailAccount
from open_work_hub_api.domains.mail.schemas import (
    MailAccountConnectionRequest,
    MailAccountUpdateRequest,
)


def test_settings_from_payload_normalizes_connection_identity() -> None:
    settings = settings_from_payload(
        MailAccountConnectionRequest(
            email_address=" USER@Example.TEST ",
            display_name=" User ",
            protocol="imap",
            incoming_host=" imap.example.test ",
            incoming_port=993,
            incoming_security="ssl",
            incoming_username=" user ",
            incoming_password="incoming-secret",
            smtp_host=" smtp.example.test ",
            smtp_port=587,
            smtp_security="starttls",
            smtp_username=" smtp-user ",
            smtp_password="smtp-secret",
        )
    )

    assert settings.email_address == "user@example.test"
    assert settings.display_name == "User"
    assert settings.incoming_host == "imap.example.test"
    assert settings.incoming_username == "user"
    assert settings.smtp_host == "smtp.example.test"
    assert settings.smtp_username == "smtp-user"
    assert settings.provider_kind == "imap"


def test_account_update_reuses_blank_passwords_and_detects_incoming_identity_change() -> None:
    current = _settings()
    secrets = encrypt_connection_secrets(current)
    account = _account(
        incoming_password_encrypted=secrets.incoming_password_encrypted,
        smtp_password_encrypted=secrets.smtp_password_encrypted,
    )

    updated = settings_from_account_update(
        account,
        MailAccountUpdateRequest(
            display_name=" Updated ",
            incoming_host=" imap2.example.test ",
            incoming_password="",
            smtp_password="",
        ),
    )

    assert updated.display_name == "Updated"
    assert updated.incoming_host == "imap2.example.test"
    assert updated.incoming_password == "incoming-secret"
    assert updated.smtp_password == "smtp-secret"
    assert incoming_identity(account) != incoming_identity(updated)


def test_account_settings_decrypt_stored_profile_secrets() -> None:
    secrets = encrypt_connection_secrets(_settings())
    account = _account(
        incoming_password_encrypted=secrets.incoming_password_encrypted,
        smtp_password_encrypted=secrets.smtp_password_encrypted,
    )

    settings = settings_from_account(account)

    assert settings.incoming_password == "incoming-secret"
    assert settings.smtp_password == "smtp-secret"


def test_validate_connection_profile_returns_public_policy_message() -> None:
    assert (
        validate_connection_profile(
            _settings(incoming_port=2525),
            incoming=True,
            smtp=False,
        )
        == "Mail incoming port is not allowed."
    )


def _settings(**overrides: object) -> MailConnectionSettings:
    settings = MailConnectionSettings(
        protocol="imap",
        incoming_host="imap.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="user",
        incoming_password="incoming-secret",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="smtp-user",
        smtp_password="smtp-secret",
        email_address="user@example.test",
        display_name="User",
        provider_kind="imap",
    )
    return MailConnectionSettings(
        **{
            **settings.__dict__,
            **overrides,
        }
    )


def _account(**overrides: object) -> MailAccount:
    values = {
        "id": "account-1",
        "user_id": "user-1",
        "email_address": "user@example.test",
        "display_name": "User",
        "protocol": "imap",
        "provider_kind": "imap",
        "incoming_host": "imap.example.test",
        "incoming_port": 993,
        "incoming_security": "ssl",
        "incoming_username": "user",
        "incoming_password_encrypted": "incoming-encrypted",
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "smtp-user",
        "smtp_password_encrypted": "smtp-encrypted",
    }
    values.update(overrides)
    return MailAccount(**values)
