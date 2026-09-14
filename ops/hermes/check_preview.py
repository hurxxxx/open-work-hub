"""Offline Chromium acceptance check in the pinned development gateway."""
import base64
import hashlib
import json
import sys
from unittest.mock import patch

sys.path.insert(0, "/opt/hermes/plugins")
import owh_runtime
from owh_runtime.preview import render_preview
from agent.display import _detect_tool_failure

files = {
    "demo/index.html": b'<body><canvas id="drawing" width="200" height="100"></canvas><script type="module" src="app.js"></script>',
    "demo/app.js": b'import {color} from "./color.js"; let c=drawing.getContext("2d"); c.fillStyle=color; c.fillRect(0,0,200,100);',
    "demo/color.js": b'export const color="green";',
}


def rpc(server, run_id, method, params):
    assert run_id == "run_preview_check"
    if method == "owh/files/list":
        return {"files": [{"id": p, "relative_path": p, "sha256": hashlib.sha256(b).hexdigest()}
                          for p, b in files.items()]}
    if method == "owh/files/read":
        return {"data": base64.b64encode(files[params["id"]]).decode()}
    raise AssertionError("Preview must not write files or invoke an application tool")


def render(*, vision=True, path="demo/index.html"):
    with patch("tools.vision_tools._should_use_native_vision_fast_path", return_value=vision):
        payload = render_preview({"path": path},
            execution={"sandbox": {"image": sys.argv[1], "no_proxy": "localhost"}},
            server={"fixture": True}, run_id="run_preview_check")
    failed, _ = _detect_tool_failure("owh_preview", payload)
    if vision and not failed:
        assert isinstance(payload, dict) and payload.get("_multimodal"), "Native vision envelope missing"
        assert payload["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    if isinstance(payload, str):
        payload = json.loads(payload)
    summary = json.loads(payload["text_summary"]) if payload.get("_multimodal") else payload
    assert failed == bool(summary.get("error")), "Native tool event misclassified preview failure"
    return summary


with patch.object(owh_runtime, "_rpc", rpc):
    good = render()
    assert good.get("status") == "rendered" and not good["errors"], good
    assert len(good["files"]) == 3 and good["page"]["canvases"] == [{"width": 200, "height": 100}]
    print("PASS: local HTML/module rendering with verified Chromium sandbox", flush=True)
    files["demo/index.htm"] = files["demo/index.html"]
    assert render(path="demo/index.htm")["status"] == "rendered"
    print("PASS: HTML and HTM entrypoints share the browser MIME contract", flush=True)
    files["demo/image.gif"] = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    files["demo/gif.html"] = b'<img id="result" src="image.gif" onerror="throw new Error(\'GIF failed to decode\')">'
    gif = render(path="demo/gif.html")
    assert gif["status"] == "rendered" and "demo/image.gif" in gif["files"], gif
    print("PASS: saved GIF image matches the web browser fixture", flush=True)
    files["demo/app.js"] = b'throw new Error("synthetic render failure");'
    broken = render()
    assert broken.get("error") == "preview.render_errors" and broken["errors"], broken
    print("PASS: JavaScript failure is observable", flush=True)
    files["demo/app.js"] = b'console.error("synthetic console failure");'
    console_error = render(vision=False)
    assert console_error.get("error") == "preview.render_errors" and console_error["errors"], console_error
    print("PASS: console failure and non-vision diagnostics", flush=True)
    files["demo/index.html"] = b'<script src="https://external.invalid/code.js"></script><script src="missing.js"></script>'
    blocked = render()
    assert blocked.get("status") == "render_errors" and blocked["errors"], blocked
    assert "https://external.invalid/code.js" not in blocked["files"]
    print("PASS: missing/external dependencies fail without network or fallback", flush=True)
