from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check-env-contract.py"
SPEC = importlib.util.spec_from_file_location("check_env_contract", MODULE_PATH)
env_contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = env_contract
assert SPEC.loader is not None
SPEC.loader.exec_module(env_contract)


class EnvContractScannerTest(unittest.TestCase):
    def evaluate(
        self,
        root: Path,
        *,
        env_texts: dict[str, str],
        settings_texts: dict[str, str] | None = None,
        source_texts: dict[str, str] | None = None,
        forbidden_patterns: tuple[re.Pattern[str], ...] = (),
        forbidden_env_keys: tuple[str, ...] = (),
    ):
        env_files = []
        for name, text in env_texts.items():
            path = root / f"{name}.env"
            path.write_text(text, encoding="utf-8")
            env_files.append(
                env_contract.EnvFileContent(
                    name=name,
                    path=path,
                    text=path.read_text(encoding="utf-8"),
                )
            )

        settings_files = []
        for relative_path, text in (settings_texts or {}).items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            settings_files.append(
                env_contract.TextFileContent(
                    path=path,
                    text=path.read_text(encoding="utf-8"),
                    label=relative_path,
                )
            )

        source_files = []
        for relative_path, text in (source_texts or {}).items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            source_files.append(
                env_contract.TextFileContent(
                    path=path,
                    text=path.read_text(encoding="utf-8"),
                    label=relative_path,
                )
            )

        return env_contract.evaluate_env_contract(
            env_files=env_files,
            settings_files=settings_files,
            source_file_contents=source_files,
            current_env_name="dev",
            forbidden_patterns=forbidden_patterns,
            forbidden_env_keys=forbidden_env_keys,
        )

    def messages(self, report) -> str:
        return "\n".join(failure.message for failure in report.failures)

    def codes(self, report) -> set[str]:
        return {failure.code for failure in report.failures}

    def test_source_files_skip_generated_runtime_environments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            generated = root / ".runtime" / "ci-api-venv" / "vendor.py"
            forbidden_token = "OPENAI_" + "API_KEY"
            source.write_text("print('source')\n", encoding="utf-8")
            generated.parent.mkdir(parents=True)
            generated.write_text(
                f"{forbidden_token} = 'vendor'\n",
                encoding="utf-8",
            )

            scanned = env_contract.source_files(root)

        self.assertEqual(scanned, [source])

    def test_reports_duplicate_env_keys_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": "OPEN_WORK_HUB_ONE=secret-one\nOPEN_WORK_HUB_ONE=secret-two\n",
                    "example": "OPEN_WORK_HUB_ONE=example\n",
                },
            )

        self.assertIn("duplicate_env_key", self.codes(report))
        messages = self.messages(report)
        self.assertIn("dev: duplicate keys: OPEN_WORK_HUB_ONE", messages)
        self.assertNotIn("secret-one", messages)
        self.assertNotIn("secret-two", messages)

    def test_reports_env_keyset_mismatch_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": "OPEN_WORK_HUB_ONE=1\nOPEN_WORK_HUB_TWO=2\n",
                    "example": "OPEN_WORK_HUB_ONE=1\nOPEN_WORK_HUB_THREE=3\n",
                },
            )

        self.assertIn("env_keyset_mismatch", self.codes(report))
        self.assertIn(
            "example: keyset mismatch against dev; missing=1 extra=1",
            self.messages(report),
        )

    def test_reports_env_key_order_mismatch_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": "OPEN_WORK_HUB_ONE=secret-one\nOPEN_WORK_HUB_TWO=secret-two\n",
                    "example": "OPEN_WORK_HUB_TWO=example-two\nOPEN_WORK_HUB_ONE=example-one\n",
                },
            )

        self.assertIn("env_key_order_mismatch", self.codes(report))
        messages = self.messages(report)
        self.assertIn("example: key order mismatch against dev", messages)
        self.assertNotIn("secret-one", messages)
        self.assertNotIn("example-one", messages)

    def test_reports_retired_or_externally_owned_env_keys(self) -> None:
        retired_key = "OPEN_WORK_HUB_RETIRED"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": f"OPEN_WORK_HUB_PRESENT=1\n{retired_key}=secret\n",
                    "example": f"OPEN_WORK_HUB_PRESENT=1\n{retired_key}=example\n",
                },
                forbidden_env_keys=(retired_key,),
            )

        self.assertIn("forbidden_env_key", self.codes(report))
        messages = self.messages(report)
        self.assertIn(retired_key, messages)
        self.assertNotIn("secret", messages)

    def test_env_file_paths_include_optional_local_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.local").write_text("OPEN_WORK_HUB_PRESENT=1\n", encoding="utf-8")

            paths = env_contract.env_file_paths(root, "dev")

        self.assertEqual(paths["local"], root / ".env.local")

    def test_reports_settings_keys_missing_from_env(self) -> None:
        settings = """
class Settings:
    present: str = Field(validation_alias="OPEN_WORK_HUB_PRESENT")
    missing: str = Field(validation_alias="OPEN_WORK_HUB_MISSING")
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": "OPEN_WORK_HUB_PRESENT=1\n",
                    "example": "OPEN_WORK_HUB_PRESENT=1\n",
                },
                settings_texts={"settings.py": settings},
            )

        self.assertIn("missing_settings_key", self.codes(report))
        self.assertIn(
            "env files are missing settings keys: OPEN_WORK_HUB_MISSING",
            self.messages(report),
        )

    def test_reports_forbidden_token_hits(self) -> None:
        token = "OPENAI_" + "API_KEY"
        pattern = re.compile(r"\b" + re.escape(token) + r"\b")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": "OPEN_WORK_HUB_PRESENT=1\n",
                    "example": "OPEN_WORK_HUB_PRESENT=1\n",
                },
                source_texts={"app.py": f"api_key = {token!r}\n"},
                forbidden_patterns=(pattern,),
            )

        self.assertIn("forbidden_env_token", self.codes(report))
        self.assertIn("app.py: forbidden env token", self.messages(report))

    def test_forbids_exact_legacy_redis_alias_without_matching_scoped_keys(self) -> None:
        legacy_token = "OPEN_WORK_HUB_" + "REDIS_URL"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": "OPEN_WORK_HUB_PRESENT=1\n",
                    "example": "OPEN_WORK_HUB_PRESENT=1\n",
                },
                source_texts={
                    "legacy.py": f"redis_url = os.getenv({legacy_token!r})\n",
                    "scoped.py": (
                        "collab = os.getenv('OPEN_WORK_HUB_API_COLLAB_REDIS_URL')\n"
                        "realtime = os.getenv('OPEN_WORK_HUB_API_REALTIME_REDIS_URL')\n"
                    ),
                },
                forbidden_patterns=tuple(env_contract.FORBIDDEN_ENV_PATTERNS),
            )

        self.assertEqual([hit.path for hit in report.forbidden_hits], ["legacy.py"])
        self.assertIn("forbidden_env_token", self.codes(report))


if __name__ == "__main__":
    unittest.main()
