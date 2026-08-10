#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from re import Pattern


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE_PARTS = [
    Path("apps/api/src/open_work_hub_api/core/settings.py"),
    Path("apps/worker/src/open_work_hub_worker/settings.py"),
]
SETTINGS_FILES = [ROOT / part for part in SETTINGS_FILE_PARTS]
DEPLOY_ENV_KEYS: frozenset[str] = frozenset()

FORBIDDEN_ENV_KEYS = frozenset(
    {
        "OPEN_WORK_HUB_AI_MANAGER_ENABLED",
        "OPEN_WORK_HUB_AI_MANAGER_HOSTED_TOOLS_ENABLED",
        "OPEN_WORK_HUB_AI_MANAGER_MAX_LOOPS",
        "OPEN_WORK_HUB_AI_MANAGER_MODEL",
        "OPEN_WORK_HUB_AI_MANAGER_PROVIDER",
        "OPEN_WORK_HUB_AI_MANAGER_STORE_RESPONSE",
        "OPEN_WORK_HUB_AI_MANAGER_TRACE_SENSITIVE_DATA",
        "OPEN_WORK_HUB_API_RECORDING_CHUNK_SECONDS",
        "OPEN_WORK_HUB_CUSTOMER_CODE",
        "OPEN_WORK_HUB_ENABLED_EXTENSION_APPS",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_CONCURRENCY",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_ENABLED",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_LANGUAGE",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_MAX_NEW_TOKENS",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_MODEL",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_PUBLIC_MODEL",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_ASR_REVISION",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_DEVICE",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_DOCLING_CONCURRENCY",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_DOCLING_ENABLED",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_DTYPE",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_EMBEDDING_BATCH_SIZE",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_EMBEDDING_CONCURRENCY",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_EMBEDDING_ENABLED",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_EMBEDDING_MODEL",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_EMBEDDING_QUERY_PROMPT_NAME",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_EMBEDDING_REVISION",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_HF_TOKEN_FILE",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_HOST",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_MAX_EMBEDDING_INPUTS",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_MAX_RERANK_DOCUMENTS",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_MAX_TEXT_CHARS",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_MAX_UPLOAD_BYTES",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_PORT",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_RERANKER_BATCH_SIZE",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_RERANKER_CONCURRENCY",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_RERANKER_ENABLED",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_RERANKER_MODEL",
        "OPEN_WORK_HUB_INFERENCE_GATEWAY_RERANKER_REVISION",
        "OPEN_WORK_HUB_RAG_UI_ENABLED",
        "GOOGLE_CLOUD_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
    }
)

FORBIDDEN_ENV_PATTERNS = [
    re.compile(r"\bOPEN WORK HUB_[A-Z0-9_]*\b"),
    re.compile(r"(?<!OPEN_WORK_HUB_)\bLOCAL_AI_[A-Z0-9_]*\b"),
    re.compile(r"\bAI_AGENT_MAX_[A-Z0-9_]*\b"),
    re.compile(r"\bAI_TOOL_CALLING_ENABLED\b"),
    re.compile(r"\bOPENAI_API_KEY\b"),
    re.compile(r"\bANTHROPIC_API_KEY\b"),
    re.compile(r"\bGEMINI_API_KEY\b"),
    re.compile(r"\bCOHERE_API_KEY\b"),
    re.compile(r"\bHUGGINGFACE_HUB_TOKEN\b"),
    re.compile(r"\bOPEN_WORK_HUB_REDIS_URL\b"),
]

