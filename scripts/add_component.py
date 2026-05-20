#!/usr/bin/env python3
"""
Add one component to an existing plugin.

Usage:
    python -m scripts.add_component <plugin-root> \
      --kind skill --name pdf-extract --description "Extract PDF tables. Invoke when ..."

Supported kinds:
    skill     -> skills/<name>/SKILL.md
    command   -> commands/<name>.md
    agent     -> agents/<name>.md
    hook      -> append to hooks/hooks.json (requires --event and --command)
    mcp       -> append to .mcp.json (requires --command)
    lsp       -> append to .lsp.json (requires --command and --extension)
    monitor   -> append to monitors/monitors.json (requires --command and --description)
    theme     -> themes/<name>.json (requires --base)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.utils import (
    ALLOWED_HOOK_EVENTS,
    is_kebab_case,
    read_json,
    write_json,
)


def add_skill(plugin_root: Path, name: str, description: str) -> Path:
    if not is_kebab_case(name):
        raise SystemExit(f"skill name must be kebab-case, got: {name!r}")
    skill_dir = plugin_root / "skills" / name
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        raise SystemExit(f"already exists: {skill_md}")
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        f"""---
name: {name}
description: {description}
---

# /{name}

{description}

## Process

1. (describe the steps the skill should take)
""",
        encoding="utf-8",
    )
    return skill_md


def add_command(plugin_root: Path, name: str, description: str) -> Path:
    if not is_kebab_case(name):
        raise SystemExit(f"command name must be kebab-case, got: {name!r}")
    commands_dir = plugin_root / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    cmd_md = commands_dir / f"{name}.md"
    if cmd_md.exists():
        raise SystemExit(f"already exists: {cmd_md}")
    cmd_md.write_text(
        f"# /{name}\n\n{description}\n",
        encoding="utf-8",
    )
    return cmd_md


def add_agent(plugin_root: Path, name: str, description: str) -> Path:
    if not is_kebab_case(name):
        raise SystemExit(f"agent name must be kebab-case, got: {name!r}")
    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agents_dir / f"{name}.md"
    if agent_md.exists():
        raise SystemExit(f"already exists: {agent_md}")
    agent_md.write_text(
        f"""---
name: {name}
description: {description}
---

You are the {name} subagent. {description}

## Process

