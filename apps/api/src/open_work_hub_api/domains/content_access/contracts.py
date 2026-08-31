from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentStream:
    body: Iterable[bytes]
    media_type: str
    headers: dict[str, str]


__all__ = ["ContentStream"]