SKIP_DIRS = {
    ".dev",
    ".git",
    ".mypy_cache",
    ".nx",
    ".rag-validation",
    ".ruff_cache",
    ".runtime",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
SKIP_FILE_PARTS = (".backup",)
SKIP_SETTINGS_KEYS = {"OPEN_WORK_HUB_API_OPEN_WORK_HUB_DESKTOP_UPDATE_DIRS"}
SOURCE_FILE_SUFFIXES = {
    ".py",
    ".sh",
    ".mjs",
    ".mts",
    ".ts",
    ".tsx",
    ".js",
    ".cjs",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".template",
    ".conf",
    ".toml",
    ".ini",
}
SOURCE_FILE_NAMES = {".env", ".env.example"}


@dataclass(frozen=True)
class EnvFileContent:
    name: str
    path: Path
    text: str | None


@dataclass(frozen=True)
class TextFileContent:
    path: Path
    text: str | None
    label: str | None = None

    @property
    def display_name(self) -> str:
        return self.label or str(self.path)


@dataclass(frozen=True)
class ParsedEnvFile:
    name: str
    path: Path
    keys: tuple[str, ...]
    key_lines: Mapping[str, tuple[int, ...]]
    missing: bool = False

    @property
    def key_set(self) -> frozenset[str]:
        return frozenset(self.keys)

    @property
    def duplicate_lines(self) -> dict[str, tuple[int, ...]]:
        return {key: refs for key, refs in self.key_lines.items() if len(refs) > 1}


@dataclass(frozen=True)
class SettingsFileScan:
    path: Path
    keys: frozenset[str]
    missing: bool = False
    parse_error: str | None = None


@dataclass(frozen=True)
class ForbiddenTokenHit:
    path: str
    pattern: str


@dataclass(frozen=True)
class EnvContractFailure:
    code: str
    message: str


@dataclass(frozen=True)
class EnvContractReport:
    current_env_name: str
    env_files: tuple[ParsedEnvFile, ...]
    settings_files: tuple[SettingsFileScan, ...]
    forbidden_hits: tuple[ForbiddenTokenHit, ...]
    failures: tuple[EnvContractFailure, ...]

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def env_by_name(self) -> dict[str, ParsedEnvFile]:
        return {env_file.name: env_file for env_file in self.env_files}

    @property
    def settings_keys(self) -> frozenset[str]:
        keys: set[str] = set()
        for settings_file in self.settings_files:
            keys.update(settings_file.keys)
        keys.update(DEPLOY_ENV_KEYS)
        return frozenset(keys)

    def success_message(self) -> str:
        base = self.env_by_name.get(self.current_env_name)
        base_key_count = len(base.key_set) if base else 0
        env_names = ", ".join(sorted(self.env_by_name))
        return (
            f"ok: {base_key_count} keys across {env_names}; "
            f"{len(self.settings_keys)} settings keys covered"
        )


def current_env_name(root: Path) -> str:
    return root.name if root.name in {"dev", "prod"} else "current"


def env_file_paths(root: Path, env_name: str) -> dict[str, Path]:
    env_files = {
        env_name: root / ".env",
        "example": root / ".env.example",
    }
    local_env = root / ".env.local"
    if local_env.exists():
        env_files["local"] = local_env
    for sibling_name in ("dev", "prod"):
        sibling_env = root.parent / sibling_name / ".env"
        if sibling_name != env_name and sibling_env.exists():
            env_files[sibling_name] = sibling_env
    return env_files


def settings_file_paths(root: Path) -> tuple[Path, ...]:
    return tuple(root / part for part in SETTINGS_FILE_PARTS)


def parse_env_text(text: str) -> tuple[tuple[str, ...], dict[str, tuple[int, ...]]]:
    keys: list[str] = []
    lines: dict[str, list[int]] = {}
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if not key:
            continue
        keys.append(key)
        lines.setdefault(key, []).append(line_number)
    return tuple(keys), {key: tuple(refs) for key, refs in lines.items()}


def parse_env(env_file: EnvFileContent) -> ParsedEnvFile:
    if env_file.text is None:
        return ParsedEnvFile(
            name=env_file.name,
            path=env_file.path,
            keys=(),
            key_lines={},
            missing=True,
        )
    keys, lines = parse_env_text(env_file.text)
    return ParsedEnvFile(
        name=env_file.name,
        path=env_file.path,
        keys=keys,
        key_lines=lines,
    )


def string_literals(node: ast.AST) -> list[str]:
    values: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.append(node.value)
    for child in ast.iter_child_nodes(node):
        values.extend(string_literals(child))
    return values


def env_prefix_from_model_config(stmt: ast.stmt) -> str | None:
    value: ast.AST | None = None
    target_name: str | None = None
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
    ):
        target_name = stmt.targets[0].id
        value = stmt.value
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        target_name = stmt.target.id
        value = stmt.value
    if target_name != "model_config" or not isinstance(value, ast.Call):
        return None
    for keyword in value.keywords:
        if (
            keyword.arg == "env_prefix"
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        ):
            return keyword.value.value
    return None


def uppercase_field_name(name: str) -> str:
    return name.upper()


