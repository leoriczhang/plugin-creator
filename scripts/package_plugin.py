#!/usr/bin/env python3
"""
Package a plugin into a distributable .zip.

Usage:
    python -m scripts.package_plugin <plugin-root> [--output <dir>] [--skip-validate]

The output is `<plugin-name>-<version>.zip` in <dir> (defaults to cwd).

Validation runs first; packaging refuses on errors unless --skip-validate is passed.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from pathlib import Path

from scripts.utils import read_json
from scripts.validate_plugin import validate_plugin

EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".idea", ".vscode"}
EXCLUDE_GLOBS = {"*.pyc", "*.pyo", "*.swp", "*.swo"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}


def should_exclude(rel_path: Path) -> bool:
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def package(plugin_root: Path, output_dir: Path, skip_validate: bool = False) -> Path | None:
    plugin_root = plugin_root.resolve()
    if not plugin_root.is_dir():
        raise SystemExit(f"not a directory: {plugin_root}")

    if not skip_validate:
        print("🔍 Validating plugin...")
        report = validate_plugin(plugin_root)
        if not report.ok:
            print("❌ Validation failed. Fix errors before packaging:")
            for issue in report.errors:
                print(f"   [{issue.field}] {issue.message}")
            print("Use --skip-validate to package anyway (not recommended).")
            return None
        if report.warnings:
            print(f"⚠️  {len(report.warnings)} warning(s) — packaging anyway.")
        print("✅ Validation passed.\n")

    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        name = manifest.get("name") or plugin_root.name
        version = manifest.get("version") or "0.0.0"
    else:
        name = plugin_root.name
        version = "0.0.0"

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{name}-{version}.zip"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in plugin_root.rglob("*"):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(plugin_root.parent)
            rel_for_check = file_path.relative_to(plugin_root)
            if should_exclude(rel_for_check):
                print(f"  skipped: {arcname}")
                continue
            zf.write(file_path, arcname)
            print(f"  added:   {arcname}")

    print(f"\n✅ Packaged to: {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Package a Claude Code plugin into a .zip.")
    p.add_argument("plugin_root", type=Path)
    p.add_argument("--output", type=Path, default=Path.cwd(), help="Output directory.")
    p.add_argument("--skip-validate", action="store_true", help="Skip validation (not recommended).")
    args = p.parse_args(argv)

    out = package(args.plugin_root, args.output, args.skip_validate)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
