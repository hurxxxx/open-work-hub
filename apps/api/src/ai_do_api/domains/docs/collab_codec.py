from __future__ import annotations

import base64
import binascii
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from ai_do_api.core.settings import WORKSPACE_ROOT


logger = logging.getLogger(__name__)

CODEC_SCRIPT = WORKSPACE_ROOT / "scripts" / "blocknote-collab-codec.mjs"

CodecMode = Literal["encode", "decode"]
CodecPayload = dict[str, object]


class CodecRunner(Protocol):
    def run(self, mode: CodecMode, payload: CodecPayload) -> CodecPayload:
        ...


class CodecCommand(Protocol):
    def run(self, mode: CodecMode, payload_json: str) -> "CodecProcessResult":
        ...


class YjsStateCodec(Protocol):
    def encode(self, yjs_state: bytes) -> str:
        ...

    def decode(self, yjs_state: str) -> bytes:
        ...


@dataclass(frozen=True)
class CodecProcessResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class NodeCodecCommand:
    script_path: Path | None = None
    workspace_root: Path | None = None
    executable: str = "node"

    def run(self, mode: CodecMode, payload_json: str) -> CodecProcessResult:
        script_path = self.script_path or CODEC_SCRIPT
        if not script_path.exists():
            raise RuntimeError(f"Collaboration codec script is missing: {script_path}")

        completed = subprocess.run(
            [self.executable, str(script_path), mode],
            input=payload_json,
            text=True,
            capture_output=True,
            cwd=str(self.workspace_root or WORKSPACE_ROOT),
            check=False,
        )
        return CodecProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True)
class JsonSubprocessCodecRunner:
    command: CodecCommand = field(default_factory=NodeCodecCommand)

    def run(self, mode: CodecMode, payload: CodecPayload) -> CodecPayload:
        result = self.command.run(
            mode,
            json.dumps(payload),
        )
        if result.returncode != 0:
            logger.error(
                "BlockNote collaboration codec failed: mode=%s stderr=%s",
                mode,
                result.stderr.strip(),
            )
            raise RuntimeError("BlockNote collaboration codec failed.")

        try:
            decoded = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise RuntimeError("BlockNote collaboration codec returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("BlockNote collaboration codec returned invalid JSON object.")
        return decoded


@dataclass(frozen=True)
class Base64YjsStateCodec:
    def encode(self, yjs_state: bytes) -> str:
        return base64.b64encode(yjs_state).decode("ascii")

    def decode(self, yjs_state: str) -> bytes:
        try:
            return base64.b64decode(yjs_state.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error) as exc:
            raise RuntimeError(
                "BlockNote collaboration codec returned invalid yjs state."
            ) from exc


@dataclass(frozen=True)
class BlockNoteCollabCodec:
    runner: CodecRunner = field(default_factory=JsonSubprocessCodecRunner)
    yjs_state_codec: YjsStateCodec = field(default_factory=Base64YjsStateCodec)

    def blocks_to_yjs_state(self, blocks: list[dict] | None) -> bytes | None:
        if blocks is None:
            return None
        payload = self.runner.run("encode", {"blocks": blocks})
        value = payload.get("yjs_state")
        if not isinstance(value, str) or not value:
            return None
        return self.yjs_state_codec.decode(value)

    def yjs_state_to_blocks(self, yjs_state: bytes | None) -> list[dict] | None:
        if yjs_state is None:
            return None
        payload = self.runner.run(
            "decode",
            {"yjs_state": self.yjs_state_codec.encode(yjs_state)},
        )
        blocks = payload.get("blocks")
        if blocks is None:
            return None
        if not isinstance(blocks, list):
            raise RuntimeError("BlockNote collaboration codec returned invalid blocks.")
        return blocks


_DEFAULT_CODEC = BlockNoteCollabCodec()


def _run_codec(mode: CodecMode, payload: CodecPayload) -> CodecPayload:
    return _DEFAULT_CODEC.runner.run(mode, payload)


def blocks_to_yjs_state(blocks: list[dict] | None) -> bytes | None:
    return _DEFAULT_CODEC.blocks_to_yjs_state(blocks)


def yjs_state_to_blocks(yjs_state: bytes | None) -> list[dict] | None:
    return _DEFAULT_CODEC.yjs_state_to_blocks(yjs_state)


def codec_script_path() -> Path:
    return CODEC_SCRIPT
