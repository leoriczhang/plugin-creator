#!/usr/bin/env python3
"""
Generate a static HTML overview of a plugin.

Usage:
    python -m scripts.generate_review <plugin-root> --output /tmp/plugin_review.html

The output is a self-contained HTML file showing:
- Manifest contents (formatted)
- Component tree
- Each skill / agent's frontmatter and body preview
- Hooks, MCP, LSP, monitors, themes — tabular summaries
- Validation summary inline
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from scripts.utils import (
    iter_agent_files,
    iter_skill_dirs,
    parse_frontmatter,
    read_json,
)
from scripts.validate_plugin import validate_plugin


def _h(s: object) -> str:
    return html.escape(str(s))


def _section(title: str, body: str) -> str:
    return f"<section><h2>{_h(title)}</h2>{body}</section>\n"


def _kv_table(d: dict) -> str:
    rows = "".join(
        f"<tr><th>{_h(k)}</th><td><pre>{_h(json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else v)}</pre></td></tr>"
        for k, v in d.items()
    )
    return f"<table class='kv'>{rows}</table>"


def _component_summary(plugin_root: Path) -> str:
    counts = {
        "skills": len(list(iter_skill_dirs(plugin_root))),
        "agents": len(list(iter_agent_files(plugin_root))),
        "commands": len(list((plugin_root / "commands").glob("*.md"))) if (plugin_root / "commands").is_dir() else 0,
    }
    hooks_path = plugin_root / "hooks" / "hooks.json"
    if hooks_path.exists():
        try:
            h = read_json(hooks_path)
            counts["hook events"] = sum(len(v) for v in h.get("hooks", {}).values()) if isinstance(h, dict) else 0
        except ValueError:
            counts["hook events"] = "(parse error)"
    mcp_path = plugin_root / ".mcp.json"
    if mcp_path.exists():
        try:
            counts["mcp servers"] = len(read_json(mcp_path).get("mcpServers", {}) or {})
        except ValueError:
            counts["mcp servers"] = "(parse error)"
    lsp_path = plugin_root / ".lsp.json"
    if lsp_path.exists():
        try:
            counts["lsp servers"] = len(read_json(lsp_path) or {})
        except ValueError:
            counts["lsp servers"] = "(parse error)"
    monitors_path = plugin_root / "monitors" / "monitors.json"
    if monitors_path.exists():
        try:
            counts["monitors"] = len(read_json(monitors_path) or [])
        except ValueError:
            counts["monitors"] = "(parse error)"
    themes_dir = plugin_root / "themes"
    if themes_dir.is_dir():
        counts["themes"] = len(list(themes_dir.glob("*.json")))
    return _kv_table(counts)


def _skills_section(plugin_root: Path) -> str:
    parts = []
    for skill_dir in iter_skill_dirs(plugin_root):
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        preview = "\n".join(body.splitlines()[:80])
        parts.append(
            f"<details open><summary><code>{_h(skill_dir.name)}</code> — {_h(fm.get('description', ''))[:200]}</summary>"
            f"<div class='frontmatter'>{_kv_table(fm)}</div>"
            f"<pre class='body'>{_h(preview)}</pre>"
            "</details>"
        )
    if not parts:
        return "<p><em>(no skills)</em></p>"
    return "".join(parts)


def _agents_section(plugin_root: Path) -> str:
    parts = []
    for agent_md in iter_agent_files(plugin_root):
        text = agent_md.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        preview = "\n".join(body.splitlines()[:80])
        parts.append(
            f"<details><summary><code>{_h(agent_md.stem)}</code> — {_h(fm.get('description', ''))[:200]}</summary>"
            f"<div class='frontmatter'>{_kv_table(fm)}</div>"
            f"<pre class='body'>{_h(preview)}</pre>"
            "</details>"
        )
    if not parts:
        return "<p><em>(no agents)</em></p>"
    return "".join(parts)


def _hooks_section(plugin_root: Path) -> str:
    hp = plugin_root / "hooks" / "hooks.json"
    if not hp.exists():
        return "<p><em>(no hooks file)</em></p>"
    try:
        data = read_json(hp)
    except ValueError as e:
        return f"<p class='err'>parse error: {_h(e)}</p>"
    rows = []
    for event, entries in (data.get("hooks") or {}).items():
        for entry in entries:
            matcher = entry.get("matcher", "(any)")
            for action in entry.get("hooks", []):
                rows.append(
                    f"<tr><td>{_h(event)}</td><td><code>{_h(matcher)}</code></td>"
                    f"<td>{_h(action.get('type'))}</td><td><code>{_h(action.get('command') or action.get('url') or action.get('tool') or action.get('prompt') or action.get('agent'))}</code></td></tr>"
                )
    return (
        "<table><thead><tr><th>event</th><th>matcher</th><th>type</th><th>command/target</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _mcp_section(plugin_root: Path) -> str:
    p = plugin_root / ".mcp.json"
    if not p.exists():
        return "<p><em>(no .mcp.json)</em></p>"
    try:
        data = read_json(p).get("mcpServers", {})
    except ValueError as e:
        return f"<p class='err'>parse error: {_h(e)}</p>"
    return _kv_table(data)


def _lsp_section(plugin_root: Path) -> str:
    p = plugin_root / ".lsp.json"
    if not p.exists():
        return "<p><em>(no .lsp.json)</em></p>"
    try:
        data = read_json(p)
    except ValueError as e:
        return f"<p class='err'>parse error: {_h(e)}</p>"
    return _kv_table(data or {})


def _monitors_section(plugin_root: Path) -> str:
    p = plugin_root / "monitors" / "monitors.json"
    if not p.exists():
        return "<p><em>(no monitors.json)</em></p>"
    try:
        data = read_json(p)
    except ValueError as e:
        return f"<p class='err'>parse error: {_h(e)}</p>"
    rows = "".join(
        f"<tr><td><code>{_h(m.get('name'))}</code></td><td>{_h(m.get('description'))}</td>"
        f"<td><code>{_h(m.get('command'))}</code></td><td>{_h(m.get('when', 'always'))}</td></tr>"
        for m in data
    )
    return (
        "<table><thead><tr><th>name</th><th>description</th><th>command</th><th>when</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _themes_section(plugin_root: Path) -> str:
    d = plugin_root / "themes"
    if not d.is_dir():
        return "<p><em>(no themes)</em></p>"
    rows = []
    for f in d.glob("*.json"):
        try:
            data = read_json(f)
        except ValueError as e:
            rows.append(f"<tr><td>{_h(f.name)}</td><td class='err'>{_h(e)}</td><td>—</td></tr>")
            continue
        rows.append(
            f"<tr><td>{_h(data.get('name'))}</td><td>{_h(data.get('base'))}</td>"
            f"<td><code>{_h(json.dumps(data.get('overrides', {}), ensure_ascii=False))}</code></td></tr>"
        )
    return (
        "<table><thead><tr><th>name</th><th>base</th><th>overrides</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _validation_section(plugin_root: Path) -> str:
    report = validate_plugin(plugin_root)
    rows = []
    for issue in report.issues:
        rows.append(
            f"<tr class='{_h(issue.severity)}'><td>{_h(issue.severity)}</td>"
            f"<td><code>{_h(issue.field)}</code></td>"
            f"<td>{_h(issue.message)}</td><td>{_h(issue.fix)}</td></tr>"
        )
    s = report.to_dict()["summary"]
    head = f"<p>{s['errors']} error(s), {s['warnings']} warning(s), {s['info']} info</p>"
    if not rows:
        return head + "<p><em>(no issues)</em></p>"
    return (
        head
        + "<table><thead><tr><th>severity</th><th>field</th><th>message</th><th>fix</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 980px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #222; }
h1 { border-bottom: 2px solid #444; padding-bottom: .25rem; }
h2 { margin-top: 2.2rem; border-bottom: 1px solid #ccc; padding-bottom: .15rem; }
section { margin-bottom: 1rem; }
details { margin: .5rem 0; padding: .5rem .75rem; background: #f6f6f8; border-radius: 6px; }
summary { cursor: pointer; font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin: .5rem 0; }
th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #eee; vertical-align: top; }
th { background: #f0f0f3; font-weight: 600; }
table.kv th { width: 18%; }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; background: #fafafa; padding: .5rem; border-radius: 4px; font-size: .85em; }
code { background: #fafafa; padding: 0 .2rem; border-radius: 3px; font-size: .9em; }
tr.error td { background: #fff0f0; }
tr.warning td { background: #fff8e0; }
tr.info td { background: #f0f4ff; }
.err { color: #b00020; }
"""


