import argparse
from pathlib import Path
from typing import Sequence

from open_alm_ops.scenario_catalog import (
    DEFAULT_SCENARIO_DIR,
    ScenarioCatalogError,
    list_scenario_ids,
)

SCENARIO_DIR = DEFAULT_SCENARIO_DIR


def list_scenarios(scenario_dir: Path = SCENARIO_DIR) -> int:
    for scenario_id in list_scenario_ids(scenario_dir):
        print(scenario_id)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open ALM ops scaffold")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list-scenarios", help="List scenario ids from the harness manifests")

    args = parser.parse_args(argv)
    if args.command == "list-scenarios":
        try:
            return list_scenarios()
        except ScenarioCatalogError as exc:
            parser.exit(1, f"error: {exc}\n")

    parser.print_help()
    return 0
