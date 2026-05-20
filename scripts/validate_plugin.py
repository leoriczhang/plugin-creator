#!/usr/bin/env python3
"""
Validate a Claude Code plugin against the official plugins reference.

Usage:
    python -m scripts.validate_plugin <plugin-root> [--marketplace] [--json]

Exit codes:
    0 — no errors (warnings/info allowed)
    1 — at least one error
    2 — usage error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.utils import (
    ALLOWED_AGENT_FRONTMATTER,
    ALLOWED_EXPERIMENTAL_KEYS,
    ALLOWED_HOOK_EVENTS,
    ALLOWED_HOOK_TYPES,
    ALLOWED_MANIFEST_FIELDS,
    FORBIDDEN_AGENT_FRONTMATTER,
    Report,
    is_kebab_case,
    is_semver,
    iter_agent_files,
    iter_skill_dirs,
    parse_frontmatter,
    read_json,
    under_root,
)

URL_RE = re.compile(r"^https?://[^\s]+$")
SPDX_RE = re.compile(r"^[A-Za-z0-9.\-+]+$")


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


def validate_manifest(plugin_root: Path, report: Report, marketplace: bool) -> dict:
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        # Manifest is optional — if missing, the plugin is auto-discovered.
        report.info(
            "manifest",
            "No .claude-plugin/plugin.json — components will be auto-discovered. "
            "Add a manifest to declare metadata or custom paths.",
        )
        return {}

    try:
        manifest = read_json(manifest_path)
    except ValueError as e:
        report.error("manifest.json", str(e), "Fix JSON syntax — no trailing commas, no comments.")
        return {}

    if not isinstance(manifest, dict):
        report.error("manifest", "Top-level value must be an object.")
        return {}

    # Unknown fields
    unknown = set(manifest.keys()) - ALLOWED_MANIFEST_FIELDS
    if unknown:
        report.warning(
            "manifest",
            f"Unknown manifest field(s): {', '.join(sorted(unknown))}",
            f"Allowed: {', '.join(sorted(ALLOWED_MANIFEST_FIELDS))}",
        )

    # Required: name
    name = manifest.get("name")
    if not name:
        report.error("name", "Required field 'name' is missing.", "Add a kebab-case name.")
    elif not isinstance(name, str):
        report.error("name", f"Must be a string, got {type(name).__name__}")
    else:
        if not is_kebab_case(name):
            report.error(
                "name",
                f"'{name}' is not kebab-case",
                "Use lowercase letters, digits, and single hyphens.",
            )
        if len(name) > 64:
            report.error("name", f"name is {len(name)} chars (max 64)")
        # Cross-check with directory name
        if name != plugin_root.name:
            report.warning(
                "name",
                f"manifest name '{name}' differs from directory '{plugin_root.name}'",
                "Rename one to match the other.",
            )

    # Version
    version = manifest.get("version")
    if version is not None:
        if not isinstance(version, str) or not is_semver(version):
            report.error(
                "version",
                f"'{version}' is not valid SemVer",
                "Use MAJOR.MINOR.PATCH, e.g. '0.1.0'.",
            )
    else:
        report.warning("version", "No 'version' declared.", "Add a SemVer string for distribution.")

    # Description
    desc = manifest.get("description")
    if desc is not None:
        if not isinstance(desc, str):
            report.error("description", "Must be a string.")
        else:
            if "<" in desc or ">" in desc:
                report.error(
                    "description",
                    "Cannot contain angle brackets (< or >).",
                )

    # Author
    author = manifest.get("author")
    if author is not None:
        if not isinstance(author, dict):
            report.error("author", "Must be an object.")
        else:
            if "name" not in author:
                report.error("author.name", "Required when 'author' is set.")
            for url_field in ("url",):
                v = author.get(url_field)
                if v and not URL_RE.match(v):
                    report.warning(f"author.{url_field}", f"'{v}' is not a valid http(s) URL.")
            email = author.get("email")
            if email and "@" not in email:
                report.warning("author.email", f"'{email}' does not look like an email.")

    # URLs
    for url_field in ("homepage", "repository"):
        v = manifest.get(url_field)
        if v and not URL_RE.match(v):
            report.warning(url_field, f"'{v}' is not a valid http(s) URL.")

    # License
    lic = manifest.get("license")
    if lic and not isinstance(lic, str):
        report.error("license", "Must be a string SPDX identifier.")
    elif lic and not SPDX_RE.match(lic):
        report.warning("license", f"'{lic}' does not look like a SPDX identifier.")

    # Keywords
    kw = manifest.get("keywords")
    if kw is not None:
        if not isinstance(kw, list) or not all(isinstance(k, str) for k in kw):
            report.error("keywords", "Must be an array of strings.")
        else:
            for k in kw:
                if len(k) > 50:
                    report.warning("keywords", f"keyword '{k}' is longer than 50 chars.")

    # experimental keys
    exp = manifest.get("experimental")
    if exp is not None:
        if not isinstance(exp, dict):
            report.error("experimental", "Must be an object.")
        else:
            unknown_exp = set(exp.keys()) - ALLOWED_EXPERIMENTAL_KEYS
            if unknown_exp:
                report.warning(
                    "experimental",
                    f"Unknown experimental key(s): {', '.join(sorted(unknown_exp))}",
                    f"Allowed: {', '.join(sorted(ALLOWED_EXPERIMENTAL_KEYS))}",
                )

    # Path-valued fields must resolve under plugin_root
    for path_field in ("skills", "commands", "agents", "hooks"):
        v = manifest.get(path_field)
        if isinstance(v, str):
            _check_path(plugin_root, v, path_field, report)
        elif isinstance(v, list):
            for entry in v:
                if isinstance(entry, str):
                    _check_path(plugin_root, entry, path_field, report)

    # Marketplace mode
    if marketplace:
        for required in ("version", "description", "repository", "homepage", "license"):
            if not manifest.get(required):
                report.error(
                    f"manifest.{required}",
                    f"Required for marketplace publishing.",
                    "Set this field before submitting to a marketplace.",
                )
        if not manifest.get("keywords"):
            report.error("keywords", "Marketplace plugins should declare keywords.")
        author = manifest.get("author") or {}
        if not author.get("name"):
            report.error("author.name", "Required for marketplace publishing.")

    return manifest


def _check_path(plugin_root: Path, rel: str, field: str, report: Report) -> None:
    if rel.startswith("/"):
        report.error(field, f"Path '{rel}' is absolute; must be relative to plugin root.")
        return
    candidate = (plugin_root / rel).resolve()
    if not under_root(plugin_root, candidate):
        report.error(field, f"Path '{rel}' escapes the plugin root.")
        return
    if not candidate.exists():
        report.warning(field, f"Path '{rel}' does not exist on disk.")


# ---------------------------------------------------------------------------
# Skill validation
# ---------------------------------------------------------------------------


def validate_skills(plugin_root: Path, report: Report) -> None:
    for skill_dir in iter_skill_dirs(plugin_root):
        skill_md = skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        fm, _body = parse_frontmatter(text)
        rel = skill_md.relative_to(plugin_root)
        if not fm:
            report.error(str(rel), "SKILL.md has no YAML frontmatter.")
            continue
        if "name" not in fm:
            report.error(str(rel), "Missing 'name' in frontmatter.")
        else:
            n = str(fm["name"]).strip()
            if not is_kebab_case(n):
                report.error(str(rel), f"name '{n}' is not kebab-case.")
            if n != skill_dir.name:
                report.warning(
                    str(rel),
                    f"frontmatter name '{n}' differs from directory '{skill_dir.name}'.",
                )
        if "description" not in fm:
            report.error(
                str(rel),
                "Missing 'description' — Claude can't decide when to invoke this skill.",
            )
        else:
            d = str(fm["description"]).strip()
            if "<" in d or ">" in d:
                report.error(str(rel), "description must not contain angle brackets.")
            if len(d) > 1024:
                report.warning(str(rel), f"description is {len(d)} chars (recommended ≤ 1024).")


# ---------------------------------------------------------------------------
# Agent validation
# ---------------------------------------------------------------------------


def validate_agents(plugin_root: Path, report: Report) -> None:
    for agent_md in iter_agent_files(plugin_root):
        text = agent_md.read_text(encoding="utf-8")
        fm, _body = parse_frontmatter(text)
        rel = agent_md.relative_to(plugin_root)
        if not fm:
            report.error(str(rel), "Agent file has no YAML frontmatter.")
            continue
        if "name" not in fm:
            report.error(str(rel), "Missing 'name' in agent frontmatter.")
        if "description" not in fm:
            report.error(str(rel), "Missing 'description' in agent frontmatter.")
        forbidden = set(fm.keys()) & FORBIDDEN_AGENT_FRONTMATTER
        if forbidden:
            report.error(
                str(rel),
                f"Plugin-shipped agents must NOT set: {', '.join(sorted(forbidden))}",
                "Remove these keys — they are disallowed for security reasons.",
            )
        unknown = set(fm.keys()) - ALLOWED_AGENT_FRONTMATTER
        if unknown:
            report.warning(
                str(rel),
                f"Unknown agent frontmatter key(s): {', '.join(sorted(unknown))}",
                f"Allowed: {', '.join(sorted(ALLOWED_AGENT_FRONTMATTER))}",
            )
        iso = fm.get("isolation")
        if iso and iso != "worktree":
            report.error(
                str(rel),
                f"Invalid isolation value '{iso}'.",
                "Only 'worktree' is allowed.",
            )


# ---------------------------------------------------------------------------
# Hooks validation
# ---------------------------------------------------------------------------


def validate_hooks(plugin_root: Path, report: Report, manifest: dict) -> None:
    # Either external file, or inline in manifest
    inline = manifest.get("hooks")
    inline_path = isinstance(inline, str)
    inline_obj = isinstance(inline, dict)

    external = plugin_root / "hooks" / "hooks.json"
    if inline_path:
        external = (plugin_root / inline).resolve()

    data = None
    if external.exists():
        if inline_obj:
            report.warning(
                "hooks",
                "hooks declared inline in plugin.json AND hooks/hooks.json exists — ambiguous.",
                "Pick one source of truth.",
            )
        try:
            data = read_json(external)
        except ValueError as e:
            report.error(str(external.relative_to(plugin_root)), str(e))
            return
    elif inline_obj:
        data = inline
    else:
        return  # No hooks declared, nothing to validate

    if not isinstance(data, dict):
        report.error("hooks", "Hooks file/inline must be an object with a 'hooks' key.")
        return
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        report.error("hooks.hooks", "Must be an object mapping event names to arrays.")
        return

    for event_name, entries in hooks.items():
        if event_name not in ALLOWED_HOOK_EVENTS:
            report.error(
                f"hooks.{event_name}",
                f"Unknown event '{event_name}'.",
                f"Allowed events: see references/hooks_events.md",
            )
            continue
        if not isinstance(entries, list):
            report.error(f"hooks.{event_name}", "Must be an array of matcher objects.")
            continue
        for i, matcher_entry in enumerate(entries):
            if not isinstance(matcher_entry, dict):
                report.error(
                    f"hooks.{event_name}[{i}]",
                    "Each entry must be an object with optional 'matcher' and a 'hooks' array.",
                )
                continue
            inner_hooks = matcher_entry.get("hooks")
            if not isinstance(inner_hooks, list):
                report.error(
                    f"hooks.{event_name}[{i}].hooks",
                    "Must be an array of hook actions.",
                )
                continue
            for j, action in enumerate(inner_hooks):
                _validate_hook_action(event_name, i, j, action, report)


def _validate_hook_action(event: str, i: int, j: int, action: dict, report: Report) -> None:
    field = f"hooks.{event}[{i}].hooks[{j}]"
    if not isinstance(action, dict):
        report.error(field, "Hook action must be an object.")
        return
    t = action.get("type")
    if t not in ALLOWED_HOOK_TYPES:
        report.error(
            field,
            f"Unknown hook type '{t}'.",
            f"Allowed types: {', '.join(sorted(ALLOWED_HOOK_TYPES))}",
        )
        return
    if t == "command":
        cmd = action.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            report.error(f"{field}.command", "Required and non-empty for type 'command'.")
        elif "${CLAUDE_PLUGIN_ROOT}" in cmd and '"${CLAUDE_PLUGIN_ROOT}"' not in cmd and r'\"${CLAUDE_PLUGIN_ROOT}\"' not in cmd:
            report.warning(
                f"{field}.command",
                "${CLAUDE_PLUGIN_ROOT} should be quoted to handle paths with spaces.",
                'Wrap as: "\\"${CLAUDE_PLUGIN_ROOT}\\"/scripts/foo.sh"',
            )
    elif t == "http":
        if not action.get("url"):
            report.error(f"{field}.url", "Required for type 'http'.")
    elif t == "mcp_tool":
        if not action.get("tool"):
            report.error(f"{field}.tool", "Required for type 'mcp_tool'.")
    elif t == "prompt":
        if not action.get("prompt"):
            report.error(f"{field}.prompt", "Required for type 'prompt'.")
    elif t == "agent":
        if not action.get("agent"):
            report.error(f"{field}.agent", "Required for type 'agent'.")


# ---------------------------------------------------------------------------
# MCP / LSP / monitors / themes
# ---------------------------------------------------------------------------


def validate_mcp(plugin_root: Path, report: Report, manifest: dict) -> None:
    inline = manifest.get("mcpServers")
    external = plugin_root / ".mcp.json"
    if external.exists() and inline:
        report.warning(
            "mcpServers",
            ".mcp.json AND inline mcpServers both present — ambiguous.",
        )
    if external.exists():
        try:
            data = read_json(external)
        except ValueError as e:
            report.error(".mcp.json", str(e))
            return
        servers = data.get("mcpServers") if isinstance(data, dict) else None
    else:
        servers = inline

    if not servers:
        return
    if not isinstance(servers, dict):
        report.error("mcpServers", "Must be an object mapping server keys to configs.")
        return
    for key, cfg in servers.items():
        prefix = f"mcpServers.{key}"
        if not isinstance(cfg, dict):
            report.error(prefix, "Each server entry must be an object.")
            continue
        if not cfg.get("command"):
            report.error(f"{prefix}.command", "Required.")
        for arg_field in ("args",):
            v = cfg.get(arg_field)
            if v is not None and not isinstance(v, list):
                report.error(f"{prefix}.{arg_field}", "Must be a list of strings.")
        env = cfg.get("env")
        if env is not None and not isinstance(env, dict):
            report.error(f"{prefix}.env", "Must be an object mapping name → value.")


def validate_lsp(plugin_root: Path, report: Report, manifest: dict) -> None:
    inline = manifest.get("lspServers")
    external = plugin_root / ".lsp.json"
    if external.exists() and inline:
        report.warning(
            "lspServers",
            ".lsp.json AND inline lspServers both present — ambiguous.",
        )
    if external.exists():
        try:
            data = read_json(external)
        except ValueError as e:
            report.error(".lsp.json", str(e))
            return
        servers = data
    else:
        servers = inline

    if not servers:
        return
    if not isinstance(servers, dict):
        report.error("lspServers", "Must be an object.")
        return
    for key, cfg in servers.items():
        prefix = f"lspServers.{key}"
        if not isinstance(cfg, dict):
            report.error(prefix, "Each server entry must be an object.")
            continue
        if not cfg.get("command"):
            report.error(f"{prefix}.command", "Required.")
        ext_map = cfg.get("extensionToLanguage")
        if not isinstance(ext_map, dict) or not ext_map:
            report.error(
                f"{prefix}.extensionToLanguage",
                "Required and must be a non-empty object.",
            )
        else:
            for ext_key in ext_map:
                if not ext_key.startswith("."):
                    report.warning(
                        f"{prefix}.extensionToLanguage",
                        f"Extension key '{ext_key}' should start with '.'",
                    )


def validate_monitors(plugin_root: Path, report: Report, manifest: dict) -> None:
    exp = manifest.get("experimental") or {}
    inline = exp.get("monitors")
    external = plugin_root / "monitors" / "monitors.json"
    if isinstance(inline, str):
        external = (plugin_root / inline).resolve()
        inline = None
    if external.exists() and isinstance(inline, list):
        report.warning(
            "experimental.monitors",
            "Both monitors.json and inline monitors declared — ambiguous.",
        )
    if external.exists():
        try:
            data = read_json(external)
        except ValueError as e:
            report.error(str(external.relative_to(plugin_root)), str(e))
            return
    elif isinstance(inline, list):
        data = inline
    else:
        return
    if not isinstance(data, list):
        report.error("monitors", "Must be a JSON array of monitor entries.")
        return
    seen = set()
    for i, entry in enumerate(data):
        prefix = f"monitors[{i}]"
        if not isinstance(entry, dict):
            report.error(prefix, "Each monitor must be an object.")
            continue
        n = entry.get("name")
        if not n:
            report.error(f"{prefix}.name", "Required.")
        elif n in seen:
            report.error(f"{prefix}.name", f"Duplicate monitor name '{n}' (must be unique per plugin).")
        else:
            seen.add(n)
        if not entry.get("command"):
            report.error(f"{prefix}.command", "Required.")
        if not entry.get("description"):
            report.error(f"{prefix}.description", "Required.")
        when = entry.get("when")
        if when and not (when == "always" or when.startswith("on-skill-invoke:")):
            report.error(
                f"{prefix}.when",
                f"Invalid 'when' value: {when!r}.",
                "Use 'always' or 'on-skill-invoke:<skill-name>'.",
            )


def validate_themes(plugin_root: Path, report: Report, manifest: dict) -> None:
    exp = manifest.get("experimental") or {}
    custom = exp.get("themes")
    if isinstance(custom, str):
        themes_dir = (plugin_root / custom).resolve()
    else:
        themes_dir = plugin_root / "themes"
    if not themes_dir.exists():
        return
    for theme_file in themes_dir.glob("*.json"):
        rel = theme_file.relative_to(plugin_root)
        try:
            data = read_json(theme_file)
        except ValueError as e:
            report.error(str(rel), str(e))
            continue
        if not isinstance(data, dict):
            report.error(str(rel), "Theme file must be an object.")
            continue
        if not data.get("name"):
            report.error(str(rel), "Missing 'name'.")
        if not data.get("base"):
            report.error(str(rel), "Missing 'base' preset.")
        overrides = data.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            report.error(str(rel), "'overrides' must be an object.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def validate_plugin(plugin_root: Path, marketplace: bool = False) -> Report:
    report = Report()
    if not plugin_root.is_dir():
        report.error("plugin_root", f"Not a directory: {plugin_root}")
        return report
    manifest = validate_manifest(plugin_root, report, marketplace)
    validate_skills(plugin_root, report)
    validate_agents(plugin_root, report)
    validate_hooks(plugin_root, report, manifest)
    validate_mcp(plugin_root, report, manifest)
    validate_lsp(plugin_root, report, manifest)
    validate_monitors(plugin_root, report, manifest)
    validate_themes(plugin_root, report, manifest)
    return report


def _print_report(report: Report) -> None:
    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
    for issue in report.issues:
        line = f"{icon[issue.severity]}  [{issue.field}] {issue.message}"
        print(line)
        if issue.fix:
            print(f"   ↳ {issue.fix}")
    print()
    s = report.to_dict()["summary"]
    print(
        f"summary: {s['errors']} error(s), {s['warnings']} warning(s), {s['info']} info"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate a Claude Code plugin.")
    p.add_argument("plugin_root", type=Path)
    p.add_argument("--marketplace", action="store_true", help="Apply stricter marketplace checks.")
    p.add_argument("--json", action="store_true", help="Emit JSON report instead of text.")
    args = p.parse_args(argv)

    report = validate_plugin(args.plugin_root, marketplace=args.marketplace)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
