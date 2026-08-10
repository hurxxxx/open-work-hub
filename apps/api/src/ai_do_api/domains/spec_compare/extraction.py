from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from ai_do_api.domains.document_processing import DocumentExtractBundle, EvidenceBlock


_SPEC_EXTRACTION_CHUNK_MAX_CHARS = 30_000
_KEY_VALUE_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z0-9가-힣][^:：=]{1,90})\s*[:：=]\s*(?P<value>.+?)\s*$"
)
_UNIT_RE = re.compile(
    r"\b(?:mm|cm|m|kg|g|w|kw|v|hz|pa|kpa|mpa|rpm|ea|%|℃|°c)\b",
    re.I,
)
_NUMERIC_OR_UNIT_RE = re.compile(
    r"\d|mm|cm|kg|g|kw|w|v|hz|db|℃|°c|pa|kpa|mpa|rpm|ea|%|cmh|㎥|sec|초|분",
    re.I,
)
_MEASUREMENT_UNIT_RE = re.compile(
    r"\d[\d,.\s~/-]*(?:mm|cm|kg|kw|w|v|hz|db|pa|kpa|mpa|rpm|ea|cmh|kph|"
    r"sec|초|분|㎥|℃|°c|%)",
    re.I,
)
_GENERIC_TABLE_KEY_RE = re.compile(
    r"\bColumn\b|^\d+\s+(?:비고|내용|구분|P/NAME|P/NO|SPEC NO)$",
    re.I,
)
_INDEXED_TABLE_KEY_RE = re.compile(
    r"^\d+\s+(?:목표|환경규제|비고|재질|공법|U/S|C/O|P/NAME|P/NO|END ITEM|SIZE|중량)",
    re.I,
)
_HEADING_ONLY_RE = re.compile(
    r"^(?:\d+(?:\.\d+)+\.?\s*[^:=]{0,80}|표\s*\d+\.?|-\s*계속|<[^>]+>)"
)
_REPORT_KEYWORD_RE = re.compile(
    r"출력|전압|전류|방열|냉방|난방|풍량|소음|중량|무게|SIZE|크기|길이|폭|높이|"
    r"법규|인증|보안|통신|CAN|LIN|Ethernet|이더넷|센서|HEATER|PTC|HVAC|"
    r"BLOWER|FILTER|AIR|A/C|전석|후석|사양|성능|요구|중금속|Recycle",
    re.I,
)
_TABLE_HEADER_HINT_RE = re.compile(
    r"^(?:NO|번호|항목|구분|내용|값|단위|사양|SPEC|END ITEM|P/NO|P/NAME|U/S|C/O|"
    r"재질|공법|비고|목표|환경규제|품명|부품명|ITEM|DESCRIPTION)$",
    re.I,
)
_TABLE_HELPER_CELL_RE = re.compile(r"^(?:sub\d+|concept drawing)$", re.I)
_PART_NUMBER_RE = re.compile(
    r"^(?:\d{5}[-\s]?[A-Z0-9]{2,}|[A-Z0-9]+-[A-Z0-9]+)$",
    re.I,
)
_TABLE_SUBJECT_HEADERS = (
    "P/NAME",
    "품명",
    "부품명",
    "항목",
    "구분",
    "ITEM",
    "DESCRIPTION",
    "사양",
)
_LOW_VALUE_HEADERS = {"NO", "번호", "END ITEM"}
_VALUE_UNIT_RE = re.compile(
    r"(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>mm|cm|kg|g|kw|w|v|hz|db|"
    r"pa|kpa|mpa|rpm|ea|cmh|kph|sec|㎥/h|㎥|℃|°c|%)",
    re.I,
)


@dataclass(frozen=True)
class DocumentMarkdownChunk:
    chunk_id: str
    document_id: str
    section_path: str
    locator_label: str
    evidence_ids: list[str]
    markdown: str

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "section": self.section_path,
            "locator": self.locator_label,
            "evidence_ids": self.evidence_ids,
            "markdown": self.markdown,
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SpecCandidate:
    candidate_id: str
    document_id: str
    spec_name: str
    value: str
    evidence_id: str
    locator_label: str
    section_path: str

    def to_prompt_dict(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "spec_name": self.spec_name,
            "value": self.value,
            "evidence_id": self.evidence_id,
            "locator": self.locator_label,
            "section": self.section_path,
        }


