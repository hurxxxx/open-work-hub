from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from pydantic import ValidationError

from codex_console.auth import password_hash, verify
from codex_console.config import CODEX_VERSION, Settings
from codex_console.rpc import CONTRACT


def test_generated_protocol_schemas_are_valid():
    assert CONTRACT["codexVersion"] == CODEX_VERSION
    for schema in CONTRACT["schemas"].values():
        Draft7Validator.check_schema(schema)


def test_password_salts_and_whitespace_are_significant():
    first, second = password_hash(" password "), password_hash(" password ")
    assert first != second
    assert verify(" password ", first)
    assert not verify("password", first)


def test_example_covers_exact_typed_env_contract():
    example = Path(__file__).resolve().parents[1] / ".env.example"
    keys = {
        line.split("=", 1)[0]
        for line in example.read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert keys == {field.validation_alias for field in Settings.model_fields.values()}
    assert all(key.startswith("OPEN_WORK_HUB_") for key in keys)


def test_remote_http_and_product_database_are_rejected(repository):
    data = {
        "database_url": "postgresql+psycopg://test@localhost/console_test",
        "workspace": repository,
        "origin": "http://example.com",
        "_env_file": None,
    }
    with pytest.raises(ValidationError):
        Settings(**data)
    data.update(
        origin="https://example.com",
        database_url="postgresql+psycopg://test@localhost/product_db",
        forbidden_database_names=["product_db"],
    )
    with pytest.raises(ValidationError):
        Settings(**data)


def test_protected_workspace_and_storage_paths_are_rejected(repository):
    data = {
        "database_url": "postgresql+psycopg://test@localhost/console_test",
        "workspace": repository,
        "origin": "http://localhost",
        "_env_file": None,
    }
    with pytest.raises(ValidationError):
        Settings(**data, protected_workspaces=[repository.parent])
    with pytest.raises(ValidationError):
        Settings(**data, worktree_root=repository / "sessions")
    assert Settings(**data).worktree_base_ref == "HEAD"
