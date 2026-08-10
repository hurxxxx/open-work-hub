#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE_ROOTS = (
    Path("apps/api/src/ai_do_api"),
    Path("apps/worker/src/ai_do_worker"),
)

FORBIDDEN_DIRECT_LLM_IMPORTS = {
    "complete_chat",
    "complete_chat_stream",
    "complete_chat_text",
    "resolve_chat_execution",
}


@dataclass(frozen=True, order=True)
class Finding:
    path: Path
    line: int
    code: str
    message: str


def _is_overload(definition: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in definition.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "overload":
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == "overload":
            return True
    return False


def _duplicate_top_level_definitions(tree: ast.Module, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_overload(statement):
            continue
        previous = seen.get(statement.name)
        if previous is not None:
            findings.append(
                Finding(
                    path=path,
                    line=statement.lineno,
                    code="duplicate-top-level-definition",
                    message=(
                        f"{statement.name!r} shadows the top-level definition on line "
                        f"{previous.lineno}."
                    ),
                )
            )
        else:
            seen[statement.name] = statement
    return findings


def _duplicate_literal_dict_keys(tree: ast.Module, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict[object, int] = {}
        for key in node.keys:
            if key is None:
                continue
            try:
                value = ast.literal_eval(key)
                hash(value)
            except (ValueError, TypeError):
                continue
            previous_line = seen.get(value)
            if previous_line is not None:
                findings.append(
                    Finding(
                        path=path,
                        line=getattr(key, "lineno", node.lineno),
                        code="duplicate-literal-dict-key",
                        message=(
                            f"literal dict key {value!r} duplicates the key on line "
                            f"{previous_line}."
                        ),
                    )
                )
            else:
                seen[value] = getattr(key, "lineno", node.lineno)
    return findings


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _duplicate_router_specs(tree: ast.Module, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) != "_RouterSpec":
            continue
        router_node = node.args[0] if node.args else next(
            (keyword.value for keyword in node.keywords if keyword.arg == "router"),
            None,
        )
        if router_node is None:
            continue
        router_name = _call_name(router_node)
        if router_name is None:
            continue
        previous_line = seen.get(router_name)
        if previous_line is not None:
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    code="duplicate-router-spec",
                    message=(
                        f"_RouterSpec registers {router_name!r} again; first registration "
                        f"is on line {previous_line}."
                    ),
                )
            )
        else:
            seen[router_name] = node.lineno
    return findings


def _direct_core_llm_imports(tree: ast.Module, path: Path) -> list[Finding]:
    normalized = path.as_posix()
    if normalized.endswith("/core/llm.py") or normalized.endswith("/domains/ai/gateway.py"):
        return []

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports_core_llm_module = module == "ai_do_api.core.llm" or (
                node.level > 0 and module == "core.llm"
            )
            imports_core_package = module == "ai_do_api.core" or (
                node.level > 0 and module == "core"
            )
            for imported in node.names:
                if (
                    imports_core_llm_module
                    and imported.name in FORBIDDEN_DIRECT_LLM_IMPORTS
                ):
                    findings.append(
                        Finding(
                            path=path,
                            line=node.lineno,
                            code="direct-core-llm-import",
                            message=(
                                f"{imported.name!r} bypasses the AI gateway even when aliased."
                            ),
                        )
                    )
                elif imports_core_package and imported.name == "llm":
                    findings.append(
                        Finding(
                            path=path,
                            line=node.lineno,
                            code="direct-core-llm-import",
                            message="core.llm module import can bypass the AI gateway.",
                        )
                    )
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == "ai_do_api.core.llm":
                    findings.append(
                        Finding(
                            path=path,
                            line=node.lineno,
                            code="direct-core-llm-import",
                            message="module import can bypass the AI gateway.",
                        )
                    )
    return findings


def check_python_file(path: Path) -> list[Finding]:
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=(3, 12),
        )
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [
            Finding(
                path=path,
                line=getattr(exc, "lineno", 1) or 1,
                code="python-source-parse-error",
                message=str(exc),
            )
        ]
    return [
        *_duplicate_top_level_definitions(tree, path),
        *_duplicate_literal_dict_keys(tree, path),
        *_duplicate_router_specs(tree, path),
        *_direct_core_llm_imports(tree, path),
    ]


def check_python_sources(source_roots: list[Path] | tuple[Path, ...]) -> list[Finding]:
    findings: list[Finding] = []
    for source_root in source_roots:
        if not source_root.is_dir():
            findings.append(
                Finding(
                    path=source_root,
                    line=1,
                    code="missing-python-source-root",
                    message="configured Python source root does not exist.",
                )
            )
            continue
        for path in sorted(source_root.rglob("*.py")):
            findings.extend(check_python_file(path))
    return sorted(findings)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect Python source shadowing and duplicate static registrations."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used to resolve default source roots.",
    )
    parser.add_argument(
        "--source-root",
        action="append",
        type=Path,
        default=None,
        help="Source root to scan. May be repeated; defaults to API and worker sources.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    source_roots = (
        [path.resolve() for path in args.source_root]
        if args.source_root
        else [repo_root / relative_path for relative_path in DEFAULT_SOURCE_ROOTS]
    )
    findings = check_python_sources(source_roots)
    if findings:
        for finding in findings:
            try:
                display_path = finding.path.relative_to(repo_root)
            except ValueError:
                display_path = finding.path
            print(
                f"[python-source-integrity] {display_path}:{finding.line}: "
                f"{finding.code}: {finding.message}",
                file=sys.stderr,
            )
        return 1
    file_count = sum(1 for root in source_roots for _ in root.rglob("*.py"))
    print(f"[python-source-integrity] ok ({file_count} Python source files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
