"""Streaming ``<artifact>`` tag parser for assistant chat output.

The chat stream publisher feeds this parser each ``content_delta`` chunk the
LLM produces. The parser splits the incoming text into three streams:

- ``ParsedText``: plain content outside any artifact — flows to the client
  as a regular ``content_delta`` envelope exactly as before.
- ``ParsedArtifactStart``: an ``<artifact type="..." title="...">`` open tag.
- ``ParsedArtifactBody``: the body text between the open and close tags.
- ``ParsedArtifactEnd``: the ``</artifact>`` close tag.

The parser is incremental: it buffers partial ``<`` tokens across chunks so
a tag that arrives as ``<arti`` + ``fact type="document">`` still parses
correctly. Unknown / malformed ``<...>`` sequences are emitted as plain
text so the wire stays backward compatible — only the literal
``<artifact`` / ``</artifact`` prefixes trigger special handling.

The parser returns structured records instead of raising; the caller is
responsible for turning them into envelopes so this module stays free of
any FastAPI/pydantic dependency and is easy to unit-test in isolation.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


@dataclass(frozen=True)
class ParsedText:
    """Plain text segment outside any artifact block."""

    text: str


@dataclass(frozen=True)
class ParsedArtifactStart:
    """Opening ``<artifact ...>`` tag detected.

    The parser generates the ``artifact_id`` so callers don't need to
    coordinate id allocation. ``attrs`` carries the parsed attribute map
    minus the id (``type`` and ``title`` are the conventional keys).
    """

    artifact_id: str
    attrs: dict[str, str]


@dataclass(frozen=True)
class ParsedArtifactBody:
    artifact_id: str
    text: str


@dataclass(frozen=True)
class ParsedArtifactEnd:
    artifact_id: str


ArtifactParseEvent = (
    ParsedText | ParsedArtifactStart | ParsedArtifactBody | ParsedArtifactEnd
)


class _State(Enum):
    OUTSIDE = "outside"
    INSIDE = "inside"


# `<artifact` and `</artifact` prefixes are the only `<` sequences this
# parser treats specially. Other tags flow through as plain text so a model
# that spits out markdown HTML (`<br>`, `<span>`, etc.) doesn't surprise us.
_OPEN_PREFIX = "<artifact"
_CLOSE_PREFIX = "</artifact"
_ATTR_RE = re.compile(
    r'([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*"((?:\\.|[^"\\])*)"'
)
# Characters that can legally follow `<artifact` / `</artifact` in a valid
# tag (whitespace, self-close, tag-end). Anything else — letters, digits,
# `-`, `_` — means we're looking at a different tag name that happens to
# share the prefix (e.g. `<artifacts>`). Those must pass through as plain
# text rather than get rerouted into the artifact channel.
_TAG_BOUNDARY_CHARS = frozenset(" \t\n\r\f\v>/")


@dataclass
class ArtifactStreamParser:
    """Incremental parser. Feed one ``feed(chunk)`` per content_delta.

    Call ``flush()`` once the stream terminates to drain any partial buffer
    — if the model closed the turn mid-tag, the buffered characters are
    emitted as plain text so nothing is silently dropped.
    """

    _state: _State = _State.OUTSIDE
    _buffer: str = ""
    _current_artifact_id: str | None = None
    # Tracks whether we've emitted a start event for the current artifact
    # but not yet its end. If the stream ends in this state, ``flush()``
    # synthesizes a close so the client isn't stuck waiting.
    _open_artifact_ids: list[str] = field(default_factory=list)
    # Markdown awareness: when the model shows the `<artifact>` syntax as
    # literal example text (fenced code block or inline backticks), the
    # markup must flow through as plain text instead of being rerouted
    # into the side panel. Two signals cover the common cases:
    # - ``_in_fence`` flips on/off at each ```` ``` ```` triple-backtick
    #   boundary. While on, `<artifact` never activates.
    # - ``_inline_code_open`` tracks whether we're currently inside an
    #   unclosed single-backtick span. An open span suppresses artifact
    #   parsing; a directly-preceding *closing* backtick (span already
    #   closed) does not, so outputs like `` `FMEA`<artifact ...> `` still
    #   activate correctly. Reset on newlines because inline code can't
    #   span paragraphs in CommonMark.
    _in_fence: bool = False
    _inline_code_open: bool = False
    # Current-line prefixes for literal-example detection. Outside artifacts,
    # syntax help often introduces a literal example after a colon
    # ("형식은 다음과 같습니다: <artifact ...>"). Inside artifacts, a
    # `</artifact>` shown inside an indented example block must stay literal
    # body text.
    _outside_line_prefix: str = ""
    _body_line_prefix: str = ""

    def feed(self, chunk: str) -> list[ArtifactParseEvent]:
        if not chunk:
            return []
        self._buffer += chunk
        return self._drain()

    def flush(self) -> list[ArtifactParseEvent]:
        """Drain any remaining buffer + synthesize a close for any
        artifact left open at stream end."""
        events: list[ArtifactParseEvent] = []
        # Flush any residual text. When state is OUTSIDE, the buffer is
        # plain text (possibly a partial `<` that never completed). When
        # INSIDE, it's unflushed artifact body.
        if self._buffer:
            if self._state is _State.OUTSIDE:
                self._emit_text(events, self._buffer)
            elif self._state is _State.INSIDE and self._current_artifact_id:
                self._emit_body(events, self._buffer)
            self._buffer = ""

        # Close any artifact that opened but never saw its terminator — the
        # client needs a terminal event per id to finalize its buffer.
        while self._open_artifact_ids:
            artifact_id = self._open_artifact_ids.pop()
            events.append(ParsedArtifactEnd(artifact_id))
        self._current_artifact_id = None
        self._state = _State.OUTSIDE
        self._in_fence = False
        self._inline_code_open = False
        self._outside_line_prefix = ""
        self._body_line_prefix = ""
        return events

    def _emit_text(
        self,
        events: list[ArtifactParseEvent],
        text: str,
        *,
        track_inline_code: bool = True,
    ) -> None:
        """Append plain text + advance inline-code span tracking.

        ``track_inline_code`` is set to ``False`` when emitting fence
        markers themselves, where the ``` run is a block delimiter rather
        than three inline-code toggles that would leave the tracker in an
        odd-count state after the fence opener.
        """
        if not text:
            return
        events.append(ParsedText(text))
        self._outside_line_prefix = _advance_line_prefix(
            self._outside_line_prefix, text
        )
        if not track_inline_code or self._in_fence:
            return
        for ch in text:
            if ch == "`":
                self._inline_code_open = not self._inline_code_open
            elif ch == "\n":
                # Inline code spans can't cross paragraph boundaries.
                self._inline_code_open = False

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _drain(self) -> list[ArtifactParseEvent]:
        events: list[ArtifactParseEvent] = []
        while self._buffer:
            if self._state is _State.OUTSIDE:
                progressed = self._drain_outside(events)
            else:
                progressed = self._drain_inside(events)
            if not progressed:
                # Cannot decide yet — keep the residual buffer for the next
                # feed() call (e.g. partial `<artifac` at a chunk boundary).
                break
        return events

    def _drain_outside(self, events: list[ArtifactParseEvent]) -> bool:
        # When inside a ```fenced``` block, everything is literal until
        # the matching close fence. `<artifact` never activates here.
        if self._in_fence:
            return self._drain_in_fence(events)

        # Earliest trigger wins: a potential artifact tag at `<` or a
        # code-fence opener at ```.
        idx_lt = self._buffer.find("<")
        idx_fence = self._buffer.find("```")

        # Nothing interesting found — but a trailing 1-2 backtick run could
        # still become a fence, so hold those for the next chunk.
        if idx_lt == -1 and idx_fence == -1:
            partial = _trailing_backtick_run(self._buffer)
            if partial == 0:
                self._emit_text(events, self._buffer)
                self._buffer = ""
                return True
            if partial == len(self._buffer):
                # Entire buffer is a pending partial fence. Wait.
                return False
            emit = self._buffer[: -partial]
            self._emit_text(events, emit)
            self._buffer = self._buffer[-partial:]
            return False  # Hold the trailing ticks until more arrives.

        # If a code fence opens before the next `<`, consume it and flip
        # into fence mode. The fence markers themselves are plain text.
        if idx_fence != -1 and (idx_lt == -1 or idx_fence < idx_lt):
            if idx_fence > 0:
                self._emit_text(events, self._buffer[:idx_fence])
                self._buffer = self._buffer[idx_fence:]
            # Emit the opening ``` verbatim without touching inline-code
            # state — this is a fence delimiter, not three inline toggles.
            self._emit_text(events, self._buffer[:3], track_inline_code=False)
            self._buffer = self._buffer[3:]
            # A fence supersedes any pending inline span that might have
            # opened on the prior line (rare but possible).
            self._inline_code_open = False
            self._in_fence = True
            return True

        # `<` comes first (or is the only trigger). Emit any preceding
        # text so `_last_emitted_char` reflects what sits just before `<`.
        if idx_lt > 0:
            self._emit_text(events, self._buffer[:idx_lt])
            self._buffer = self._buffer[idx_lt:]

        # Now the buffer starts with `<`. Decide: artifact open tag, or
        # some other `<` we should pass through as plain text.
        classification = self._classify_open_candidate()
        if classification == "reject":
            # The `<` is followed by something that definitively isn't
            # `<artifact ...>`, so emit it as plain text and keep going.
            self._emit_text(events, self._buffer[0])
            self._buffer = self._buffer[1:]
            return True
        if classification == "wait":
            # Not enough characters yet to decide — wait for more.
            return False

        # Buffer starts with `<artifact` followed by a boundary char. Look
        # for the terminating `>` while respecting quoted attribute values
        # so `<artifact title="A > B">` parses correctly.
        gt_idx = _find_tag_end_index(self._buffer, len(_OPEN_PREFIX))
        if gt_idx is None:
            # Open tag body still streaming — wait.
            return False

        open_tag = self._buffer[: gt_idx + 1]
        self._buffer = self._buffer[gt_idx + 1 :]
        attrs = _parse_attrs(open_tag)

        # Escape hatch 1: without a `type` attribute the markup is almost
        # certainly the model quoting the syntax itself — emit as plain.
        # Escape hatch 2: we're currently inside an unclosed inline-code
        # span (`` ` ``), so the entire tag is literal example text. A
        # *closed* prior span (e.g. `` `FMEA`<artifact ...> ``) leaves the
        # tracker flipped back to False and correctly activates the tag.
        # Escape hatch 3: a 4-space-indented line is almost certainly a
        # literal example block (matches the agent prompt's indented syntax
        # example) rather than a real artifact emission.
        # Escape hatch 4: an inline untitled `<artifact type="...">...`
        # immediately after an explanatory colon is usually syntax help
        # rather than a real side-panel doc.
        if (
            "type" not in attrs
            or self._inline_code_open
            or _is_indented_code_prefix(self._outside_line_prefix)
            or (
                "title" not in attrs
                and _looks_like_inline_example_prefix(self._outside_line_prefix)
            )
        ):
            self._emit_text(events, open_tag)
            return True

        # Self-closing `<artifact type="..." />` — emit start+end atomically
        # and stay OUTSIDE so any trailing summary text isn't captured into
        # an artifact body that will never see its terminator.
        is_self_closing = open_tag[:-1].rstrip().endswith("/")

        artifact_id = str(uuid.uuid4())
        events.append(ParsedArtifactStart(artifact_id=artifact_id, attrs=attrs))
        if is_self_closing:
            events.append(ParsedArtifactEnd(artifact_id))
            return True
        self._current_artifact_id = artifact_id
        self._open_artifact_ids.append(artifact_id)
        self._state = _State.INSIDE
        self._body_line_prefix = ""
        return True

    def _drain_in_fence(self, events: list[ArtifactParseEvent]) -> bool:
        """Everything inside a ```fenced``` block flows through as plain
        text. The close fence flips us back to the normal outside path.
        """
        close_idx = self._buffer.find("```")
        if close_idx == -1:
            # No close visible yet — emit what we can and hold back any
            # trailing partial backticks (could be the start of the close).
            partial = _trailing_backtick_run(self._buffer)
            if partial == len(self._buffer):
                return False
            if partial == 0:
                self._emit_text(events, self._buffer)
                self._buffer = ""
                return True
            self._emit_text(events, self._buffer[: -partial])
            self._buffer = self._buffer[-partial:]
            return False

        # Emit everything up to and including the close fence — the close
        # ``` delimiter itself must not advance inline-code tracking (same
        # reasoning as the opener).
        end = close_idx + 3
        if close_idx > 0:
            self._emit_text(events, self._buffer[:close_idx])
        self._emit_text(events, self._buffer[close_idx:end], track_inline_code=False)
        self._buffer = self._buffer[end:]
        self._in_fence = False
        # Reset inline-code tracking after the fence — any backticks the
        # body contained were literal content, not inline-code toggles.
        self._inline_code_open = False
        return True

    def _classify_open_candidate(self) -> str:
        """Return ``"accept"``, ``"wait"``, or ``"reject"`` for the `<`
        prefix sitting at the head of the buffer. ``accept`` means it's an
        ``<artifact`` open with a valid tag boundary char right after.
        ``wait`` means we've only seen a partial prefix that could still
        resolve to ``<artifact``. ``reject`` means the character after
        ``<artifact`` is an identifier character (e.g. ``<artifacts>``) or
        the prefix doesn't match at all, so the ``<`` is plain text.
        """
        buffer = self._buffer
        if buffer.startswith(_OPEN_PREFIX):
            if len(buffer) == len(_OPEN_PREFIX):
                return "wait"
            return (
                "accept"
                if buffer[len(_OPEN_PREFIX)] in _TAG_BOUNDARY_CHARS
                else "reject"
            )
        if len(buffer) < len(_OPEN_PREFIX) and _OPEN_PREFIX.startswith(buffer):
            return "wait"
        return "reject"

    def _emit_body(
        self,
        events: list[ArtifactParseEvent],
        text: str,
        *,
        track_inline_code: bool = True,
    ) -> None:
        """Append artifact body text + advance inline-code tracking.

        Body text is markdown in its own right, so fence and inline-code
        state must keep advancing inside the artifact. Otherwise a close
        tag that appears as literal example text inside a code fence
        inside the document would terminate the artifact prematurely.
        """
        if not text or self._current_artifact_id is None:
            return
        events.append(ParsedArtifactBody(self._current_artifact_id, text))
        self._body_line_prefix = _advance_line_prefix(self._body_line_prefix, text)
        if not track_inline_code or self._in_fence:
            return
        for ch in text:
            if ch == "`":
                self._inline_code_open = not self._inline_code_open
            elif ch == "\n":
                self._inline_code_open = False

    def _drain_inside(self, events: list[ArtifactParseEvent]) -> bool:
        # If we're inside a fence opened within the body, nothing counts
        # as a close tag until the fence closes — flush body + close fence.
        if self._in_fence:
            return self._drain_in_fence_body(events)

        # Earliest trigger decides: a `<` (potential close tag) or ``` (a
        # fenced example of the syntax that must be left intact).
        idx_lt = self._buffer.find("<")
        idx_fence = self._buffer.find("```")

        if idx_lt == -1 and idx_fence == -1:
            # No triggers visible. Hold back a trailing 1-2 backtick run —
            # the next chunk could grow it into a fence opener we must
            # detect before any following `</artifact>`.
            partial = _trailing_backtick_run(self._buffer)
            if partial == 0:
                self._emit_body(events, self._buffer)
                self._buffer = ""
                return True
            if partial == len(self._buffer):
                return False
            self._emit_body(events, self._buffer[:-partial])
            self._buffer = self._buffer[-partial:]
            return False

        # Fence opener inside the body — enter fence mode so any literal
        # `</artifact>` the example contains stays as body text.
        if idx_fence != -1 and (idx_lt == -1 or idx_fence < idx_lt):
            if idx_fence > 0:
                self._emit_body(events, self._buffer[:idx_fence])
                self._buffer = self._buffer[idx_fence:]
            self._emit_body(events, self._buffer[:3], track_inline_code=False)
            self._buffer = self._buffer[3:]
            self._inline_code_open = False
            self._in_fence = True
            return True

        # `<` is earliest. Emit any preceding body text so inline-code
        # tracking reflects what precedes the `<`.
        if idx_lt > 0:
            self._emit_body(events, self._buffer[:idx_lt])
            self._buffer = self._buffer[idx_lt:]

        # Now buffer starts with `<`. Could it be the close tag?
        if _is_indented_code_prefix(self._body_line_prefix):
            self._emit_body(events, self._buffer[0])
            self._buffer = self._buffer[1:]
            return True
        classification = self._classify_close_candidate()
        if classification == "reject":
            # Not `</artifact ...>` — it's a literal `<` inside the body
            # (e.g. markdown may contain `<br>`, `<artifacts>`). Emit it as
            # body text.
            self._emit_body(events, self._buffer[0])
            self._buffer = self._buffer[1:]
            return True
        if classification == "wait":
            return False

        # Suppress the close if we're inside an unclosed inline-code span
        # — the literal `</artifact>` is example text the document wants
        # to show, not a real terminator. Emit the `<` as body and keep
        # scanning; subsequent chars flow through normally.
        if self._inline_code_open:
            self._emit_body(events, self._buffer[0])
            self._buffer = self._buffer[1:]
            return True

        gt_idx = _find_tag_end_index(self._buffer, len(_CLOSE_PREFIX))
        if gt_idx is None:
            return False

        # Consume the close tag.
        self._buffer = self._buffer[gt_idx + 1 :]
        artifact_id = self._current_artifact_id
        if artifact_id is not None:
            if artifact_id in self._open_artifact_ids:
                self._open_artifact_ids.remove(artifact_id)
            events.append(ParsedArtifactEnd(artifact_id))
        self._current_artifact_id = None
        self._state = _State.OUTSIDE
        # Fence/inline state shouldn't bleed across the artifact boundary.
        self._inline_code_open = False
        self._body_line_prefix = ""
        return True

    def _drain_in_fence_body(self, events: list[ArtifactParseEvent]) -> bool:
        """Inside-artifact + inside-fence: everything flows through as
        body text until the close fence. Mirrors ``_drain_in_fence`` but
        emits ``ParsedArtifactBody`` instead of ``ParsedText``.
        """
        close_idx = self._buffer.find("```")
        if close_idx == -1:
            partial = _trailing_backtick_run(self._buffer)
            if partial == len(self._buffer):
                return False
            if partial == 0:
                self._emit_body(events, self._buffer)
                self._buffer = ""
                return True
            self._emit_body(events, self._buffer[:-partial])
            self._buffer = self._buffer[-partial:]
            return False

        end = close_idx + 3
        if close_idx > 0:
            self._emit_body(events, self._buffer[:close_idx])
        self._emit_body(events, self._buffer[close_idx:end], track_inline_code=False)
        self._buffer = self._buffer[end:]
        self._in_fence = False
        self._inline_code_open = False
        return True

    def _classify_close_candidate(self) -> str:
        """Mirror of :meth:`_classify_open_candidate` for the close tag."""
        buffer = self._buffer
        if buffer.startswith(_CLOSE_PREFIX):
            if len(buffer) == len(_CLOSE_PREFIX):
                return "wait"
            return (
                "accept"
                if buffer[len(_CLOSE_PREFIX)] in _TAG_BOUNDARY_CHARS
                else "reject"
            )
        if len(buffer) < len(_CLOSE_PREFIX) and _CLOSE_PREFIX.startswith(buffer):
            return "wait"
        return "reject"


