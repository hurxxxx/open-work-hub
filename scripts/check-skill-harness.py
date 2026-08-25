#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".agents" / "skills"
SELF = Path(__file__).resolve()
MAX_SKILL_BYTES = 8 * 1024
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

REQUIRED_SKILLS = {
    "agent-browser",
    "caveman",
    "diagnose",
    "grill-me",
    "grill-with-docs",
    "improve-codebase-architecture",
    "open-work-hub-agent-skill-governance",
    "open-work-hub-agent-work-intake",
    "open-work-hub-codex-review-harness",
    "open-work-hub-development-environment",
    "open-work-hub-docs-organization",
    "open-work-hub-docs-reader",
    "open-work-hub-env-management",
    "open-work-hub-i18n",
    "open-work-hub-mcp-capability-governance",
    "open-work-hub-pr-review-validation",
    "open-work-hub-production-operations",
    "open-work-hub-release-promotion",
    "open-work-hub-runtime-separation-audit",
    "open-work-hub-vibe-app-delivery",
    "open-work-hub-worktree-management",
    "prototype",
    "tdd",
    "to-issues",
    "to-prd",
    "triage",
    "write-a-skill",
    "zoom-out",
}

RETIRED_SKILLS = {
    "open-work-hub-desktop-release",
    "setup-matt-pocock-skills",
}

REQUIRED_RESOURCES = {
    Path(".agents/skills/diagnose/scripts/hitl-loop.template.sh"),
    Path(".agents/skills/grill-with-docs/ADR-FORMAT.md"),
    Path(".agents/skills/improve-codebase-architecture/DEEPENING.md"),
    Path(".agents/skills/improve-codebase-architecture/INTERFACE-DESIGN.md"),
    Path(".agents/skills/improve-codebase-architecture/LANGUAGE.md"),
    Path(".agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py"),
    Path(".agents/skills/open-work-hub-env-management/scripts/env-inventory.sh"),
    Path(".agents/skills/open-work-hub-env-management/scripts/local-env-files.sh"),
    Path(".agents/skills/prototype/LOGIC.md"),
    Path(".agents/skills/prototype/UI.md"),
    Path(".agents/skills/tdd/deep-modules.md"),
    Path(".agents/skills/tdd/interface-design.md"),
    Path(".agents/skills/tdd/mocking.md"),
    Path(".agents/skills/tdd/refactoring.md"),
    Path(".agents/skills/tdd/tests.md"),
    Path(".agents/skills/triage/AGENT-BRIEF.md"),
}

STALE_SKILL_GUIDE_PATTERNS = {
    r"\bCONTEXT(?:-MAP)?\.md\b": "Open Work Hub does not use generic context glossary files",
    r"\bdocs/adr/": "Open Work Hub ADRs live in root adr/",
    r"(?i)\bai-do\b|\bAI_DO\b": "retired project identifiers must not appear in skills",
    r"(?i)\bGitLab\b|\bglab\b|\.gitlab": "skills must use the current GitHub workflow",
    r"\bMR\b|mr-review": "project guidance must use GitHub pull-request terminology",
    r"/projects/": "fixed internal checkout paths are not portable",
    r"\bdocs/current/": "docs/README.md and current owner docs replace docs/current",
    r"\b(?:Legacy Issues|mcloudoc)\b": "retired internal apps must not appear in skills",
}

RETIRED_TRIAGE_PATTERNS = {
    r"\bneeds-info\b": "needs-info is not a documented GitHub label",
    r"\bneeds-triage\b": "workflow-state labels are not part of the current GitHub contract",
    r"\bready-for-agent\b": "workflow-state labels are not part of the current GitHub contract",
    r"\bready-for-human\b": "ready-for-human is not a documented GitHub label",
    r"\.out-of-scope\b": "the parallel out-of-scope archive is retired",
    r"OUT-OF-SCOPE\.md": "the parallel out-of-scope archive is retired",
}

