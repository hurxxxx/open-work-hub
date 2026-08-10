from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from ai_do_api.core.settings import get_settings


class AiModelCredentialError(RuntimeError):
    pass


def resolve_ai_model_credential_key(key: str) -> bytes:
    normalized_key = key.strip()
    if not normalized_key:
        raise AiModelCredentialError("AI model credential encryption key is not configured")
    try:
        candidate = normalized_key.encode("ascii")
        Fernet(candidate)
        return candidate
    except (UnicodeEncodeError, ValueError):
        return base64.urlsafe_b64encode(hashlib.sha256(normalized_key.encode("utf-8")).digest())


def _fernet() -> Fernet:
    return Fernet(
        resolve_ai_model_credential_key(get_settings().ai_model_credential_encryption_key)
    )


def encrypt_api_key(secret: SecretStr | str) -> str:
    value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    normalized = value.strip()
    if not normalized:
        raise AiModelCredentialError("AI model API key cannot be empty")
    return _fernet().encrypt(normalized.encode("utf-8")).decode("ascii")


def decrypt_api_key(token: str) -> SecretStr:
    try:
        value = _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise AiModelCredentialError("AI model API key could not be decrypted") from exc
    return SecretStr(value)


__all__ = [
    "AiModelCredentialError",
    "decrypt_api_key",
    "encrypt_api_key",
    "resolve_ai_model_credential_key",
]
