from __future__ import annotations

import pytest
from pydantic import ValidationError

from open_work_hub_api.core.settings import Settings


POSTGRES_DSN = "postgresql+psycopg://test:test@127.0.0.1:1/test"


def test_development_accepts_seeded_login_without_required_object_storage() -> None:
    settings = Settings(
        _env_file=None,
        postgres_dsn=POSTGRES_DSN,
        environment="development",
        seed_dev_login_account=True,
        object_storage_required=False,
    )

    assert settings.seed_dev_login_account is True
    assert settings.object_storage_required is False


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        (
            {"seed_dev_login_account": True},
            "OPEN_WORK_HUB_API_SEED_DEV_LOGIN_ACCOUNT",
        ),
        (
            {"object_storage_required": False},
            "OPEN_WORK_HUB_API_OBJECT_STORAGE_REQUIRED",
        ),
    ],
)
def test_production_rejects_minimal_runtime_settings(
    overrides: dict[str, bool],
    expected_message: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        Settings(
            _env_file=None,
            postgres_dsn=POSTGRES_DSN,
            environment="production",
            **overrides,
        )
