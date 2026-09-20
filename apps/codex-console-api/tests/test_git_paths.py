import os
import subprocess

import pytest
from conftest import new_task

from codex_console import git
from codex_console.errors import ConsoleError


def test_parent_symlink_to_repository_secrets_is_not_exposed(client, repository):
    docs = repository / "docs"
    docs.mkdir()
    (docs / "file.txt").write_text("Public document")
    subprocess.run(["git", "-C", str(repository), "add", "docs"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "public fixture"],
        check=True,
        capture_output=True,
    )
    private = repository / "secrets"
    private.mkdir()
    (private / "file.txt").write_text("SYNTHETIC_PRIVATE_VALUE")
    (docs / "file.txt").unlink()
    docs.rmdir()
    docs.symlink_to(private, target_is_directory=True)
    task = new_task(client)
    changes = client.get(f"/api/tasks/{task['id']}/changes").json()
    assert not any(row["path"] == "docs/file.txt" for row in changes)
    response = client.get(f"/api/tasks/{task['id']}/diff", params={"path": "docs/file.txt"})
    assert response.status_code in (403, 404)
    assert "SYNTHETIC_PRIVATE_VALUE" not in response.text


def test_file_open_rejects_parent_link_installed_after_path_check(repository, monkeypatch):
    docs = repository / "docs"
    docs.mkdir()
    (docs / "file.txt").write_text("Public document")
    private = repository / "secrets"
    private.mkdir()
    (private / "file.txt").write_text("SYNTHETIC_PRIVATE_VALUE")
    original = git.safe_path

    def replace_after_validation(root, relative):
        path = original(root, relative)
        docs.rename(repository / "previous-docs")
        docs.symlink_to(private, target_is_directory=True)
        return path

    monkeypatch.setattr(git, "safe_path", replace_after_validation)
    with pytest.raises(ConsoleError) as error:
        git.read_worktree_file(repository, "docs/file.txt")
    assert error.value.code == "path_denied"


def test_worktree_read_bounds_growth_and_rejects_special_files(repository, monkeypatch):
    monkeypatch.setattr(git, "MAX_BYTES", 8)
    (repository / "large.txt").write_bytes(b"x" * 9)
    with pytest.raises(ConsoleError) as error:
        git.read_worktree_file(repository, "large.txt")
    assert error.value.code == "output_too_large"
    os.mkfifo(repository / "pipe")
    with pytest.raises(ConsoleError) as error:
        git.read_worktree_file(repository, "pipe")
    assert error.value.code == "output_too_large"
    assert git.read_worktree_file(repository, "deleted.txt") == b""
