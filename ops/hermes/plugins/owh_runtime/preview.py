"""Read-only visual evidence through a disposable, offline Chromium sandbox."""

import json
from pathlib import Path
import shlex
import subprocess

from .sandbox import WorkspaceEnvironment


def render_preview(args, *, execution, server, run_id):
    path = args.get("path")
    if not isinstance(path, str):
        return json.dumps({"error": "preview.path_required"})
    path = path.removeprefix("/workspace/")
    if (not path or len(path) > 1024 or "\\" in path
            or any(ord(c) < 32 for c in path)
            or any(p in {"", ".", "..", ".owh-runtime"} for p in path.split("/"))
            or Path(path).suffix.lower() not in {".html", ".htm"}):
        return json.dumps({"error": "preview.invalid_html_path"})
    environment = WorkspaceEnvironment(
        policy=execution["sandbox"], server=server, run_id=run_id, timeout=30, preview=True,
    )
    try:
        process = environment._run_bash(
            f"node --input-type=module - {shlex.quote(path)}",
            stdin_data=Path(__file__).with_name("preview.mjs").read_text(), timeout=30,
        )
        try:
            output, _ = process.communicate(timeout=35)
        except subprocess.TimeoutExpired:
            environment._kill_process(process)
            process.communicate()
            return json.dumps({"error": "preview.timeout"})
        if len(output) > 800_000:
            return json.dumps({"error": "preview.output_too_large"})
        try:
            result = json.loads(output)
        except (TypeError, ValueError):
            return json.dumps({"error": "preview.browser_unavailable",
                               "hint": "Run the administrator preview sandbox check; do not install another browser or disable its sandbox."})
        screenshot = result.pop("screenshot", None)
        if result.get("status") == "render_errors":
            result["error"] = "preview.render_errors"
        summary = json.dumps(result, ensure_ascii=False)
        # Pinned native failure detection expects JSON errors, and treats
        # multimodal envelopes as success. Preserve its error contract.
        if screenshot and not result.get("error"):
            from tools.vision_tools import _should_use_native_vision_fast_path

            if _should_use_native_vision_fast_path():
                return {"_multimodal": True, "content": [
                    {"type": "text", "text": summary + "\nInspect the attached rendering before declaring the result complete."},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + screenshot}},
                ], "text_summary": summary}
        return summary
    finally:
        environment.cleanup()
