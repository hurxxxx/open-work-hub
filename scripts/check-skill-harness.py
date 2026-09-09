#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".agents" / "skills"
SELF = Path(__file__).resolve()
MAX_SKILL_BYTES = 8 * 1024
MAX_SKILL_LINES = 130
MAX_SKILL_DESCRIPTION_CHARS = 400
MAX_TOTAL_DESCRIPTION_CHARS = 4700
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
LOWERCASE_AGENTS_REFERENCE_RE = re.compile(r"(?<![A-Za-z])agents\.md\b")

SCOPED_INSTRUCTION_DIRECTORIES = (
    Path(".agents/skills"),
    Path("apps/api"),
    Path("apps/web"),
    Path("apps/worker"),
    Path("docs"),
    Path("packages/ui"),
)

INSTRUCTION_LINE_LIMITS = {
    Path("AGENTS.md"): 60,
    Path("CLAUDE.md"): 12,
    **{
        directory / "AGENTS.md": 24
        for directory in SCOPED_INSTRUCTION_DIRECTORIES
    },
    **{
        directory / "CLAUDE.md": 1
        for directory in SCOPED_INSTRUCTION_DIRECTORIES
    },
}

ALLOWED_INSTRUCTION_PATHS = frozenset(INSTRUCTION_LINE_LIMITS)
SCOPED_CLAUDE_PATHS = frozenset(
    directory / "CLAUDE.md" for directory in SCOPED_INSTRUCTION_DIRECTORIES
)

REQUIRED_SKILLS = {
    "agent-browser",
    "diagnose",
    "owh-agent-harness",
    "owh-ai-capabilities",
    "owh-app-delivery",
    "owh-design-review",
    "owh-dev-environment",
    "owh-docs-reader",
    "owh-env-contracts",
    "owh-issues",
    "owh-mr-review",
    "owh-production",
    "owh-release",
    "owh-worktrees",
}

RETIRED_SKILLS = {
    "caveman",
    "grill-me",
    "open-work-hub-agent-work-intake",
    "open-work-hub-desktop-release",
    "open-work-hub-pr-review-validation",
    "prototype",
    "setup-matt-pocock-skills",
    "tdd",
    "write-a-skill",
    "zoom-out",
}

REQUIRED_RESOURCES = {
    Path(".agents/skills/diagnose/scripts/hitl-loop.template.sh"),
    Path(".agents/skills/owh-design-review/ADR-FORMAT.md"),
    Path(".agents/skills/owh-design-review/DEEPENING.md"),
    Path(".agents/skills/owh-design-review/INTERFACE-DESIGN.md"),
    Path(".agents/skills/owh-design-review/LANGUAGE.md"),
    Path(".agents/skills/owh-docs-reader/scripts/read_open_work_hub_doc.py"),
    Path(".agents/skills/owh-env-contracts/scripts/env-inventory.sh"),
    Path(".agents/skills/owh-env-contracts/scripts/local-env-files.sh"),
    Path(".agents/skills/owh-issues/AGENT-BRIEF.md"),
    Path(".agents/skills/owh-agent-harness/references/ci-review.md"),
    Path(".agents/skills/owh-design-review/references/plan-review.md"),
    Path(".agents/skills/owh-design-review/references/architecture.md"),
    Path(".agents/skills/owh-env-contracts/references/env-files.md"),
    Path(".agents/skills/owh-env-contracts/references/separation.md"),
    Path(".agents/skills/owh-issues/references/prd.md"),
    Path(".agents/skills/owh-issues/references/slices.md"),
    Path(".agents/skills/owh-issues/references/triage.md"),
}

STALE_SKILL_GUIDE_PATTERNS = {
    r"\bCONTEXT(?:-MAP)?\.md\b": "Open Work Hub does not use generic context glossary files",
    r"\bdocs/adr/": "Open Work Hub ADRs live in root adr/",
    r"/projects/": "fixed internal checkout paths are not portable",
    r"\bdocs/current/": "docs/README.md and current owner docs replace docs/current",
    r"\b(?:Legacy Issues|mcloudoc)\b": "retired internal apps must not appear in skills",
}

RETIRED_TRIAGE_PATTERNS = {
    r"\benhancement\b": "feature issues do not use a category label in the current GitLab contract",
    r"\bneeds-info\b": "needs-info is not a documented GitLab label",
    r"\bready-for-human\b": "ready-for-human is not a documented GitLab label",
    r"\bwontfix\b": "wontfix is not a documented GitLab label",
    r"\.out-of-scope\b": "the parallel out-of-scope archive is retired",
    r"OUT-OF-SCOPE\.md": "the parallel out-of-scope archive is retired",
}

