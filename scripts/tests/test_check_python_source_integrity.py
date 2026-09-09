from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check-python-source-integrity.py"
SPEC = importlib.util.spec_from_file_location("check_python_source_integrity", MODULE_PATH)
source_integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = source_integrity
assert SPEC.loader is not None
SPEC.loader.exec_module(source_integrity)


class CheckPythonSourceIntegrityTest(unittest.TestCase):
    def scan(self, source: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.py"
            path.write_text(source, encoding="utf-8")
            return source_integrity.check_python_file(path)

    def codes(self, source: str) -> set[str]:
        return {finding.code for finding in self.scan(source)}

    def test_detects_duplicate_top_level_definition(self) -> None:
        self.assertIn(
            "duplicate-top-level-definition",
            self.codes("def load():\n    return 1\n\ndef load():\n    return 2\n"),
        )

    def test_allows_typing_overloads_before_one_implementation(self) -> None:
        findings = self.scan(
            "from typing import overload\n"
            "@overload\n"
            "def load(value: int) -> int: ...\n"
            "@overload\n"
            "def load(value: str) -> str: ...\n"
            "def load(value):\n"
            "    return value\n"
        )

        self.assertEqual(findings, [])

    def test_detects_duplicate_literal_dict_key(self) -> None:
        self.assertIn(
            "duplicate-literal-dict-key",
            self.codes('TASK_BUDGETS = {"summary": 10, "summary": 20}\n'),
        )

    def test_detects_duplicate_router_registration(self) -> None:
        self.assertIn(
            "duplicate-router-spec",
            self.codes(
                "SPECS = [\n"
                '    _RouterSpec(report_router, "reports"),\n'
                '    _RouterSpec(report_router, "api"),\n'
                "]\n"
            ),
        )

    def test_detects_duplicate_keyword_router_registration(self) -> None:
        self.assertIn(
            "duplicate-router-spec",
            self.codes(
                "SPECS = [\n"
                '    _RouterSpec(router=report_router, prefix="reports"),\n'
                '    _RouterSpec(router=report_router, prefix="api"),\n'
                "]\n"
            ),
        )

    def test_detects_aliased_direct_core_llm_import(self) -> None:
        self.assertIn(
            "direct-core-llm-import",
            self.codes(
                "from open_work_hub_api.core.llm import complete_chat_text as run_chat\n"
                "run_chat(context, db)\n"
            ),
        )

    def test_detects_relative_direct_core_llm_import(self) -> None:
        self.assertIn(
            "direct-core-llm-import",
            self.codes(
                "from ...core.llm import complete_chat_text as run_chat\n"
                "run_chat(context, db)\n"
            ),
        )

    def test_detects_core_llm_module_from_package_import(self) -> None:
        self.assertIn(
            "direct-core-llm-import",
            self.codes(
                "from open_work_hub_api.core import llm\n"
                "run_chat = llm.complete_chat_text\n"
                "run_chat(context, db)\n"
            ),
        )

    def test_reports_syntax_errors(self) -> None:
        self.assertIn("python-source-parse-error", self.codes("def broken(:\n"))

    def test_accepts_project_target_python_312_syntax(self) -> None:
        self.assertEqual(
            self.scan("def identity[T](value: T) -> T:\n    return value\n"),
            [],
        )

    def test_rejects_python_314_only_syntax(self) -> None:
        self.assertIn(
            "python-source-parse-error",
            self.codes(
                "try:\n"
                "    pass\n"
                "except ValueError, TypeError:\n"
                "    pass\n"
            ),
        )


if __name__ == "__main__":
    unittest.main()
