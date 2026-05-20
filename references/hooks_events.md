# Hook Events

Authoritative reference: <https://code.claude.com/docs/en/plugins-reference#hooks> and <https://code.claude.com/docs/en/hooks>

This is the complete catalog of events a plugin's `hooks/hooks.json` may handle. Each row lists when the event fires and what the hook can do with it.

| Event | Fires when | Useful for |
|---|---|---|
| `SessionStart` | A session begins or resumes | Loading session-wide state, registering ephemeral tools |
| `Setup` | `--init-only`, or `--init`/`--maintenance` in `-p` mode | One-time CI/script setup |
| `UserPromptSubmit` | User submits a prompt, before Claude processes it | Logging, quick rewriting, gating |
| `UserPromptExpansion` | A user-typed command expands into a prompt | Block or transform expansions |
| `PreToolUse` | Before a tool call executes | Block tool calls, inject context |
| `PermissionRequest` | A permission dialog appears | Augment dialogs, auto-approve in CI |
| `PermissionDenied` | Tool call denied by auto-mode classifier | Return `{retry: true}` to allow retry |
| `PostToolUse` | After a tool call succeeds | Format code, run linters, log |
| `PostToolUseFailure` | After a tool call fails | Diagnose failures, retry policies |
| `PostToolBatch` | After a batch of parallel tool calls resolves | Aggregation, deduplication |
| `Notification` | Claude sends a notification | Forward to external systems |
| `SubagentStart` | A subagent is spawned | Allocate resources, log |
| `SubagentStop` | A subagent finishes | Cleanup |
| `TaskCreated` | `TaskCreate` runs | Track tasks externally |
| `TaskCompleted` | A task is marked completed | Track completion |
| `Stop` | Claude finishes responding | End-of-turn telemetry |
| `StopFailure` | Turn ended due to API error | Log; exit code is ignored |
| `TeammateIdle` | Agent-team teammate about to go idle | Wake teammates, reassign work |
| `InstructionsLoaded` | A `CLAUDE.md` or `.claude/rules/*.md` is loaded | Augment loaded instructions |
| `ConfigChange` | A config file changes during a session | React to config edits |
| `CwdChanged` | Working directory changes (e.g. `cd`) | direnv-style env reload |
| `FileChanged` | A watched file changes; `matcher` selects filenames | File-watch side effects |
| `WorktreeCreate` | Worktree being created | Replace git default behavior |
| `WorktreeRemove` | Worktree being removed | Cleanup |
| `PreCompact` | Before context compaction | Snapshot state |
| `PostCompact` | After compaction completes | Restore or annotate |
| `Elicitation` | MCP server requests user input | Auto-respond, log |
| `ElicitationResult` | After user responds, before sending back | Transform responses |
| `SessionEnd` | Session terminates | Final cleanup |

## Hook action types

For each event, the entries are objects of the form `{ "matcher": "<regex>", "hooks": [ <action>, ... ] }`. Each action has a `type`:

| `type` | What it does | Required field |
|---|---|---|
| `command` | Run a shell command/script | `command` |
| `http` | POST the event JSON to a URL | `url` |
| `mcp_tool` | Call a tool on a configured MCP server | `tool` |
| `prompt` | Evaluate a prompt with an LLM (uses `$ARGUMENTS`) | `prompt` |
| `agent` | Run an agentic verifier with tools | `agent` |

## Common matchers

The `matcher` field is a regex matched against an event-specific target:

| Event | Target |
|---|---|
| `PreToolUse` / `PostToolUse` / `PostToolUseFailure` | Tool name (e.g. `Write`, `Edit`, `Bash`) |
| `FileChanged` | File path |
| `UserPromptSubmit` | The prompt text |
| Most others | Free-form; consult docs |

Use `Write|Edit` for "either of these tools", `.*` for "any" (use sparingly), or specific names like `Bash` for one tool.

## Quoting `${CLAUDE_PLUGIN_ROOT}`

When emitting a `command` action, always quote `${CLAUDE_PLUGIN_ROOT}`:

```json
{ "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}\"/scripts/foo.sh" }
```

This handles paths with spaces correctly. The validator surfaces a warning if the variable appears unquoted.

## Things to avoid

- **Long-running commands on `PreToolUse`** — they block every tool call.
- **Network calls on `UserPromptSubmit`** — they delay every prompt.
- **State that depends on session order** — events can fire concurrently across subagents.
- **Mixing `hooks` inline AND `hooks/hooks.json`** — pick one.
