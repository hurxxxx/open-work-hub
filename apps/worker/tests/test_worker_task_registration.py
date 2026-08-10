from __future__ import annotations

import ast
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
TASKS_DIR = WORKSPACE_ROOT / "apps" / "worker" / "src" / "ai_do_worker" / "tasks"


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value)
        if base is None:
            return node.attr
        return f"{base}.{node.attr}"
    return None


def _declares_celery_task(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if _qualified_name(target) == "celery_app.task":
                return True
    return False


def _registered_task_modules() -> set[str]:
    init_path = TASKS_DIR / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    registered: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ai_do_worker.tasks":
            registered.update(alias.name for alias in node.names)
    return registered


def test_celery_task_modules_are_registered_for_worker_bootstrap() -> None:
    task_modules = {
        path.stem
        for path in TASKS_DIR.glob("*.py")
        if path.name != "__init__.py" and _declares_celery_task(path)
    }

    assert task_modules <= _registered_task_modules()
