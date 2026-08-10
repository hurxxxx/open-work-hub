from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from open_work_hub_api.domains.docs.collab_codec import (
    BlockNoteCollabCodec,
    CodecPayload,
    CodecProcessResult,
    JsonSubprocessCodecRunner,
    NodeCodecCommand,
)


class FakeRunner:
    def __init__(self, responses: list[CodecPayload]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, CodecPayload]] = []

    def run(self, mode: str, payload: CodecPayload) -> CodecPayload:
        self.calls.append((mode, payload))
        return self.responses.pop(0)


class FakeCommand:
    def __init__(self, result: CodecProcessResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def run(self, mode: str, payload_json: str) -> CodecProcessResult:
        self.calls.append((mode, payload_json))
        return self.result


def test_blocknote_codec_skips_runner_for_none_inputs() -> None:
    runner = FakeRunner([])
    codec = BlockNoteCollabCodec(runner=runner)

    assert codec.blocks_to_yjs_state(None) is None
    assert codec.yjs_state_to_blocks(None) is None
    assert runner.calls == []


def test_blocknote_codec_maps_blocks_to_encode_payload() -> None:
    raw_state = b"encoded-yjs-state"
    blocks = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Mapped to Yjs"}],
        }
    ]
    runner = FakeRunner(
        [{"yjs_state": base64.b64encode(raw_state).decode("ascii")}],
    )
    codec = BlockNoteCollabCodec(runner=runner)

    assert codec.blocks_to_yjs_state(blocks) == raw_state
    assert runner.calls == [("encode", {"blocks": blocks})]


def test_blocknote_codec_maps_state_to_decode_payload() -> None:
    raw_state = b"raw-yjs-state"
    blocks = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Decoded from Yjs"}],
        }
    ]
    runner = FakeRunner([{"blocks": blocks}])
    codec = BlockNoteCollabCodec(runner=runner)

    assert codec.yjs_state_to_blocks(raw_state) == blocks
    assert runner.calls == [
        ("decode", {"yjs_state": base64.b64encode(raw_state).decode("ascii")})
    ]


def test_blocknote_codec_rejects_invalid_yjs_state_payload() -> None:
    runner = FakeRunner([{"yjs_state": "not base64"}])
    codec = BlockNoteCollabCodec(runner=runner)

    with pytest.raises(RuntimeError, match="invalid yjs state"):
        codec.blocks_to_yjs_state([{"type": "paragraph"}])


def test_blocknote_codec_rejects_invalid_blocks_payload() -> None:
    runner = FakeRunner([{"blocks": {"type": "paragraph"}}])
    codec = BlockNoteCollabCodec(runner=runner)

    with pytest.raises(RuntimeError, match="invalid blocks"):
        codec.yjs_state_to_blocks(b"raw-yjs-state")


def test_json_subprocess_runner_serializes_payload_and_decodes_response() -> None:
    command = FakeCommand(CodecProcessResult(returncode=0, stdout='{"ok": true}', stderr=""))
    runner = JsonSubprocessCodecRunner(command=command)
    payload = {"blocks": [{"type": "paragraph"}]}

    assert runner.run("encode", payload) == {"ok": True}
    assert command.calls == [("encode", json.dumps(payload))]


def test_json_subprocess_runner_raises_on_process_failure() -> None:
    command = FakeCommand(CodecProcessResult(returncode=1, stdout="", stderr="boom"))
    runner = JsonSubprocessCodecRunner(command=command)

    with pytest.raises(RuntimeError, match="codec failed"):
        runner.run("decode", {"yjs_state": "AAAA"})


def test_json_subprocess_runner_raises_on_invalid_json() -> None:
    command = FakeCommand(CodecProcessResult(returncode=0, stdout="not json", stderr=""))
    runner = JsonSubprocessCodecRunner(command=command)

    with pytest.raises(RuntimeError, match="invalid JSON"):
        runner.run("decode", {"yjs_state": "AAAA"})


def test_json_subprocess_runner_rejects_non_object_json() -> None:
    command = FakeCommand(CodecProcessResult(returncode=0, stdout="[]", stderr=""))
    runner = JsonSubprocessCodecRunner(command=command)

    with pytest.raises(RuntimeError, match="invalid JSON object"):
        runner.run("decode", {"yjs_state": "AAAA"})


def test_node_codec_command_reports_missing_script(tmp_path: Path) -> None:
    command = NodeCodecCommand(script_path=tmp_path / "missing.mjs")

    with pytest.raises(RuntimeError, match="codec script is missing"):
        command.run("encode", "{}")
