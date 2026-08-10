"""Artifact stream parser output projection into serialized SSE envelopes."""

from __future__ import annotations

from typing import Any, Protocol

from ai_do_api.domains.ai.artifact_parser import (
    ArtifactStreamParser,
    ParsedArtifactBody,
    ParsedArtifactEnd,
    ParsedArtifactStart,
    ParsedText,
)
from ai_do_api.domains.ai.events import EnvelopeEncoder, make_envelope, serialize_sse


class AssistantEventObserver(Protocol):
    def observe(self, event_dict: dict[str, str]) -> None: ...


def parser_events_to_envelopes(
    parsed_events: list[Any],
    *,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    """Turn ArtifactStreamParser output into serialized SSE envelopes."""

    envelopes: list[dict[str, str]] = []
    for parsed in parsed_events:
        if isinstance(parsed, ParsedText):
            if not parsed.text:
                continue
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "content_delta",
                        encoder.next_seq(),
                        {"text": parsed.text},
                    )
                )
            )
        elif isinstance(parsed, ParsedArtifactStart):
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "artifact_started",
                        encoder.next_seq(),
                        {
                            "artifact_id": parsed.artifact_id,
                            "artifact_type": parsed.attrs.get("type", "document"),
                            "title": parsed.attrs.get("title"),
                            "language": parsed.attrs.get("language"),
                        },
                    )
                )
            )
        elif isinstance(parsed, ParsedArtifactBody):
            if not parsed.text:
                continue
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "artifact_delta",
                        encoder.next_seq(),
                        {
                            "artifact_id": parsed.artifact_id,
                            "delta": parsed.text,
                        },
                    )
                )
            )
        elif isinstance(parsed, ParsedArtifactEnd):
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "artifact_completed",
                        encoder.next_seq(),
                        {"artifact_id": parsed.artifact_id},
                    )
                )
            )
    return envelopes


def emit_content_through_parser(
    text: str,
    *,
    parser: ArtifactStreamParser,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    return parser_events_to_envelopes(parser.feed(text), encoder=encoder)


def flush_parser(
    parser: ArtifactStreamParser,
    *,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    return parser_events_to_envelopes(parser.flush(), encoder=encoder)


def serialize_agent_event_through_artifacts(
    *,
    event: Any,
    artifact_parser: ArtifactStreamParser,
    buffer: AssistantEventObserver,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    if event.type == "done":
        flushed_envelopes = flush_parser(artifact_parser, encoder=encoder)
        out: list[dict[str, str]] = []
        for flushed in flushed_envelopes:
            buffer.observe(flushed)
            out.append(flushed)
        if flushed_envelopes:
            reissued = serialize_sse(
                make_envelope(
                    "done",
                    encoder.next_seq(),
                    event.data.model_dump(),
                    timestamp_ms=event.timestamp_ms,
                )
            )
            buffer.observe(reissued)
            out.append(reissued)
            return out
        serialized = serialize_sse(event)
        buffer.observe(serialized)
        out.append(serialized)
        return out

    if event.type == "content_delta":
        text = event.data.text
        parsed_events = artifact_parser.feed(text)
        if (
            len(parsed_events) == 1
            and isinstance(parsed_events[0], ParsedText)
            and parsed_events[0].text == text
        ):
            serialized = serialize_sse(event)
            buffer.observe(serialized)
            return [serialized]

        out: list[dict[str, str]] = []
        for parsed_out in parser_events_to_envelopes(parsed_events, encoder=encoder):
            buffer.observe(parsed_out)
            out.append(parsed_out)
        return out

    serialized = serialize_sse(event)
    buffer.observe(serialized)
    return [serialized]


__all__ = [
    "AssistantEventObserver",
    "emit_content_through_parser",
    "flush_parser",
    "parser_events_to_envelopes",
    "serialize_agent_event_through_artifacts",
]
