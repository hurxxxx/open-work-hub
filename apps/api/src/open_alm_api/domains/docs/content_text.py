from __future__ import annotations

from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any


class _VisibleHtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        normalized = " ".join(data.split()).strip()
        if normalized:
            self.parts.append(normalized)


def html_to_visible_text(content: str | None) -> str:
    if not content:
        return ""
    parser = _VisibleHtmlTextParser()
    parser.feed(content)
    parser.close()
    return " ".join(parser.parts).strip()


def extract_page_text(
    *,
    content_format: str,
    content_blocks: list[dict[str, Any]] | None,
    content_text: str | None,
    block_extractor: Callable[[list[dict[str, Any]] | None], str],
) -> str:
    if content_format == "html":
        return html_to_visible_text(content_text)
    return block_extractor(content_blocks)