TRIAGE_GUIDANCE_PATHS = {
    Path(".agents/skills/open-work-hub-agent-work-intake/SKILL.md"),
    Path(".agents/skills/to-issues/SKILL.md"),
    Path(".agents/skills/to-prd/SKILL.md"),
}

PNPM_BUILTINS = {
    "add",
    "audit",
    "config",
    "create",
    "deploy",
    "dlx",
    "env",
    "exec",
    "fetch",
    "help",
    "import",
    "init",
    "install",
    "link",
    "list",
    "outdated",
    "pack",
    "patch",
    "prune",
    "publish",
    "rebuild",
    "remove",
    "root",
    "run",
    "setup",
    "store",
    "update",
    "why",
}

STALE_PATTERNS = {
    r"\bvm:app\b": "preview VM app scripts are retired",
    r"\bvm-app-stack\b": "preview VM app harness is retired",
    r"\bopen-work-hub-preview-deploy\b": "preview deploy skill is retired",
    r"\.env\.remote-dev\b": "remote-dev profile is retired",
    r"\bremote-dev\b": "remote-dev profile is retired",
}

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".nx",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
}

SKIP_SUFFIXES = {".pyc", ".pyo"}

# Test fixtures may intentionally mention retired tokens while proving scanners work.
SKIP_RELATIVE_PREFIXES = {("scripts", "tests")}


@dataclass(frozen=True)
class SkillHarnessFinding:
    code: str
    message: str


@dataclass(frozen=True)
class TextFileContent:
    path: Path
    text: str


@dataclass(frozen=True)
class SkillHarnessSnapshot:
    root: Path
    skill_files: tuple[TextFileContent, ...]
    skill_guides: tuple[TextFileContent, ...]
    checked_files: tuple[TextFileContent, ...]
    project_skill_entries: tuple[Path, ...]
    codex_skill_entries: tuple[Path, ...]
    package_scripts: frozenset[str]
    stale_skip_paths: frozenset[Path]


