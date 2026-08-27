from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from open_work_hub_api.domains.agent_terminal.schemas import (
    AgentTerminalGitChangeResponse,
    AgentTerminalGitCommitDetailResponse,
    AgentTerminalGitCommitDiffResponse,
    AgentTerminalGitCommitFileResponse,
    AgentTerminalGitCommitResponse,
    AgentTerminalGitDiffResponse,
    AgentTerminalGitHistoryResponse,
    AgentTerminalGitRefResponse,
    AgentTerminalGitStashResponse,
    AgentTerminalGitStatusResponse,
    AgentTerminalGitSummaryResponse,
)


_GIT_TIMEOUT_SECONDS = 5
_MAX_STATUS_BYTES = 1_000_000
_MAX_CONTENT_BYTES = 1_000_000
_MAX_CHANGES = 1_000
_MAX_REFS = 500
_MAX_STASHES = 100
_MAX_HISTORY_PAGE_SIZE = 100
_COMMIT_SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40,64}")
_STATUS_KIND = {
    "A": "added",
    "C": "copied",
    "D": "deleted",
    "M": "modified",
    "R": "renamed",
    "T": "type_changed",
    "U": "conflicted",
}


class AgentTerminalGitError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _Content:
    value: str = ""
    binary: bool = False
    too_large: bool = False


def get_git_status(root: Path) -> AgentTerminalGitStatusResponse:
    repository_root = _repository_root(root)
    if repository_root is None or repository_root != root:
        return AgentTerminalGitStatusResponse(is_repository=False)

    completed = _run_git(
        root,
        ["status", "--porcelain=v2", "--branch", "--untracked-files=all", "-z"],
        max_output_bytes=_MAX_STATUS_BYTES,
    )
    if completed.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_status_failed")
    return _parse_status(completed.stdout)


def get_git_diff(
    root: Path,
    *,
    path: str,
    scope: str,
) -> AgentTerminalGitDiffResponse:
    _validate_relative_path(path)
    status_response = get_git_status(root)
    if not status_response.is_repository:
        raise AgentTerminalGitError("agent_terminal.git_repository_unavailable")

    change = next(
        (item for item in status_response.changes if item.path == path and item.scope == scope),
        None,
    )
    if change is None:
        raise AgentTerminalGitError("agent_terminal.git_change_not_found")

    old_path = change.old_path or change.path
    if scope == "staged":
        old_content = _read_blob(root, f"HEAD:{old_path}")
        new_content = _read_blob(root, f":{change.path}")
    elif scope == "unstaged":
        old_content = _read_blob(root, f":{old_path}")
        new_content = _read_worktree_file(root, change.path)
    elif scope == "untracked":
        old_content = _Content()
        new_content = _read_worktree_file(root, change.path)
    else:
        old_content = _read_blob(root, f"HEAD:{old_path}")
        new_content = _read_worktree_file(root, change.path)

    is_binary = old_content.binary or new_content.binary
    too_large = old_content.too_large or new_content.too_large
    return AgentTerminalGitDiffResponse(
        path=change.path,
        old_path=change.old_path,
        scope=change.scope,
        kind=change.kind,
        old_content=None if is_binary or too_large else old_content.value,
        new_content=None if is_binary or too_large else new_content.value,
        is_binary=is_binary,
        too_large=too_large,
    )


def get_git_summary(root: Path) -> AgentTerminalGitSummaryResponse:
    repository_root = _repository_root(root)
    if repository_root is None or repository_root != root:
        return AgentTerminalGitSummaryResponse(is_repository=False)

    refs_response = _run_git(
        root,
        [
            "for-each-ref",
            "--sort=refname",
            f"--count={_MAX_REFS + 1}",
            "--format=%(refname)%00%(objectname)%00%(HEAD)%00%(symref)",
            "refs/heads",
            "refs/remotes",
            "refs/tags",
        ],
        max_output_bytes=_MAX_STATUS_BYTES,
    )
    if refs_response.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_summary_failed")
    refs, refs_truncated = _parse_refs(refs_response.stdout)

    stash_response = _run_git(
        root,
        [
            "stash",
            "list",
            f"--max-count={_MAX_STASHES + 1}",
            "--format=%H%x00%gd%x00%gs",
        ],
        max_output_bytes=_MAX_STATUS_BYTES,
    )
    if stash_response.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_summary_failed")
    stashes, stashes_truncated = _parse_stashes(stash_response.stdout)
    return AgentTerminalGitSummaryResponse(
        is_repository=True,
        refs=refs,
        stashes=stashes,
        refs_truncated=refs_truncated,
        stashes_truncated=stashes_truncated,
    )