@dataclass(frozen=True)
class SpecItem:
    item_id: str
    document_id: str
    category: str
    item_name: str
    value: str
    unit: str
    condition: str
    evidence_id: str
    locator_label: str
    section_path: str
    source_text: str
    confidence: float
    extraction_method: str

    def to_candidate(self) -> SpecCandidate:
        return SpecCandidate(
            candidate_id=self.item_id,
            document_id=self.document_id,
            spec_name=self.item_name[:300],
            value=join_value_unit(self.value, self.unit)[:1000],
            evidence_id=self.evidence_id,
            locator_label=self.locator_label,
            section_path=self.section_path,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_document_markdown_chunks(bundle: DocumentExtractBundle) -> list[DocumentMarkdownChunk]:
    blocks = [block for block in bundle.evidence_blocks if _block_has_spec_signal(block)]
    chunks: list[DocumentMarkdownChunk] = []
    pending: list[EvidenceBlock] = []
    pending_chars = 0
    for block in blocks:
        block_markdown = _evidence_block_to_markdown(block)
        if pending and pending_chars + len(block_markdown) > _SPEC_EXTRACTION_CHUNK_MAX_CHARS:
            chunks.append(_build_markdown_chunk(bundle.document_id, len(chunks) + 1, pending))
            pending = []
            pending_chars = 0
        pending.append(block)
        pending_chars += len(block_markdown)
    if pending:
        chunks.append(_build_markdown_chunk(bundle.document_id, len(chunks) + 1, pending))
    return chunks


def build_deterministic_spec_items(bundle: DocumentExtractBundle) -> list[SpecItem]:
    items: list[SpecItem] = []
    seen: set[tuple[str, str, str]] = set()
    for block in bundle.evidence_blocks:
        for spec_name, raw_value in _candidates_from_block(block):
            if not _looks_like_structured_spec_item(spec_name, raw_value):
                continue
            value, unit = split_value_unit(raw_value)
            key = (normalize_spec_key(spec_name), normalize_spec_value(value), block.block_id)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                SpecItem(
                    item_id=f"{bundle.document_id}:spec:{len(items) + 1}",
                    document_id=bundle.document_id,
                    category=block.section_path,
                    item_name=spec_name[:300],
                    value=value[:1000],
                    unit=unit[:80],
                    condition="",
                    evidence_id=block.block_id,
                    locator_label=block.locator_label,
                    section_path=block.section_path,
                    source_text=(raw_value or block.text)[:1200],
                    confidence=0.55,
                    extraction_method="deterministic",
                )
            )
    return items


