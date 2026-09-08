from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace
from typing import Protocol

_MAX_EXTRACTED_CHARS = 200_000
_MAX_EXTRACT_SECONDS = 20.0


class UnsupportedDocumentType(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceBlock:
    document_id: str
    block_id: str
    locator_kind: str
    locator_label: str
    section_path: str
    block_kind: str
    text: str
    rows: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _ExtractionBudget:
    """Bounds text extraction by cumulative characters and wall-clock time.

    Shared by every extractor so that no single document (regardless of format)
    can exhaust CPU/memory during parsing.
    """

    max_chars: int = _MAX_EXTRACTED_CHARS
    max_seconds: float = _MAX_EXTRACT_SECONDS
    started_at: float = field(default_factory=time.monotonic)
    chars: int = 0

    def should_continue(self) -> bool:
        return self.chars < self.max_chars and time.monotonic() - self.started_at < self.max_seconds

    def append(self, blocks: list[EvidenceBlock], block: EvidenceBlock) -> bool:
        if not self.should_continue():
            return False
        remaining = self.max_chars - self.chars
        text = block.text[:remaining].strip()
        if not text:
            return False
        if text != block.text:
            block = replace(block, text=text)
        blocks.append(block)
        self.chars += len(text)
        return self.should_continue()


@dataclass(frozen=True)
class DocumentExtractBundle:
    document_id: str
    filename: str
    mime_type: str
    evidence_blocks: list[EvidenceBlock]
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def normalized_text(self) -> str:
        lines: list[str] = []
        for block in self.evidence_blocks:
            lines.append(f"[{block.locator_label}] {block.text}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "evidence_blocks": [block.to_dict() for block in self.evidence_blocks],
            "metadata": dict(self.metadata),
        }


class DocumentExtractor(Protocol):
    def supports(self, *, mime_type: str, filename: str) -> bool: ...

    def extract(
        self,
        *,
        document_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> DocumentExtractBundle: ...
