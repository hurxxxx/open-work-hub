from __future__ import annotations

import json
import shutil

from pydantic import TypeAdapter
import pytest

from open_work_hub_worker import settings
from open_work_hub_worker.runtime import ensure_api_src_on_path


@pytest.mark.parametrize("key, field", [
    ("OPEN_WORK_HUB_WORKER_DB_POOL_SIZE", "db_pool_size"),
    ("OPEN_WORK_HUB_WORKER_CONCURRENCY", "concurrency"),
])
def test_worker_uses_profile_defaults_and_preserves_env_overrides(tmp_path, monkeypatch, key, field):
    shutil.copytree(settings.WORKSPACE_ROOT / "config", tmp_path / "config")
    path = tmp_path / "config/runtime.json"
    document = json.loads(path.read_text())
    document["profiles"]["test"][key] = 2
    path.write_text(json.dumps(document))
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OPEN_WORK_HUB_ENV_PROFILE", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPEN_WORK_HUB_ENV_PROFILE=test\n")
    assert getattr(settings.Settings(_env_file=env), field) == 2
    env.write_text(f"OPEN_WORK_HUB_ENV_PROFILE=test\n{key}=3\n")
    assert getattr(settings.Settings(_env_file=env), field) == 3
    monkeypatch.setenv(key, "4")
    assert getattr(settings.Settings(_env_file=env), field) == 4
    assert getattr(settings.Settings(_env_file=env, **{key: 5}), field) == 5


def test_runtime_schema_matches_typed_api_and_worker_constraints():
    ensure_api_src_on_path()
    from open_work_hub_api.core.settings import Settings as ApiSettings

    schema = json.loads((settings.WORKSPACE_ROOT / "config/runtime.schema.json").read_text())
    properties = schema["$defs"]["settings"]["properties"]
    covered = set()
    for cls in (settings.Settings, ApiSettings):
        for name, field in cls.model_fields.items():
            key = field.validation_alias or f"{cls.model_config['env_prefix']}{name.upper()}"
            if key in properties:
                assert properties[key] == TypeAdapter(field.rebuild_annotation()).json_schema(), key
                covered.add(key)
    assert covered == properties.keys()
