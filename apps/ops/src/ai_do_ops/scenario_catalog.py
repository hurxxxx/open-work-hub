from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCENARIO_DIR = ROOT / "docs" / "harness" / "manifests" / "scenarios"


class ScenarioCatalogError(RuntimeError):
    """Base error for scenario manifest catalog failures."""


class ScenarioDirectoryNotFoundError(ScenarioCatalogError):
    """Raised when the scenario manifest directory is missing."""


class ScenarioManifestJsonError(ScenarioCatalogError):
    """Raised when a scenario manifest cannot be parsed as JSON."""


class ScenarioManifestIdError(ScenarioCatalogError):
    """Raised when a scenario manifest has no valid scenario_id."""


@dataclass(frozen=True, slots=True)
class ScenarioManifest:
    scenario_id: str
    path: Path


def list_scenario_manifests(
    scenario_dir: Path = DEFAULT_SCENARIO_DIR,
) -> list[ScenarioManifest]:
    if not scenario_dir.is_dir():
        raise ScenarioDirectoryNotFoundError(
            f"Scenario manifest directory does not exist: {scenario_dir}"
        )

    manifests = [load_scenario_manifest(path) for path in sorted(scenario_dir.glob("*.json"))]
    return sorted(manifests, key=lambda manifest: (manifest.scenario_id, manifest.path.name))


def list_scenario_ids(scenario_dir: Path = DEFAULT_SCENARIO_DIR) -> list[str]:
    return [manifest.scenario_id for manifest in list_scenario_manifests(scenario_dir)]


def load_scenario_manifest(path: Path) -> ScenarioManifest:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ScenarioManifestJsonError(
            f"Invalid JSON in scenario manifest {path}: {exc.msg}"
        ) from exc

    scenario_id = _read_scenario_id(payload, path)
    return ScenarioManifest(scenario_id=scenario_id, path=path)


def _read_scenario_id(payload: object, path: Path) -> str:
    if isinstance(payload, dict):
        scenario_id = payload.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id:
            return scenario_id

    raise ScenarioManifestIdError(
        f"Scenario manifest is missing a non-empty scenario_id: {path}"
    )
