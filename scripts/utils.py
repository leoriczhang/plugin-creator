#!/usr/bin/env python3
"""
Shared utilities for plugin-creator scripts.

These helpers are used by validate_plugin / scaffold_plugin / add_component /
bump_version / package_plugin / generate_review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Constants from the official plugins reference
# ---------------------------------------------------------------------------

ALLOWED_HOOK_EVENTS = {
    "SessionStart",
    "Setup",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "PreToolUse",
    "PermissionRequest",
    "PermissionDenied",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "InstructionsLoaded",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "PreCompact",
    "PostCompact",
    "Elicitation",
    "ElicitationResult",
    "SessionEnd",
}

ALLOWED_HOOK_TYPES = {"command", "http", "mcp_tool", "prompt", "agent"}

# Plugin-shipped agents have stricter rules — these frontmatter keys are forbidden.
FORBIDDEN_AGENT_FRONTMATTER = {"hooks", "mcpServers", "permissionMode"}

ALLOWED_AGENT_FRONTMATTER = {
    "name",
    "description",
    "model",
    "effort",
    "maxTurns",
    "tools",
    "disallowedTools",
    "skills",
    "memory",
    "background",
    "isolation",
}

ALLOWED_MANIFEST_FIELDS = {
    "name",
    "displayName",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "skills",
    "commands",
    "agents",
    "hooks",
    "mcpServers",
    "lspServers",
    "experimental",
}

ALLOWED_EXPERIMENTAL_KEYS = {"monitors", "themes"}

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)

# ---------------------------------------------------------------------------
# Diagnostic dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    field: str
    message: str
    fix: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
            "fix": self.fix,
        }


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def error(self, fld: str, message: str, fix: str = "") -> None:
        self.issues.append(Issue("error", fld, message, fix))

    def warning(self, fld: str, message: str, fix: str = "") -> None:
        self.issues.append(Issue("warning", fld, message, fix))

    def info(self, fld: str, message: str, fix: str = "") -> None:
        self.issues.append(Issue("info", fld, message, fix))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "info"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
            "info": [i.to_dict() for i in self.infos],
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "info": len(self.infos),
                "ok": self.ok,
            },
        }


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def read_json(path: Path) -> Any:
    """Read a JSON file. Raises with a helpful message on parse error."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{path}: invalid JSON ({e.msg} at line {e.lineno} col {e.colno})"
        ) from e


def write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON with a trailing newline. Does not insert comments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a markdown file's YAML frontmatter.

    Returns (frontmatter_dict, body). Frontmatter is empty dict if missing.
    Uses a minimal in-house parser to avoid the PyYAML dependency.
    """
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = m.group(2)
    return _parse_simple_yaml(fm_text), body


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset: scalar key:value, lists, multiline > and |."""
    out: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in ("|", ">"):
            block_lines: list[str] = []
            i += 1
            base_indent: int | None = None
            while i < len(lines):
                next_line = lines[i]
                if next_line.strip() == "":
                    block_lines.append("")
                    i += 1
                    continue
                stripped = next_line.lstrip()
                indent = len(next_line) - len(stripped)
                if base_indent is None:
                    base_indent = indent
                if indent < base_indent:
                    break
                block_lines.append(next_line[base_indent:])
                i += 1
            joined = "\n".join(block_lines) if val == "|" else " ".join(
                line.strip() for line in block_lines
            )
            out[key] = joined.rstrip()
            continue
        if val == "":
            out[key] = ""
        else:
            # Strip surrounding quotes if any
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            out[key] = val
        i += 1
    return out


# ---------------------------------------------------------------------------
# Validators (small enough to live here; bigger orchestration in validate_plugin.py)
# ---------------------------------------------------------------------------


def is_kebab_case(s: str) -> bool:
    return bool(KEBAB_CASE_RE.match(s))


def is_semver(s: str) -> bool:
    return bool(SEMVER_RE.match(s))


def parse_semver(s: str) -> tuple[int, int, int, str, str]:
    m = SEMVER_RE.match(s)
    if not m:
        raise ValueError(f"Not a SemVer string: {s!r}")
    return (
        int(m.group("major")),
        int(m.group("minor")),
        int(m.group("patch")),
        m.group("prerelease") or "",
        m.group("build") or "",
    )


def under_root(plugin_root: Path, candidate: Path) -> bool:
    """True iff `candidate` is contained within `plugin_root` (no `..` traversal)."""
    try:
        candidate.resolve().relative_to(plugin_root.resolve())
    except ValueError:
        return False
    return True


def iter_skill_dirs(plugin_root: Path) -> Iterable[Path]:
    skills_dir = plugin_root / "skills"
    if not skills_dir.is_dir():
        return []
    return [p for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]


def iter_agent_files(plugin_root: Path) -> Iterable[Path]:
    agents_dir = plugin_root / "agents"
    if not agents_dir.is_dir():
        return []
    return [p for p in agents_dir.iterdir() if p.is_file() and p.suffix == ".md"]
