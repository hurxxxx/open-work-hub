#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps/api/src/open_work_hub_api"
I18N_CATALOG_PATH = API_SRC / "core/i18n_catalog.py"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str

    def render(self, root: Path = ROOT) -> str:
        rel_path = _relative_path(self.path, root)
        return f"{rel_path}:{self.line}: {self.message}"


@dataclass(frozen=True)
class PythonSource:
    path: Path
    text: str


@dataclass(frozen=True)
class CodeUse:
    code: str
    path: Path
    line: int
    source: str


@dataclass(frozen=True)
class ApiI18nCatalogSnapshot:
    path: Path
    supported_locales: tuple[str, ...]
    messages: dict[str, Any]
    param_value_translations: dict[str, Any]
    message_param_value_translations: dict[tuple[str, str], str]


@dataclass(frozen=True)
class ApiI18nSnapshot:
    catalog: ApiI18nCatalogSnapshot
    static_code_uses: tuple[CodeUse, ...]
    validation_code_uses: tuple[CodeUse, ...]
    raw_http_exception_details: tuple[Finding, ...]


@dataclass(frozen=True)
class ApiI18nReport:
    snapshot: ApiI18nSnapshot
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings


def _relative_path(path: Path, root: Path = ROOT) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _literal_assignment(tree: ast.AST, name: str, catalog_path: Path) -> Any:
    for node in ast.walk(tree):
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                value = node.value
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                value = node.value
        if value is not None:
            return ast.literal_eval(value)
    raise RuntimeError(f"{name} was not found in {_relative_path(catalog_path)}")


def _py_files() -> list[Path]:
    return sorted(API_SRC.rglob("*.py"))


def _read_python_source(path: Path) -> PythonSource:
    # 소스는 항상 UTF-8 이다. 인코딩을 생략하면 로케일 기본값을 쓰므로
    # Windows(cp949)에서 한글이 든 파일을 읽다가 UnicodeDecodeError 로 죽는다.
    return PythonSource(path=path, text=path.read_text(encoding="utf-8"))


def _api_source_files() -> tuple[PythonSource, ...]:
    return tuple(_read_python_source(path) for path in _py_files())


def _parse_python_source(source_file: PythonSource) -> ast.AST:
    return ast.parse(
        source_file.text,
        filename=str(source_file.path),
        feature_version=(3, 12),
    )


def parse_api_i18n_catalog(catalog_source: PythonSource) -> ApiI18nCatalogSnapshot:
    tree = _parse_python_source(catalog_source)
    return ApiI18nCatalogSnapshot(
        path=catalog_source.path,
        supported_locales=tuple(_literal_assignment(tree, "SUPPORTED_LOCALES", catalog_source.path)),
        messages=_literal_assignment(tree, "MESSAGES", catalog_source.path),
        param_value_translations=_literal_assignment(
            tree,
            "PARAM_VALUE_TRANSLATIONS",
            catalog_source.path,
        ),
        message_param_value_translations=_literal_assignment(
            tree,
            "MESSAGE_PARAM_VALUE_TRANSLATIONS",
            catalog_source.path,
        ),
    )


def _function_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _keyword_string(node: ast.Call, name: str) -> str | None:
    for keyword in node.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                return keyword.value.value
    return None


def _collect_static_code_uses(source_files: tuple[PythonSource, ...]) -> list[CodeUse]:
    uses: list[CodeUse] = []
    for source_file in source_files:
        tree = _parse_python_source(source_file)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = _function_name(node)
            if function_name in {"localized_http_exception", "LocalizedApiMessage"}:
                code = _keyword_string(node, "code")
                if code is not None:
                    uses.append(CodeUse(code, source_file.path, node.lineno, function_name))
            elif function_name == "PydanticCustomError":
                if node.args and isinstance(node.args[0], ast.Constant):
                    code = node.args[0].value
                    if isinstance(code, str):
                        uses.append(CodeUse(code, source_file.path, node.lineno, function_name))
    return uses


def _collect_validation_code_uses(source_files: tuple[PythonSource, ...]) -> list[CodeUse]:
    uses: list[CodeUse] = []
    for source_file in source_files:
        tree = _parse_python_source(source_file)
        for node in ast.walk(tree):
            value: ast.expr | None = None
            target_name: str | None = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        target_name = target.id
                        value = node.value
                        break
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_name = node.target.id
                value = node.value
            if target_name is None or value is None:
                continue
            if target_name == "GENERIC_VALIDATION_ERROR_TYPES" and isinstance(value, ast.Dict):
                for item in value.values:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        uses.append(
                            CodeUse(
                                item.value,
                                source_file.path,
                                getattr(item, "lineno", node.lineno),
                                target_name,
                            )
                        )
            elif target_name.endswith("VALIDATION_ERROR_TYPES"):
                for child in ast.walk(value):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        uses.append(
                            CodeUse(
                                child.value,
                                source_file.path,
                                getattr(child, "lineno", node.lineno),
                                target_name,
                            )
                        )
    return uses