1. (describe the agent's behavior)
""",
        encoding="utf-8",
    )
    return agent_md


def add_hook(
    plugin_root: Path,
    event: str,
    command: str,
    matcher: str | None = None,
) -> Path:
    if event not in ALLOWED_HOOK_EVENTS:
        raise SystemExit(f"unknown hook event: {event!r}")
    hooks_path = plugin_root / "hooks" / "hooks.json"
    if hooks_path.exists():
        data = read_json(hooks_path)
    else:
        data = {"hooks": {}}
    data.setdefault("hooks", {}).setdefault(event, [])
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        entry["matcher"] = matcher
    data["hooks"][event].append(entry)
    write_json(hooks_path, data)
    return hooks_path


def add_mcp(
    plugin_root: Path,
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    mcp_path = plugin_root / ".mcp.json"
    if mcp_path.exists():
        data = read_json(mcp_path)
    else:
        data = {"mcpServers": {}}
    if name in data.get("mcpServers", {}):
        raise SystemExit(f"mcp server '{name}' already declared")
    cfg: dict = {"command": command}
    if args:
        cfg["args"] = args
    if env:
        cfg["env"] = env
    data.setdefault("mcpServers", {})[name] = cfg
    write_json(mcp_path, data)
    return mcp_path


def add_lsp(
    plugin_root: Path,
    name: str,
    command: str,
    extension_to_language: dict[str, str],
    args: list[str] | None = None,
) -> Path:
    lsp_path = plugin_root / ".lsp.json"
    if lsp_path.exists():
        data = read_json(lsp_path)
    else:
        data = {}
    if name in data:
        raise SystemExit(f"lsp server '{name}' already declared")
    cfg: dict = {"command": command, "extensionToLanguage": extension_to_language}
    if args:
        cfg["args"] = args
    data[name] = cfg
    write_json(lsp_path, data)
    return lsp_path


def add_monitor(
    plugin_root: Path,
    name: str,
    command: str,
    description: str,
    when: str | None = None,
) -> Path:
    monitors_path = plugin_root / "monitors" / "monitors.json"
    if monitors_path.exists():
        data = read_json(monitors_path)
    else:
        data = []
    if not isinstance(data, list):
        raise SystemExit(f"{monitors_path} must be a JSON array")
    if any(m.get("name") == name for m in data):
        raise SystemExit(f"monitor '{name}' already exists")
    entry: dict = {"name": name, "command": command, "description": description}
    if when:
        entry["when"] = when
    data.append(entry)
    write_json(monitors_path, data)
    return monitors_path


def add_theme(
    plugin_root: Path,
    name: str,
    base: str,
    overrides: dict[str, str] | None = None,
) -> Path:
    themes_dir = plugin_root / "themes"
    themes_dir.mkdir(parents=True, exist_ok=True)
    theme_path = themes_dir / f"{name}.json"
    if theme_path.exists():
        raise SystemExit(f"already exists: {theme_path}")
    write_json(theme_path, {"name": name, "base": base, "overrides": overrides or {}})
    return theme_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Add a single component to a plugin.")
    p.add_argument("plugin_root", type=Path)
    p.add_argument(
        "--kind",
        required=True,
        choices=["skill", "command", "agent", "hook", "mcp", "lsp", "monitor", "theme"],
    )
    p.add_argument("--name", required=False, help="Component name (skill/agent/command/mcp/lsp/monitor/theme).")
    p.add_argument("--description", default="")
    p.add_argument("--event", help="Hook event (e.g. PostToolUse).")
    p.add_argument("--matcher", help="Hook matcher regex (optional).")
    p.add_argument("--command", help="Command for hook/mcp/lsp/monitor.")
    p.add_argument("--args", help="JSON array of args (for mcp/lsp).")
    p.add_argument("--env", help="JSON object of env vars (for mcp).")
    p.add_argument("--extension", help="JSON object mapping extensions to languages (for lsp).")
    p.add_argument("--when", help="Monitor `when` value.")
    p.add_argument("--base", help="Theme base preset.")
    p.add_argument("--overrides", help="Theme overrides as JSON object.")
    args = p.parse_args(argv)

    root = args.plugin_root.resolve()
    if not (root / ".claude-plugin" / "plugin.json").exists() and not root.is_dir():
        raise SystemExit(f"not a plugin directory: {root}")

    if args.kind == "skill":
        if not args.name or not args.description:
            raise SystemExit("--name and --description are required for skill")
        path = add_skill(root, args.name, args.description)
    elif args.kind == "command":
        if not args.name or not args.description:
            raise SystemExit("--name and --description are required for command")
        path = add_command(root, args.name, args.description)
    elif args.kind == "agent":
        if not args.name or not args.description:
            raise SystemExit("--name and --description are required for agent")
        path = add_agent(root, args.name, args.description)
    elif args.kind == "hook":
        if not args.event or not args.command:
            raise SystemExit("--event and --command are required for hook")
        path = add_hook(root, args.event, args.command, args.matcher)
    elif args.kind == "mcp":
        if not args.name or not args.command:
            raise SystemExit("--name and --command are required for mcp")
        args_list = json.loads(args.args) if args.args else None
        env_map = json.loads(args.env) if args.env else None
        path = add_mcp(root, args.name, args.command, args_list, env_map)
    elif args.kind == "lsp":
        if not args.name or not args.command or not args.extension:
            raise SystemExit("--name, --command, --extension are required for lsp")
        ext = json.loads(args.extension)
        args_list = json.loads(args.args) if args.args else None
        path = add_lsp(root, args.name, args.command, ext, args_list)
    elif args.kind == "monitor":
        if not args.name or not args.command or not args.description:
            raise SystemExit("--name, --command, --description are required for monitor")
        path = add_monitor(root, args.name, args.command, args.description, args.when)
    elif args.kind == "theme":
        if not args.name or not args.base:
            raise SystemExit("--name and --base are required for theme")
        overrides = json.loads(args.overrides) if args.overrides else None
        path = add_theme(root, args.name, args.base, overrides)
    else:
        raise SystemExit(f"unknown kind: {args.kind}")

    print(f"✅ Added {args.kind}: {path}")
    print("Next steps:")
    print(f"  python -m scripts.validate_plugin {root}")
    print(f"  python -m scripts.bump_version {root} minor   # if this is a new feature")
    return 0


if __name__ == "__main__":
    sys.exit(main())
