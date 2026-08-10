from __future__ import annotations

import pytest
from pydantic import SecretStr

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai.model_credentials import (
    AiModelCredentialError,
    decrypt_api_key,
    encrypt_api_key,
)


def test_ai_model_api_key_round_trip_is_write_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AI_DO_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
        "unit-test-ai-model-key",
    )
    get_settings.cache_clear()
    try:
        token = encrypt_api_key(SecretStr("secret-value"))

        assert "secret-value" not in token
        secret = decrypt_api_key(token)
        assert secret.get_secret_value() == "secret-value"
        assert repr(secret) == "SecretStr('**********')"
    finally:
        get_settings.cache_clear()


def test_ai_model_api_key_requires_encryption_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DO_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(AiModelCredentialError, match="not configured"):
            encrypt_api_key("secret-value")
    finally:
        get_settings.cache_clear()
