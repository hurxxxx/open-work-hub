import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from pydantic import ValidationError

from codex_console.auth import password_hash, verify
from codex_console.config import Settings
from codex_console.protocol_contract import (
    COMPATIBILITY_SCHEMA_NAMES,
    build_contract,
    schemas_are_compatible,
    supports_contract_version,
)
from codex_console.rpc import CONTRACT


def test_generated_protocol_schemas_are_valid():
    assert supports_contract_version("codex-cli 0.155.1", CONTRACT["codexVersion"])
    for schema in CONTRACT["schemas"].values():
        Draft7Validator.check_schema(schema)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("codex-cli 0.155.1", True),
        ("codex-cli 0.156.0", True),
        ("codex-cli 1.0.0", True),
        ("codex-cli 0.155.0", False),
        ("codex-cli 0.156.0-alpha.1", False),
        ("codex-cli latest", False),
    ],
)
def test_codex_contract_requires_a_stable_minimum_version(output, expected):
    assert supports_contract_version(output, CONTRACT["codexVersion"]) is expected


def test_codex_contract_accepts_only_matching_selected_schemas(tmp_path):
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    for name in COMPATIBILITY_SCHEMA_NAMES:
        (tmp_path / f"{name}.json").write_text(json.dumps(schema))
    contract = build_contract("0.155.1", tmp_path)
    assert schemas_are_compatible(contract, tmp_path)

    changed = json.loads((tmp_path / "ModelListParams.json").read_text())
    changed["required"] = ["incompatible"]
    (tmp_path / "ModelListParams.json").write_text(json.dumps(changed))
    assert not schemas_are_compatible(contract, tmp_path)


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


def test_reasoning_policy_is_configurable_and_rejects_empty_efforts(repository, monkeypatch):
    data = {
        "database_url": "postgresql+psycopg://test@localhost/console_test",
        "workspace": repository,
        "origin": "http://localhost",
        "_env_file": None,
    }
    key = "OPEN_WORK_HUB_CODEX_CONSOLE_ALLOWED_REASONING_EFFORTS"
    monkeypatch.setenv(key, '["low","high"]')
    assert Settings(**data).allowed_reasoning_efforts == ["low", "high"]
    for invalid in ("[]", '[""]', '[" "]', '["two words"]'):
        monkeypatch.setenv(key, invalid)
        with pytest.raises(ValidationError):
            Settings(**data)


def test_sso_origins_are_exact_secure_origins(repository):
    data = {
        "database_url": "postgresql+psycopg://test@localhost/console_test",
        "workspace": repository,
        "origin": "http://localhost",
        "_env_file": None,
    }
    assert Settings(
        **data,
        sso_origins=["https://dev.example.com/", "http://127.0.0.1:4200"],
    ).sso_origins == ["https://dev.example.com", "http://127.0.0.1:4200"]
    for origins in (
        ["http://example.com"],
        ["https://example.com/path"],
        ["https://user@example.com"],
        ["https://:password@example.com"],
        ["https://example.com", "https://example.com/"],
    ):
        with pytest.raises(ValidationError):
            Settings(**data, sso_origins=origins)


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
