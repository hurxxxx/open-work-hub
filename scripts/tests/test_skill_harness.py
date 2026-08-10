from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check-skill-harness.py"
SPEC = importlib.util.spec_from_file_location("check_skill_harness", MODULE_PATH)
skill_harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = skill_harness
assert SPEC.loader is not None
SPEC.loader.exec_module(skill_harness)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def valid_skill_text(name: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: Maintains {name}. Use when testing skill harness checks.\n"
        "---\n"
        "\n"
        "# Skill\n"
    )


class SkillHarnessScannerTest(unittest.TestCase):
    def snapshot(self, root: Path):
        return skill_harness.build_skill_harness_snapshot(
            root,
            self_path=root / "scripts" / "check-skill-harness.py",
        )

    def evaluate(self, root: Path, *, required_skills: set[str]):
        return skill_harness.evaluate_skill_harness(
            self.snapshot(root),
            required_skills=required_skills,
        )

    def codes(self, report) -> set[str]:
        return {finding.code for finding in report.findings}

    def messages(self, report) -> str:
        return "\n".join(finding.message for finding in report.findings)

    def test_frontmatter_quote_rule_requires_quoted_colon_space(self) -> None:
        bad = (
            "---\n"
            "name: sample\n"
            "description: Handles one thing: carefully. Use when testing.\n"
            "---\n"
        )
        good = (
            "---\n"
            "name: sample\n"
            'description: "Handles one thing: carefully. Use when testing."\n'
            "---\n"
        )

        with self.assertRaisesRegex(ValueError, "quote scalar values"):
            skill_harness.parse_frontmatter(bad)

        metadata = skill_harness.parse_frontmatter(good)

        self.assertEqual(
            "Handles one thing: carefully. Use when testing.",
            metadata["description"],
        )

    def test_reports_missing_required_skills_and_codex_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".codex" / "skills" / "project-skill" / "SKILL.md",
                "not a project skill location\n",
            )

            report = self.evaluate(root, required_skills={"required-skill"})

        self.assertIn("codex_skills_present", self.codes(report))
        self.assertIn("missing_required_skills", self.codes(report))
        self.assertIn(
            ".codex/skills must not contain project skills",
            self.messages(report),
        )
        self.assertIn(
            "missing required project skills: required-skill",
            self.messages(report),
        )

    def test_reports_skill_metadata_contract_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".agents" / "skills" / "example" / "SKILL.md",
                (
                    "---\n"
                    "name: wrong-name\n"
                    "description: Maintains an example skill.\n"
                    "---\n"
                ),
            )

            report = self.evaluate(root, required_skills={"example"})

        self.assertIn("skill_name_mismatch", self.codes(report))
        self.assertIn("missing_use_when_trigger", self.codes(report))
        self.assertIn(
            ".agents/skills/example/SKILL.md: name must be 'example'",
            self.messages(report),
        )

    def test_reports_oversized_skill_guide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".agents" / "skills" / "example" / "SKILL.md",
                valid_skill_text("example")
                + ("optional detail that belongs in a reference\n" * 300),
            )

            report = self.evaluate(root, required_skills={"example"})

        self.assertIn("skill_guide_too_large", self.codes(report))
        self.assertIn(
            "keep it at or below 8192 bytes",
            self.messages(report),
        )

    def test_reports_retired_skill_entries_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".agents" / "skills" / "ai-do-desktop-release" / "REFERENCE.md",
                "retired content\n",
            )
            write_text(
                root / ".agents" / "skills" / "clean" / "SKILL.md",
                valid_skill_text("clean") + "Run /setup-matt-pocock-skills.\n",
            )

            report = self.evaluate(
                root,
                required_skills={"clean"},
            )

        self.assertIn("retired_skill_present", self.codes(report))
        self.assertIn("retired_skill_reference", self.codes(report))
        self.assertIn(
            "retired project skill directories must be removed: ai-do-desktop-release",
            self.messages(report),
        )

    def test_reports_stale_domain_conventions_in_skill_guides_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".agents" / "skills" / "clean" / "SKILL.md",
                valid_skill_text("clean"),
            )
            write_text(
                root / ".agents" / "skills" / "clean" / "GUIDE.md",
                "Read CONTEXT.md and write decisions under docs/adr/.\n",
            )
            write_text(
                root / "docs" / "archive" / "history.md",
                "Historical CONTEXT-MAP.md and docs/adr/ reference.\n",
            )

            report = self.evaluate(root, required_skills={"clean"})

        messages = self.messages(report)
        self.assertIn("stale_skill_convention", self.codes(report))
        self.assertIn(".agents/skills/clean/GUIDE.md", messages)
        self.assertNotIn("docs/archive/history.md", messages)

    def test_reports_retired_triage_terms_only_in_triage_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".agents" / "skills" / "clean" / "SKILL.md",
                valid_skill_text("clean"),
            )
            write_text(
                root / ".agents" / "skills" / "triage" / "GUIDE.md",
                "Move incomplete work to needs-info, then wontfix.\n",
            )
            write_text(
                root / "docs" / "archive" / "history.md",
                "Historical needs-info label.\n",
            )

            report = self.evaluate(root, required_skills={"clean"})

        messages = self.messages(report)
        self.assertIn("retired_triage_contract", self.codes(report))
        self.assertIn(".agents/skills/triage/GUIDE.md", messages)
        self.assertNotIn("docs/archive/history.md", messages)

    def test_reports_unknown_direct_pnpm_script_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / "package.json",
                '{"scripts":{"check:known":"true","nx":"nx"}}\n',
            )
            write_text(
                root / ".agents" / "skills" / "clean" / "SKILL.md",
                valid_skill_text("clean")
                + "pnpm check:known\n"
                + "pnpm nx test api\n"
                + "pnpm install\n"
                + "pnpm <prototype-name>\n"
                + "pnpm missing:script\n",
            )

            report = self.evaluate(root, required_skills={"clean"})

        messages = self.messages(report)
        self.assertIn("unknown_pnpm_script", self.codes(report))
        self.assertIn("pnpm script 'missing:script'", messages)
        self.assertNotIn("check:known' is not defined", messages)
        self.assertNotIn("pnpm script 'nx'", messages)
        self.assertNotIn("pnpm script 'install'", messages)

    def test_reports_retired_token_hits_and_preserves_skip_exceptions(self) -> None:
        retired_profile = "remote" + "-dev"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_text(
                root / ".agents" / "skills" / "clean" / "SKILL.md",
                valid_skill_text("clean"),
            )
            write_text(
                root / "scripts" / "check-skill-harness.py",
                f"{retired_profile}\n",
            )
            write_text(
                root / "scripts" / "check-runtime-separation.py",
                f"{retired_profile}\n",
            )
            write_text(
                root / "scripts" / "tests" / "fixture.py",
                f"{retired_profile}\n",
            )
            write_text(root / "docs" / "note.md", f"{retired_profile}\n")
            write_text(root / "README.md", f"{retired_profile}\n")
            write_text(root / "CLAUDE.md", f"{retired_profile}\n")

            report = self.evaluate(root, required_skills={"clean"})

        messages = self.messages(report)
        self.assertIn("stale_reference", self.codes(report))
        self.assertIn("docs/note.md: stale reference", messages)
        self.assertIn("README.md: stale reference", messages)
        self.assertIn("CLAUDE.md: stale reference", messages)
        self.assertNotIn("scripts/check-skill-harness.py", messages)
        self.assertNotIn("scripts/check-runtime-separation.py", messages)
        self.assertNotIn("scripts/tests/fixture.py", messages)


if __name__ == "__main__":
    unittest.main()
