"""Generate the request contracts we use from the pinned official Codex binary."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from codex_console.protocol_contract import render_contract, supports_contract_version

VERSION = "0.156.0"
TARGET = Path(__file__).resolve().parents[1] / "src/codex_console/protocol.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    version = subprocess.check_output(["codex", "--version"], text=True).strip()
    if args.check:
        if not supports_contract_version(version, VERSION):
            raise SystemExit(f"Expected a stable codex-cli {VERSION} or newer")
    elif version != f"codex-cli {VERSION}":
        raise SystemExit(f"Regeneration requires codex-cli {VERSION}")
    with tempfile.TemporaryDirectory(prefix="codex-console-schema-") as directory:
        subprocess.run(
            ["codex", "app-server", "generate-json-schema", "--experimental", "--out", directory],
            check=True,
        )
        generated = render_contract(VERSION, Path(directory))
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != generated:
            raise SystemExit("Codex protocol contract drift")
    else:
        TARGET.write_text(generated)


if __name__ == "__main__":
    main()
