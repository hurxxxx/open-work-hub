#!/usr/bin/env python3
import json
import pathlib
import sys
from datetime import datetime, timezone


def main() -> int:
    data = json.load(sys.stdin)
    project_dir = pathlib.Path(data.get("cwd", "."))
    state_dir = project_dir / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {})
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "hook_event_name": data.get("hook_event_name"),
        "tool_name": tool_name,
        "path": tool_input.get("file_path"),
        "command": tool_input.get("command")
    }

    lowered_path = (tool_input.get("file_path") or "").replace("\\", "/").lower()
    lowered_command = (tool_input.get("command") or "").lower()
    payload["needs_regression_attention"] = any(
        token in lowered_path for token in [
            "docs/harness/",
            ".claude/",
            ".github/copilot-instructions.md",
            ".cursor/rules/",
            "claude.md"
        ]
    ) or any(token in lowered_command for token in ["eval", "pytest", "benchmark", "regression", "scorecard"])

    with (state_dir / "post-tool-use.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=True) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
