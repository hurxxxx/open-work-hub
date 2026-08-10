from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_do_api.domains.mail import connection_policy
from ai_do_api.domains.mail.clients import MailConnectionSettings
from ai_do_api.domains.mail.connection_policy import (
    MailConnectionPolicyError,
    validate_connection_settings,
)


def _settings(**overrides: object) -> MailConnectionSettings:
    settings = MailConnectionSettings(
        protocol="imap",
        incoming_host="8.8.8.8",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="admin@example.test",
        incoming_password="mail-password",
        smtp_host="1.1.1.1",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="admin@example.test",
        smtp_password="mail-password",
        email_address="admin@example.test",
    )
    return replace(settings, **overrides)


@pytest.fixture(autouse=True)
def _policy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = SimpleNamespace(
        mail_allowed_private_hosts="",
        mail_allow_insecure_transport=False,
    )
    monkeypatch.setattr(connection_policy, "get_settings", lambda: fake_settings)


@pytest.mark.parametrize(
    "host",
    [
        "10.0.0.1",
        "127.0.0.1",
        "100.64.0.1",
    ],
)
def test_incoming_policy_blocks_private_loopback_and_cgnat_hosts(host: str) -> None:
    with pytest.raises(
        MailConnectionPolicyError,
        match="Mail host resolves to a blocked network.",
    ):
        validate_connection_settings(_settings(incoming_host=host), incoming=True, smtp=False)


def test_smtp_policy_blocks_private_hosts() -> None:
    with pytest.raises(
        MailConnectionPolicyError,
        match="Mail host resolves to a blocked network.",
    ):
        validate_connection_settings(_settings(smtp_host="10.0.0.1"), incoming=False, smtp=True)


def test_insecure_transport_is_blocked() -> None:
    with pytest.raises(
        MailConnectionPolicyError,
        match="Insecure mail transport is not allowed.",
    ):
        validate_connection_settings(
            _settings(incoming_port=143, incoming_security="none"),
            incoming=True,
            smtp=False,
        )


def test_insecure_transport_is_allowed_when_policy_flag_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_settings = SimpleNamespace(
        mail_allowed_private_hosts="",
        mail_allow_insecure_transport=True,
    )
    monkeypatch.setattr(connection_policy, "get_settings", lambda: fake_settings)

    validate_connection_settings(
        _settings(
            incoming_port=143,
            incoming_security="none",
            smtp_port=25,
            smtp_security="none",
        )
    )


def test_invalid_incoming_port_is_blocked() -> None:
    with pytest.raises(MailConnectionPolicyError, match="Mail incoming port is not allowed."):
        validate_connection_settings(_settings(incoming_port=2525), incoming=True, smtp=False)


def test_invalid_smtp_port_is_blocked() -> None:
    with pytest.raises(MailConnectionPolicyError, match="Mail SMTP port is not allowed."):
        validate_connection_settings(_settings(smtp_port=143), incoming=False, smtp=True)


def test_allowed_private_host_override_bypasses_blocked_network_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_settings = SimpleNamespace(
        mail_allowed_private_hosts=" 127.0.0.1. ",
        mail_allow_insecure_transport=False,
    )
    monkeypatch.setattr(connection_policy, "get_settings", lambda: fake_settings)

    validate_connection_settings(
        _settings(incoming_host="127.0.0.1"),
        incoming=True,
        smtp=False,
    )
