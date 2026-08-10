import pytest

from open_work_hub_ops.scenario_catalog import (
    ScenarioDirectoryNotFoundError,
    ScenarioManifestIdError,
    ScenarioManifestJsonError,
    list_scenario_ids,
)


def test_list_scenario_ids_returns_ids_sorted_by_manifest_id(tmp_path):
    (tmp_path / "second.json").write_text('{"scenario_id": "beta"}', encoding="utf-8")
    (tmp_path / "first.json").write_text('{"scenario_id": "alpha"}', encoding="utf-8")

    assert list_scenario_ids(tmp_path) == ["alpha", "beta"]


def test_list_scenario_ids_rejects_missing_directory(tmp_path):
    missing_dir = tmp_path / "scenarios"

    with pytest.raises(ScenarioDirectoryNotFoundError, match="does not exist"):
        list_scenario_ids(missing_dir)


def test_list_scenario_ids_rejects_invalid_json(tmp_path):
    manifest_path = tmp_path / "broken.json"
    manifest_path.write_text("{", encoding="utf-8")

    with pytest.raises(ScenarioManifestJsonError, match="Invalid JSON"):
        list_scenario_ids(tmp_path)


def test_list_scenario_ids_rejects_missing_scenario_id(tmp_path):
    manifest_path = tmp_path / "missing-id.json"
    manifest_path.write_text('{"name": "No id"}', encoding="utf-8")

    with pytest.raises(ScenarioManifestIdError, match="scenario_id"):
        list_scenario_ids(tmp_path)