def render(plugin_root: Path) -> str:
    plugin_root = plugin_root.resolve()
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    title = manifest.get("name") or plugin_root.name

    parts = [
        f"<!doctype html><html><head><meta charset='utf-8'><title>Plugin: {_h(title)}</title>",
        f"<style>{CSS}</style></head><body>",
        f"<h1>Plugin: {_h(title)}</h1>",
        f"<p><strong>Path:</strong> <code>{_h(plugin_root)}</code></p>",
    ]

    parts.append(_section("Manifest", _kv_table(manifest) if manifest else "<p><em>(no manifest)</em></p>"))
    parts.append(_section("Component summary", _component_summary(plugin_root)))
    parts.append(_section("Skills", _skills_section(plugin_root)))
    parts.append(_section("Agents", _agents_section(plugin_root)))
    parts.append(_section("Hooks", _hooks_section(plugin_root)))
    parts.append(_section("MCP servers", _mcp_section(plugin_root)))
    parts.append(_section("LSP servers", _lsp_section(plugin_root)))
    parts.append(_section("Monitors", _monitors_section(plugin_root)))
    parts.append(_section("Themes", _themes_section(plugin_root)))
    parts.append(_section("Validation", _validation_section(plugin_root)))
    parts.append("</body></html>")

    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate a static HTML overview of a plugin.")
    p.add_argument("plugin_root", type=Path)
    p.add_argument("--output", type=Path, required=True, help="Path for the HTML file.")
    args = p.parse_args(argv)

    html_text = render(args.plugin_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(f"✅ Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
