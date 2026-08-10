from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

ChunkAssemblyError = Literal["no_chunks_to_finalize", "chunks_incomplete"]


@dataclass(frozen=True)
class ChunkAssemblyPlan:
    sequences: list[int]
    error: ChunkAssemblyError | None = None


def chunk_sequences(chunks_meta: Mapping[str, object] | None) -> list[int]:
    return sorted(int(seq) for seq in (chunks_meta or {}).keys() if str(seq).isdigit())


def plan_chunk_assembly(
    *,
    chunks_meta: Mapping[str, object] | None,
    highest_seq: int,
) -> ChunkAssemblyPlan:
    if highest_seq < 0:
        return ChunkAssemblyPlan(sequences=[], error="no_chunks_to_finalize")

    sequences = chunk_sequences(chunks_meta)
    expected = list(range(sequences[0], sequences[-1] + 1)) if sequences else []
    if not sequences or sequences != expected:
        return ChunkAssemblyPlan(sequences=sequences, error="chunks_incomplete")

    return ChunkAssemblyPlan(sequences=sequences)
