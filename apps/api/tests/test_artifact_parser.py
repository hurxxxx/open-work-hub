"""Unit tests for the streaming ``<artifact>`` parser."""

from __future__ import annotations

import pytest

from aidoo_api.domains.ai.artifact_parser import (
    ArtifactStreamParser,
    ParsedArtifactBody,
    ParsedArtifactEnd,
    ParsedArtifactStart,
    ParsedText,
    iter_feed,
)


def _collect(chunks: list[str]) -> list:
    return iter_feed(ArtifactStreamParser(), chunks)


def test_plain_text_passes_through_unchanged() -> None:
    events = _collect(["hello ", "world"])
    assert events == [ParsedText("hello "), ParsedText("world")]


def test_no_artifact_ever_seen_is_all_text() -> None:
    events = _collect(["some markdown **bold** text"])
    assert events == [ParsedText("some markdown **bold** text")]


def test_single_artifact_full_chunk() -> None:
    events = _collect([
        "Here is your doc: ",
        '<artifact type="document" title="Email">body **here**</artifact>',
        " thanks!",
    ])

    assert [type(e).__name__ for e in events] == [
        "ParsedText",
        "ParsedArtifactStart",
        "ParsedArtifactBody",
        "ParsedArtifactEnd",
        "ParsedText",
    ]
    start = events[1]
    assert isinstance(start, ParsedArtifactStart)
    assert start.attrs == {"type": "document", "title": "Email"}
    assert start.artifact_id
    body = events[2]
    assert isinstance(body, ParsedArtifactBody)
    assert body.text == "body **here**"
    assert body.artifact_id == start.artifact_id
    end = events[3]
    assert isinstance(end, ParsedArtifactEnd)
    assert end.artifact_id == start.artifact_id
    assert events[0] == ParsedText("Here is your doc: ")
    assert events[4] == ParsedText(" thanks!")


def test_open_tag_split_across_chunks() -> None:
    events = _collect([
        "prefix <arti",
        'fact type="document">body</artifact> suffix',
    ])
    kinds = [type(e).__name__ for e in events]
    assert kinds == [
        "ParsedText",
        "ParsedArtifactStart",
        "ParsedArtifactBody",
        "ParsedArtifactEnd",
        "ParsedText",
    ]
    assert events[0] == ParsedText("prefix ")
    assert events[2].text == "body"
    assert events[4] == ParsedText(" suffix")


def test_close_tag_split_across_chunks() -> None:
    events = _collect([
        '<artifact type="document">part one',
        " part two</arti",
        "fact>after",
    ])
    kinds = [type(e).__name__ for e in events]
    assert "ParsedArtifactStart" in kinds
    body_parts = [e.text for e in events if isinstance(e, ParsedArtifactBody)]
    assert "".join(body_parts) == "part one part two"
    assert events[-1] == ParsedText("after")
    assert isinstance(events[-2], ParsedArtifactEnd)


def test_angle_bracket_inside_body_is_preserved_as_text() -> None:
    events = _collect([
        '<artifact type="document">',
        "see <br> and <span>x</span>",
        "</artifact>",
    ])
    body = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert body == "see <br> and <span>x</span>"


def test_non_artifact_tag_outside_is_plain_text() -> None:
    events = _collect(["<br>note<hr/>"])
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == "<br>note<hr/>"
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)


def test_multiple_artifacts_in_one_stream() -> None:
    events = _collect([
        '<artifact type="document" title="one">first</artifact>',
        "between ",
        '<artifact type="document" title="two">second</artifact>',
    ])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(starts) == 2
    assert len(ends) == 2
    assert starts[0].artifact_id != starts[1].artifact_id
    assert starts[0].attrs["title"] == "one"
    assert starts[1].attrs["title"] == "two"
    bodies = [e for e in events if isinstance(e, ParsedArtifactBody)]
    assert bodies[0].artifact_id == starts[0].artifact_id
    assert bodies[0].text == "first"
    assert bodies[1].artifact_id == starts[1].artifact_id
    assert bodies[1].text == "second"


