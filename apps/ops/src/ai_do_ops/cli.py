import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCENARIO_DIR = ROOT / "docs" / "harness" / "manifests" / "scenarios"


def list_scenarios() -> int:
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(payload["scenario_id"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-DO ops scaffold")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list-scenarios", help="List scenario ids from the harness manifests")

    args = parser.parse_args()
    if args.command == "list-scenarios":
        return list_scenarios()

    parser.print_help()
    return 0
