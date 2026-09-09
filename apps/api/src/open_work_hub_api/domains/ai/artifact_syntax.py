"""Pure string helpers for the streaming artifact parser."""

from __future__ import annotations

import re
from typing import Literal

ArtifactTagCandidate = Literal["accept", "wait", "reject"]

ARTIFACT_OPEN_PREFIX = "<artifact"
ARTIFACT_CLOSE_PREFIX = "</artifact"

_ATTR_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*"((?:\\.|[^"\\])*)"')
# Characters that can legally follow `<artifact` / `</artifact` in a valid
# tag (whitespace, self-close, tag-end). Anything else means we're looking at
# a different tag name that happens to share the prefix, such as `<artifacts>`.
_TAG_BOUNDARY_CHARS = frozenset(" \t\n\r\f\v>/")


def classify_artifact_tag_candidate(
    buffer: str,
    prefix: str,
) -> ArtifactTagCandidate:
    """Classify whether ``buffer`` starts with a complete artifact tag prefix."""
    if buffer.startswith(prefix):
        if len(buffer) == len(prefix):
            return "wait"
        return "accept" if buffer[len(prefix)] in _TAG_BOUNDARY_CHARS else "reject"
    if len(buffer) < len(prefix) and prefix.startswith(buffer):
        return "wait"
    return "reject"


def trailing_backtick_run(buffer: str) -> int:
    """Count how many backticks end ``buffer``."""
    count = 0
    for ch in reversed(buffer):
        if ch == "`":
            count += 1
        else:
            break
    return count


def advance_line_prefix(prefix: str, text: str) -> str:
    for ch in text:
        if ch == "\n":
            prefix = ""
        else:
            prefix += ch
    return prefix


def is_indented_code_prefix(prefix: str) -> bool:
    if not prefix or any(ch not in {" ", "\t"} for ch in prefix):
        return False
    indent = 0
    for ch in prefix:
        indent += 4 if ch == "\t" else 1
    return indent >= 4


def looks_like_inline_example_prefix(prefix: str) -> bool:
    return prefix.rstrip().endswith((":", "："))


def find_artifact_tag_end_index(buffer: str, start: int) -> int | None:
    """Return the terminating ``>`` index while honoring quoted values."""
    in_quotes = False
    i = start
    length = len(buffer)
    while i < length:
        ch = buffer[i]
        if in_quotes and ch == "\\":
            i += 2
            continue
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ">" and not in_quotes:
            return i
        i += 1
    return None


def parse_artifact_attrs(open_tag: str) -> dict[str, str]:
    """Pull strict ``key=\"value\"`` attributes from an artifact tag."""
    return {
        match.group(1): _unescape_attr_value(match.group(2))
        for match in _ATTR_RE.finditer(open_tag)
    }


def _unescape_attr_value(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value) and value[i + 1] in {'"', "\\"}:
            out.append(value[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)
