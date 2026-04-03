#!/usr/bin/env python3
import json
import pathlib
import sys


PROMPT_HINTS = ("prompt", "workflow")


def deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }
    print(json.dumps(payload))


def main() -> int:
    data = json.load(sys.stdin)
    path = data.get("tool_input", {}).get("file_path", "")
    normalized = path.replace("\\", "/")
    name = pathlib.Path(normalized).name.lower()

    if "legacy_ai_portal_prototype/" in normalized:
        deny("Do not edit legacy_ai_portal_prototype/ files unless the user explicitly asks for it.")
        return 0

    if "/.git/" in normalized or normalized.endswith("/.git"):
        deny("Do not edit .git internals from Claude Code.")
        return 0

    if any(token in name for token in PROMPT_HINTS) or "/prompts/" in normalized or "/workflows/" in normalized:
        deny(
            "Prompt/workflow changes must be paired with scenario and eval updates. Update docs/harness first, then retry."
        )
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