def _format_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _literal, field_name, _format_spec, _conversion in Formatter().parse(template):
        if field_name:
            fields.add(field_name)
    return fields


def _validate_messages(catalog: ApiI18nCatalogSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    messages = catalog.messages
    supported_locales = catalog.supported_locales
    for code, translations in sorted(messages.items()):
        if not isinstance(translations, dict):
            findings.append(Finding(catalog.path, 1, f"{code} translations must be a mapping."))
            continue
        missing = [locale for locale in supported_locales if locale not in translations]
        if missing:
            findings.append(
                Finding(catalog.path, 1, f"{code} is missing locale(s): {', '.join(missing)}")
            )
            continue
        placeholder_sets: dict[str, set[str]] = {}
        for locale in supported_locales:
            template = translations[locale]
            if not isinstance(template, str) or not template:
                findings.append(Finding(catalog.path, 1, f"{code}.{locale} must be a non-empty string."))
                continue
            try:
                placeholder_sets[locale] = _format_fields(template)
            except ValueError as error:
                findings.append(
                    Finding(catalog.path, 1, f"{code}.{locale} has invalid format placeholders: {error}")
                )
        if len(set(map(frozenset, placeholder_sets.values()))) > 1:
            rendered = ", ".join(
                f"{locale}={sorted(fields)}" for locale, fields in sorted(placeholder_sets.items())
            )
            findings.append(Finding(catalog.path, 1, f"{code} placeholder mismatch: {rendered}"))
    return findings


def _validate_param_value_translations(catalog: ApiI18nCatalogSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    messages = catalog.messages
    supported_locales = catalog.supported_locales
    param_value_translations = catalog.param_value_translations
    message_param_value_translations = catalog.message_param_value_translations
    for (message_code, param_name), translation_key in sorted(message_param_value_translations.items()):
        if message_code not in messages:
            findings.append(
                Finding(catalog.path, 1, f"{message_code}.{param_name} param translation uses unknown message code.")
            )
        if translation_key not in param_value_translations:
            findings.append(
                Finding(catalog.path, 1, f"{message_code}.{param_name} uses unknown param translation {translation_key}.")
            )
            continue
        for raw_value, translations in sorted(param_value_translations[translation_key].items()):
            missing = [locale for locale in supported_locales if locale not in translations]
            if missing:
                findings.append(
                    Finding(
                        catalog.path,
                        1,
                        f"{translation_key}.{raw_value} is missing locale(s): {', '.join(missing)}",
                    )
                )
    return findings


def _validate_code_uses(
    messages: dict[str, Any],
    uses: tuple[CodeUse, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for use in sorted(set(uses), key=lambda item: (str(item.path), item.line, item.code)):
        if use.code not in messages:
            findings.append(Finding(use.path, use.line, f"{use.source} uses unknown i18n code: {use.code}"))
    return findings


def _collect_raw_http_exception_details(source_files: tuple[PythonSource, ...]) -> list[Finding]:
    findings: list[Finding] = []
    for source_file in source_files:
        tree = _parse_python_source(source_file)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _function_name(node) != "HTTPException":
                continue
            detail = _keyword_string(node, "detail")
            if detail is not None:
                findings.append(
                    Finding(
                        source_file.path,
                        node.lineno,
                        "HTTPException detail must use localized_http_exception or LocalizedApiMessage.",
                    )
                )
    return findings


def build_api_i18n_snapshot(
    *,
    catalog_source: PythonSource,
    source_files: tuple[PythonSource, ...],
) -> ApiI18nSnapshot:
    return ApiI18nSnapshot(
        catalog=parse_api_i18n_catalog(catalog_source),
        static_code_uses=tuple(_collect_static_code_uses(source_files)),
        validation_code_uses=tuple(_collect_validation_code_uses(source_files)),
        raw_http_exception_details=tuple(_collect_raw_http_exception_details(source_files)),
    )


def evaluate_api_i18n_messages(
    *,
    catalog_source: PythonSource,
    source_files: tuple[PythonSource, ...],
) -> ApiI18nReport:
    snapshot = build_api_i18n_snapshot(
        catalog_source=catalog_source,
        source_files=source_files,
    )
    findings: list[Finding] = []
    findings.extend(_validate_messages(snapshot.catalog))
    findings.extend(_validate_param_value_translations(snapshot.catalog))
    findings.extend(_validate_code_uses(snapshot.catalog.messages, snapshot.static_code_uses))
    findings.extend(_validate_code_uses(snapshot.catalog.messages, snapshot.validation_code_uses))
    findings.extend(snapshot.raw_http_exception_details)
    return ApiI18nReport(snapshot=snapshot, findings=tuple(findings))


def main() -> int:
    report = evaluate_api_i18n_messages(
        catalog_source=_read_python_source(I18N_CATALOG_PATH),
        source_files=_api_source_files(),
    )
    if report.findings:
        print("API i18n guard found issue(s):")
        for finding in report.findings:
            print(f"  {finding.render()}")
        return 1

    print("API i18n guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
