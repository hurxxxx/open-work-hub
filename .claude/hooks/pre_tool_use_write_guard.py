#!/usr/bin/env python3
import json
import sys


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

    if "legacy_ai_portal_prototype/" in normalized:
        deny("Do not edit legacy_ai_portal_prototype/ files unless the user explicitly asks for it.")
        return 0

    if "/.git/" in normalized or normalized.endswith("/.git"):
        deny("Do not edit .git internals from Claude Code.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
