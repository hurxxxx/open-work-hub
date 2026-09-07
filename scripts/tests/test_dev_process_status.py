from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_dev_status_excludes_production_and_sibling_workers(tmp_path) -> None:
    (tmp_path / "pgrep").write_text(
        "#!/bin/sh\n"
        "cat <<'PROCESSES'\n"
        "101 /opt/open-work-hub/apps/worker/.venv/bin/python "
        "apps/worker/.venv/bin/celery -A open_work_hub_worker.celery_app:celery_app worker\n"
        f"102 {ROOT}-sibling/apps/worker/.venv/bin/python "
        "apps/worker/.venv/bin/celery -A open_work_hub_worker.celery_app:celery_app worker\n"
        "PROCESSES\n"
    )
    (tmp_path / "pgrep").chmod(0o755)
    env = {**os.environ, "OPEN_WORK_HUB_SKIP_DOTENV": "1", "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    result = subprocess.run(
        ["bash", str(ROOT / "dev.sh"), "--with-worker", "--status"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert "worker stopped" in result.stdout
    assert "101 " not in result.stdout
    assert "102 " not in result.stdout

    with (tmp_path / "pgrep").open("a") as script:
        script.write(
            f"printf '%s\\n' '103 {ROOT}/apps/worker/.venv/bin/python "
            "apps/worker/.venv/bin/celery -A open_work_hub_worker.celery_app:celery_app worker'\n"
        )
    result = subprocess.run(
        ["bash", str(ROOT / "dev.sh"), "--with-worker", "--status"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert "worker running" in result.stdout
    assert "103 " in result.stdout