def test_open_but_never_closed_synthesizes_end_on_flush() -> None:
    parser = ArtifactStreamParser()
    events = parser.feed('<artifact type="document">truncated body')
    events.extend(parser.flush())
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    bodies = [e for e in events if isinstance(e, ParsedArtifactBody)]
    assert len(starts) == 1
    assert len(ends) == 1 and ends[0].artifact_id == starts[0].artifact_id
    assert any(b.text == "truncated body" for b in bodies)


def test_partial_open_tag_at_end_is_flushed_as_text() -> None:
    parser = ArtifactStreamParser()
    events = parser.feed("prefix <arti")
    events.extend(parser.flush())
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == "prefix <arti"


def test_empty_body_artifact_still_emits_all_three_events() -> None:
    events = _collect(['<artifact type="document"></artifact>'])
    kinds = [type(e).__name__ for e in events]
    assert kinds == ["ParsedArtifactStart", "ParsedArtifactEnd"]


def test_attrs_with_spaces_and_mixed_order() -> None:
    events = _collect([
        '<artifact   title="A B"   type="document"  >x</artifact>',
    ])
    start = next(e for e in events if isinstance(e, ParsedArtifactStart))
    assert start.attrs == {"title": "A B", "type": "document"}


def test_artifact_followed_immediately_by_plain_text_boundary() -> None:
    events = _collect(['prefix<artifact type="document">body</artifact>suffix'])
    assert events[0] == ParsedText("prefix")
    assert events[-1] == ParsedText("suffix")


def test_prefix_collision_with_similar_tag_stays_plain_text() -> None:
    # `<artifacts>` is a different tag name; the parser must not enter
    # artifact mode just because it shares the `<artifact` prefix.
    events = _collect(["<artifacts>body</artifacts>"])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == "<artifacts>body</artifacts>"


def test_literal_backticked_artifact_example_stays_plain_text() -> None:
    # Documentation snippets like "`<artifactfoo>`" must not trigger the
    # open-tag branch. Boundary char right after `<artifact` is required.
    events = _collect(["use `<artifactfoo>` for foo"])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == "use `<artifactfoo>` for foo"


def test_title_containing_gt_inside_quotes_is_preserved() -> None:
    # `>` is legal in markdown/headings and the model may put it in a
    # title. The scanner must not terminate the tag on that `>`.
    events = _collect(['<artifact title="A > B" type="document">body</artifact>'])
    start = next(e for e in events if isinstance(e, ParsedArtifactStart))
    assert start.attrs["title"] == "A > B"
    assert start.attrs["type"] == "document"
    bodies = [e.text for e in events if isinstance(e, ParsedArtifactBody)]
    assert "".join(bodies) == "body"


def test_title_containing_escaped_double_quotes_is_preserved() -> None:
    events = _collect([
        '<artifact type="document" title="\\"Q2 보고서\\"">body</artifact>',
    ])
    start = next(e for e in events if isinstance(e, ParsedArtifactStart))
    assert start.attrs["title"] == '"Q2 보고서"'
    assert start.attrs["type"] == "document"
    bodies = [e.text for e in events if isinstance(e, ParsedArtifactBody)]
    assert "".join(bodies) == "body"


def test_close_tag_prefix_collision_stays_inside_body() -> None:
    # `</artifacts>` inside body must not be treated as a close tag.
    events = _collect([
        '<artifact type="document">see </artifacts> note</artifact>',
    ])
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == "see </artifacts> note"
    # The real close still fires once.
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(ends) == 1


def test_bare_artifact_without_type_stays_plain_text() -> None:
    # The model may quote `<artifact>` literally in help text. Without a
    # `type=` attribute we don't treat it as a real open — the whole tag
    # stays as plain text so the explanation renders untouched.
    events = _collect([
        "Use <artifact> like this: <artifact>body</artifact> (example)",
    ])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == (
        "Use <artifact> like this: <artifact>body</artifact> (example)"
    )


