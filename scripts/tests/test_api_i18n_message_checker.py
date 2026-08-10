from __future__ import annotations

import importlib.util
import locale
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check-api-i18n-messages.py"
SPEC = importlib.util.spec_from_file_location("check_api_i18n_messages", MODULE_PATH)
api_i18n = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = api_i18n
assert SPEC.loader is not None
SPEC.loader.exec_module(api_i18n)


class ApiI18nMessageCheckerTest(unittest.TestCase):
    def evaluate(
        self,
        catalog_messages: str,
        *,
        source_texts: dict[str, str] | None = None,
    ):
        catalog_messages_text = textwrap.dedent(catalog_messages).strip()
        catalog_source = api_i18n.PythonSource(
            path=Path("/repo/apps/api/src/ai_do_api/core/i18n_catalog.py"),
            text=(
                'SUPPORTED_LOCALES = ("ko-KR", "en-US")\n'
                f"MESSAGES = {catalog_messages_text}\n"
                "PARAM_VALUE_TRANSLATIONS = {}\n"
                "MESSAGE_PARAM_VALUE_TRANSLATIONS = {}\n"
            ),
        )
        source_files = tuple(
            api_i18n.PythonSource(
                path=Path("/repo/apps/api/src/ai_do_api") / relative_path,
                text=textwrap.dedent(text),
            )
            for relative_path, text in (source_texts or {}).items()
        )
        return api_i18n.evaluate_api_i18n_messages(
            catalog_source=catalog_source,
            source_files=source_files,
        )

    def messages(self, report) -> str:
        return "\n".join(finding.message for finding in report.findings)

    def test_reports_missing_locale(self) -> None:
        report = self.evaluate(
            """
            {
                "auth.invalid": {
                    "ko-KR": "Invalid session."
                }
            }
            """
        )

        self.assertFalse(report.ok)
        self.assertIn("auth.invalid is missing locale(s): en-US", self.messages(report))

    def test_reports_placeholder_mismatch(self) -> None:
        report = self.evaluate(
            """
            {
                "profile.name": {
                    "ko-KR": "Name {name}",
                    "en-US": "Name {value}"
                }
            }
            """
        )

        self.assertIn("profile.name placeholder mismatch", self.messages(report))
        self.assertIn("en-US=['value']", self.messages(report))
        self.assertIn("ko-KR=['name']", self.messages(report))

    def test_reports_unknown_static_code_use(self) -> None:
        report = self.evaluate(
            """
            {
                "known.code": {
                    "ko-KR": "Known.",
                    "en-US": "Known."
                }
            }
            """,
            source_texts={
                "domains/auth/router.py": """
                def route():
                    return localized_http_exception(status_code=400, code="unknown.code")
                """
            },
        )

        self.assertIn(
            "localized_http_exception uses unknown i18n code: unknown.code",
            self.messages(report),
        )

    def test_reports_raw_http_exception_detail(self) -> None:
        report = self.evaluate(
            """
            {
                "known.code": {
                    "ko-KR": "Known.",
                    "en-US": "Known."
                }
            }
            """,
            source_texts={
                "domains/files/router.py": """
                def route():
                    raise HTTPException(status_code=404, detail="Not found")
                """
            },
        )

        self.assertIn(
            "HTTPException detail must use localized_http_exception or LocalizedApiMessage.",
            self.messages(report),
        )


class ReadPythonSourceEncodingTest(unittest.TestCase):
    """소스 읽기는 로케일 기본 인코딩이 아니라 항상 UTF-8 이어야 한다.

    인코딩을 생략하면 Windows(cp949) 처럼 기본값이 UTF-8 이 아닌 환경에서
    한글이 든 파일을 읽다가 UnicodeDecodeError 로 죽고, check:api-i18n 과
    check:api-architecture 가 아예 실행되지 않는다.
    """

    def test_non_ascii_source_is_read_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "korean_message.py"
            body = 'MESSAGE = "근태 정보를 불러오지 못했습니다."\n'
            path.write_text(body, encoding="utf-8")

            source = api_i18n._read_python_source(path)

        self.assertEqual(source.text, body)
        self.assertIn("근태", source.text)

    def test_read_ignores_locale_default_encoding(self) -> None:
        # locale.getpreferredencoding() 이 cp949 를 돌려주는 환경을 흉내내
        # read_text() 가 기본 인코딩에 의존하지 않는지 확인한다.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "korean_message.py"
            body = 'MESSAGE = "결재선을 불러오는 중입니다."\n'
            path.write_text(body, encoding="utf-8")

            original = locale.getpreferredencoding

            def cp949(do_setlocale: bool = True) -> str:  # noqa: ARG001
                return "cp949"

            locale.getpreferredencoding = cp949
            try:
                source = api_i18n._read_python_source(path)
            finally:
                locale.getpreferredencoding = original

        self.assertEqual(source.text, body)


if __name__ == "__main__":
    unittest.main()
