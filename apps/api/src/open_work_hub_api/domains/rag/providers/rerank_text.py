from __future__ import annotations

import re
from typing import Any

from open_work_hub_api.domains.rag.contracts import RagVectorSearchHit

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def build_rerank_document_text(hit: RagVectorSearchHit, *, max_chars: int = 2000) -> str:
    metadata = dict(hit.metadata or {})
    context_lines: list[str] = []

    title = _clean(hit.projection.title, max_chars=240)
    if title:
        context_lines.append(f"Title: {title}")

    summary = _clean(hit.summary or hit.projection.summary, max_chars=360)
    if summary:
        context_lines.append(f"Summary: {summary}")

    page_title = _clean(_metadata_value(metadata.get("page_title")), max_chars=240)
    if page_title:
        context_lines.append(f"Page: {page_title}")

    section_path = _metadata_path(metadata.get("section_path"))
    if section_path:
        context_lines.append(f"Section: {section_path}")

    excerpt = _clean(hit.text, max_chars=1400)
    if not context_lines:
        return _clean(excerpt or hit.text, max_chars=max_chars) or ""

    lines = list(context_lines)
    if excerpt:
        lines.append(f"Excerpt: {excerpt}")

    return _clean("\n".join(lines) or hit.text, max_chars=max_chars) or ""


def _metadata_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _metadata_path(value: Any) -> str | None:
    if isinstance(value, list):
        parts = [_clean(_metadata_value(part), max_chars=120) for part in value]
        return " > ".join(part for part in parts if part)
    return _clean(_metadata_value(value), max_chars=360)


def _clean(value: str | None, *, max_chars: int) -> str | None:
    if value is None:
        return None
    normalized = _CONTROL_CHARS.sub(" ", value).replace("```", "` ` `")
    normalized = " ".join(normalized.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
