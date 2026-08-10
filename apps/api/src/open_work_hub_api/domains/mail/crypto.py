from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from open_work_hub_api.core.settings import get_settings


class MailCredentialError(RuntimeError):
    pass


def resolve_mail_credential_key(key: str) -> bytes:
    normalized_key = key.strip()
    if not normalized_key:
        raise MailCredentialError("mail credential encryption key is not configured")
    try:
        candidate = normalized_key.encode("ascii")
        Fernet(candidate)
        return candidate
    except (UnicodeEncodeError, ValueError):
        return base64.urlsafe_b64encode(hashlib.sha256(normalized_key.encode("utf-8")).digest())


def _fernet() -> Fernet:
    key = get_settings().mail_credential_encryption_key
    return Fernet(resolve_mail_credential_key(key))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise MailCredentialError("mail credential could not be decrypted") from exc
