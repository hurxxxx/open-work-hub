from __future__ import annotations

from typing import Any

from open_alm_api.core.asr_contracts import TranscriptResult, TranscriptSegment


def parse_transcript_payload(
    payload: dict[str, Any],
    *,
    language_hint: str | None = None,
) -> TranscriptResult:
    return TranscriptResult(
        text=payload_text(payload).strip(),
        segments=payload_segments(payload),
        language=payload_string(payload, "language") or language_hint,
        duration_sec=payload_float(payload, "duration_sec") or payload_float(payload, "duration"),
    )


def payload_text(payload: dict[str, Any]) -> str:
    result = payload.get("results")
    candidates = [
        payload.get("text"),
        payload.get("transcript"),
        result.get("text") if isinstance(result, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    segments = payload_segments(payload)
    return " ".join(segment.text for segment in segments if segment.text).strip()


def payload_segments(payload: dict[str, Any]) -> list[TranscriptSegment]:
    result = payload.get("results")
    raw_segments = payload.get("segments")
    if raw_segments is None and isinstance(result, dict):
        raw_segments = result.get("segments") or result.get("chunks")
    if raw_segments is None:
        raw_segments = payload.get("chunks")
    if not isinstance(raw_segments, list):
        return []

    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp")
        start = segment_time(item, "start", timestamp, 0)
        end = segment_time(item, "end", timestamp, 1)
        segments.append(
            TranscriptSegment(
                start=start,
                end=max(start, end),
                text=str(item.get("text") or item.get("sentence") or "").strip(),
            )
        )
    return segments


def segment_time(item: dict[str, Any], key: str, timestamp: Any, index: int) -> float:
    if key in item:
        return coerce_float(item.get(key))
    if isinstance(timestamp, (list, tuple)) and len(timestamp) > index:
        return coerce_float(timestamp[index])
    return 0.0


def payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def payload_float(payload: dict[str, Any], key: str) -> float | None:
    if key not in payload:
        return None
    return coerce_float(payload.get(key))


def coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