TRIAGE_GUIDANCE_PATHS = {
    Path(".agents/skills/owh-issues/SKILL.md"),
    Path("docs/agents/triage-labels.md"),
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
    r"(?i)\bai-do\b|\bAI_DO\b|\bai_do\b": "retired AI-DO identifiers must not appear in Open Work Hub guidance",
    r"/projects/ai-do\b": "AI-DO internal checkout paths are not portable",
    r"\bdwdcc\b": "DWDCC project references must not appear in Open Work Hub guidance",
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
    ".runtime",
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
    instruction_files: tuple[TextFileContent, ...]
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
        if key.strip() in result:
            raise ValueError(f"line {line_number}: duplicate key {key.strip()}")
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


def _walk_files(root: Path, directory: Path) -> Iterable[Path]:
    """Prune generated/dependency trees before descent; never follow symlinks."""
    for current, directories, filenames in os.walk(directory, followlinks=False):
        directories[:] = [
            name for name in directories
            if not _should_skip_checked_file(root, Path(current) / name)
            and not (Path(current) / name).is_symlink()
        ]
        for name in filenames:
            candidate = Path(current) / name
            if not _should_skip_checked_file(root, candidate):
                yield candidate


def instruction_files(root: Path = ROOT) -> list[Path]:
    if not root.exists():
        return []
    names = {
        "AGENTS.md",
        "AGENTS.override.md",
        "CLAUDE.md",
        "agents.md",
        "agents.override.md",
        "claude.md",
    }
    return sorted(
        path
        for path in _walk_files(root, root)
        if (path.is_file() or path.is_symlink())
        and path.name in names
        and not _should_skip_checked_file(root, path)
    )


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
        root / ".codex",
        root / ".github",
        root / ".gitlab",
        root / ".gitlab-ci.yml",
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
                for path in _walk_files(root, scan_root)
                if path.is_file()
                and not _should_skip_checked_file(root, path)
            )
    files.extend(instruction_files(root))
    return sorted({path.resolve() for path in files if not path.is_symlink()})


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
        instruction_files=tuple(
            TextFileContent(
                path=path.absolute(),
                text="" if path.is_symlink() else path.read_text(encoding="utf-8"),
            )
            for path in instruction_files(resolved_root)
        ),
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
        or relative.parts[:3] == (".agents", "skills", "owh-issues")
    )


def _is_core_agent_guidance(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    return (
        relative in ALLOWED_INSTRUCTION_PATHS
        or relative
        in {
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

    instruction_paths = {
        file_content.path.relative_to(root): file_content
        for file_content in snapshot.instruction_files
    }
    unexpected_instruction_paths = sorted(
        str(path)
        for path in instruction_paths
        if path not in ALLOWED_INSTRUCTION_PATHS
    )
    if unexpected_instruction_paths:
        findings.append(
            _finding(
                "unexpected_agent_instruction",
                "agent instruction files may exist only at approved scopes: "
                + ", ".join(unexpected_instruction_paths),
            )
        )

    if require_tool_bridges:
        missing_instruction_paths = sorted(
            str(path)
            for path in ALLOWED_INSTRUCTION_PATHS
            if path not in instruction_paths
        )
        if missing_instruction_paths:
            findings.append(
                _finding(
                    "missing_agent_instruction",
                    "missing required root/scoped agent instructions: "
                    + ", ".join(missing_instruction_paths),
                )
            )

    for relative, file_content in sorted(instruction_paths.items()):
        if file_content.path.is_symlink():
            findings.append(_finding("symlink_agent_instruction", f"{relative}: instruction files must be owned regular files, not symlinks"))
        limit = INSTRUCTION_LINE_LIMITS.get(relative)
        if limit is None:
            continue
        line_count = len(file_content.text.splitlines())
        if line_count > limit:
            findings.append(
                _finding(
                    "agent_instruction_too_long",
                    f"{relative}: {line_count} lines exceeds the {limit}-line limit",
                )
            )
        if (
            relative in SCOPED_CLAUDE_PATHS
            and file_content.text.strip() != "@AGENTS.md"
        ):
            findings.append(
                _finding(
                    "invalid_scoped_claude_bridge",
                    f"{relative}: scoped CLAUDE.md must contain only @AGENTS.md",
                )
            )

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
        if claude_path.is_file() and not claude_path.is_symlink() and "@AGENTS.md" not in claude_path.read_text(
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
        if (
            not claude_skills.is_symlink()
            or claude_skills.resolve() != canonical_skills.resolve()
        ):
            findings.append(
                _finding(
                    "invalid_claude_skills_bridge",
                    ".claude/skills must link to ../.agents/skills; "
                    "run pnpm setup:claude-skills",
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

    description_total = 0
    for file_content in sorted(snapshot.skill_files, key=lambda item: str(item.path)):
        skill_size = len(file_content.text.encode("utf-8"))
        skill_line_count = len(file_content.text.splitlines())
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
        if skill_line_count > MAX_SKILL_LINES:
            findings.append(
                _finding(
                    "skill_guide_too_long",
                    f"{_display_path(root, file_content.path)}: "
                    f"SKILL.md is {skill_line_count} lines; keep it at or below "
                    f"{MAX_SKILL_LINES} lines",
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
        if "Use when" not in metadata.get("description", ""):
            findings.append(
                _finding(
                    "missing_use_when_trigger",
                    f"{_display_path(root, file_content.path)}: "
                    "description must include 'Use when'",
                )
            )
        description = metadata.get("description", "")
        description_total += len(description)
        if description in {"", ">", "|", ">-", "|-"}:
            findings.append(
                _finding(
                    "invalid_skill_description",
                    f"{_display_path(root, file_content.path)}: "
                    "description must be a concise single-line scalar",
                )
            )
        elif len(description) > MAX_SKILL_DESCRIPTION_CHARS:
            findings.append(
                _finding(
                    "skill_description_too_long",
                    f"{_display_path(root, file_content.path)}: description is "
                    f"{len(description)} characters; keep it at or below "
                    f"{MAX_SKILL_DESCRIPTION_CHARS}",
                )
            )

    if description_total > MAX_TOTAL_DESCRIPTION_CHARS:
        findings.append(_finding("skill_catalog_too_large", f"skill descriptions total {description_total} characters; limit {MAX_TOTAL_DESCRIPTION_CHARS}"))

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
        if LOWERCASE_AGENTS_REFERENCE_RE.search(file_content.text):
            findings.append(
                _finding(
                    "lowercase_agents_reference",
                    f"{_display_path(root, file_content.path)}: "
                    "refer to the canonical filename as AGENTS.md",
                )
            )
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
