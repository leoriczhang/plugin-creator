# Component Layouts and Field Rules

Authoritative reference: <https://code.claude.com/docs/en/plugins-reference#plugin-components-reference>

This file is the canonical guide the `component-author` subagent and the `add_component.py` script reach for. When in doubt, prefer the templates here verbatim.

---

## Skill

**Location:** `skills/<skill-name>/SKILL.md` (or a single `SKILL.md` at plugin root for one-skill plugins)
**Companion files:** `reference.md`, `scripts/`, `assets/` are all permitted alongside `SKILL.md`.

```markdown
---
name: pdf-extract
description: Extract structured tables from PDF files. Invoke when the user has a PDF and wants tabular data, mentions "extract tables from PDF", or pastes PDF content.
---

# /pdf-extract

Extract tabular data from PDF documents using `scripts/extract.py`.

## Process

1. Read the input PDF.
2. Run `scripts/extract.py <input>.pdf`.
3. Verify the resulting CSV is non-empty and has the expected columns.

## Examples

Input: `Q4_sales.pdf`
Output: `Q4_sales.csv` with columns `region, product, units, revenue`.
```

**Rules:**

- Frontmatter MUST contain `name` (kebab-case) and `description`.
- `description` MUST cover BOTH "what it does" AND "when to invoke it".
- The directory name should match the frontmatter `name`.
- Keep `SKILL.md` under ~500 lines; push large content into `reference.md`.

---

## Command

**Location:** `commands/<command-name>.md`
A command is a simple markdown file (no frontmatter required) that runs as `/command-name`.

```markdown
# /sync-deps

Sync this project's dependencies after pulling main.

Run:
1. `git fetch origin && git pull --rebase`
2. `npm ci` (or `pip install -r requirements.txt`)
3. `npm run build` if a build script is defined
```

For dynamic commands (with arguments), prefer authoring a skill instead.

---

## Agent

**Location:** `agents/<agent-name>.md`

```markdown
---
name: pdf-reviewer
description: Reviews PDFs for redaction completeness. Invoke after a redaction skill produces output.
model: sonnet
effort: medium
maxTurns: 20
disallowedTools: Write, Edit
---

You are a PDF redaction reviewer. Your job is to read the redacted PDF and verify that no PII remains in the rendered text or in the embedded text layer.

## Process

1. Open the redacted PDF.
2. Extract its text layer.
3. Search for common PII patterns: SSNs, phone numbers, emails, full names from the source.
4. Report any matches with page and offset.
```

**Allowed frontmatter fields:** `name`, `description`, `model`, `effort`, `maxTurns`, `tools`, `disallowedTools`, `skills`, `memory`, `background`, `isolation` (only `"worktree"`).

**FORBIDDEN frontmatter for plugin-shipped agents:** `hooks`, `mcpServers`, `permissionMode` (security restriction).

---

## Hook

**Location:** `hooks/hooks.json` OR inline under `hooks` in `plugin.json`.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}\"/scripts/format-code.sh"
          }
        ]
      }
    ]
  }
}
```

**Top-level shape:** `{ "hooks": { "<EventName>": [ <matcher_entry>, ... ] } }`

**Matcher entry shape:** `{ "matcher": "<regex>", "hooks": [ <action>, ... ] }` (matcher is optional).

**Action types:**

| `type` | Required fields |
|---|---|
| `command` | `command` (shell string) |
| `http` | `url` |
| `mcp_tool` | `tool` |
| `prompt` | `prompt` |
| `agent` | `agent` |

**Always quote `${CLAUDE_PLUGIN_ROOT}`** in shell commands so paths with spaces work:

```
"\"${CLAUDE_PLUGIN_ROOT}\"/scripts/foo.sh"
```

For the full event catalog, see `hooks_events.md`.

---

## MCP Server

**Location:** `.mcp.json` OR inline `mcpServers` in `plugin.json`.

```json
{
  "mcpServers": {
    "plugin-database": {
      "command": "${CLAUDE_PLUGIN_ROOT}/servers/db-server",
      "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"],
      "env": {
        "DB_PATH": "${CLAUDE_PLUGIN_ROOT}/data"
      }
    },
    "plugin-api-client": {
      "command": "npx",
      "args": ["@company/mcp-server", "--plugin-mode"],
      "cwd": "${CLAUDE_PLUGIN_ROOT}"
    }
  }
}
```

**Required:** `command` for each server.
**Optional:** `args` (string[]), `env` (object), `cwd` (string).

The MCP server starts automatically when the plugin is enabled.

---

## LSP Server

**Location:** `.lsp.json` OR inline `lspServers` in `plugin.json`.

```json
{
  "go": {
    "command": "gopls",
    "args": ["serve"],
    "extensionToLanguage": { ".go": "go" }
  }
}
```

**Required:** `command`, `extensionToLanguage`.

**Optional:**

| Field | Notes |
|---|---|
| `args` | Command-line arguments |
| `transport` | `stdio` (default) or `socket` |
| `env` | Environment variables |
| `initializationOptions` | LSP `initializationOptions` |
| `settings` | Sent via `workspace/didChangeConfiguration` |
| `workspaceFolder` | Workspace folder path |
| `startupTimeout` | ms |
| `shutdownTimeout` | ms |
| `restartOnCrash` | bool |
| `maxRestarts` | int |

**Important:** the LSP binary is NOT bundled by the plugin. Document the install command in the README.

---

## Monitor (experimental, v2.1.105+)

**Location:** `monitors/monitors.json` OR inline `experimental.monitors` in `plugin.json`.

```json
[
  {
    "name": "deploy-status",
    "command": "\"${CLAUDE_PLUGIN_ROOT}\"/scripts/poll-deploy.sh ${user_config.api_endpoint}",
    "description": "Deployment status changes"
  },
  {
    "name": "error-log",
    "command": "tail -F ./logs/error.log",
    "description": "Application error log",
    "when": "on-skill-invoke:debug"
  }
]
```

**Required:** `name`, `command`, `description`.
**Optional:** `when` — `"always"` (default) or `"on-skill-invoke:<skill-name>"`.

Monitor `name` MUST be unique per plugin. Disabling a plugin mid-session does NOT stop a running monitor.

---

## Theme (experimental)

**Location:** `themes/<theme-name>.json`.

```json
{
  "name": "Dracula",
  "base": "dark",
  "overrides": {
    "claude": "#bd93f9",
    "error": "#ff5555",
    "success": "#50fa7b"
  }
}
```

**Required:** `name`, `base` (one of the built-in presets).
**Optional:** `overrides` — sparse map of color tokens.

Themes are read-only as shipped; users press `Ctrl+E` in `/theme` to fork into `~/.claude/themes/`.

---

## Environment variables in component configs

These can appear inside any `command`/`args`/`env` value:

| Variable | Meaning |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}` | Absolute path to the plugin's root directory |
| `${CLAUDE_PLUGIN_DATA}` | Persistent data directory (created on first install) |
| `${CLAUDE_PROJECT_DIR}` | Current project working directory |
| `${user_config.<key>}` | A value from the user's plugin configuration |
| `${ENV_VAR}` | Any host environment variable |

Always quote `${CLAUDE_PLUGIN_ROOT}` when embedding in a shell string to handle spaces in paths.
