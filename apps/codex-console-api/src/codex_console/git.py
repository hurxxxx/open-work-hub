"""Bounded Git access; no shell, external diff driver, arbitrary cwd or raw file endpoint."""

import hashlib
import os
import selectors
import subprocess
import time
from pathlib import Path

from .errors import ConsoleError

MAX_BYTES = 2 * 1024 * 1024


def git(root: Path, *args: str, limit: int = MAX_BYTES) -> bytes:
    env = {k: os.environ[k] for k in ("HOME", "PATH", "LANG") if k in os.environ}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    process = subprocess.Popen(
        ["git", "--no-pager", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if not selector.select(timeout=0.2):
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > limit:
                    raise ConsoleError("output_too_large")
            else:
                raise ConsoleError("git_timeout")
        if process.wait(timeout=1) != 0:
            raise ConsoleError("git_unavailable")
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ConsoleError("path_denied", 403)
    if any(
        part == ".git"
        or part == ".secure"
        or part == "secrets"
        or part.startswith(".auth_info")
        or (part.startswith(".env") and part != ".env.example")
        or part in ("auth.json", "id_rsa", "id_ed25519")
        for part in path.parts
    ):
        raise ConsoleError("path_denied", 403)
    candidate = root / path
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ConsoleError("path_denied", 403)
    return candidate


def changes(root: Path) -> list[dict]:
    records = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    result, i = [], 0
    while i < len(records):
        record = records[i]
        i += 1
        if not record:
            continue
        status, path = record[:2].decode(), record[3:].decode("utf-8", "replace")
        old_path = None
        if "R" in status or "C" in status:
            old_path = records[i].decode("utf-8", "replace")
            i += 1
        try:
            safe_path(root, path)
            if old_path:
                safe_path(root, old_path)
        except ConsoleError:
            continue
        result.append({"path": path, "status": status, "old_path": old_path})
    return result


def fingerprint(root: Path) -> str:
    result = hashlib.sha256(git(root, "rev-parse", "HEAD"))
    result.update(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    # Include bytes so edits to already-dirty files cannot masquerade as our own previous diff.
    result.update(git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD"))
    for item in changes(root):
        if item["status"] == "??":
            path = safe_path(root, item["path"])
            if path.is_file():
                if path.stat().st_size > MAX_BYTES:
                    raise ConsoleError("output_too_large")
                result.update(path.read_bytes())
    return result.hexdigest()


def prepare_workspace(workspace: Path, task_id: str, previous: str | None) -> tuple[Path, bool]:
    if previous is not None:
        if fingerprint(workspace) != previous:
            raise ConsoleError("workspace_changed")
        return workspace, False
    if not git(workspace, "status", "--porcelain=v1", "--untracked-files=all").strip():
        return workspace, False
    target = workspace.parent / "worktrees" / f"codex-{task_id}"
    if target.exists():
        raise ConsoleError("worktree_exists")
    git(workspace, "worktree", "add", "--detach", str(target), "origin/dev")
    return target, True


def diff(root: Path, relative: str) -> dict:
    candidates = {item["path"]: item for item in changes(root)}
    if relative not in candidates:
        raise ConsoleError("file_not_changed", 404)
    item = candidates[relative]
    path = safe_path(root, relative)
    if path.exists() and (not path.is_file() or path.stat().st_size > MAX_BYTES):
        raise ConsoleError("output_too_large")
    new = path.read_bytes() if path.is_file() else b""
    old = b""
    if item["status"] != "??":
        try:
            old = git(root, "show", f"HEAD:{item['old_path'] or relative}")
        except ConsoleError:
            # An added tracked file has no HEAD object. Do not mask other errors.
            if "A" not in item["status"]:
                raise
    if b"\x00" in old or b"\x00" in new:
        return {"path": relative, "binary": True, "old": "", "new": ""}
    return {
        "path": relative,
        "binary": False,
        "old": old.decode("utf-8", "replace"),
        "new": new.decode("utf-8", "replace"),
    }
