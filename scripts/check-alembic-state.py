#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REVISION_ASSIGNMENT_RE = re.compile(
    r"^revision\s*(?::[^=]+)?=\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
ALEMBIC_REVISION_LINE_RE = re.compile(r"^([0-9a-f]{4,})\b", re.IGNORECASE)
GRAPH_ERROR_MARKERS = (
    "present more than once",
    "Cycle is detected",
    "Dependency cycle is detected",
)


def parse_revision_assignment(source: str) -> str | None:
    match = REVISION_ASSIGNMENT_RE.search(source)
    if match is None:
        return None
    return match.group(1)


def collect_revision_files(api_root: Path) -> dict[str, list[Path]]:
    versions_dir = api_root / "alembic" / "versions"
    revisions: dict[str, list[Path]] = defaultdict(list)
    if not versions_dir.is_dir():
        raise RuntimeError(f"Alembic versions directory does not exist: {versions_dir}")

    for path in sorted(versions_dir.glob("*.py")):
        revision = parse_revision_assignment(path.read_text(encoding="utf-8"))
        if revision:
            revisions[revision].append(path)
    return dict(revisions)


def validate_unique_revision_ids(api_root: Path) -> None:
    revisions = collect_revision_files(api_root)
    duplicates = {revision: paths for revision, paths in revisions.items() if len(paths) > 1}
    if not duplicates:
        print(f"[alembic-state] revision ids unique across {len(revisions)} migration file(s)")
        return

    lines = ["Duplicate Alembic revision id(s) detected:"]
    for revision, paths in sorted(duplicates.items()):
        rendered_paths = ", ".join(str(path.relative_to(api_root)) for path in paths)
        lines.append(f"- {revision}: {rendered_paths}")
    raise RuntimeError("\n".join(lines))


@dataclass(frozen=True)
class StaticRevision:
    revision: str
    down_revisions: tuple[str, ...]
    dependencies: tuple[str, ...]
    path: Path


def _assignment_values(source: str, name: str, *, path: Path) -> list[object]:
    try:
        tree = ast.parse(source, filename=str(path), feature_version=(3, 12))
    except SyntaxError as exc:
        raise RuntimeError(f"Cannot parse migration {path}: {exc}") from exc

    values: list[object] = []
    for statement in tree.body:
        value_node: ast.expr | None = None
        targets: list[ast.expr] = []
        if isinstance(statement, ast.Assign):
            value_node = statement.value
            targets = list(statement.targets)
        elif isinstance(statement, ast.AnnAssign):
            value_node = statement.value
            targets = [statement.target]
        if value_node is None or not any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            continue
        try:
            values.append(ast.literal_eval(value_node))
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"Migration {path} must declare {name} as a literal value."
            ) from exc
    return values


def parse_static_revision(source: str, *, path: Path) -> StaticRevision:
    revision_values = _assignment_values(source, "revision", path=path)
    down_revision_values = _assignment_values(source, "down_revision", path=path)
    branch_label_values = _assignment_values(source, "branch_labels", path=path)
    dependency_values = _assignment_values(source, "depends_on", path=path)
    if len(revision_values) != 1:
        raise RuntimeError(
            f"Migration {path} must declare revision exactly once; found {len(revision_values)}."
        )
    if len(down_revision_values) != 1:
        raise RuntimeError(
            "Migration "
            f"{path} must declare down_revision exactly once; found {len(down_revision_values)}."
        )
    if len(branch_label_values) != 1:
        raise RuntimeError(
            f"Migration {path} must declare branch_labels exactly once; found "
            f"{len(branch_label_values)}."
        )
    if len(dependency_values) != 1:
        raise RuntimeError(
            f"Migration {path} must declare depends_on exactly once; found {len(dependency_values)}."
        )

    revision = revision_values[0]
    if not isinstance(revision, str) or not revision:
        raise RuntimeError(f"Migration {path} has an invalid revision value: {revision!r}")
    if branch_label_values[0] is not None:
        raise RuntimeError(
            f"Migration {path} branch_labels must be None; symbolic branch labels "
            "are not supported by the static CI graph contract."
        )

    def normalize_references(raw_value: object, label: str) -> tuple[str, ...]:
        if raw_value is None:
            references: tuple[str, ...] = ()
        elif isinstance(raw_value, str):
            references = (raw_value,)
        elif isinstance(raw_value, (tuple, list)) and all(
            isinstance(parent, str) and parent for parent in raw_value
        ):
            references = tuple(raw_value)
        else:
            raise RuntimeError(
                f"Migration {path} has an invalid {label} value: {raw_value!r}"
            )
        if len(set(references)) != len(references):
            raise RuntimeError(f"Migration {path} declares the same {label} more than once.")
        return references

    return StaticRevision(
        revision=revision,
        down_revisions=normalize_references(down_revision_values[0], "down_revision"),
        dependencies=normalize_references(dependency_values[0], "depends_on"),
        path=path,
    )


