"""Remove only redundant public defaults from a private checkout env file."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from dotenv import dotenv_values
from open_work_hub_api.core.runtime_config import runtime_defaults


def prune_defaults(
    text: str, defaults: dict[str, object]
) -> tuple[str, tuple[str, ...]]:
    """Preserve every override, comment and unrelated line verbatim."""
    assignments = re.findall(
        r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", text, re.MULTILINE
    )
    if len(assignments) != len(set(assignments)):
        raise ValueError("Resolve duplicate env keys before migration.")
    original_values = dotenv_values(stream=StringIO(text), interpolate=False)
    retained = []
    removed = []
    for line in text.splitlines(keepends=True):
        raw = line.strip().removeprefix("export ")
        key, separator, _value = raw.partition("=")
        key = key.strip()
        if separator and key in defaults:
            value = dotenv_values(stream=StringIO(line), interpolate=False).get(key)
            expected = str(defaults[key])
            referenced = re.search(r"\$\{" + re.escape(key) + r"(?::|\})", text)
            if value == expected and not referenced:
                removed.append(key)
                continue
        retained.append(line)
    updated = "".join(retained)
    expected_values = {
        key: value for key, value in original_values.items() if key not in removed
    }
    if dotenv_values(stream=StringIO(updated), interpolate=False) != expected_values:
        raise ValueError(
            "Migration would change unrelated env values; review multiline entries."
        )
    return updated, tuple(removed)


def migrate(root: Path, filename: str, *, apply: bool) -> tuple[str, ...]:
    if filename != ".env":
        raise ValueError(
            "Only the checkout .env can be migrated; review overlays separately."
        )
    target = root / filename
    mode = target.lstat().st_mode
    if not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o600:
        raise ValueError("Env file must be a regular non-symlink file with mode 0600.")
    ignored = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--quiet", filename], check=False
    )
    if ignored.returncode:
        raise ValueError("Env file must be ignored and untracked.")
    original = target.read_text(encoding="utf-8")
    profile = dotenv_values(target, interpolate=False).get(
        "OPEN_WORK_HUB_ENV_PROFILE", ""
    )
    updated, removed = prune_defaults(original, runtime_defaults(root, profile or ""))
    if apply and removed:
        # Keep a private recovery copy; never print its contents.
        backup_fd, backup = tempfile.mkstemp(
            prefix=f"{filename}.backup-config-", dir=root
        )
        with os.fdopen(backup_fd, "w", encoding="utf-8") as stream:
            stream.write(original)
        fd, temporary = tempfile.mkstemp(prefix=f"{filename}.config-", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            if target.read_text(encoding="utf-8") != original:
                raise ValueError(
                    "Env file changed during migration; retry after review."
                )
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Private backup created: {Path(backup).name}")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Apply after reviewing the default dry run"
    )
    args = parser.parse_args()
    try:
        removed = migrate(ROOT, ".env", apply=args.apply)
    except (OSError, ValueError):
        print(
            "Config migration failed; check config, env file ownership/mode and Git exclusion.",
            file=sys.stderr,
        )
        return 1
    print(
        f"{'Removed' if args.apply else 'Would remove'} {len(removed)} redundant public settings."
    )
    for key in removed:
        print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
