"""Browser-test entrypoint. No fake runtime or password is installed in the application."""

import asyncio
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
import uvicorn
from conftest import PASSWORD, FakeRPC
from psycopg import sql
from sqlalchemy.engine import make_url

from codex_console.app import create_app
from codex_console.auth import password_hash
from codex_console.cli import migrate
from codex_console.config import Settings
from codex_console.models import Owner, database


class BrowserRPC(FakeRPC):
    def __init__(self, *args):
        super().__init__(*args)
        self.jobs = set()

    async def call(self, method, params):
        result = await super().call(method, params)
        if method == "turn/start":
            job = asyncio.create_task(self.finish(params, result["turn"]["id"]))
            self.jobs.add(job)
            job.add_done_callback(self.jobs.discard)
        return result

    async def finish(self, params, turn_id):
        await asyncio.sleep(0.15)
        envelope = {"threadId": params["threadId"], "turnId": turn_id}
        user = {
            "id": str(uuid4()),
            "clientId": params["clientUserMessageId"],
            "type": "userMessage",
            "content": params["input"],
        }
        await self.on_message({"method": "item/completed", "params": {**envelope, "item": user}})
        await self.on_message(
            {
                "method": "turn/plan/updated",
                "params": {
                    **envelope,
                    "explanation": None,
                    "plan": [
                        {"step": "Inspect files", "status": "completed"},
                        {"step": "Check result", "status": "inProgress"},
                    ],
                },
            }
        )
        await asyncio.sleep(3)
        if params["collaborationMode"]["mode"] == "plan":
            item = {
                "id": str(uuid4()),
                "type": "plan",
                "text": (
                    "# A small, verifiable change\n\nAdd a greeting to the project.\n\n"
                    "1. Inspect the existing files.\n2. Implement the greeting.\n"
                    "3. Run a focused check.\n\n"
                    "**Acceptance:** the greeting is visible and the check passes."
                ),
            }
        else:
            (Path(params["cwd"]) / "greeting.txt").write_text("Hello from the Codex console.\n")
            command = {
                "id": str(uuid4()),
                "type": "commandExecution",
                "command": "python -m unittest",
                "status": "completed",
                "exitCode": 0,
                "aggregatedOutput": "1 test passed",
            }
            await self.on_message(
                {"method": "item/completed", "params": {**envelope, "item": command}}
            )
            item = {
                "id": str(uuid4()),
                "type": "agentMessage",
                "phase": "final_answer",
                "text": "Implemented the greeting. Focused check passed. Review greeting.txt.",
            }
        await self.on_message({"method": "item/completed", "params": {**envelope, "item": item}})
        await self.on_message(
            {
                "method": "turn/completed",
                "params": {**envelope, "turn": {"id": turn_id, "status": "completed"}},
            }
        )

    async def close(self):
        for job in list(self.jobs):
            job.cancel()
        await asyncio.gather(*self.jobs, return_exceptions=True)
        await super().close()


def main():
    port = int(os.environ.get("OPEN_WORK_HUB_CODEX_CONSOLE_PORT", "19365"))
    url = make_url(os.environ["OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN"])
    name = "console_test_browser_" + uuid4().hex
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            target = url.set(drivername="postgresql+psycopg", database=name).render_as_string(
                hide_password=False
            )
            migrate(target)
            engine, factory = database(target)
            with factory.begin() as db:
                db.add(Owner(password_hash=password_hash(PASSWORD)))
            engine.dispose()
            with tempfile.TemporaryDirectory(prefix="codex-console-browser-") as directory:
                root = Path(directory) / "dev"
                root.mkdir()
                for args in (
                    ("init", "-b", "dev"),
                    ("config", "user.name", "Console Test"),
                    ("config", "user.email", "console@test.invalid"),
                ):
                    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
                (root / "README.md").write_text("Browser regression fixture\n")
                subprocess.run(["git", "-C", str(root), "add", "."], check=True)
                subprocess.run(
                    ["git", "-C", str(root), "commit", "-m", "fixture"],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(root), "update-ref", "refs/remotes/origin/dev", "HEAD"],
                    check=True,
                    capture_output=True,
                )
                settings = Settings(
                    database_url=target,
                    origin=f"http://127.0.0.1:{port}",
                    base_path=os.environ.get("OPEN_WORK_HUB_CODEX_CONSOLE_BASE_PATH", ""),
                    workspace=root,
                    attachment_cache=Path(directory) / "attachments",
                    web_dist=Path(__file__).resolve().parents[2] / "codex-console-web/dist",
                    _env_file=None,
                )
                uvicorn.run(
                    create_app(settings, rpc_factory=BrowserRPC),
                    host="127.0.0.1",
                    port=port,
                    access_log=False,
                    log_level="warning",
                )
        finally:
            # The runner signals the process group and uv may forward that signal again.
            # Complete this fixture's cleanup even if a second SIGINT arrives during DROP.
            previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            finally:
                signal.signal(signal.SIGINT, previous_handler)


if __name__ == "__main__":
    main()
