# Version Management

Authoritative reference: <https://code.claude.com/docs/en/plugins-reference#version-management>

Plugins follow **Semantic Versioning** (`MAJOR.MINOR.PATCH`, with optional `-prerelease` and `+build` metadata). The `version` field in `.claude-plugin/plugin.json` is the single source of truth — `claude plugin update` compares it against the marketplace's published versions.

---

## When to bump each part

### MAJOR — `1.x.x → 2.0.0`

Bump MAJOR for **breaking changes** that could surprise existing users. Examples:

- Renaming or removing a skill, command, or agent
- Removing a hook event or matcher that users may have grown to depend on
- Removing or renaming an MCP/LSP server entry (changes the available tools)
- Changing a `user_config` key (breaks existing user configurations)
- Restructuring the manifest in a way that older Claude Code versions can't parse
- Changing default behavior of a hook (e.g., `PreToolUse` now blocks instead of warning)

### MINOR — `1.2.x → 1.3.0`

Bump MINOR for **additive, backwards-compatible features**:

- Adding a new skill, command, agent, monitor, or theme
- Adding a new optional manifest field
- Adding a new hook to a previously-empty event (no overlap with existing matchers)
- Adding new MCP/LSP capabilities

### PATCH — `1.2.3 → 1.2.4`

Bump PATCH for **fixes that don't change the public surface**:

- Wording tweaks in a skill description (unless they materially change triggering)
- Bugfixes in a script that didn't change its CLI
- Documentation edits
- Internal refactors invisible to users

### Pre-release tags — `2.0.0-beta.1`

Use prerelease segments for unstable iterations:

```
0.9.0
1.0.0-alpha.1
1.0.0-alpha.2
1.0.0-beta.1
1.0.0-rc.1
1.0.0
```

Prereleases never auto-update from non-prerelease versions.

---

## The cardinal rule

> **Never re-publish an existing version with different content.**

If you've already pushed `1.2.0` and you find a typo, ship `1.2.1`. Re-publishing breaks marketplace caches, confuses installed users, and silently lies to anyone who reads the changelog. The `bump_version.py` script enforces this by always advancing the version.

---

## Bumping with `bump_version.py`

```bash
python -m scripts.bump_version <plugin-root> patch     # 1.2.3 → 1.2.4
python -m scripts.bump_version <plugin-root> minor     # 1.2.3 → 1.3.0
python -m scripts.bump_version <plugin-root> major     # 1.2.3 → 2.0.0
python -m scripts.bump_version <plugin-root> set:1.0.0-beta.1
```

The script also seeds a new entry in `CHANGELOG.md` if the file exists.

---

## Marketplace tags

For marketplace publishers, **tags** are symbolic names that resolve to a specific version at install time:

```bash
claude plugin tag my-plugin latest
claude plugin tag my-plugin stable
claude plugin tag my-plugin beta
```

Common tagging strategy:

| Tag | Meaning |
|---|---|
| `latest` | Newest non-prerelease |
| `stable` | Curated; only after soak time |
| `beta` | Latest prerelease |
| `<major>.x` | Latest within a major (e.g. `1.x` → `1.6.3`) |

Users can pin to tags or to specific versions:

```bash
claude plugin install x/p@latest
claude plugin install x/p@beta
claude plugin install x/p@1.2.0
```

A pinned `@1.2.0` won't auto-update; a pinned `@latest` follows the tag.

---

## CHANGELOG conventions

Maintain a `CHANGELOG.md` at the plugin root with reverse-chronological entries:

```markdown
# Changelog

## [1.3.0] - 2026-04-01

- Added `redact-pii` skill.
- Improved `pdf-extract` table detection on multi-column layouts.

## [1.2.1] - 2026-03-22

- Fixed `format-code` hook crash when working in subdirectories.
```

`bump_version.py` seeds these entries. Fill in the bullet points before committing.

---

## Pre-publish checklist

Before pushing a new version:

1. Run the validator: `python -m scripts.validate_plugin <plugin-root>` — must be 0 errors.
2. Bump the version.
3. Update the CHANGELOG.
4. Commit with a message that includes the version: `git commit -am "release v1.3.0"`.
5. Tag: `git tag v1.3.0`.
6. Push: `git push --follow-tags`.
7. (Marketplace) Update the marketplace tag if applicable: `claude plugin tag my-plugin latest`.

The plugin-analyzer subagent's `recommended_bump` field is a good sanity check — if you think you're shipping a `patch` but the analyzer says `major`, double-check you haven't accidentally introduced a breaking change.
