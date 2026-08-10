from __future__ import annotations

from sqlalchemy import create_engine, inspect


def test_platform_api_key_migration_matches_security_contract(
    application_postgres_dsn: str,
) -> None:
    engine = create_engine(application_postgres_dsn)
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("platform_api_keys")}
        assert set(columns) == {
            "id",
            "token_hash",
            "secret_ciphertext",
            "key_prefix",
            "name",
            "scopes",
            "status",
            "created_by_user_id",
            "created_at",
            "revoked_by_user_id",
            "revoked_at",
            "last_used_at",
        }
        assert columns["token_hash"]["nullable"] is False
        assert columns["secret_ciphertext"]["nullable"] is False
        assert columns["scopes"]["nullable"] is False

        checks = {check["name"] for check in inspector.get_check_constraints("platform_api_keys")}
        assert {
            "ck_platform_api_keys_name",
            "ck_platform_api_keys_prefix",
            "ck_platform_api_keys_revocation",
            "ck_platform_api_keys_status",
        }.issubset(checks)

        indexes = {index["name"]: index for index in inspector.get_indexes("platform_api_keys")}
        assert indexes["ix_platform_api_keys_token_hash"]["unique"] is True
        assert indexes["ix_platform_api_keys_key_prefix"]["unique"] is True
        assert "ix_platform_api_keys_status_created" in indexes

        foreign_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspector.get_foreign_keys("platform_api_keys")
        }
        assert foreign_keys[("created_by_user_id",)]["referred_table"] == "users"
        assert foreign_keys[("revoked_by_user_id",)]["referred_table"] == "users"
        assert foreign_keys[("created_by_user_id",)]["options"].get("ondelete") == "SET NULL"
        assert foreign_keys[("revoked_by_user_id",)]["options"].get("ondelete") == "SET NULL"
    finally:
        engine.dispose()
