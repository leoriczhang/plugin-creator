# `claude plugin` CLI Commands

Authoritative reference: <https://code.claude.com/docs/en/plugins-reference#cli-commands-reference>

These are the commands a plugin author or installer typically runs. The `plugin-creator` skill recommends them in its workflow output.

---

## `claude plugin install <source>`

Install a plugin.

```bash
claude plugin install ./my-plugin                   # local path
claude plugin install https://github.com/x/p.git    # git repo
claude plugin install x/p                           # marketplace handle
claude plugin install x/p@1.2.0                     # pinned version
```

**Flags:**

| Flag | Effect |
|---|---|
| `--scope user\|project\|local\|managed` | Where to install (default `user`) |
| `--enable` | Install AND enable in one step (default behavior) |
| `--no-enable` | Install but leave disabled |
| `--from-marketplace <name>` | Force a specific marketplace as the source |

---

## `claude plugin uninstall <name>`

Remove a plugin from the current scope.

```bash
claude plugin uninstall my-plugin
claude plugin uninstall my-plugin --scope project
```

---

## `claude plugin prune`

Remove orphaned plugin data — `${CLAUDE_PLUGIN_DATA}` directories whose owning plugin is no longer installed.

```bash
claude plugin prune
claude plugin prune --dry-run
```

---

## `claude plugin enable <name>` / `claude plugin disable <name>`

Toggle without uninstalling.

```bash
claude plugin disable noisy-plugin
claude plugin enable  noisy-plugin
```

Disabling a plugin mid-session does NOT stop monitors that are already running — they stop at session end.

---

## `claude plugin update <name>[@version]`

Upgrade to the latest published version, or pin a specific version.

```bash
claude plugin update my-plugin            # latest
claude plugin update my-plugin@1.2.0      # pinned
claude plugin update --all                # all installed plugins
```

`update` also re-runs the install hooks if the plugin declares any.

---

## `claude plugin list`

List installed plugins. Useful for verifying scope and version.

```bash
claude plugin list
claude plugin list --scope project
claude plugin list --json
```

---

## `claude plugin details <name>`

Show full metadata, declared components, and runtime errors (e.g., MCP servers that failed to start, missing LSP binaries).

```bash
claude plugin details my-plugin
```

The "Errors" tab in the `/plugin` UI shows the same data interactively.

---

## `claude plugin tag <name> <tag>`

For marketplace publishers — manage symbolic version tags (`latest`, `beta`, `stable`).

```bash
claude plugin tag my-plugin latest
claude plugin tag my-plugin beta
claude plugin tag my-plugin --remove unstable
```

Symbolic tags resolve at install time: `claude plugin install x/y@latest` follows the tag.

---

## Useful one-liners

```bash
# Reinstall after editing locally
claude plugin uninstall my-plugin && claude plugin install ./my-plugin

# Force a clean reload mid-session
claude plugin disable my-plugin && claude plugin enable my-plugin

# Inspect what a marketplace plugin would install
claude plugin details x/y --remote

# Validate before committing (uses this skill's validator)
python -m scripts.validate_plugin ./my-plugin
```