def _trailing_backtick_run(buffer: str) -> int:
    """Count how many backticks end the buffer. Used to hold back 1-2
    trailing ``` `` `` chars that could still grow into a ```` ``` ````
    fence marker on the next chunk without emitting them prematurely.
    Returns 0 when the last char isn't a backtick.
    """
    count = 0
    for ch in reversed(buffer):
        if ch == "`":
            count += 1
        else:
            break
    return count


def _advance_line_prefix(prefix: str, text: str) -> str:
    for ch in text:
        if ch == "\n":
            prefix = ""
        else:
            prefix += ch
    return prefix


def _is_indented_code_prefix(prefix: str) -> bool:
    if not prefix or any(ch not in {" ", "\t"} for ch in prefix):
        return False
    indent = 0
    for ch in prefix:
        indent += 4 if ch == "\t" else 1
    return indent >= 4


def _looks_like_inline_example_prefix(prefix: str) -> bool:
    return prefix.rstrip().endswith((":", "："))


def _find_tag_end_index(buffer: str, start: int) -> int | None:
    """Return the index of the terminating ``>`` for an open/close tag,
    honoring double-quoted attribute values. Returns ``None`` when the
    tag isn't fully present yet (caller should wait for more chars).

    Artifact tag grammar only uses double quotes for attribute values;
    unquoted or single-quoted attrs are treated as plain characters so a
    stray ``"`` inside the body doesn't poison the scanner.
    """
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


def _parse_attrs(open_tag: str) -> dict[str, str]:
    """Pull ``key="value"`` pairs out of an open tag.

    Only understands double-quoted string values — matches the contract we
    teach the model via the system prompt. Unquoted or single-quoted attrs
    are ignored rather than coerced, to keep the grammar strict and the
    failure mode obvious.
    """

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


def iter_feed(
    parser: ArtifactStreamParser, chunks: Iterable[str]
) -> list[ArtifactParseEvent]:
    """Convenience helper for tests — feed a list of chunks and flush."""
    events: list[ArtifactParseEvent] = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    events.extend(parser.flush())
    return events