def get_git_history(
    root: Path,
    *,
    offset: int = 0,
    limit: int = 50,
) -> AgentTerminalGitHistoryResponse:
    _require_repository(root)
    if offset < 0 or limit < 1 or limit > _MAX_HISTORY_PAGE_SIZE:
        raise AgentTerminalGitError("agent_terminal.git_history_query_invalid")
    if not _has_head(root):
        return AgentTerminalGitHistoryResponse(offset=offset)

    completed = _run_git(
        root,
        [
            "log",
            "--date-order",
            f"--skip={offset}",
            f"--max-count={limit + 1}",
            "--format=%H%x00%P%x00%an%x00%aI%x00%s",
            "HEAD",
            "--",
        ],
        max_output_bytes=_MAX_STATUS_BYTES,
    )
    if completed.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_history_failed")
    commits = _parse_commits(completed.stdout)
    return AgentTerminalGitHistoryResponse(
        items=commits[:limit],
        offset=offset,
        has_more=len(commits) > limit,
    )


def get_git_commit_detail(
    root: Path,
    *,
    commit: str,
) -> AgentTerminalGitCommitDetailResponse:
    _require_repository(root)
    metadata = _get_current_head_commit(root, commit)
    files, truncated = _commit_files(root, metadata)
    return AgentTerminalGitCommitDetailResponse(
        **metadata.model_dump(),
        files=files,
        files_truncated=truncated,
    )


def get_git_commit_diff(
    root: Path,
    *,
    commit: str,
    path: str,
) -> AgentTerminalGitCommitDiffResponse:
    _validate_relative_path(path)
    detail = get_git_commit_detail(root, commit=commit)
    change = next((item for item in detail.files if item.path == path), None)
    if change is None:
        raise AgentTerminalGitError("agent_terminal.git_change_not_found")

    parent = detail.parents[0] if detail.parents else None
    old_path = change.old_path or change.path
    old_content = (
        _Content()
        if parent is None or change.kind == "added"
        else _read_blob(root, f"{parent}:{old_path}")
    )
    new_content = (
        _Content() if change.kind == "deleted" else _read_blob(root, f"{detail.sha}:{change.path}")
    )
    is_binary = old_content.binary or new_content.binary
    too_large = old_content.too_large or new_content.too_large
    return AgentTerminalGitCommitDiffResponse(
        commit=detail.sha,
        path=change.path,
        old_path=change.old_path,
        kind=change.kind,
        old_content=None if is_binary or too_large else old_content.value,
        new_content=None if is_binary or too_large else new_content.value,
        is_binary=is_binary,
        too_large=too_large,
    )


def _require_repository(root: Path) -> None:
    repository_root = _repository_root(root)
    if repository_root is None or repository_root != root:
        raise AgentTerminalGitError("agent_terminal.git_repository_unavailable")


def _has_head(root: Path) -> bool:
    completed = _run_git(
        root,
        ["rev-parse", "--verify", "--quiet", "HEAD"],
        max_output_bytes=256,
    )
    return completed.returncode == 0


def _get_current_head_commit(
    root: Path,
    commit: str,
) -> AgentTerminalGitCommitResponse:
    if _COMMIT_SHA_PATTERN.fullmatch(commit) is None or not _has_head(root):
        raise AgentTerminalGitError("agent_terminal.git_commit_not_found")
    ancestor_response = _run_git(
        root,
        ["merge-base", "--is-ancestor", commit, "HEAD"],
        max_output_bytes=256,
    )
    if ancestor_response.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_commit_not_found")
    completed = _run_git(
        root,
        [
            "show",
            "--no-patch",
            "--format=%H%x00%P%x00%an%x00%aI%x00%s",
            commit,
            "--",
        ],
        max_output_bytes=64_000,
    )
    if completed.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_commit_not_found")
    commits = _parse_commits(completed.stdout)
    if len(commits) != 1:
        raise AgentTerminalGitError("agent_terminal.git_output_invalid")
    return commits[0]


