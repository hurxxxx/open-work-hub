#!/usr/bin/env python3
import json
import pathlib
import sys
from datetime import datetime, timezone


KEYWORDS = ("eval", "regression", "pytest", "benchmark", "scorecard")


def main() -> int:
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    lowered = command.lower()

    if not any(keyword in lowered for keyword in KEYWORDS):
        return 0

    project_dir = pathlib.Path(data.get("cwd", "."))
    state_dir = project_dir / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "event": "eval-command-finished",
        "command": command,
        "trace_hint": "Review scorecard, regressions, and release gate impact before closing the task."
    }

    with (state_dir / "notifications.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=True) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
