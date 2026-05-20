#!/usr/bin/env python3
"""
Bump a plugin's version following SemVer rules.

Usage:
    python -m scripts.bump_version <plugin-root> <major|minor|patch|set:X.Y.Z>

Examples:
    python -m scripts.bump_version ./my-plugin patch       # 1.2.3 -> 1.2.4
    python -m scripts.bump_version ./my-plugin minor       # 1.2.3 -> 1.3.0
    python -m scripts.bump_version ./my-plugin major       # 1.2.3 -> 2.0.0
    python -m scripts.bump_version ./my-plugin set:2.0.0-beta.1
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from scripts.utils import is_semver, parse_semver, read_json, write_json


def bump(plugin_root: Path, command: str) -> tuple[str, str]:
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise SystemExit("manifest must be an object")
    current = manifest.get("version") or "0.0.0"
    if not is_semver(current):
        raise SystemExit(f"current version {current!r} is not SemVer; aborting")

    if command in ("major", "minor", "patch"):
        major, minor, patch, _pre, _build = parse_semver(current)
        if command == "major":
            major, minor, patch = major + 1, 0, 0
        elif command == "minor":
            major, minor, patch = major, minor + 1, 0
        else:
            major, minor, patch = major, minor, patch + 1
        new_version = f"{major}.{minor}.{patch}"
    elif command.startswith("set:"):
        new_version = command[4:]
        if not is_semver(new_version):
            raise SystemExit(f"target {new_version!r} is not SemVer")
    else:
        raise SystemExit(f"unknown bump command: {command!r}")

    manifest["version"] = new_version
    write_json(manifest_path, manifest)

    # Touch CHANGELOG.md if it exists
    changelog = plugin_root / "CHANGELOG.md"
    if changelog.exists():
        old = changelog.read_text(encoding="utf-8")
        today = date.today().isoformat()
        header = f"## [{new_version}] - {today}\n\n- (describe the change)\n\n"
        if old.startswith("# Changelog\n"):
            new = "# Changelog\n\n" + header + old[len("# Changelog\n") :].lstrip("\n")
        else:
            new = "# Changelog\n\n" + header + old
        changelog.write_text(new, encoding="utf-8")

    return current, new_version


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bump a plugin's version.")
    p.add_argument("plugin_root", type=Path)
    p.add_argument("command", help="One of: major, minor, patch, set:X.Y.Z")
    args = p.parse_args(argv)

    old, new = bump(args.plugin_root, args.command)
    print(f"✅ {old} → {new}")
    print(
        "Don't forget to commit and tag this version before publishing:\n"
        f"  git commit -am 'bump version to {new}'\n"
        f"  git tag v{new}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
