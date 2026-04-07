#!/usr/bin/env python3
import json
import re
import sys


DANGEROUS_PATTERNS = [
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bgit\s+clean\b.*\b-f\b",
    r"\brm\s+-rf\b",
    r"\bgit\s+push\s+--force\b",
    r"\bgit\s+push\s+-f\b",
]


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
    command = data.get("tool_input", {}).get("command", "")

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            deny(
                "Project policy blocks destructive git commands and git commit/push without an explicit user request."
            )
            return 0

    if "legacy_ai_portal_prototype/" in command and re.search(r"\b(rm|mv|cp|sed|perl|python)\b", command):
        deny("Do not mutate files under legacy_ai_portal_prototype/ unless the user explicitly asks for it.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