def settings_env_keys_from_tree(tree: ast.AST) -> frozenset[str]:
    keys: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Settings":
            continue
        env_prefix = ""
        for stmt in node.body:
            env_prefix = env_prefix_from_model_config(stmt) or env_prefix
        for stmt in node.body:
            field_name: str | None = None
            value: ast.AST | None = None
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                field_name = stmt.target.id
                value = stmt.value
            elif (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                field_name = stmt.targets[0].id
                value = stmt.value
            if not field_name or field_name.startswith("_") or field_name == "model_config":
                continue
            aliases: list[str] = []
            if isinstance(value, ast.Call):
                for keyword in value.keywords:
                    if keyword.arg == "validation_alias":
                        aliases.extend(
                            literal
                            for literal in string_literals(keyword.value)
                            if re.fullmatch(r"[A-Z][A-Z0-9_]*", literal)
                        )
            if aliases:
                keys.update(aliases)
            elif env_prefix:
                keys.add(env_prefix + uppercase_field_name(field_name))
    return frozenset(keys - SKIP_SETTINGS_KEYS)


def settings_env_keys_from_text(
    text: str,
    *,
    filename: str = "<settings>",
) -> frozenset[str]:
    tree = ast.parse(text, filename=filename)
    return settings_env_keys_from_tree(tree)


def settings_env_keys(path: Path) -> frozenset[str]:
    return settings_env_keys_from_text(path.read_text(encoding="utf-8"), filename=str(path))


def scan_settings_file(settings_file: TextFileContent) -> SettingsFileScan:
    if settings_file.text is None:
        return SettingsFileScan(settings_file.path, frozenset(), missing=True)
    try:
        keys = settings_env_keys_from_text(
            settings_file.text,
            filename=settings_file.display_name,
        )
    except SyntaxError as exc:
        return SettingsFileScan(
            settings_file.path,
            frozenset(),
            parse_error=f"{exc.__class__.__name__}: {exc.msg}",
        )
    return SettingsFileScan(settings_file.path, keys)


def should_scan_source_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    if any(part in path.name for part in SKIP_FILE_PARTS):
        return False
    return path.suffix in SOURCE_FILE_SUFFIXES or path.name in SOURCE_FILE_NAMES


def source_files(
    root: Path = ROOT,
    *,
    excluded_paths: Iterable[Path] = (),
) -> list[Path]:
    excluded = {path.resolve() for path in excluded_paths}
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() in excluded:
            continue
        if should_scan_source_file(path, root):
            result.append(path)
    return result


def scan_forbidden_tokens(
    source_file_contents: Iterable[TextFileContent],
    forbidden_patterns: Iterable[Pattern[str]],
) -> tuple[ForbiddenTokenHit, ...]:
    patterns = tuple(forbidden_patterns)
    hits: list[ForbiddenTokenHit] = []
    for source_file in source_file_contents:
        if source_file.text is None:
            continue
        for pattern in patterns:
            if pattern.search(source_file.text):
                hits.append(
                    ForbiddenTokenHit(
                        path=source_file.display_name,
                        pattern=pattern.pattern,
                    )
                )
                break
    return tuple(hits)


def evaluate_env_contract(
    env_files: Iterable[EnvFileContent],
    settings_files: Iterable[TextFileContent],
    source_file_contents: Iterable[TextFileContent],
    current_env_name: str,
    forbidden_patterns: Iterable[Pattern[str]],
    forbidden_env_keys: Iterable[str] = (),
) -> EnvContractReport:
    parsed_env_files = tuple(parse_env(env_file) for env_file in env_files)
    settings_scans = tuple(
        scan_settings_file(settings_file) for settings_file in settings_files
    )
    forbidden_hits = scan_forbidden_tokens(source_file_contents, forbidden_patterns)

    failures: list[EnvContractFailure] = []
    env_by_name = {env_file.name: env_file for env_file in parsed_env_files}

    for env_file in parsed_env_files:
        if env_file.missing:
            failures.append(
                EnvContractFailure(
                    code="missing_env_file",
                    message=f"{env_file.name}: missing env file at {env_file.path}",
                )
            )
            continue
        duplicates = env_file.duplicate_lines
        if duplicates:
            failures.append(
                EnvContractFailure(
                    code="duplicate_env_key",
                    message=(
                        f"{env_file.name}: duplicate keys: "
                        f"{', '.join(sorted(duplicates))}"
                    ),
                )
            )

    base = env_by_name.get(current_env_name)
    if base is None:
        failures.append(
            EnvContractFailure(
                code="missing_current_env",
                message=f"{current_env_name}: current env file was not provided",
            )
        )
    elif not base.missing:
        for env_file in parsed_env_files:
            if env_file.name == current_env_name or env_file.missing:
                continue
            missing = sorted(base.key_set - env_file.key_set)
            extra = sorted(env_file.key_set - base.key_set)
            if missing or extra:
                failures.append(
                    EnvContractFailure(
                        code="env_keyset_mismatch",
                        message=(
                            f"{env_file.name}: keyset mismatch against {current_env_name}; "
                            f"missing={len(missing)} extra={len(extra)}"
                        ),
                    )
                )
            elif env_file.keys != base.keys:
                failures.append(
                    EnvContractFailure(
                        code="env_key_order_mismatch",
                        message=(
                            f"{env_file.name}: key order mismatch against "
                            f"{current_env_name}"
                        ),
                    )
                )

        forbidden_keys_present = sorted(base.key_set.intersection(forbidden_env_keys))
        if forbidden_keys_present:
            failures.append(
                EnvContractFailure(
                    code="forbidden_env_key",
                    message=(
                        "env files contain retired or externally owned keys: "
                        + ", ".join(forbidden_keys_present)
                    ),
                )
            )

    for settings_scan in settings_scans:
        if settings_scan.missing:
            failures.append(
                EnvContractFailure(
                    code="missing_settings_file",
                    message=f"{settings_scan.path}: missing settings file",
                )
            )
        elif settings_scan.parse_error:
            failures.append(
                EnvContractFailure(
                    code="invalid_settings_file",
                    message=f"{settings_scan.path}: {settings_scan.parse_error}",
                )
            )

    settings_keys: set[str] = set(DEPLOY_ENV_KEYS)
    for settings_scan in settings_scans:
        settings_keys.update(settings_scan.keys)
    if base is not None and not base.missing:
        missing_settings_keys = sorted(settings_keys - base.key_set)
        if missing_settings_keys:
            failures.append(
                EnvContractFailure(
                    code="missing_settings_key",
                    message=(
                        "env files are missing settings keys: "
                        + ", ".join(missing_settings_keys)
                    ),
                )
            )

    for hit in forbidden_hits:
        failures.append(
            EnvContractFailure(
                code="forbidden_env_token",
                message=f"{hit.path}: forbidden env token {hit.pattern}",
            )
        )

    return EnvContractReport(
        current_env_name=current_env_name,
        env_files=parsed_env_files,
        settings_files=settings_scans,
        forbidden_hits=forbidden_hits,
        failures=tuple(failures),
    )


def relative_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_text_maybe(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def load_env_file(name: str, path: Path) -> EnvFileContent:
    return EnvFileContent(name=name, path=path, text=read_text_maybe(path))


def load_text_file(path: Path, *, root: Path = ROOT) -> TextFileContent:
    return TextFileContent(
        path=path,
        text=read_text_maybe(path),
        label=relative_label(path, root),
    )


def build_report(root: Path = ROOT) -> EnvContractReport:
    env_name = current_env_name(root)
    env_files = tuple(
        load_env_file(name, path) for name, path in env_file_paths(root, env_name).items()
    )
    settings_files = tuple(
        load_text_file(path, root=root) for path in settings_file_paths(root)
    )
    source_file_contents = tuple(
        load_text_file(path, root=root)
        for path in source_files(root, excluded_paths={Path(__file__).resolve()})
    )
    return evaluate_env_contract(
        env_files=env_files,
        settings_files=settings_files,
        source_file_contents=source_file_contents,
        current_env_name=env_name,
        forbidden_patterns=FORBIDDEN_ENV_PATTERNS,
        forbidden_env_keys=FORBIDDEN_ENV_KEYS,
    )


def format_report_lines(report: EnvContractReport) -> tuple[str, ...]:
    if report.failures:
        return tuple(f"[env-contract] {failure.message}" for failure in report.failures)
    return (f"[env-contract] {report.success_message()}",)


def main() -> int:
    report = build_report(ROOT)

    if not report.ok:
        for line in format_report_lines(report):
            print(line, file=sys.stderr)
        return 1

    for line in format_report_lines(report):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
