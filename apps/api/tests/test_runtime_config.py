from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
from pydantic import ValidationError

from open_work_hub_api.core import settings
from open_work_hub_api.core.runtime_config import (
    RuntimeConfigError,
    load_runtime_document,
    runtime_defaults,
)

POOL_KEY = "OPEN_WORK_HUB_API_DB_POOL_SIZE"


@pytest.fixture
def config_root(tmp_path, monkeypatch):
    source_root = settings.WORKSPACE_ROOT
    shutil.copytree(source_root / "config", tmp_path / "config")
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path)
    return tmp_path


def update_config(root: Path, change) -> None:
    path = root / "config/runtime.json"
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def test_profile_dotenv_environment_and_explicit_setting_priority(config_root, monkeypatch):
    update_config(config_root, lambda doc: doc["profiles"]["dev"].update({POOL_KEY: 3}))
    monkeypatch.setenv("OPEN_WORK_HUB_ENV_PROFILE", "dev")
    monkeypatch.delenv(POOL_KEY, raising=False)
    env = config_root / ".env"
    env.write_text("# no override\n")
    assert settings.Settings(_env_file=env).db_pool_size == 3
    env.write_text(f"{POOL_KEY}=6\n")
    assert settings.Settings(_env_file=env).db_pool_size == 6
    monkeypatch.setenv(POOL_KEY, "7")
    assert settings.Settings(_env_file=env).db_pool_size == 7
    assert settings.Settings(_env_file=env, **{POOL_KEY: 8}).db_pool_size == 8
    assert settings.Settings(_env_file=env, db_pool_size=9).db_pool_size == 9
    monkeypatch.setenv(POOL_KEY, "0")
    with pytest.raises(ValidationError):
        settings.Settings(_env_file=env)


@pytest.mark.parametrize("profile", ["local", "dev", "prod", "preview", "test", " Production "])
def test_default_profiles_cover_pool_and_model_tuning(config_root, profile):
    values = runtime_defaults(config_root, profile)
    assert values[POOL_KEY] == 5
    assert values["OPEN_WORK_HUB_WORKER_DB_POOL_SIZE"] == 1
    assert values["OPEN_WORK_HUB_RAG_EMBEDDING_MODEL"]
    assert "OPEN_WORK_HUB_POSTGRES_DSN" not in values
    assert "OPEN_WORK_HUB_HERMES_API_KEY" not in values


@pytest.mark.parametrize(
    "change",
    [
        lambda doc: doc["defaults"].update({"OPEN_WORK_HUB_HERMES_API_KEY": "synthetic-secret"}),
        lambda doc: doc["profiles"]["prod"].update({POOL_KEY: 0}),
        lambda doc: doc["defaults"].pop(POOL_KEY),
        lambda doc: doc["profiles"].pop("prod"),
        lambda doc: doc.update(version=99),
    ],
)
def test_invalid_config_fails_without_exposing_values(config_root, change):
    update_config(config_root, change)
    with pytest.raises(RuntimeConfigError) as caught:
        runtime_defaults(config_root)
    assert "synthetic-secret" not in str(caught.value)


def test_missing_config_and_unknown_profile_fail_closed(config_root):
    with pytest.raises(RuntimeConfigError):
        runtime_defaults(config_root, "misspelled")
    (config_root / "config/runtime.json").unlink()
    with pytest.raises(RuntimeConfigError):
        runtime_defaults(config_root)


def test_duplicate_config_keys_fail(config_root):
    path = config_root / "config/runtime.json"
    path.write_text(path.read_text().replace('"version": 1', '"version": 1, "version": 1'))
    with pytest.raises(RuntimeConfigError, match="duplicate"):
        load_runtime_document(config_root)


def test_api_and_worker_settings_do_not_read_live_model_selection_from_config(config_root):
    # Models selected in Admin remain owned by DB routing. This file contains
    # only deployment tuning and preprocessing-model defaults.
    values = runtime_defaults(config_root)
    assert not any(key.endswith("_DEFAULT_EXTERNAL_LLM_PROVIDER") for key in values)