def test_artifact_without_type_does_not_swallow_trailing_text_on_flush() -> None:
    # Regression: previously a bare `<artifact>` entered INSIDE mode and
    # the rest of the stream got synthesized into a phantom artifact on
    # flush. Now it must flow through as plain text end-to-end.
    parser = ArtifactStreamParser()
    events = parser.feed("intro <artifact> and more explanation")
    events.extend(parser.flush())
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    assert not any(isinstance(e, ParsedArtifactEnd) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == "intro <artifact> and more explanation"


def test_self_closing_artifact_emits_start_and_end_atomically() -> None:
    # XML-style `<artifact type="document"/>` must not enter INSIDE mode —
    # otherwise trailing prose ends up in a phantom body until flush.
    events = _collect([
        'prefix <artifact type="document" title="Empty"/> summary text',
    ])
    kinds = [type(e).__name__ for e in events]
    assert kinds == [
        "ParsedText",
        "ParsedArtifactStart",
        "ParsedArtifactEnd",
        "ParsedText",
    ]
    assert events[0] == ParsedText("prefix ")
    assert events[-1] == ParsedText(" summary text")
    start = events[1]
    assert isinstance(start, ParsedArtifactStart)
    assert start.attrs == {"type": "document", "title": "Empty"}
    end = events[2]
    assert isinstance(end, ParsedArtifactEnd)
    assert end.artifact_id == start.artifact_id


def test_inline_typed_artifact_example_without_title_stays_plain_text() -> None:
    # Help text may show the literal syntax inline after visible prose.
    # Treat untitled inline snippets as examples, not real side-panel docs.
    stream = '형식은 다음과 같습니다: <artifact type="document">...</artifact>'
    events = _collect([stream])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == stream


def test_inline_backtick_wrapped_artifact_stays_plain_text() -> None:
    # When the model shows the markup inside inline code — e.g. explaining
    # the format — the whole `<artifact ...>` must flow through as plain
    # text even though it carries a valid `type=` attribute.
    events = _collect([
        'Use `<artifact type="document" title="Example">body</artifact>` for docs.',
    ])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == (
        'Use `<artifact type="document" title="Example">body</artifact>`'
        " for docs."
    )


def test_closed_inline_code_span_before_artifact_still_activates() -> None:
    # Regression: a naive "last char was a backtick" check would
    # suppress this artifact because `FMEA` closes with a backtick
    # immediately before `<artifact`. The span is already closed, so
    # the tag is real content and must open the panel.
    events = _collect([
        '요약은 `FMEA`<artifact type="document" title="Draft">본문</artifact> 참고.',
    ])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    assert len(starts) == 1
    assert starts[0].attrs == {"type": "document", "title": "Draft"}
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == "본문"


def test_newline_resets_inline_code_tracking() -> None:
    # Markdown inline code cannot cross paragraph breaks. An unmatched
    # backtick on one line must not leak into the next line's parsing.
    stream = (
        "stray backtick here: `\n"
        '<artifact type="document" title="Doc">body</artifact> end'
    )
    events = _collect([stream])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    assert len(starts) == 1
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == "body"


def test_fenced_close_tag_inside_body_does_not_terminate_artifact() -> None:
    # A document that explains the artifact markup itself may contain a
    # fenced `</artifact>` example. The parser must not mistake that
    # literal example for the real close — otherwise the artifact gets
    # truncated and trailing text leaks back into the chat bubble.
    body = (
        "Usage example:\n"
        "```\n"
        "<artifact type=\"document\">sample</artifact>\n"
        "```\n"
        "End of doc."
    )
    stream = (
        f'<artifact type="document" title="Guide">{body}</artifact> outro'
    )
    events = _collect([stream])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(starts) == 1 and len(ends) == 1
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == body
    trailing = [
        e.text
        for e in events
        if isinstance(e, ParsedText) and e.text.strip()
    ]
    assert trailing == [" outro"]


def test_inline_code_close_tag_inside_body_does_not_terminate() -> None:
    # Inline-code example of the close tag inside the document body
    # — e.g. "see `</artifact>` for the terminator" — must not be
    # interpreted as a real close.
    body = "see `</artifact>` for the terminator, then continue reading"
    stream = (
        f'<artifact type="document" title="G">{body}</artifact> done'
    )
    events = _collect([stream])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(starts) == 1 and len(ends) == 1
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == body


def test_indented_close_tag_inside_body_does_not_terminate() -> None:
    body = (
        "예시:\n"
        "    </artifact>\n"
        "이 줄까지 본문에 남아야 한다."
    )
    stream = (
        f'<artifact type="document" title="Guide">{body}</artifact> done'
    )
    events = _collect([stream])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(starts) == 1 and len(ends) == 1
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == body
    trailing = [e.text for e in events if isinstance(e, ParsedText) and e.text.strip()]
    assert trailing == [" done"]


def test_fenced_code_block_suppresses_artifact_parsing() -> None:
    # A ```fenced``` example of the artifact syntax must render inline —
    # never captured into the side panel — so explanatory replies keep
    # their code block intact.
    stream = (
        "Here is the format:\n"
        "```\n"
        '<artifact type="document" title="Draft">\n'
        "body text\n"
        "</artifact>\n"
        "```\n"
        "That is the whole API."
    )
    events = _collect([stream])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == stream


def test_indented_artifact_example_stays_plain_text() -> None:
    # The agent prompt teaches the syntax as a 4-space-indented example.
    # If the model echoes that literally, it must stay in the chat bubble.
    stream = (
        "형식은 다음과 같습니다:\n"
        '    <artifact type="document" title="Draft">\n'
        "    markdown 본문...\n"
        "    </artifact>\n"
        "위 형식을 사용하세요."
    )
    events = _collect([stream])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == stream


def test_fence_split_across_chunks_still_suppresses() -> None:
    # The fence opener may straddle a chunk boundary. We must hold back
    # partial 1-2 backtick runs until the third arrives instead of
    # emitting them as text and then matching `<artifact` inside the body.
    events = _collect([
        "prose ``",
        '`\n<artifact type="document">example</artifact>\n```\nend',
    ])
    assert not any(isinstance(e, ParsedArtifactStart) for e in events)
    joined = "".join(e.text for e in events if isinstance(e, ParsedText))
    assert joined == (
        'prose ```\n<artifact type="document">example</artifact>\n```\nend'
    )


def test_fence_followed_by_real_artifact_still_parses() -> None:
    # After a fenced example closes, a subsequent real artifact open must
    # still be recognized — fence tracking is per-block, not sticky.
    stream = (
        "Example format:\n"
        "```\n"
        '<artifact type="document">ignore</artifact>\n'
        "```\n"
        "And here is your real draft: "
        '<artifact type="document" title="Real">the body</artifact>'
    )
    events = _collect([stream])
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    assert len(starts) == 1
    assert starts[0].attrs == {"type": "document", "title": "Real"}
    bodies = "".join(e.text for e in events if isinstance(e, ParsedArtifactBody))
    assert bodies == "the body"


def test_self_closing_artifact_does_not_leave_open_for_flush() -> None:
    # Follow-up to the atomic start+end: nothing should be open when the
    # stream ends, so flush must not synthesize an extra close.
    parser = ArtifactStreamParser()
    events = parser.feed('<artifact type="document"/>done')
    events.extend(parser.flush())
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(ends) == 1


@pytest.mark.parametrize(
    "chunks",
    [
        ['<artifact type="document" title="T">hello</artifact>'],
        ['<arti', 'fact type="document" title="T">hello</artifact>'],
        ['<artifact type="document" title="T">', "hello", "</artifact>"],
        ['<artifact type="document" title="T">hel', "lo</artifact>"],
    ],
)
def test_chunk_boundaries_do_not_change_semantics(chunks: list[str]) -> None:
    events = _collect(chunks)
    starts = [e for e in events if isinstance(e, ParsedArtifactStart)]
    bodies = [e for e in events if isinstance(e, ParsedArtifactBody)]
    ends = [e for e in events if isinstance(e, ParsedArtifactEnd)]
    assert len(starts) == 1 and len(ends) == 1
    assert starts[0].attrs == {"type": "document", "title": "T"}
    assert "".join(b.text for b in bodies) == "hello"
