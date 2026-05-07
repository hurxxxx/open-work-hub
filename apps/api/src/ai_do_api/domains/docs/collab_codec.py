from __future__ import annotations

import base64
import json
import logging
import subprocess
from pathlib import Path

from ai_do_api.core.settings import WORKSPACE_ROOT


logger = logging.getLogger(__name__)

CODEC_SCRIPT = WORKSPACE_ROOT / "scripts" / "blocknote-collab-codec.mjs"


def _run_codec(mode: str, payload: dict[str, object]) -> dict[str, object]:
    if not CODEC_SCRIPT.exists():
        raise RuntimeError(f"Collaboration codec script is missing: {CODEC_SCRIPT}")

    completed = subprocess.run(
        ["node", str(CODEC_SCRIPT), mode],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(WORKSPACE_ROOT),
        check=False,
    )
    if completed.returncode != 0:
        logger.error(
            "BlockNote collaboration codec failed: mode=%s stderr=%s",
            mode,
            completed.stderr.strip(),
        )
        raise RuntimeError("BlockNote collaboration codec failed.")

    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RuntimeError("BlockNote collaboration codec returned invalid JSON.") from exc


def blocks_to_yjs_state(blocks: list[dict] | None) -> bytes | None:
    if blocks is None:
        return None
    payload = _run_codec("encode", {"blocks": blocks})
    value = payload.get("yjs_state")
    if not isinstance(value, str) or not value:
        return None
    return base64.b64decode(value.encode("ascii"))


def yjs_state_to_blocks(yjs_state: bytes | None) -> list[dict] | None:
    if yjs_state is None:
        return None
    payload = _run_codec(
        "decode",
        {"yjs_state": base64.b64encode(yjs_state).decode("ascii")},
    )
    blocks = payload.get("blocks")
    if blocks is None:
        return None
    if not isinstance(blocks, list):
        raise RuntimeError("BlockNote collaboration codec returned invalid blocks.")
    return blocks


def codec_script_path() -> Path:
    return CODEC_SCRIPT