def merge_spec_items(primary: list[SpecItem], coverage: list[SpecItem]) -> list[SpecItem]:
    merged: list[SpecItem] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in [*primary, *coverage]:
        key = (
            item.document_id,
            item.evidence_id,
            normalize_spec_key(item.item_name),
            compact_spec_value(join_value_unit(item.value, item.unit)),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return [
        SpecItem(
            item_id=f"{item.document_id}:spec:{index}",
            document_id=item.document_id,
            category=item.category,
            item_name=item.item_name,
            value=item.value,
            unit=item.unit,
            condition=item.condition,
            evidence_id=item.evidence_id,
            locator_label=item.locator_label,
            section_path=item.section_path,
            source_text=item.source_text,
            confidence=item.confidence,
            extraction_method=item.extraction_method,
        )
        for index, item in enumerate(merged, start=1)
    ]


def build_spec_candidates(bundle: DocumentExtractBundle) -> list[SpecCandidate]:
    candidates: list[SpecCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for block in bundle.evidence_blocks:
        for spec_name, value in _candidates_from_block(block):
            normalized = (normalize_spec_key(spec_name), value.casefold(), block.block_id)
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(
                SpecCandidate(
                    candidate_id=f"{bundle.document_id}:c{len(candidates) + 1}",
                    document_id=bundle.document_id,
                    spec_name=spec_name[:300],
                    value=value[:1000],
                    evidence_id=block.block_id,
                    locator_label=block.locator_label,
                    section_path=block.section_path,
                )
            )
    return candidates


def split_value_unit(value: str, *, preferred_unit: str = "") -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", value).strip()
    unit = preferred_unit.strip()
    if not unit:
        match = _VALUE_UNIT_RE.search(cleaned)
        if match:
            unit = match.group("unit")
    return cleaned, unit


def join_value_unit(value: str, unit: str) -> str:
    value = value.strip()
    unit = unit.strip()
    if not value or not unit:
        return value
    if unit.casefold() in value.casefold():
        return value
    return f"{value} {unit}"


def normalize_spec_key(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", value.casefold())


def normalize_spec_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def compact_spec_value(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value.casefold())


def is_date_or_identifier_only(value: str) -> bool:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return bool(
        re.fullmatch(r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}", cleaned)
        or re.fullmatch(r"[A-Z]{1,5}\d?[A-Z]?", cleaned)
        or re.fullmatch(r"(?:XV|LW)[A-Z0-9()’.'\-\s]+", cleaned)
    )


def _block_has_spec_signal(block: EvidenceBlock) -> bool:
    if block.block_kind == "table" and block.rows:
        return True
    text = block.text or ""
    return bool(_NUMERIC_OR_UNIT_RE.search(text) or _REPORT_KEYWORD_RE.search(text))


def _build_markdown_chunk(
    document_id: str,
    chunk_index: int,
    blocks: list[EvidenceBlock],
) -> DocumentMarkdownChunk:
    first = blocks[0]
    markdown = "\n\n".join(_evidence_block_to_markdown(block) for block in blocks)
    return DocumentMarkdownChunk(
        chunk_id=f"{document_id}:chunk:{chunk_index}",
        document_id=document_id,
        section_path=first.section_path,
        locator_label=f"{first.locator_label} 외 {max(0, len(blocks) - 1)}개",
        evidence_ids=[block.block_id for block in blocks],
        markdown=markdown,
    )


def _evidence_block_to_markdown(block: EvidenceBlock) -> str:
    header = (
        f"### evidence_id={block.block_id} | locator={block.locator_label} | "
        f"section={block.section_path}"
    )
    if block.block_kind == "table" and block.rows:
        return f"{header}\n\n{_rows_to_markdown_table(block.rows)}"
    return f"{header}\n\n{block.text.strip()}"


def _rows_to_markdown_table(rows: list[list[str]]) -> str:
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return ""
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = [_markdown_cell(cell) for cell in padded[0]]
    body = padded[1:] if len(padded) > 1 else []
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _markdown_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", "<br />")


def _looks_like_structured_spec_item(spec_name: str, value: str) -> bool:
    name = spec_name.strip()
    raw_value = value.strip()
    if not name or not raw_value:
        return False
    if _GENERIC_TABLE_KEY_RE.search(name) or _INDEXED_TABLE_KEY_RE.search(name):
        return False
    if is_date_or_identifier_only(name) and is_date_or_identifier_only(raw_value):
        return False
    if compact_spec_value(name) == compact_spec_value(raw_value) and not (
        _MEASUREMENT_UNIT_RE.search(raw_value) or _PART_NUMBER_RE.search(raw_value)
    ):
        return False
    if _HEADING_ONLY_RE.match(name) and not (
        _MEASUREMENT_UNIT_RE.search(raw_value) or _PART_NUMBER_RE.search(raw_value)
    ):
        return False
    return bool(
        _MEASUREMENT_UNIT_RE.search(raw_value)
        or _PART_NUMBER_RE.search(raw_value)
        or _REPORT_KEYWORD_RE.search(f"{name} {raw_value}")
    )


def _candidates_from_block(block: EvidenceBlock) -> list[tuple[str, str]]:
    if block.block_kind == "table" and block.rows:
        return _candidates_from_table(block.rows)

    out: list[tuple[str, str]] = []
    for line in _split_candidate_lines(block.text):
        parsed = _parse_key_value(line)
        if parsed is not None:
            out.append(parsed)
        elif _looks_like_spec_line(line):
            out.append((_line_label(line), line))
    return out


def _candidates_from_table(rows: list[list[str]]) -> list[tuple[str, str]]:
    if not rows:
        return []
    out: list[tuple[str, str]] = []
    header_index, header = _detect_table_header(rows)
    data_rows = rows[header_index + 1 :] if header else rows
    for row in data_rows:
        if _is_table_helper_row(row):
            continue
        if len(row) == 1:
            line = row[0]
            parsed = _parse_key_value(line)
            if parsed is not None:
                out.append(parsed)
            elif _looks_like_spec_line(line):
                out.append((_line_label(line), line))
            continue
        if header:
            aligned = _align_table_row(header, row)
            if _is_two_column_value_table(aligned):
                filled = [(column, value) for column, value in aligned if value]
                subject = filled[0][1]
                value = filled[1][1]
                if subject and value:
                    out.append((subject, value))
                continue
            subject = _table_subject(aligned) or row[0]
            subject_header = _normalize_header(
                next(
                    (
                        column
                        for column, value in aligned
                        if value and _normalize_cell(value) == _normalize_cell(subject)
                    ),
                    "",
                )
            )
            for column, value in aligned:
                normalized_column = _normalize_header(column)
                if not value or normalized_column in _LOW_VALUE_HEADERS:
                    continue
                if subject_header and normalized_column == subject_header:
                    continue
                label = f"{subject} {column}".strip()
                out.append((label, value))
            continue
        row_label = row[0]
        for index, value in enumerate(row[1:], start=1):
            if not value:
                continue
            column = header[index] if index < len(header) and header[index] else f"Column {index + 1}"
            label = f"{row_label} {column}".strip()
            out.append((label, value))
    return out


def _detect_table_header(rows: list[list[str]]) -> tuple[int, list[str]]:
    best: tuple[int, int, list[str]] | None = None
    for index, row in enumerate(rows[:8]):
        if len(row) < 2 or _is_table_helper_row(row):
            continue
        score = sum(1 for cell in row if _is_header_cell(cell))
        if score < 2:
            continue
        if best is None or score > best[1]:
            best = (index, score, row)
    if best is None:
        return 0, []
    return best[0], best[2]


def _is_header_cell(value: str) -> bool:
    normalized = _normalize_header(value)
    return bool(_TABLE_HEADER_HINT_RE.search(normalized) or "목표" in normalized)


def _is_table_helper_row(row: list[str]) -> bool:
    if not row:
        return True
    return all(_TABLE_HELPER_CELL_RE.match(cell.strip()) for cell in row if cell.strip())


def _align_table_row(header: list[str], row: list[str]) -> list[tuple[str, str]]:
    if not header:
        return [(f"Column {index + 1}", value) for index, value in enumerate(row)]
    if len(row) == len(header):
        return list(zip(header, row, strict=False))

    normalized_header = [_normalize_header(cell) for cell in header]
    if "P/NO" in normalized_header and "P/NAME" in normalized_header:
        pno_index = normalized_header.index("P/NO")
        pname_index = normalized_header.index("P/NAME")
        if len(row) >= 2 and _looks_like_part_number(row[1]):
            return _zip_from_offset(header, row, max(0, pno_index - 1))
        if len(row) >= 2 and not _looks_like_part_number(row[1]):
            mapped = _zip_from_offset(header, [row[0], "", *row[1:]], max(0, pno_index - 1))
            if len(mapped) >= pname_index + 1:
                return mapped
    if len(row) == len(header) - 1 and _normalize_header(header[0]) in {"NO", "번호"}:
        return list(zip(header[1:], row, strict=False))
    return list(zip(header, row, strict=False))


def _zip_from_offset(header: list[str], row: list[str], offset: int) -> list[tuple[str, str]]:
    selected = header[offset : offset + len(row)]
    return list(zip(selected, row, strict=False))


def _looks_like_part_number(value: str) -> bool:
    return bool(_PART_NUMBER_RE.match(value.strip()))


def _table_subject(aligned: list[tuple[str, str]]) -> str:
    for preferred_header in _TABLE_SUBJECT_HEADERS:
        for column, value in aligned:
            if _normalize_header(column) == _normalize_header(preferred_header) and value:
                return value
    for column, value in aligned:
        if _normalize_header(column) not in _LOW_VALUE_HEADERS and value:
            return value
    return ""


def _is_two_column_value_table(aligned: list[tuple[str, str]]) -> bool:
    filled = [(column, value) for column, value in aligned if value]
    if len(filled) != 2:
        return False
    first_header = _normalize_header(filled[0][0])
    second_header = _normalize_header(filled[1][0])
    return first_header in {
        "항목",
        "구분",
        "사양",
        "ITEM",
        "DESCRIPTION",
    } and second_header in {"값", "VALUE", "내용", "SPEC"}


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().upper()


def _normalize_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _split_candidate_lines(text: str) -> list[str]:
    raw_lines: list[str] = []
    for line in text.splitlines():
        raw_lines.extend(part.strip() for part in re.split(r"\s{2,}|[;•]", line))
    return [line for line in raw_lines if len(line) >= 3]


def _parse_key_value(line: str) -> tuple[str, str] | None:
    match = _KEY_VALUE_RE.match(line)
    if not match:
        return None
    key = re.sub(r"\s+", " ", match.group("key")).strip(" -")
    value = re.sub(r"\s+", " ", match.group("value")).strip()
    if len(key) < 2 or not value:
        return None
    return key, value


def _looks_like_spec_line(line: str) -> bool:
    if len(line) > 160:
        return False
    return bool(_UNIT_RE.search(line) or re.search(r"\d", line))


def _line_label(line: str) -> str:
    words = line.split()
    if len(words) <= 5:
        return line
    return " ".join(words[:5])