@dataclass(frozen=True)
class SkillHarnessReport:
    findings: tuple[SkillHarnessFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def failures(self) -> tuple[SkillHarnessFinding, ...]:
        return self.findings


def _frontmatter_text(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return text[4:end]


def parse_frontmatter(text: str) -> dict[str, str]:
    frontmatter = _frontmatter_text(text)
    if frontmatter is None:
        return {}
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(frontmatter.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace():
            continue
        if ":" not in raw_line:
            raise ValueError(f"line {line_number}: expected key/value pair")
        key, value = raw_line.split(":", 1)
        value = value.strip()
        if (
            value
            and not value.startswith(("'", '"', ">", "|"))
            and re.search(r":\s", value)
        ):
            raise ValueError(
                f"line {line_number}: quote scalar values containing ': '"
            )
        result[key.strip()] = value.strip("\"'")
    return result


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def skill_files(root: Path = ROOT) -> list[Path]:
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.exists():
        return []
    return sorted(path for path in skills_dir.glob("*/SKILL.md") if path.is_file())


def skill_guides(root: Path = ROOT) -> list[Path]:
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.exists():
        return []
    return sorted(path for path in skills_dir.rglob("*.md") if path.is_file())


def project_skill_entries(root: Path = ROOT) -> list[Path]:
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.exists():
        return []
    return sorted(path for path in skills_dir.iterdir() if path.is_dir())


def package_scripts(root: Path = ROOT) -> frozenset[str]:
    package_path = root / "package.json"
    if not package_path.is_file():
        return frozenset()
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = payload.get("scripts", {})
    if not isinstance(scripts, dict):
        return frozenset()
    return frozenset(str(name) for name in scripts)


def checked_files(root: Path = ROOT) -> list[Path]:
    roots = [
        root / "AGENTS.md",
        root / "README.md",
        root / "CLAUDE.md",
        root / "docs",
        root / "scripts",
        root / ".agents",
        root / ".github",
        root / "package.json",
        root / "skills-lock.json",
    ]
    files: list[Path] = []
    for scan_root in roots:
        if scan_root.is_file():
            files.append(scan_root)
        elif scan_root.exists():
            files.extend(
                path
                for path in scan_root.rglob("*")
                if path.is_file()
                and not _should_skip_checked_file(root, path)
            )
    return sorted({path.resolve() for path in files})


def _should_skip_checked_file(root: Path, path: Path) -> bool:
    parts = path.relative_to(root).parts
    if any(part in SKIP_DIRS for part in parts):
        return True
    if any(parts[: len(prefix)] == prefix for prefix in SKIP_RELATIVE_PREFIXES):
        return True
    return path.suffix in SKIP_SUFFIXES


def codex_skill_entries(root: Path = ROOT) -> list[Path]:
    return sorted((root / ".codex" / "skills").glob("*"))


def build_skill_harness_snapshot(
    root: Path = ROOT,
    *,
    self_path: Path = SELF,
) -> SkillHarnessSnapshot:
    resolved_root = root.resolve()
    runtime_separation_path = resolved_root / "scripts" / "check-runtime-separation.py"
    return SkillHarnessSnapshot(
        root=resolved_root,
        skill_files=tuple(
            TextFileContent(
                path=path.resolve(),
                text=path.read_text(encoding="utf-8"),
            )
            for path in skill_files(resolved_root)
        ),
        skill_guides=tuple(
            TextFileContent(
                path=path.resolve(),
                text=path.read_text(encoding="utf-8"),
            )
            for path in skill_guides(resolved_root)
        ),
        checked_files=tuple(
            TextFileContent(
                path=path.resolve(),
                text=path.read_text(encoding="utf-8", errors="replace"),
            )
            for path in checked_files(resolved_root)
        ),
        project_skill_entries=tuple(
            path.resolve() for path in project_skill_entries(resolved_root)
        ),
        codex_skill_entries=tuple(
            path.resolve() for path in codex_skill_entries(resolved_root)
        ),
        package_scripts=package_scripts(resolved_root),
        stale_skip_paths=frozenset(
            {
                self_path.resolve(),
                runtime_separation_path.resolve(),
            }
        ),
    )


def _finding(code: str, message: str) -> SkillHarnessFinding:
    return SkillHarnessFinding(code=code, message=message)


def _is_triage_guidance(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    return (
        relative in TRIAGE_GUIDANCE_PATHS
        or relative.parts[:3] == (".agents", "skills", "triage")
    )


def _is_core_agent_guidance(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    return (
        relative
        in {
            Path("AGENTS.md"),
            Path("CLAUDE.md"),
            Path("README.md"),
            Path("docs/README.md"),
            Path(".github/copilot-instructions.md"),
        }
        or relative.parts[:2] == ("docs", "agents")
    )


def _referenced_pnpm_scripts(text: str) -> set[str]:
    commands = set(
        re.findall(
            r"(?m)(?:^[ \t]*|&&[ \t]*|\|\|[ \t]*|;[ \t]*)"
            r"pnpm(?:[ \t]+run)?[ \t]+([^\s`]+)",
            text,
        )
    )
    return {
        command.strip("'\"")
        for command in commands
        if command
        and not command.startswith("-")
        and not any(marker in command for marker in ("$", "*", "<", ">", "{", "}"))
    }


def _missing_local_markdown_links(file_content: TextFileContent) -> list[str]:
    missing: list[str] = []
    for raw_target in MARKDOWN_LINK_RE.findall(file_content.text):
        target = raw_target.strip().strip("<>").split("#", 1)[0]
        if (
            not target
            or target.startswith(("/", "#", "mailto:"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target)
        ):
            continue
        if not (file_content.path.parent / target).resolve().exists():
            missing.append(raw_target)
    return sorted(set(missing))


def evaluate_skill_harness(
    snapshot: SkillHarnessSnapshot,
    *,
    required_skills: Iterable[str] = REQUIRED_SKILLS,
    required_resources: Iterable[Path] = REQUIRED_RESOURCES,
    require_tool_bridges: bool = True,
    stale_patterns: Mapping[str, str] = STALE_PATTERNS,
) -> SkillHarnessReport:
    root = snapshot.root.resolve()
    findings: list[SkillHarnessFinding] = []

    if snapshot.codex_skill_entries:
        findings.append(
            _finding(
                "codex_skills_present",
                ".codex/skills must not contain project skills; use .agents/skills",
            )
        )

    if require_tool_bridges:
        bridge_paths = {
            "AGENTS.md": root / "AGENTS.md",
            "CLAUDE.md": root / "CLAUDE.md",
            ".github/copilot-instructions.md": root
            / ".github"
            / "copilot-instructions.md",
        }
        missing_bridges = sorted(
            name for name, path in bridge_paths.items() if not path.is_file()
        )
        if missing_bridges:
            findings.append(
                _finding(
                    "missing_tool_bridge",
                    "missing agent tool bridge files: " + ", ".join(missing_bridges),
                )
            )

        claude_path = bridge_paths["CLAUDE.md"]
        if claude_path.is_file() and "@AGENTS.md" not in claude_path.read_text(
            encoding="utf-8"
        ):
            findings.append(
                _finding(
                    "claude_bridge_missing_agents_import",
                    "CLAUDE.md must import the canonical root guidance with @AGENTS.md",
                )
            )

        claude_skills = root / ".claude" / "skills"
        canonical_skills = root / ".agents" / "skills"
        if not claude_skills.is_symlink() or claude_skills.resolve() != canonical_skills.resolve():
            findings.append(
                _finding(
                    "invalid_claude_skills_bridge",
                    ".claude/skills must be a symlink to ../.agents/skills",
                )
            )

    missing_resources = sorted(
        str(path) for path in required_resources if not (root / path).is_file()
    )
    if missing_resources:
        findings.append(
            _finding(
                "missing_required_resources",
                "missing required skill resources: " + ", ".join(missing_resources),
            )
        )

    present = {file_content.path.parent.name for file_content in snapshot.skill_files}
    missing = sorted(set(required_skills) - present)
    if missing:
        findings.append(
            _finding(
                "missing_required_skills",
                "missing required project skills: " + ", ".join(missing),
            )
        )

    retired_entries = sorted(
        path.name
        for path in snapshot.project_skill_entries
        if path.name in RETIRED_SKILLS
    )
    if retired_entries:
        findings.append(
            _finding(
                "retired_skill_present",
                "retired project skill directories must be removed: "
                + ", ".join(retired_entries),
            )
        )

    for file_content in sorted(snapshot.skill_files, key=lambda item: str(item.path)):
        skill_size = len(file_content.text.encode("utf-8"))
        if skill_size > MAX_SKILL_BYTES:
            findings.append(
                _finding(
                    "skill_guide_too_large",
                    f"{_display_path(root, file_content.path)}: "
                    f"SKILL.md is {skill_size} bytes; keep it at or below "
                    f"{MAX_SKILL_BYTES} bytes and move optional detail to "
                    "references or scripts",
                )
            )
        try:
            metadata = parse_frontmatter(file_content.text)
        except ValueError as exc:
            findings.append(
                _finding(
                    "invalid_frontmatter",
                    f"{_display_path(root, file_content.path)}: "
                    f"invalid YAML frontmatter: {exc}",
                )
            )
            continue
        frontmatter_text = _frontmatter_text(file_content.text) or ""
        expected_name = file_content.path.parent.name
        if metadata.get("name") != expected_name:
            findings.append(
                _finding(
                    "skill_name_mismatch",
                    f"{_display_path(root, file_content.path)}: "
                    f"name must be {expected_name!r}",
                )
            )
        if len(expected_name) > 64 or not SKILL_NAME_RE.fullmatch(expected_name):
            findings.append(
                _finding(
                    "invalid_skill_name",
                    f"{_display_path(root, file_content.path)}: "
                    "skill folder name must be at most 64 characters and use "
                    "lowercase letters, digits, and hyphens",
                )
            )
        if "Use when" not in frontmatter_text:
            findings.append(
                _finding(
                    "missing_use_when_trigger",
                    f"{_display_path(root, file_content.path)}: "
                    "description must include 'Use when'",
                )
            )

    for file_content in sorted(snapshot.skill_guides, key=lambda item: str(item.path)):
        for target in _missing_local_markdown_links(file_content):
            findings.append(
                _finding(
                    "missing_skill_reference",
                    f"{_display_path(root, file_content.path)}: "
                    f"local Markdown link does not resolve: {target}",
                )
            )
        for pattern, reason in STALE_SKILL_GUIDE_PATTERNS.items():
            if re.search(pattern, file_content.text):
                findings.append(
                    _finding(
                        "stale_skill_convention",
                        f"{_display_path(root, file_content.path)}: {reason}",
                    )
                )
                break

        unknown_scripts = sorted(
            command
            for command in _referenced_pnpm_scripts(file_content.text)
            if command not in PNPM_BUILTINS
            and command not in snapshot.package_scripts
        )
        for command in unknown_scripts:
            findings.append(
                _finding(
                    "unknown_pnpm_script",
                    f"{_display_path(root, file_content.path)}: "
                    f"pnpm script {command!r} is not defined in root package.json",
                )
            )

    core_agent_guides = (
        file_content
        for file_content in snapshot.checked_files
        if _is_core_agent_guidance(root, file_content.path)
    )
    for file_content in sorted(core_agent_guides, key=lambda item: str(item.path)):
        for target in _missing_local_markdown_links(file_content):
            findings.append(
                _finding(
                    "missing_agent_guidance_reference",
                    f"{_display_path(root, file_content.path)}: "
                    f"local Markdown link does not resolve: {target}",
                )
            )
        unknown_scripts = sorted(
            command
            for command in _referenced_pnpm_scripts(file_content.text)
            if command not in PNPM_BUILTINS
            and command not in snapshot.package_scripts
        )
        for command in unknown_scripts:
            findings.append(
                _finding(
                    "unknown_agent_guidance_pnpm_script",
                    f"{_display_path(root, file_content.path)}: "
                    f"pnpm script {command!r} is not defined in root package.json",
                )
            )

    stale_skip_paths = {path.resolve() for path in snapshot.stale_skip_paths}
    for file_content in sorted(snapshot.checked_files, key=lambda item: str(item.path)):
        if file_content.path.resolve() in stale_skip_paths:
            continue
        for retired_skill in RETIRED_SKILLS:
            if retired_skill in file_content.text:
                findings.append(
                    _finding(
                        "retired_skill_reference",
                        f"{_display_path(root, file_content.path)}: "
                        f"references retired skill {retired_skill!r}",
                    )
                )
                break
        if _is_triage_guidance(root, file_content.path):
            for pattern, reason in RETIRED_TRIAGE_PATTERNS.items():
                if re.search(pattern, file_content.text):
                    findings.append(
                        _finding(
                            "retired_triage_contract",
                            f"{_display_path(root, file_content.path)}: {reason}",
                        )
                    )
                    break
        for pattern, reason in stale_patterns.items():
            if re.search(pattern, file_content.text):
                findings.append(
                    _finding(
                        "stale_reference",
                        f"{_display_path(root, file_content.path)}: "
                        f"stale reference ({reason})",
                    )
                )
                break

    return SkillHarnessReport(findings=tuple(findings))


def main() -> int:
    report = evaluate_skill_harness(build_skill_harness_snapshot())

    if report.findings:
        for finding in report.findings:
            print(f"[skill-harness] {finding.message}", file=sys.stderr)
        return 1
    print("[skill-harness] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
