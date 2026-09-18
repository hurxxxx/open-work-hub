from __future__ import annotations

import importlib.util
import json
import re
import shutil
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
    def test_rolling_cutover_validates_each_checkout_contract_without_ignoring_peer_errors(self):
        source = MODULE_PATH.parents[1]
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            for name in ("dev", "prod"):
                root = parent / name
                root.mkdir()
                shutil.copytree(source / "config", root / "config")
                for relative_path in env_contract.SETTINGS_FILE_PARTS:
                    destination = root / relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source / relative_path, destination)
                template = (source / ".env.example").read_text()
                if name == "prod":
                    template += "\nOPEN_WORK_HUB_LLM_LOCAL_API_KEY=synthetic-only\n"
                (root / ".env.example").write_text(template)
                (root / ".env").write_text(template)
                (root / "scripts").mkdir()
                (root / "scripts/check-env-contract.py").write_text(
                    'FORBIDDEN_ENV_KEYS = frozenset(["OLD_RETIRED_KEY"])\n'
                )
            report = env_contract.build_report(parent / "dev")
            self.assertTrue(report.ok, self.messages(report))
            peer_env = parent / "prod/.env"
            peer_env.write_text(peer_env.read_text() + "OLD_RETIRED_KEY=synthetic-secret\n")
            report = env_contract.build_report(parent / "dev")
            self.assertIn("forbidden_env_key", self.codes(report))
            self.assertIn("env_keyset_mismatch", self.codes(report))
            self.assertIn("prod:", self.messages(report))
            self.assertNotIn("synthetic-secret", self.messages(report))
            (parent / "prod/scripts/check-env-contract.py").unlink()
            self.assertIn("invalid_peer_env_contract", self.codes(env_contract.build_report(parent / "dev")))

    def test_llm_env_cutover_matches_current_template_and_typed_settings(self):
        source = MODULE_PATH.parents[1]
        migration_spec = importlib.util.spec_from_file_location(
            "migrate_llm_settings_contract", source / "scripts/migrate-llm-settings.py"
        )
        migration = importlib.util.module_from_spec(migration_spec)
        migration_spec.loader.exec_module(migration)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(source / "config", root / "config")
            for relative_path in env_contract.SETTINGS_FILE_PARTS:
                destination = root / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative_path, destination)
            template = (source / ".env.example").read_text()
            (root / ".env.example").write_text(template)
            retired = set(migration.RETIRED) | {"OPENROUTER_API_KEY"}
            old_env = template + "\n" + "\n".join(
                f"{key}=synthetic-only" for key in sorted(retired)
            ) + "\n"
            (root / ".env").write_text(old_env)
            self.assertIn("forbidden_env_key", self.codes(env_contract.build_report(root)))
            (root / ".env").write_text(migration.prune_keys(old_env, retired))
            report = env_contract.build_report(root)
            self.assertTrue(report.ok, self.messages(report))

    def test_build_report_rejects_invalid_runtime_config_without_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(MODULE_PATH.parents[1] / "config", root / "config")
            path = root / "config/runtime.json"
            doc = json.loads(path.read_text())
            doc["defaults"]["OPEN_WORK_HUB_HERMES_API_KEY"] = "synthetic-secret"
            path.write_text(json.dumps(doc))
            report = env_contract.build_report(root)
            self.assertIn("invalid_runtime_config", self.codes(report))
            self.assertNotIn("synthetic-secret", self.messages(report))

    def evaluate(
        self,
        root: Path,
        *,
        env_texts: dict[str, str],
        settings_texts: dict[str, str] | None = None,
        source_texts: dict[str, str] | None = None,
        forbidden_patterns: tuple[re.Pattern[str], ...] = (),
        forbidden_env_keys: tuple[str, ...] = (),
        runtime_config_keys: tuple[str, ...] = (),
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
            runtime_config_keys=runtime_config_keys,
        )

    def test_public_defaults_cover_optional_env_overrides_without_hiding_secret_mismatches(self):
        settings = '''
class Settings:
    model_config = SettingsConfigDict(env_prefix="OPEN_WORK_HUB_")
    tuning: int = 5
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={"dev": "OPEN_WORK_HUB_SECRET=private\n",
                           "example": "OPEN_WORK_HUB_TUNING=8\nOPEN_WORK_HUB_SECRET=\n"},
                settings_texts={"settings.py": settings},
                runtime_config_keys=("OPEN_WORK_HUB_TUNING",),
            )
            self.assertNotIn("env_keyset_mismatch", self.codes(report))
            self.assertNotIn("env_key_order_mismatch", self.codes(report))
            self.assertNotIn("OPEN_WORK_HUB_TUNING", self.messages(report))
            report = self.evaluate(
                root,
                env_texts={"dev": "OPEN_WORK_HUB_SECRET=private\n", "example": ""},
                runtime_config_keys=("OPEN_WORK_HUB_TUNING",),
            )
            self.assertIn("env_keyset_mismatch", self.codes(report))
            self.assertIn("unknown_runtime_config_key", self.codes(report))

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
        env_text = "OPEN_WORK_HUB_PRESENT=1\n" + "".join(
            f"{key}=example\n" for key in sorted(env_contract.DEPLOY_ENV_KEYS)
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.evaluate(
                root,
                env_texts={
                    "dev": env_text,
                    "example": env_text,
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
