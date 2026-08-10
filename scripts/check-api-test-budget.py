#!/usr/bin/env python3
"""Preserve the full API inventory and enforce the routine critical-suite budget."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps/api"
CRITICAL_MANIFEST = ROOT / "scripts/api-critical-test-manifest.txt"

LANES = ("standard", "slow", "migration", "external")
LANE_MARKERS = {
    "slow": "slow",
    "migration": "migration",
    "external": "external_integration",
}
DB_TEST_CLIENT_FIXTURES = frozenset(
    {
        "application_postgres_dsn",
        "application_postgres_state",
        "client",
        "client_without_collab_relay",
        "postgres_dsn",
        "postgres_template_dsn",
    }
)
DEFAULT_BUDGETS = {
    "total": 900,
    "standard": 861,
    "slow": 15,
    "migration": 12,
    "external": 12,
    "dbTestClientFixtureClosure": 100,
}
DEFAULT_MINIMUMS = {
    "total": 595,
    "standard": 570,
    "slow": 4,
    "migration": 12,
    "external": 9,
    "dbTestClientFixtureClosure": 100,
}
FULL_INVENTORY_MINIMUMS = {
    "total": 3136,
    "standard": 3065,
    "slow": 19,
    "migration": 40,
    "external": 12,
    "dbTestClientFixtureClosure": 624,
}


@dataclass(frozen=True)
class CollectedApiTest:
    nodeid: str
    markers: tuple[str, ...]
    fixture_closure: tuple[str, ...]


class ApiTestCollectionPlugin:
    """Small pytest plugin that records only stable collection metadata."""

    def __init__(self) -> None:
        self.items: list[CollectedApiTest] = []
        self.collection_errors: list[str] = []

    def pytest_collection_modifyitems(self, items: Sequence[Any]) -> None:
        snapshots: list[CollectedApiTest] = []
        for item in items:
            fixture_info = getattr(item, "_fixtureinfo", None)
            fixture_names = getattr(fixture_info, "names_closure", None)
            if fixture_names is None:
                fixture_names = getattr(item, "fixturenames", ())
            snapshots.append(
                CollectedApiTest(
                    nodeid=str(item.nodeid),
                    markers=tuple(sorted({marker.name for marker in item.iter_markers()})),
                    fixture_closure=tuple(sorted(set(fixture_names))),
                )
            )
        self.items = sorted(snapshots, key=lambda item: item.nodeid)

    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self.collection_errors.append(str(report.nodeid))


def _lane_names(item: CollectedApiTest) -> tuple[str, ...]:
    marked_lanes = tuple(
        lane
        for lane, marker in LANE_MARKERS.items()
        if marker in item.markers
    )
    return marked_lanes or ("standard",)


def evaluate_api_test_budget(
    items: Iterable[CollectedApiTest],
    *,
    budgets: Mapping[str, int] = DEFAULT_BUDGETS,
    minimums: Mapping[str, int] | None = None,
    collection_errors: Iterable[str] = (),
    collection_exit_code: int = 0,
) -> dict[str, Any]:
    ordered_items = sorted(items, key=lambda item: item.nodeid)
    lanes: dict[str, list[str]] = {lane: [] for lane in LANES}
    db_test_client_items: list[str] = []
    overlaps: list[dict[str, Any]] = []

    for item in ordered_items:
        item_lanes = _lane_names(item)
        for lane in item_lanes:
            lanes[lane].append(item.nodeid)
        if len(item_lanes) > 1:
            overlaps.append({"nodeid": item.nodeid, "lanes": list(item_lanes)})
        if DB_TEST_CLIENT_FIXTURES.intersection(item.fixture_closure):
            db_test_client_items.append(item.nodeid)

    counts = {
        "total": len(ordered_items),
        **{lane: len(lanes[lane]) for lane in LANES},
        "dbTestClientFixtureClosure": len(db_test_client_items),
    }
    violations: list[dict[str, Any]] = []
    for metric in (
        "total",
        "standard",
        "slow",
        "migration",
        "external",
        "dbTestClientFixtureClosure",
    ):
        if counts[metric] > budgets[metric]:
            violations.append(
                {
                    "kind": "budget",
                    "metric": metric,
                    "actual": counts[metric],
                    "limit": budgets[metric],
                }
            )
        if minimums is not None and counts[metric] < minimums[metric]:
            violations.append(
                {
                    "kind": "minimum",
                    "metric": metric,
                    "actual": counts[metric],
                    "minimum": minimums[metric],
                }
            )
    for overlap in overlaps:
        violations.append(
            {
                "kind": "laneOverlap",
                "nodeid": overlap["nodeid"],
                "lanes": overlap["lanes"],
            }
        )

    stable_collection_errors = sorted(set(collection_errors))
    if collection_exit_code != 0 or stable_collection_errors:
        violations.append(
            {
                "kind": "collection",
                "exitCode": collection_exit_code,
                "errors": stable_collection_errors,
            }
        )

    return {
        "schemaVersion": 1,
        "ok": not violations,
        "budgets": dict(budgets),
        "minimums": dict(minimums) if minimums is not None else None,
        "counts": counts,
        "lanes": lanes,
        "dbTestClientFixtureClosure": {
            "fixtureNames": sorted(DB_TEST_CLIENT_FIXTURES),
            "items": db_test_client_items,
        },
        "laneOverlaps": overlaps,
        "collection": {
            "exitCode": collection_exit_code,
            "errors": stable_collection_errors,
        },
        "violations": violations,
    }


def load_critical_manifest(path: Path = CRITICAL_MANIFEST) -> list[str]:
    nodeids = [
        line.strip()
        for line in path.read_text(encoding="utf8").splitlines()
        if line.strip()
    ]
    if len(nodeids) != len(set(nodeids)):
        raise ValueError(f"critical API manifest contains duplicates: {path}")
    return nodeids


def evaluate_critical_api_test_budget(
    items: Iterable[CollectedApiTest],
    critical_nodeids: Iterable[str],
    *,
    collection_errors: Iterable[str] = (),
    collection_exit_code: int = 0,
) -> dict[str, Any]:
    ordered_items = sorted(items, key=lambda item: item.nodeid)
    items_by_nodeid = {item.nodeid: item for item in ordered_items}
    stable_critical_nodeids = sorted(set(critical_nodeids))
    missing_nodeids = [
        nodeid for nodeid in stable_critical_nodeids if nodeid not in items_by_nodeid
    ]
    critical_items = [
        items_by_nodeid[nodeid]
        for nodeid in stable_critical_nodeids
        if nodeid in items_by_nodeid
    ]

    report = evaluate_api_test_budget(
        critical_items,
        budgets=DEFAULT_BUDGETS,
        minimums=DEFAULT_MINIMUMS,
        collection_errors=collection_errors,
        collection_exit_code=collection_exit_code,
    )
    full_inventory = evaluate_api_test_budget(
        ordered_items,
        budgets={metric: sys.maxsize for metric in DEFAULT_BUDGETS},
        minimums=FULL_INVENTORY_MINIMUMS,
        collection_errors=collection_errors,
        collection_exit_code=collection_exit_code,
    )
    manifest_violations = [
        {
            "kind": "manifest",
            "missingNodeids": missing_nodeids,
        }
    ] if missing_nodeids else []
    report["schemaVersion"] = 2
    report["criticalManifest"] = {
        "path": str(CRITICAL_MANIFEST.relative_to(ROOT)),
        "nodeids": stable_critical_nodeids,
        "missingNodeids": missing_nodeids,
    }
    report["fullInventory"] = {
        "minimums": dict(FULL_INVENTORY_MINIMUMS),
        "counts": full_inventory["counts"],
        "laneOverlaps": full_inventory["laneOverlaps"],
    }
    report["violations"] = [
        *report["violations"],
        *manifest_violations,
        *[
            violation
            for violation in full_inventory["violations"]
            if violation["kind"] in {"minimum", "laneOverlap"}
        ],
    ]
    report["ok"] = not report["violations"]
    return report


def collect_api_test_inventory() -> tuple[list[CollectedApiTest], list[str], int]:
    import pytest

    plugin = ApiTestCollectionPlugin()
    original_directory = Path.cwd()
    api_root_import_path = str(API_ROOT)
    inserted_import_path = api_root_import_path not in sys.path
    try:
        os.chdir(API_ROOT)
        if inserted_import_path:
            sys.path.insert(0, api_root_import_path)
        exit_code = int(
            pytest.main(
                [
                    "--collect-only",
                    "-p",
                    "no:terminal",
                    "-p",
                    "no:cacheprovider",
                    "tests",
                ],
                plugins=[plugin],
            )
        )
    finally:
        if inserted_import_path:
            sys.path.remove(api_root_import_path)
        os.chdir(original_directory)
    return plugin.items, plugin.collection_errors, exit_code


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("api-test-report.json"),
        help="JSON report path (default: api-test-report.json)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    output_path = args.output.resolve()
    items, collection_errors, collection_exit_code = collect_api_test_inventory()
    report = evaluate_critical_api_test_budget(
        items,
        load_critical_manifest(),
        collection_errors=collection_errors,
        collection_exit_code=collection_exit_code,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )

    counts = report["counts"]
    full_counts = report["fullInventory"]["counts"]
    print(
        "API pytest routine budget:"
        f" total={counts['total']}/{DEFAULT_BUDGETS['total']}"
        f" standard={counts['standard']}/{DEFAULT_BUDGETS['standard']}"
        f" slow={counts['slow']}/{DEFAULT_BUDGETS['slow']}"
        f" migration={counts['migration']}/{DEFAULT_BUDGETS['migration']}"
        f" external={counts['external']}/{DEFAULT_BUDGETS['external']}"
        " db/TestClient="
        f"{counts['dbTestClientFixtureClosure']}/"
        f"{DEFAULT_BUDGETS['dbTestClientFixtureClosure']}"
    )
    print(
        "API pytest full inventory:"
        f" total={full_counts['total']}"
        f" standard={full_counts['standard']}"
        f" slow={full_counts['slow']}"
        f" migration={full_counts['migration']}"
        f" external={full_counts['external']}"
        f" db/TestClient={full_counts['dbTestClientFixtureClosure']}"
    )
    print(f"API pytest budget report: {output_path}")
    for violation in report["violations"]:
        print(json.dumps(violation, sort_keys=True), file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
