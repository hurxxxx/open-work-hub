from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_console_service_preserves_host_privileges_for_native_yolo_turns():
    unit = (ROOT / "ops/codex-console/codex-console.service").read_text()
    directives = {
        line.strip()
        for line in unit.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "NoNewPrivileges=false" in directives
    assert "NoNewPrivileges=true" not in directives
