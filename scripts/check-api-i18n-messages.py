#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps/api/src/aidoo_api"
I18N_PATH = API_SRC / "core/i18n.py"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str

    def render(self) -> str:
        rel_path = self.path.relative_to(ROOT)
        return f"{rel_path}:{self.line}: {self.message}"


def _literal_assignment(tree: ast.AST, name: str) -> Any:
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
    raise RuntimeError(f"{name} was not found in {I18N_PATH.relative_to(ROOT)}")


def _py_files() -> list[Path]:
    return sorted(API_SRC.rglob("*.py"))


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


def _collect_static_code_uses() -> list[tuple[str, Path, int, str]]:
    uses: list[tuple[str, Path, int, str]] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = _function_name(node)
            if function_name in {"localized_http_exception", "LocalizedApiMessage"}:
                code = _keyword_string(node, "code")
                if code is not None:
                    uses.append((code, path, node.lineno, function_name))
            elif function_name == "PydanticCustomError":
                if node.args and isinstance(node.args[0], ast.Constant):
                    code = node.args[0].value
                    if isinstance(code, str):
                        uses.append((code, path, node.lineno, function_name))
    return uses


def _collect_validation_code_uses() -> list[tuple[str, Path, int, str]]:
    uses: list[tuple[str, Path, int, str]] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(), filename=str(path))
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
                        uses.append((item.value, path, getattr(item, "lineno", node.lineno), target_name))
            elif target_name.endswith("VALIDATION_ERROR_TYPES"):
                for child in ast.walk(value):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        uses.append((child.value, path, getattr(child, "lineno", node.lineno), target_name))
    return uses


def _format_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _literal, field_name, _format_spec, _conversion in Formatter().parse(template):
        if field_name:
            fields.add(field_name)
    return fields


def _validate_messages(
    messages: dict[str, dict[str, str]],
    supported_locales: tuple[str, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for code, translations in sorted(messages.items()):
        if not isinstance(translations, dict):
            findings.append(Finding(I18N_PATH, 1, f"{code} translations must be a mapping."))
            continue
        missing = [locale for locale in supported_locales if locale not in translations]
        if missing:
            findings.append(
                Finding(I18N_PATH, 1, f"{code} is missing locale(s): {', '.join(missing)}")
            )
            continue
        placeholder_sets: dict[str, set[str]] = {}
        for locale in supported_locales:
            template = translations[locale]
            if not isinstance(template, str) or not template:
                findings.append(Finding(I18N_PATH, 1, f"{code}.{locale} must be a non-empty string."))
                continue
            try:
                placeholder_sets[locale] = _format_fields(template)
            except ValueError as error:
                findings.append(
                    Finding(I18N_PATH, 1, f"{code}.{locale} has invalid format placeholders: {error}")
                )
        if len(set(map(frozenset, placeholder_sets.values()))) > 1:
            rendered = ", ".join(
                f"{locale}={sorted(fields)}" for locale, fields in sorted(placeholder_sets.items())
            )
            findings.append(Finding(I18N_PATH, 1, f"{code} placeholder mismatch: {rendered}"))
    return findings


def _validate_param_value_translations(
    messages: dict[str, dict[str, str]],
    message_param_value_translations: dict[tuple[str, str], str],
    param_value_translations: dict[str, dict[str, dict[str, str]]],
    supported_locales: tuple[str, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for (message_code, param_name), translation_key in sorted(message_param_value_translations.items()):
        if message_code not in messages:
            findings.append(
                Finding(I18N_PATH, 1, f"{message_code}.{param_name} param translation uses unknown message code.")
            )
        if translation_key not in param_value_translations:
            findings.append(
                Finding(I18N_PATH, 1, f"{message_code}.{param_name} uses unknown param translation {translation_key}.")
            )
            continue
        for raw_value, translations in sorted(param_value_translations[translation_key].items()):
            missing = [locale for locale in supported_locales if locale not in translations]
            if missing:
                findings.append(
                    Finding(
                        I18N_PATH,
                        1,
                        f"{translation_key}.{raw_value} is missing locale(s): {', '.join(missing)}",
                    )
                )
    return findings


def _validate_code_uses(
    messages: dict[str, dict[str, str]],
    uses: list[tuple[str, Path, int, str]],
) -> list[Finding]:
    findings: list[Finding] = []
    for code, path, line, source in sorted(set(uses), key=lambda item: (str(item[1]), item[2], item[0])):
        if code not in messages:
            findings.append(Finding(path, line, f"{source} uses unknown i18n code: {code}"))
    return findings


def _validate_raw_http_exception_details() -> list[Finding]:
    findings: list[Finding] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _function_name(node) != "HTTPException":
                continue
            detail = _keyword_string(node, "detail")
            if detail is not None:
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "HTTPException detail must use localized_http_exception or LocalizedApiMessage.",
                    )
                )
    return findings


def main() -> int:
    i18n_tree = ast.parse(I18N_PATH.read_text(), filename=str(I18N_PATH))
    supported_locales = tuple(_literal_assignment(i18n_tree, "SUPPORTED_LOCALES"))
    messages = _literal_assignment(i18n_tree, "MESSAGES")
    param_value_translations = _literal_assignment(i18n_tree, "PARAM_VALUE_TRANSLATIONS")
    message_param_value_translations = _literal_assignment(
        i18n_tree,
        "MESSAGE_PARAM_VALUE_TRANSLATIONS",
    )

    findings: list[Finding] = []
    findings.extend(_validate_messages(messages, supported_locales))
    findings.extend(
        _validate_param_value_translations(
            messages,
            message_param_value_translations,
            param_value_translations,
            supported_locales,
        )
    )
    findings.extend(_validate_code_uses(messages, _collect_static_code_uses()))
    findings.extend(_validate_code_uses(messages, _collect_validation_code_uses()))
    findings.extend(_validate_raw_http_exception_details())

    if findings:
        print("API i18n guard found issue(s):")
        for finding in findings:
            print(f"  {finding.render()}")
        return 1

    print("API i18n guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
