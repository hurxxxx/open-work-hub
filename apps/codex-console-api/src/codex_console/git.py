"""Bounded Git access; no shell, external diff driver, arbitrary cwd or raw file endpoint."""

import hashlib
import os
import selectors
import stat
import subprocess
import time
from contextlib import ExitStack
from datetime import UTC, datetime
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
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ConsoleError("path_denied", 403)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ConsoleError("path_denied", 403)
    return candidate


def read_worktree_file(root: Path, relative: str) -> bytes:
    safe_path(root, relative)
    # Pin each directory and reject links at open time too: an agent may replace
    # a path between the status scan and the file read.
    try:
        with ExitStack() as stack:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            directory = os.open(root, flags)
            stack.callback(os.close, directory)
            parts = Path(relative).parts
            for part in parts[:-1]:
                directory = os.open(part, flags, dir_fd=directory)
                stack.callback(os.close, directory)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
                    raise ConsoleError("output_too_large")
                data = source.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ConsoleError("output_too_large")
                return data
    except FileNotFoundError:
        return b""  # A tracked deletion has an empty worktree side.
    except OSError:
        raise ConsoleError("path_denied", 403) from None


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
            result.update(item["path"].encode() + b"\0")
            result.update(hashlib.sha256(read_worktree_file(root, item["path"])).digest())
    return result.hexdigest()


def status(root: Path) -> dict:
    """Read local Git state only; remote counts describe cached refs, never a fetch."""
    raw = git(root, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all")
    result = dict(
        branch=None,
        head=None,
        upstream=None,
        ahead=None,
        behind=None,
        staged=0,
        unstaged=0,
        untracked=0,
        conflicts=0,
        changed=0,
    )
    records = iter(raw.split(b"\0"))
    for record in records:
        if not record:
            continue
        value = record.decode("utf-8", "replace")
        if value.startswith("# branch.head "):
            name = value.removeprefix("# branch.head ")
            result["branch"] = None if name == "(detached)" else name
        elif value.startswith("# branch.oid "):
            oid = value.removeprefix("# branch.oid ")
            result["head"] = None if oid == "(initial)" else oid
        elif value.startswith("# branch.upstream "):
            result["upstream"] = value.removeprefix("# branch.upstream ")
        elif value.startswith("# branch.ab "):
            ahead, behind = value.removeprefix("# branch.ab ").split()
            result["ahead"], result["behind"] = int(ahead), -int(behind)
        elif record[:1] in (b"1", b"2", b"u", b"?"):
            result["changed"] += 1
            if record[:1] == b"?":
                result["untracked"] += 1
            elif record[:1] == b"u":
                result["conflicts"] += 1
            else:
                xy = value.split(" ", 2)[1]
                result["staged"] += int(xy[0] != ".")
                result["unstaged"] += int(xy[1] != ".")
            if record[:1] == b"2":
                next(records, None)  # rename/copy source path
    return {
        **result,
        "root": str(root),
        "detached": result["branch"] is None,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def remove_missing_worktree(workspace: Path, target: Path) -> None:
    """Remove only this absent owned worktree's registration, never prune or force."""
    if target.exists() or target.is_symlink():
        raise ConsoleError("worktree_exists")
    expected = b"worktree " + os.fsencode(target.resolve())
    records = git(workspace, "worktree", "list", "--porcelain", "-z").split(b"\0\0")
    for record in records:
        fields = record.split(b"\0")
        if not fields or fields[0] != expected:
            continue
        if any(field == b"locked" or field.startswith(b"locked ") for field in fields):
            raise ConsoleError("worktree_exists")
        if target.exists() or target.is_symlink():
            raise ConsoleError("worktree_exists")
        # Git validates the exact registration and retains its own lock/dirty checks.
        git(workspace, "worktree", "remove", str(target))
        return


def prepare_workspace(
    workspace: Path,
    task_id: str,
    previous: str | None,
    *,
    base_ref: str,
    worktree_root: Path,
    validate_target=None,
) -> tuple[Path, bool]:
    if previous is not None:
        if fingerprint(workspace) != previous:
            raise ConsoleError("workspace_changed")
        return workspace, False
    if not git(workspace, "status", "--porcelain=v1", "--untracked-files=all").strip():
        return workspace, False
    target = worktree_root / f"codex-{task_id}"
    if validate_target is not None:
        validate_target(target)
    if target.exists():
        raise ConsoleError("worktree_exists")
    base = git(workspace, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}")
    worktree_root.mkdir(parents=True, exist_ok=True)
    git(workspace, "worktree", "add", "--detach", str(target), base.decode().strip())
    return target, True


def diff(root: Path, relative: str) -> dict:
    candidates = {item["path"]: item for item in changes(root)}
    if relative not in candidates:
        raise ConsoleError("file_not_changed", 404)
    item = candidates[relative]
    new = read_worktree_file(root, relative)
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
