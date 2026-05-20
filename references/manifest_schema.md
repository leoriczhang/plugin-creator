# Manifest Schema (`.claude-plugin/plugin.json`)

Authoritative reference: <https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema>

The manifest is **optional**. If omitted, Claude Code auto-discovers components in their default locations and derives the plugin's name from the directory name. Use a manifest when you need to provide metadata or custom component paths.

## Complete schema

```json
{
  "name": "plugin-name",
  "displayName": "Plugin Name",
  "version": "1.2.0",
  "description": "Brief plugin description",
  "author": {
    "name": "Author Name",
    "email": "author@example.com",
    "url": "https://github.com/author"
  },
  "homepage": "https://docs.example.com/plugin",
  "repository": "https://github.com/author/plugin",
  "license": "MIT",
  "keywords": ["keyword1", "keyword2"],
  "skills": "./custom/skills/",
  "commands": ["./custom/commands/special.md"],
  "agents": ["./custom/agents/reviewer.md"],
  "hooks": "./config/hooks.json",
  "mcpServers": { "...": { } },
  "lspServers": { "...": { } },
  "experimental": {
    "monitors": "./config/monitors.json",
    "themes": "./themes/"
  }
}
```

## Required fields

| Field | Required | Notes |
|---|---|---|
| `name` | yes | kebab-case, ≤ 64 chars, unique within marketplace |

`version` is *technically* optional but every distributed plugin needs it.

## Metadata fields

| Field | Type | Notes |
|---|---|---|
| `displayName` | string | Human-readable name (rendered in `/plugin` UI) |
| `version` | string | SemVer: `MAJOR.MINOR.PATCH` with optional `-prerelease` and `+build` |
| `description` | string | One sentence; aim for ≤ 200 chars; no `<` or `>` |
| `author.name` | string | Required when `author` is set |
| `author.email` | string | Optional |
| `author.url` | string | Optional, must be `http(s)://...` |
| `homepage` | URL | Project homepage |
| `repository` | URL | Source repository (often the same as the install URL) |
| `license` | SPDX | `MIT`, `Apache-2.0`, `BSD-3-Clause`, etc. |
| `keywords` | string[] | Each ≤ 50 chars; aids marketplace discovery |

## Component path fields

These fields override the default paths. All paths are resolved **relative to the plugin root**. Path traversal (`../`) outside the plugin root is rejected.

| Field | Default | Type |
|---|---|---|
| `skills` | `./skills/` and `./commands/` | string (dir) or string[] (files/dirs) |
| `commands` | `./commands/` | string (dir) or string[] |
| `agents` | `./agents/` | string (dir) or string[] |
| `hooks` | `./hooks/hooks.json` | string (path) or inline object `{ "hooks": { ... } }` |
| `mcpServers` | `./.mcp.json` | inline object |
| `lspServers` | `./.lsp.json` | inline object |
| `experimental.monitors` | `./monitors/monitors.json` | string (path) or inline array |
| `experimental.themes` | `./themes/` | string (dir) |

## Experimental components

Wrap experimental fields under `experimental` so the parser knows to load them with the experimental loader. Currently:

- `experimental.monitors` — declares background monitors (v2.1.105+)
- `experimental.themes` — declares custom themes

Both can be either a path string (for non-default locations) or an inline value.

## Path behavior rules

- Absolute paths in component fields are **rejected**.
- A path that resolves outside the plugin root via `..` is **rejected**.
- Within a marketplace, plugins MAY share files via symlinks; the symlink target must still resolve inside the marketplace.

## Cross-checks the validator runs

- `name` matches the plugin's directory basename (warn if mismatched).
- If `mcpServers` is declared inline AND `.mcp.json` exists, both are loaded — warn about ambiguity.
- Same for `lspServers` ↔ `.lsp.json` and `hooks` ↔ `hooks/hooks.json`.
- Marketplace mode requires: `version`, `description`, `repository`, `homepage`, `license`, `keywords`, `author.name`.

## Common mistakes

- Trailing commas in the JSON (most editors flag these; the parser doesn't).
- Comments in the JSON (`//` or `/* */`) — JSON has none.
- Smart quotes (curly `"`/`'`) instead of straight quotes when copy-pasting from docs.
- Setting `author` to a string instead of an object.
- Using `version: 1.0` instead of `1.0.0` — must be three components.
