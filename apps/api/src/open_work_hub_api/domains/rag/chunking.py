from __future__ import annotations

import re
from dataclasses import dataclass

from open_work_hub_api.domains.rag.contracts import RagChunk, RagProjection
from open_work_hub_api.domains.rag.sparse_terms import (
    build_korean_sparse_terms as build_korean_sparse_terms,
)
from open_work_hub_api.domains.rag.sparse_terms import (
    tokenize_sparse_terms as tokenize_sparse_terms,
)

DEFAULT_TARGET_CHARS = 900
DEFAULT_HARD_MAX_CHARS = 1400
DEFAULT_OVERLAP_CHARS = 160
DEFAULT_MIN_CHARS = 240
DEFAULT_INDEX_TEXT_MAX_CHARS = 2400


@dataclass(frozen=True)
class ChunkTextSpan:
    text: str
    start: int
    end: int


def default_korean_aware_chunks(
    projection: RagProjection,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    hard_max_chars: int = DEFAULT_HARD_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[RagChunk]:
    raw_text = projection.text_content.strip() or (projection.summary or "").strip()
    if not raw_text:
        raw_text = projection.title or projection.resource_id

    pieces = split_korean_aware_text(
        raw_text,
        target_chars=target_chars,
        hard_max_chars=hard_max_chars,
        overlap_chars=overlap_chars,
    )
    chunks: list[RagChunk] = []
    for index, piece in enumerate(pieces):
        text = piece.strip()
        if not text:
            continue
        chunks.append(
            RagChunk(
                chunk_id=f"{projection.resource_id}:{index}",
                text=text,
                summary=_summarize_text(text),
                index_text=build_contextual_index_text(
                    title=projection.title,
                    summary=projection.summary,
                    body=text,
                ),
                metadata={
                    "resource_type": projection.resource_type,
                    "resource_id": projection.resource_id,
                    "source_kind": projection.source_kind,
                    "scope_kind": projection.scope_kind.value,
                    "chunk_index": index,
                    "chunk_strategy": "default_korean_v1",
                },
            )
        )
    if chunks:
        return chunks
    return [
        RagChunk(
            chunk_id=f"{projection.resource_id}:0",
            text=projection.resource_id,
            summary=projection.title or projection.resource_id,
            index_text=build_contextual_index_text(
                title=projection.title,
                summary=projection.summary,
                body=projection.resource_id,
            ),
            metadata={
                "resource_type": projection.resource_type,
                "resource_id": projection.resource_id,
                "source_kind": projection.source_kind,
                "scope_kind": projection.scope_kind.value,
                "chunk_index": 0,
                "chunk_strategy": "default_korean_v1",
            },
        )
    ]


def split_korean_aware_text(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    hard_max_chars: int = DEFAULT_HARD_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[str]:
    return [
        chunk.text
        for chunk in split_korean_aware_text_spans(
            text,
            target_chars=target_chars,
            hard_max_chars=hard_max_chars,
            overlap_chars=overlap_chars,
            min_chars=min_chars,
        )
    ]


def split_korean_aware_text_spans(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    hard_max_chars: int = DEFAULT_HARD_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[ChunkTextSpan]:
    units = _text_units(text, hard_max_chars=hard_max_chars)
    if not units:
        return []

    chunks: list[ChunkTextSpan] = []
    current: list[ChunkTextSpan] = []
    current_len = 0

    def flush(*, keep_overlap: bool) -> None:
        nonlocal current, current_len
        piece = _compose_text(text, current)
        if piece:
            start = min(unit.start for unit in current)
            end = max(unit.end for unit in current)
            chunks.append(ChunkTextSpan(text=piece, start=start, end=end))
        overlap = (
            _tail_overlap_span(text, chunks[-1], overlap_chars)
            if keep_overlap and chunks and overlap_chars > 0
            else None
        )
        current = [overlap] if overlap is not None else []
        current_len = len(overlap.text) if overlap is not None else 0

    def trim_overlap_for(unit: ChunkTextSpan) -> None:
        nonlocal current, current_len
        if not current:
            return
        if len(_compose_text(text, [*current, unit])) <= hard_max_chars:
            return
        overlap = current[-1]
        start = max(overlap.start, unit.end - hard_max_chars)
        if start >= overlap.end:
            current = []
            current_len = 0
            return
        trimmed = _stripped_span(text, start, overlap.end)
        current = [trimmed] if trimmed is not None else []
        current_len = len(trimmed.text) if trimmed is not None else 0

    for index, unit in enumerate(units):
        unit_len = len(unit.text)
        proposed_len = len(_compose_text(text, [*current, unit])) if current else unit_len
        if current and proposed_len > target_chars and current_len >= min_chars:
            flush(keep_overlap=True)
        trim_overlap_for(unit)
        proposed_len = len(_compose_text(text, [*current, unit])) if current else unit_len
        if current and proposed_len > hard_max_chars:
            flush(keep_overlap=True)
            trim_overlap_for(unit)
        current.append(unit)
        current_len = len(_compose_text(text, current))
        if current_len >= hard_max_chars:
            flush(keep_overlap=index < len(units) - 1)

    if current:
        flush(keep_overlap=False)

    return chunks


def build_contextual_index_text(
    *,
    title: str | None,
    body: str,
    summary: str | None = None,
    page_title: str | None = None,
    section_path: list[str] | None = None,
    max_chars: int = DEFAULT_INDEX_TEXT_MAX_CHARS,
) -> str:
    header: list[str] = []
    normalized_title = _clip_text(title, 180)
    if normalized_title:
        header.append(f"문서 제목: {normalized_title}")
    normalized_summary = _clip_text(summary, 360)
    if normalized_summary:
        header.append(f"문서 요약: {normalized_summary}")
    normalized_page_title = _clip_text(page_title, 240)
    if normalized_page_title:
        header.append(f"페이지 제목: {normalized_page_title}")
    normalized_section_path = [
        part for raw_part in section_path or [] if (part := _clip_text(raw_part, 120))
    ]
    if normalized_section_path:
        header.append(f"섹션 경로: {' > '.join(normalized_section_path)}")
    normalized_body = body.strip()
    if header:
        prefix = "\n".join([*header, "본문:"]).strip()
        return _join_prefix_and_body(prefix, normalized_body, max_chars=max_chars)
    return _clip_text(normalized_body, max_chars) or ""


def _text_units(text: str, *, hard_max_chars: int) -> list[ChunkTextSpan]:
    paragraphs = _paragraph_spans(text)
    units: list[ChunkTextSpan] = []
    for paragraph in paragraphs:
        if len(paragraph.text) <= hard_max_chars:
            units.append(paragraph)
            continue
        units.extend(_split_long_text(paragraph, source=text, hard_max_chars=hard_max_chars))
    return units


def _split_long_text(
    paragraph: ChunkTextSpan,
    *,
    source: str,
    hard_max_chars: int,
) -> list[ChunkTextSpan]:
    sentences = _split_sentences(paragraph, source=source)
    pieces: list[ChunkTextSpan] = []
    current_start: int | None = None
    current_end: int | None = None
    for sentence in sentences:
        if len(sentence.text) > hard_max_chars:
            if current_start is not None and current_end is not None:
                current = _stripped_span(source, current_start, current_end)
                if current is not None:
                    pieces.append(current)
                current_start = None
                current_end = None
            pieces.extend(
                chunk
                for index in range(sentence.start, sentence.end, hard_max_chars)
                if (
                    chunk := _stripped_span(
                        source, index, min(index + hard_max_chars, sentence.end)
                    )
                )
                is not None
            )
            continue
        if (
            current_start is not None
            and current_end is not None
            and sentence.end - current_start > hard_max_chars
        ):
            current = _stripped_span(source, current_start, current_end)
            if current is not None:
                pieces.append(current)
            current_start = sentence.start
            current_end = sentence.end
            continue
        current_start = sentence.start if current_start is None else current_start
        current_end = sentence.end
    if current_start is not None and current_end is not None:
        current = _stripped_span(source, current_start, current_end)
        if current is not None:
            pieces.append(current)
    return pieces


def _split_sentences(paragraph: ChunkTextSpan, *, source: str) -> list[ChunkTextSpan]:
    relative = source[paragraph.start : paragraph.end]
    sentences: list[ChunkTextSpan] = []
    start = paragraph.start
    for match in re.finditer(r"(?<=[.!?。！？])\s+", relative):
        end = paragraph.start + match.start()
        sentence = _stripped_span(source, start, end)
        if sentence is not None:
            sentences.append(sentence)
        start = paragraph.start + match.end()
    sentence = _stripped_span(source, start, paragraph.end)
    if sentence is not None:
        sentences.append(sentence)
    return sentences


def _paragraph_spans(text: str) -> list[ChunkTextSpan]:
    spans: list[ChunkTextSpan] = []
    start = 0
    for match in re.finditer(r"\n\s*\n", text):
        paragraph = _stripped_span(text, start, match.start())
        if paragraph is not None:
            spans.append(paragraph)
        start = match.end()
    paragraph = _stripped_span(text, start, len(text))
    if paragraph is not None:
        spans.append(paragraph)
    return spans


def _compose_text(source: str, units: list[ChunkTextSpan]) -> str:
    if not units:
        return ""
    start = min(unit.start for unit in units)
    end = max(unit.end for unit in units)
    return source[start:end].strip()


def _tail_overlap_span(
    source: str,
    chunk: ChunkTextSpan,
    overlap_chars: int,
) -> ChunkTextSpan | None:
    if overlap_chars <= 0:
        return None
    start = max(chunk.start, chunk.end - overlap_chars)
    return _stripped_span(source, start, chunk.end)


def _stripped_span(source: str, start: int, end: int) -> ChunkTextSpan | None:
    start = max(start, 0)
    end = min(end, len(source))
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    return ChunkTextSpan(text=source[start:end].strip(), start=start, end=end)


def _summarize_text(text: str, *, max_chars: int = 160) -> str:
    normalized = " ".join(text.split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _clip_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _join_prefix_and_body(prefix: str, body: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if not prefix:
        return _clip_text(body, max_chars) or ""
    if len(prefix) >= max_chars:
        return _clip_text(prefix, max_chars) or ""
    separator = "\n"
    remaining = max_chars - len(prefix) - len(separator)
    if remaining <= 0:
        return _clip_text(prefix, max_chars) or ""
    clipped_body = _clip_text(body, remaining) or ""
    if not clipped_body:
        return prefix
    return f"{prefix}{separator}{clipped_body}".strip()
