from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet

from ai_do_api.domains.mail.crypto import (
    MailCredentialError,
    resolve_mail_credential_key,
)


def test_resolve_mail_credential_key_reuses_valid_fernet_key() -> None:
    key = Fernet.generate_key()

    assert resolve_mail_credential_key(key.decode("ascii")) == key


def test_resolve_mail_credential_key_derives_stable_key_from_plain_secret() -> None:
    key = resolve_mail_credential_key("plain-mail-secret")

    assert key == base64.urlsafe_b64encode(hashlib.sha256(b"plain-mail-secret").digest())
    Fernet(key)


def test_resolve_mail_credential_key_rejects_blank_secret() -> None:
    with pytest.raises(
        MailCredentialError,
        match="mail credential encryption key is not configured",
    ):
        resolve_mail_credential_key(" ")
