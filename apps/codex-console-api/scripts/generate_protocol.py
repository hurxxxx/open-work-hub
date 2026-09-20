"""Generate the request contracts we use from the pinned official Codex binary."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

VERSION = "0.155.1"
NAMES = (
    "ThreadStartParams",
    "ThreadResumeParams",
    "TurnStartParams",
    "TurnSteerParams",
    "TurnInterruptParams",
    "ModelListParams",
    "CommandExecutionRequestApprovalResponse",
    "FileChangeRequestApprovalResponse",
    "ToolRequestUserInputResponse",
    "PermissionsRequestApprovalResponse",
)
TARGET = Path(__file__).resolve().parents[1] / "src/codex_console/protocol.json"


def generate(source: Path) -> str:
    result = {"codexVersion": VERSION, "schemas": {}}
    for name in NAMES:
        schema = json.loads(next(source.rglob(name + ".json")).read_text())
        definitions = schema.pop("definitions", {})
        used = {}

        def visit(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "$ref" and item.startswith("#/definitions/"):
                        reference = item.split("/")[-1]
                        if reference not in used:
                            used[reference] = definitions[reference]
                            visit(used[reference])
                    else:
                        visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(schema)
        schema["definitions"] = used
        result["schemas"][name] = schema
    return json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    version = subprocess.check_output(["codex", "--version"], text=True).strip()
    if version != f"codex-cli {VERSION}":
        raise SystemExit(f"Expected codex-cli {VERSION}")
    with tempfile.TemporaryDirectory(prefix="codex-console-schema-") as directory:
        subprocess.run(
            ["codex", "app-server", "generate-json-schema", "--experimental", "--out", directory],
            check=True,
        )
        generated = generate(Path(directory))
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != generated:
            raise SystemExit("Codex protocol contract drift")
    else:
        TARGET.write_text(generated)


if __name__ == "__main__":
    main()
