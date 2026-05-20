#!/usr/bin/env python3
"""
Scaffold a fresh Claude Code plugin tree.

Usage:
    python -m scripts.scaffold_plugin <output-dir>/<plugin-name> \
      --name <plugin-name> \
      --version 0.1.0 \
      --description "<one-liner>" \
      --author "Author Name" \
      [--license MIT] \
      [--components skills,agents,hooks,mcpServers]

If --components is omitted, only `skills` is created plus a manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.utils import is_kebab_case, is_semver, write_json

VALID_COMPONENTS = {
    "skills",
    "commands",
    "agents",
    "hooks",
    "mcpServers",
    "lspServers",
    "monitors",
    "themes",
}


README_TEMPLATE = """# {name}

{description}

## Install

```bash
claude plugin install <path-or-git-url>
```

## Components shipped

{components_list}

## Version

`{version}` — see [CHANGELOG.md](./CHANGELOG.md) (or commit log) for details.
"""


def _components_list(components: set[str]) -> str:
    if not components:
        return "(none yet — add components and bump the version)"
    return "\n".join(f"- `{c}`" for c in sorted(components))


def scaffold(
    plugin_root: Path,
    name: str,
    version: str,
    description: str,
    author: str,
    license_id: str | None,
    components: set[str],
) -> None:
    if not is_kebab_case(name):
        raise SystemExit(f"name must be kebab-case, got: {name!r}")
    if not is_semver(version):
        raise SystemExit(f"version must be SemVer, got: {version!r}")
    bad = components - VALID_COMPONENTS
    if bad:
        raise SystemExit(f"unknown components: {', '.join(sorted(bad))}")

    plugin_root.mkdir(parents=True, exist_ok=True)

    # Manifest
    manifest = {
        "name": name,
        "version": version,
        "description": description,
        "author": {"name": author},
    }
    if license_id:
        manifest["license"] = license_id

    write_json(plugin_root / ".claude-plugin" / "plugin.json", manifest)

    # Per-component scaffolding
    if "skills" in components:
        (plugin_root / "skills").mkdir(exist_ok=True)
        # Drop a .gitkeep so empty dirs survive in git
        (plugin_root / "skills" / ".gitkeep").touch()

    if "commands" in components:
        (plugin_root / "commands").mkdir(exist_ok=True)
        (plugin_root / "commands" / ".gitkeep").touch()

    if "agents" in components:
        (plugin_root / "agents").mkdir(exist_ok=True)
        (plugin_root / "agents" / ".gitkeep").touch()

    if "hooks" in components:
        write_json(plugin_root / "hooks" / "hooks.json", {"hooks": {}})

    if "mcpServers" in components:
        write_json(plugin_root / ".mcp.json", {"mcpServers": {}})

    if "lspServers" in components:
        write_json(plugin_root / ".lsp.json", {})

    if "monitors" in components:
        write_json(plugin_root / "monitors" / "monitors.json", [])

    if "themes" in components:
        (plugin_root / "themes").mkdir(exist_ok=True)
        (plugin_root / "themes" / ".gitkeep").touch()

    # README
    (plugin_root / "README.md").write_text(
        README_TEMPLATE.format(
            name=name,
            description=description or "(add a one-line description)",
            components_list=_components_list(components),
            version=version,
        ),
        encoding="utf-8",
    )

    # CHANGELOG seed
    (plugin_root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [{version}] - initial scaffold\n\n- Created plugin skeleton.\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scaffold a fresh Claude Code plugin tree.")
    p.add_argument("plugin_root", type=Path, help="Output directory for the plugin.")
    p.add_argument("--name", required=True)
    p.add_argument("--version", default="0.1.0")
    p.add_argument("--description", default="")
    p.add_argument("--author", required=True)
    p.add_argument("--license", dest="license_id", default=None)
    p.add_argument(
        "--components",
        default="skills",
        help=f"Comma-separated subset of: {','.join(sorted(VALID_COMPONENTS))}",
    )
    args = p.parse_args(argv)

    components = {c.strip() for c in args.components.split(",") if c.strip()}

    scaffold(
        plugin_root=args.plugin_root,
        name=args.name,
        version=args.version,
        description=args.description,
        author=args.author,
        license_id=args.license_id,
        components=components,
    )
    print(f"✅ Scaffolded plugin at {args.plugin_root}")
    print("Next steps:")
    print(f"  python -m scripts.add_component {args.plugin_root} --kind skill --name <skill-name> --description '...'")
    print(f"  python -m scripts.validate_plugin {args.plugin_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