def _commit_files(
    root: Path,
    commit: AgentTerminalGitCommitResponse,
) -> tuple[list[AgentTerminalGitCommitFileResponse], bool]:
    if commit.parents:
        arguments = [
            "diff",
            "--name-status",
            "-z",
            "-M",
            "-C",
            commit.parents[0],
            commit.sha,
            "--",
        ]
    else:
        arguments = [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-z",
            "-M",
            "-C",
            commit.sha,
            "--",
        ]
    completed = _run_git(
        root,
        arguments,
        max_output_bytes=_MAX_STATUS_BYTES,
    )
    if completed.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_history_failed")
    return _parse_commit_files(completed.stdout)


def _repository_root(root: Path) -> Path | None:
    completed = _run_git(
        root,
        ["rev-parse", "--path-format=absolute", "--show-toplevel"],
        max_output_bytes=8_192,
    )
    if completed.returncode != 0:
        return None
    try:
        value = completed.stdout.decode("utf-8").strip()
        return Path(value).resolve(strict=True)
    except (OSError, UnicodeDecodeError):
        raise AgentTerminalGitError("agent_terminal.git_output_invalid") from None


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    max_output_bytes: int,
) -> subprocess.CompletedProcess[bytes]:
    git_binary = shutil.which("git")
    if git_binary is None:
        raise AgentTerminalGitError("agent_terminal.git_unavailable")
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
    }
    try:
        completed = subprocess.run(
            [
                git_binary,
                "-c",
                "core.fsmonitor=false",
                "-c",
                "diff.external=",
                "-C",
                str(root),
                *arguments,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgentTerminalGitError("agent_terminal.git_operation_failed") from exc
    if len(completed.stdout) > max_output_bytes or len(completed.stderr) > 64_000:
        raise AgentTerminalGitError("agent_terminal.git_output_too_large")
    return completed


def _parse_status(payload: bytes) -> AgentTerminalGitStatusResponse:
    try:
        records = payload.decode("utf-8").split("\0")
    except UnicodeDecodeError as exc:
        raise AgentTerminalGitError("agent_terminal.git_output_invalid") from exc

    branch: str | None = None
    head: str | None = None
    upstream: str | None = None
    ahead = 0
    behind = 0
    changes: list[AgentTerminalGitChangeResponse] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if record.startswith("# branch.head "):
            value = record.removeprefix("# branch.head ")
            branch = None if value in {"(detached)", "(unknown)"} else value
            continue
        if record.startswith("# branch.oid "):
            value = record.removeprefix("# branch.oid ")
            head = None if value == "(initial)" else value
            continue
        if record.startswith("# branch.upstream "):
            upstream = record.removeprefix("# branch.upstream ") or None
            continue
        if record.startswith("# branch.ab "):
            fields = record.removeprefix("# branch.ab ").split(" ")
            if len(fields) != 2 or not fields[0].startswith("+") or not fields[1].startswith("-"):
                raise AgentTerminalGitError("agent_terminal.git_output_invalid")
            try:
                ahead = int(fields[0][1:])
                behind = int(fields[1][1:])
            except ValueError as exc:
                raise AgentTerminalGitError("agent_terminal.git_output_invalid") from exc
            continue
        if record.startswith("? "):
            changes.append(
                AgentTerminalGitChangeResponse(
                    path=record[2:],
                    scope="untracked",
                    kind="untracked",
                )
            )
            continue
        if record.startswith("u "):
            fields = record.split(" ", 10)
            if len(fields) != 11:
                raise AgentTerminalGitError("agent_terminal.git_output_invalid")
            changes.append(
                AgentTerminalGitChangeResponse(
                    path=fields[10],
                    scope="conflicted",
                    kind="conflicted",
                )
            )
            continue
        if record.startswith("1 "):
            fields = record.split(" ", 8)
            if len(fields) != 9:
                raise AgentTerminalGitError("agent_terminal.git_output_invalid")
            _append_xy_changes(changes, xy=fields[1], path=fields[8])
            continue
        if record.startswith("2 "):
            fields = record.split(" ", 9)
            if len(fields) != 10 or index >= len(records):
                raise AgentTerminalGitError("agent_terminal.git_output_invalid")
            old_path = records[index]
            index += 1
            _append_xy_changes(
                changes,
                xy=fields[1],
                path=fields[9],
                old_path=old_path,
            )

    scope_order = {"conflicted": 0, "staged": 1, "unstaged": 2, "untracked": 3}
    changes.sort(key=lambda item: (scope_order[item.scope], item.path))
    truncated = len(changes) > _MAX_CHANGES
    return AgentTerminalGitStatusResponse(
        is_repository=True,
        branch=branch,
        head=head,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        changes=changes[:_MAX_CHANGES],
        truncated=truncated,
    )


def _parse_refs(payload: bytes) -> tuple[list[AgentTerminalGitRefResponse], bool]:
    refs: list[AgentTerminalGitRefResponse] = []
    for raw_record in payload.splitlines():
        fields = raw_record.split(b"\0")
        if len(fields) != 4:
            raise AgentTerminalGitError("agent_terminal.git_output_invalid")
        full_name, target, current, symbolic_target = (_decode_git_text(field) for field in fields)
        if symbolic_target:
            continue
        if full_name.startswith("refs/heads/"):
            kind = "local_branch"
            name = full_name.removeprefix("refs/heads/")
        elif full_name.startswith("refs/remotes/"):
            kind = "remote_branch"
            name = full_name.removeprefix("refs/remotes/")
        elif full_name.startswith("refs/tags/"):
            kind = "tag"
            name = full_name.removeprefix("refs/tags/")
        else:
            raise AgentTerminalGitError("agent_terminal.git_output_invalid")
        refs.append(
            AgentTerminalGitRefResponse(
                name=name,
                full_name=full_name,
                kind=kind,
                target=target,
                current=current.strip() == "*",
            )
        )
    truncated = len(refs) > _MAX_REFS
    return refs[:_MAX_REFS], truncated


def _parse_stashes(
    payload: bytes,
) -> tuple[list[AgentTerminalGitStashResponse], bool]:
    stashes: list[AgentTerminalGitStashResponse] = []
    for raw_record in payload.splitlines():
        fields = raw_record.split(b"\0")
        if len(fields) != 3:
            raise AgentTerminalGitError("agent_terminal.git_output_invalid")
        sha, stash_ref, subject = (_decode_git_text(field) for field in fields)
        stashes.append(
            AgentTerminalGitStashResponse(
                ref=stash_ref,
                sha=sha,
                subject=subject,
            )
        )
    truncated = len(stashes) > _MAX_STASHES
    return stashes[:_MAX_STASHES], truncated


def _parse_commits(payload: bytes) -> list[AgentTerminalGitCommitResponse]:
    commits: list[AgentTerminalGitCommitResponse] = []
    for raw_record in payload.splitlines():
        if not raw_record:
            continue
        fields = raw_record.split(b"\0")
        if len(fields) != 5:
            raise AgentTerminalGitError("agent_terminal.git_output_invalid")
        sha, parents_value, author_name, authored_at_value, subject = (
            _decode_git_text(field) for field in fields
        )
        if _COMMIT_SHA_PATTERN.fullmatch(sha) is None:
            raise AgentTerminalGitError("agent_terminal.git_output_invalid")
        parents = parents_value.split() if parents_value else []
        if any(_COMMIT_SHA_PATTERN.fullmatch(parent) is None for parent in parents):
            raise AgentTerminalGitError("agent_terminal.git_output_invalid")
        try:
            authored_at = datetime.fromisoformat(authored_at_value)
        except ValueError as exc:
            raise AgentTerminalGitError("agent_terminal.git_output_invalid") from exc
        commits.append(
            AgentTerminalGitCommitResponse(
                sha=sha,
                parents=parents,
                author_name=author_name,
                authored_at=authored_at,
                subject=subject,
            )
        )
    return commits


def _parse_commit_files(
    payload: bytes,
) -> tuple[list[AgentTerminalGitCommitFileResponse], bool]:
    try:
        records = payload.decode("utf-8").split("\0")
    except UnicodeDecodeError as exc:
        raise AgentTerminalGitError("agent_terminal.git_output_invalid") from exc
    files: list[AgentTerminalGitCommitFileResponse] = []
    index = 0
    while index < len(records):
        status_value = records[index]
        index += 1
        if not status_value:
            continue
        kind = _status_kind(status_value[0])
        if kind in {"renamed", "copied"}:
            if index + 1 >= len(records):
                raise AgentTerminalGitError("agent_terminal.git_output_invalid")
            old_path = records[index]
            path = records[index + 1]
            index += 2
        else:
            if index >= len(records):
                raise AgentTerminalGitError("agent_terminal.git_output_invalid")
            old_path = None
            path = records[index]
            index += 1
        _validate_relative_path(path)
        if old_path is not None:
            _validate_relative_path(old_path)
        files.append(
            AgentTerminalGitCommitFileResponse(
                path=path,
                old_path=old_path,
                kind=kind,
            )
        )
    truncated = len(files) > _MAX_CHANGES
    return files[:_MAX_CHANGES], truncated


def _decode_git_text(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace")


def _append_xy_changes(
    changes: list[AgentTerminalGitChangeResponse],
    *,
    xy: str,
    path: str,
    old_path: str | None = None,
) -> None:
    if len(xy) != 2:
        raise AgentTerminalGitError("agent_terminal.git_output_invalid")
    index_status, worktree_status = xy
    if "U" in xy:
        changes.append(
            AgentTerminalGitChangeResponse(
                path=path,
                old_path=old_path,
                scope="conflicted",
                kind="conflicted",
            )
        )
        return
    if index_status != ".":
        changes.append(
            AgentTerminalGitChangeResponse(
                path=path,
                old_path=old_path,
                scope="staged",
                kind=_status_kind(index_status),
            )
        )
    if worktree_status != ".":
        changes.append(
            AgentTerminalGitChangeResponse(
                path=path,
                old_path=old_path,
                scope="unstaged",
                kind=_status_kind(worktree_status),
            )
        )


def _status_kind(value: str) -> str:
    kind = _STATUS_KIND.get(value)
    if kind is None:
        raise AgentTerminalGitError("agent_terminal.git_output_invalid")
    return kind


def _validate_relative_path(value: str) -> None:
    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or value != candidate.as_posix()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise AgentTerminalGitError("agent_terminal.git_path_invalid")


def _read_blob(root: Path, spec: str) -> _Content:
    size_response = _run_git(
        root,
        ["cat-file", "-s", spec],
        max_output_bytes=128,
    )
    if size_response.returncode != 0:
        return _Content()
    try:
        size = int(size_response.stdout.strip())
    except ValueError as exc:
        raise AgentTerminalGitError("agent_terminal.git_output_invalid") from exc
    if size > _MAX_CONTENT_BYTES:
        return _Content(too_large=True)
    content_response = _run_git(
        root,
        ["cat-file", "blob", spec],
        max_output_bytes=_MAX_CONTENT_BYTES,
    )
    if content_response.returncode != 0:
        raise AgentTerminalGitError("agent_terminal.git_operation_failed")
    return _decode_content(content_response.stdout)


def _read_worktree_file(root: Path, relative_path: str) -> _Content:
    _validate_relative_path(relative_path)
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        resolved_parent.relative_to(root)
        metadata = candidate.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return _Content()
    except (OSError, ValueError) as exc:
        raise AgentTerminalGitError("agent_terminal.git_path_invalid") from exc

    if stat.S_ISLNK(metadata.st_mode):
        try:
            return _decode_content(os.readlink(candidate).encode("utf-8"))
        except (OSError, UnicodeEncodeError) as exc:
            raise AgentTerminalGitError("agent_terminal.git_operation_failed") from exc
    if not stat.S_ISREG(metadata.st_mode):
        return _Content(binary=True)
    if metadata.st_size > _MAX_CONTENT_BYTES:
        return _Content(too_large=True)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
        with os.fdopen(descriptor, "rb") as stream:
            payload = stream.read(_MAX_CONTENT_BYTES + 1)
    except OSError as exc:
        raise AgentTerminalGitError("agent_terminal.git_operation_failed") from exc
    if len(payload) > _MAX_CONTENT_BYTES:
        return _Content(too_large=True)
    return _decode_content(payload)


def _decode_content(payload: bytes) -> _Content:
    if b"\0" in payload:
        return _Content(binary=True)
    try:
        return _Content(value=payload.decode("utf-8"))
    except UnicodeDecodeError:
        return _Content(binary=True)