def collect_static_revision_graph(api_root: Path) -> dict[str, StaticRevision]:
    versions_dir = api_root / "alembic" / "versions"
    if not versions_dir.is_dir():
        raise RuntimeError(f"Alembic versions directory does not exist: {versions_dir}")

    revisions: dict[str, StaticRevision] = {}
    duplicate_paths: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(versions_dir.glob("*.py")):
        parsed = parse_static_revision(path.read_text(encoding="utf-8"), path=path)
        duplicate_paths[parsed.revision].append(path)
        revisions.setdefault(parsed.revision, parsed)

    duplicates = {
        revision: paths for revision, paths in duplicate_paths.items() if len(paths) > 1
    }
    if duplicates:
        lines = ["Duplicate Alembic revision id(s) detected:"]
        for revision, paths in sorted(duplicates.items()):
            rendered = ", ".join(str(path.relative_to(api_root)) for path in paths)
            lines.append(f"- {revision}: {rendered}")
        raise RuntimeError("\n".join(lines))
    if not revisions:
        raise RuntimeError("Alembic revision graph is empty.")
    return revisions


def validate_static_revision_graph(api_root: Path) -> str:
    revisions = collect_static_revision_graph(api_root)
    missing_parents = sorted(
        (revision, parent, node.path, label)
        for revision, node in revisions.items()
        for label, references in (
            ("down_revision", node.down_revisions),
            ("depends_on", node.dependencies),
        )
        for parent in references
        if parent not in revisions
    )
    if missing_parents:
        lines = ["Alembic migration(s) reference missing revisions:"]
        for revision, parent, path, label in missing_parents:
            lines.append(
                f"- {revision} ({path.relative_to(api_root)}) {label}: {parent}"
            )
        raise RuntimeError("\n".join(lines))

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(revision: str) -> None:
        if state.get(revision) == 2:
            return
        if state.get(revision) == 1:
            cycle_start = stack.index(revision)
            cycle = " -> ".join([*stack[cycle_start:], revision])
            raise RuntimeError(f"Alembic revision cycle detected: {cycle}")
        state[revision] = 1
        stack.append(revision)
        for parent in (
            *revisions[revision].down_revisions,
            *revisions[revision].dependencies,
        ):
            visit(parent)
        stack.pop()
        state[revision] = 2

    for revision in sorted(revisions):
        visit(revision)

    referenced = {
        parent for node in revisions.values() for parent in node.down_revisions
    }
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        rendered = ", ".join(heads) if heads else "none"
        raise RuntimeError(
            f"Expected exactly one static Alembic head, found {len(heads)} ({rendered})."
        )
    roots = sorted(
        revision for revision, node in revisions.items() if not node.down_revisions
    )
    if len(roots) != 1:
        rendered = ", ".join(roots) if roots else "none"
        raise RuntimeError(
            f"Expected exactly one Alembic base revision, found {len(roots)} ({rendered})."
        )

    head = heads[0]
    print(
        f"[alembic-state] static graph valid across {len(revisions)} migration file(s); "
        f"single head: {head}"
    )
    return head


def run_alembic(api_root: Path, *args: str) -> str:
    env = os.environ.copy()
    env["AI_DO_API_AUTO_MIGRATE"] = "0"
    process = subprocess.run(
        ["alembic", *args],
        cwd=api_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = "\n".join(part for part in (process.stdout, process.stderr) if part)
    if process.returncode != 0:
        raise RuntimeError(
            f"`alembic {' '.join(args)}` failed with exit code {process.returncode}.\n{output}"
        )
    if any(marker in output for marker in GRAPH_ERROR_MARKERS):
        raise RuntimeError(f"`alembic {' '.join(args)}` reported a graph error.\n{output}")
    return output


def extract_revision_lines(output: str) -> list[str]:
    revisions: list[str] = []
    for line in output.splitlines():
        match = ALEMBIC_REVISION_LINE_RE.match(line.strip())
        if match is not None:
            revisions.append(match.group(1))
    return revisions


def require_single_revision(label: str, revisions: list[str], raw_output: str) -> str:
    if len(revisions) == 1:
        return revisions[0]
    rendered = ", ".join(revisions) if revisions else "none"
    raise RuntimeError(
        f"Expected exactly one Alembic {label}, found {len(revisions)} ({rendered}).\n{raw_output}"
    )


def validate_alembic_state(api_root: Path, *, graph_only: bool) -> None:
    validate_unique_revision_ids(api_root)
    heads_output = run_alembic(api_root, "heads")
    head = require_single_revision("head", extract_revision_lines(heads_output), heads_output)
    print(f"[alembic-state] single head: {head}")

    if graph_only:
        return

    current_output = run_alembic(api_root, "current")
    current = require_single_revision(
        "current database revision",
        extract_revision_lines(current_output),
        current_output,
    )
    if current != head:
        raise RuntimeError(f"Alembic database revision {current} does not match head {head}.")
    print(f"[alembic-state] database current revision matches head: {current}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Alembic revision graph and, optionally, DB current state."
    )
    parser.add_argument(
        "--api-root",
        default=Path.cwd(),
        type=Path,
        help="Path to apps/api. Defaults to the current directory.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--graph-only",
        action="store_true",
        help="Validate revision files and Alembic heads without checking the DB current revision.",
    )
    modes.add_argument(
        "--static-graph-only",
        action="store_true",
        help="Validate the revision graph using only Python source parsing; do not import Alembic.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        api_root = args.api_root.resolve()
        if args.static_graph_only:
            validate_static_revision_graph(api_root)
        else:
            validate_alembic_state(api_root, graph_only=args.graph_only)
    except RuntimeError as exc:
        print(f"[alembic-state] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
