---
name: plugin-creator
description: Create new Claude Code plugins, scaffold and validate their components (skills, agents, hooks, MCP/LSP servers, monitors, themes), bump versions following SemVer, package them, AND analyze a folder of standalone skills to recommend which ones should be bundled into plugins. Use when users want to create a plugin from scratch, add components to an existing plugin, validate or fix a plugin manifest, package a plugin, prepare a release, or get advice on how to group an existing pile of skills into one or more plugins.
---

# Plugin Creator

A skill for creating new Claude Code plugins and iteratively improving them.

This skill is the plugin-level analog of [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator): where `skill-creator` produces a single `SKILL.md` with companion files, `plugin-creator` produces a *bundle* of components — skills, agents, hooks, MCP servers, LSP servers, monitors, themes — wired together by a `.claude-plugin/plugin.json` manifest, and ready to install with `claude plugin install`.

At a high level, the process of creating a plugin goes like this:

- Decide what role / job-to-be-done the plugin addresses
- Decide which components it needs (skills? agents? hooks? MCP? LSP? monitors? themes?)
- Scaffold the directory tree and the manifest
- Author each component (either inline, or by delegating to `skill-creator`/subagents)
- Validate the plugin (manifest schema, JSON correctness, references resolve, hooks/MCP/LSP shapes)
- Package and present a `.zip` (or git-installable folder) the user can ship
- Plan the version bump strategy and tag/publish

Your job when using this skill is to figure out **where the user is in this process** and jump in. A user may already have a folder of orphan skills they want bundled (skip to scaffold + manifest); they may want a single plugin from scratch (full loop); they may be adding one new hook to an installed plugin (validate + bump). Be flexible.

> **Authoritative reference**: this skill is grounded in `https://code.claude.com/docs/en/plugins-reference`. When in doubt about field names, hook events, or CLI semantics, defer to the official docs and to `references/` in this skill.

## Communicating with the user

Plugin authors range from ops folks scripting one MCP server to experienced toolsmiths shipping marketplaces. Pay attention to context cues:

- "manifest", "frontmatter", "SemVer" — usually safe to use without explanation
- "MCP", "LSP", "hook matcher", "monitor `when:` clause" — explain briefly the first time unless the user clearly already knows
- "marketplace tag", "`${CLAUDE_PLUGIN_ROOT}`" — almost always worth a one-line gloss

Default to clear, jargon-light prose. Skip the gloss only if the user is clearly fluent.

---

## Creating a plugin

### Capture intent

Start by understanding what the user is actually trying to ship. Often they say "make a plugin for X" — but the X they care about could be:

- A reusable command palette for a team (skills + commands)
- An automation harness that reacts to file edits (hooks)
- A tool integration (MCP server)
- A code-intelligence layer for a niche language (LSP)
- A vibe pack (themes + a small skill)

Ask:

1. **What role / job is this plugin for?** Who's the user and what triggers it?
2. **Which components does it need?** (skills, commands, agents, hooks, mcpServers, lspServers, monitors, themes)
3. **How will it be distributed?** (private folder, git repo, marketplace)
4. **Are there existing skills/scripts you want to fold in?** If yes, point at them.
5. **What's the versioning policy?** (start at `0.1.0`, bump on every change, follow SemVer strictly)

If the user has a vague answer, suggest a default plugin shape based on their domain (see `references/components.md` for canonical layouts).

### Interview and research

Proactively ask about:

- **Component dependencies.** MCP servers need binaries; LSP servers need language servers in `$PATH`; monitors need v2.1.105+.
- **Environment vars.** Will any commands need `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` / `${user_config.*}`? Capture the `user_config` keys early.
- **Installation scope.** `user`, `project`, `local`, or `managed` — affects the README's install instructions.
- **Existing plugin?** If updating, snapshot before editing (`cp -r <plugin> <workspace>/plugin-snapshot/`) so you can diff later.

If the user wants the plugin discoverable through a marketplace, also gather marketplace metadata: `homepage`, `repository`, `license`, `keywords`, `author.{email,url}`.

### Scaffold the plugin

Use `scripts/scaffold_plugin.py` to lay down the directory tree. This is much safer than asking Claude to create 12 files by hand — it creates exactly the components the user asked for, with valid stubs.

```bash
python -m scripts.scaffold_plugin <output-dir>/<plugin-name> \
  --name <plugin-name> \
  --version 0.1.0 \
  --description "<one-sentence description>" \
  --author "<author name>" \
  --components skills,agents,hooks,mcpServers
```

Components is a comma-separated subset of:
`skills, commands, agents, hooks, mcpServers, lspServers, monitors, themes`.

The script writes:

```
<plugin-name>/
├── .claude-plugin/
│   └── plugin.json           # Manifest with the metadata you passed
├── skills/                   # only if `skills` requested
├── commands/                 # only if `commands` requested
├── agents/                   # only if `agents` requested
├── hooks/
│   └── hooks.json            # only if `hooks` requested
├── monitors/
│   └── monitors.json         # only if `monitors` requested
├── themes/                   # only if `themes` requested
├── .mcp.json                 # only if `mcpServers` requested
├── .lsp.json                 # only if `lspServers` requested
└── README.md
```

Read the resulting tree before authoring components, so you know what's already there.

### Author each component

For each component in the plugin, you have three options:

1. **Author inline** — write the file directly. Best for small plugins or when the user has been very specific.
2. **Delegate to `skill-creator`** — for any non-trivial skill, especially if the user wants test-driven iteration. Spawn a subagent with `skill-creator` available, point it at `<plugin-root>/skills/`, and let it run its full draft → eval → improve loop.
3. **Use `add_component.py`** — the lightweight path: writes a stub for one component and updates the manifest if needed. See `scripts/add_component.py`.

```bash
python -m scripts.add_component <plugin-root> \
  --kind skill --name pdf-extract \
  --description "Extract structured data from PDFs. Invoke when the user has a PDF and wants tabular data."
```

Supported `--kind`: `skill`, `command`, `agent`, `hook`, `mcp`, `lsp`, `monitor`, `theme`.

When authoring components, follow the rules in `references/components.md`. The most important constraints:

- **Skills** must be directories with a `SKILL.md` containing `name` + `description` frontmatter.
- **Agents** must NOT set `hooks`, `mcpServers`, or `permissionMode` (security restriction for plugin-shipped agents).
- **Hooks** in `hooks.json` must use one of the documented event names — see `references/hooks_events.md` for the full list.
- **MCP servers** can be declared in `.mcp.json` *or* inline under `mcpServers` in `plugin.json`, never both.
- **LSP servers** require both `command` and `extensionToLanguage`.
- **Monitors** are experimental — declare under `experimental.monitors` in `plugin.json` if not at the default `monitors/monitors.json` path.
- **Themes** are experimental — declare under `experimental.themes` if not at the default `themes/` path.

### Validate

Run the validator before any "looks good, ship it" claim:

```bash
python -m scripts.validate_plugin <plugin-root>
```

The validator checks:

1. `.claude-plugin/plugin.json` is valid JSON with required fields (`name` at minimum).
2. `name` matches the plugin's directory name (warn if mismatched).
3. `version` parses as SemVer.
4. Every referenced path resolves inside the plugin root (no `../` traversal).
5. Each `SKILL.md` has `name` + `description` frontmatter.
6. Each agent's frontmatter does not contain forbidden keys (`hooks`, `mcpServers`, `permissionMode`).
7. Hook event names are in the allowed set.
8. MCP server commands resolve (and are reachable / executable when the path is absolute).
9. LSP server entries have both `command` and `extensionToLanguage`.
10. Every `${CLAUDE_PLUGIN_ROOT}` / `${user_config.*}` reference is properly quoted in shell strings.
11. JSON files contain no comments and no trailing commas.

If validation fails, fix the issues before proceeding. The validator's output is structured — you can pipe it through your editor or just paste it back to the user.

### Test (optional but recommended)

For plugins that ship skills, the `skill-creator` test loop applies inside the plugin directory. For plugins that ship hooks/MCP/LSP, write a small smoke-test:

- Hooks: trigger the matcher manually and inspect `monitors/error-log` or stderr.
- MCP: install the plugin in a scratch project, run `claude plugin details <name>`, and verify the server starts.
- LSP: open a file with the configured extension, check that diagnostics arrive.

### Bump the version

Before shipping, decide on a version bump:

```bash
python -m scripts.bump_version <plugin-root> <major|minor|patch|set:X.Y.Z>
```

Rules (per `references/version_management.md`):

- **MAJOR** — breaking changes (renamed skill, removed hook event, changed user_config key)
- **MINOR** — new component, new optional field, additive features
- **PATCH** — bugfix that doesn't change the public surface
- **set:X.Y.Z** — manual override, useful for prerelease tags

Never re-publish an existing version with different content. Always bump.

### Package and present

```bash
python -m scripts.package_plugin <plugin-root>
```

This produces a `.zip` next to the plugin folder (or in the directory passed via `--output`), suitable for upload to a marketplace. The script runs `validate_plugin` first and refuses to package an invalid plugin.

If the host has the `present_files` tool, present the resulting zip path to the user. Otherwise, print the path and the install command:

```
claude plugin install <path-or-url>
```

### Iterate

Plugins evolve. After packaging, common follow-ups:

- "Add a new skill that does X" → `add_component.py` + `bump_version.py minor` + repackage
- "The hook is too aggressive" → edit `hooks/hooks.json` + validator + `bump_version.py patch` + repackage
- "Switch to a different MCP server" → may be a major bump if it removes existing tools

The iteration loop is the same: edit → validate → bump → package.

---

## Recommending bundles for a folder of skills

A common starting point: the user has a *pile* of standalone skills (each its own `SKILL.md`), and they don't know which ones belong in the same plugin. Use this workflow to give them advice **before** scaffolding anything.

The pipeline is two-stage on purpose:

1. **Heuristic pass** — fast, deterministic, no LLM. Surfaces obvious clusters and obvious singletons.
2. **Qualitative pass** — a subagent (`bundle-advisor`) reads the actual `SKILL.md` content and refines the heuristic clusters based on role, job-to-be-done, and trigger context.

You should run both. Skipping the heuristic pass costs time and tokens. Skipping the qualitative pass produces clusters that look right by vocabulary but make no sense as plugins.

### Stage 1 — heuristic clustering

```bash
python -m scripts.recommend_bundles <skills-dir> \
  --threshold 0.18 \
  --min-bundle 2 \
  --output-md /tmp/bundle_report.md \
  --output-json /tmp/bundle_report.json
```

What it does:

- Walks `<skills-dir>` recursively for `SKILL.md` files.
- Tokenizes each skill's `name` + `description` (with name/description weighted 2x), stripping stopwords and plumbing words (`skill`, `claude`, `invoke`, `task`...).
- Computes pairwise Jaccard similarity between every pair of skills.
- Builds an undirected graph with edges for pairs above `--threshold` (default `0.18`).
- Connected components become candidate **bundles**; isolated skills become candidate **singletons**.
- For each bundle, proposes a kebab-case plugin name from the top shared tokens.
- For each singleton, explains *why* nothing else clustered with it (no shared tokens above threshold, or shared tokens were too generic).

The markdown report is the human-readable view. The JSON is the input for stage 2.

Threshold guidance (full table in `references/bundling_heuristics.md`):

| Jaccard | Interpretation |
|---|---|
| ≥ 0.40 | confident bundle |
| 0.20 – 0.40 | likely related, review |
| 0.12 – 0.20 | needs human/LLM review |
| < 0.08 | probably unrelated |

Default `0.18` is intentionally permissive — better to overcluster and let the advisor split, than to undercluster and miss real groupings.

### Stage 2 — qualitative review

Spawn the `bundle-advisor` subagent and feed it the JSON from stage 1:

```
Read <plugin-creator-path>/agents/bundle-advisor.md and follow it.
Inputs:
- skills_dir: <skills-dir>
- heuristic_report: /tmp/bundle_report.json
Output to: /tmp/bundle_plan.json
```

The advisor opens each `SKILL.md`, applies four coherence tests (role overlap, job-to-be-done, cold-start, trigger-context — defined in the agent prompt), and returns a structured plan:

- For each candidate bundle: `accept` / `split` / `merge` / `reject`, with a renamed plugin name that reflects the actual role+job.
- For each singleton: `solo-plugin` / `merge-into:<bundle-name>` / `drop`.
- A short rationale per decision so the user can sanity-check.

### Acting on the plan

Once you have `/tmp/bundle_plan.json`:

1. Show the user a digest of the plan (renamed bundles + accepted singletons), and confirm before scaffolding.
2. For each accepted bundle: `scripts/scaffold_plugin.py --name <renamed> --components skills`, then move/copy the member skill directories into `<plugin>/skills/`.
3. For each `solo-plugin` singleton: scaffold a minimal plugin with that one skill.
4. For `merge-into` singletons: drop them into the target bundle's `skills/` directory before validation.
5. Run `validate_plugin.py` for every produced plugin. The most common failure: skills that hardcoded paths now break — replace with `${CLAUDE_PLUGIN_ROOT}`.
6. Bump versions to `0.1.0` (these are new plugins, not updates) and package.

### When to run bundle recommendation

- User says: "I have a bunch of skills, can you suggest plugins?" / "我有一堆 Skills，帮我看看怎么分组" / "Should I split this skills folder into multiple plugins?"
- The user points at a directory with ≥ 4 standalone skills.
- The user is migrating from skill-creator-only workflows to plugin distribution.

When **not** to run it:

- The user has 1-3 skills — just bundle them; no clustering insight available with so few points.
- The user already knows the grouping — they're asking for execution, not advice. Skip to scaffold.

---

## Working with existing plugins

Users will often arrive with a half-built plugin. Common situations:

### "Bundle these orphan skills into a plugin"

1. List the skills they want to include.
2. Run `scaffold_plugin.py` with `--components skills`.
3. Move (or symlink) each skill directory into `<plugin-root>/skills/`.
4. Validate. Likely failures: skills referencing absolute paths, scripts assuming the old cwd. Patch with `${CLAUDE_PLUGIN_ROOT}`.
5. Package.

### "Add an MCP server to my plugin"

1. Read `<plugin-root>/.claude-plugin/plugin.json`.
2. Decide: external `.mcp.json` (cleaner for many servers) or inline `mcpServers` (cleaner for one).
3. Use `add_component.py --kind mcp --name <server-name>`.
4. Validate.
5. `bump_version.py minor` (new capability).

### "Validate this plugin somebody sent me"

1. Run `validate_plugin.py`.
2. If it fails on JSON syntax, often the user copy-pasted with smart quotes or trailing commas — fix and re-run.
3. If it fails on schema, surface the error verbatim (the messages are designed to be diff-friendly).

### "I want this to be a marketplace plugin"

The marketplace itself lives in a separate repo (see <https://code.claude.com/docs/en/plugin-marketplaces>). For a single plugin, just make sure:

- `name` is unique (kebab-case)
- `version` follows SemVer
- `repository` and `homepage` are set
- `license` is declared
- `keywords` are present (helps discoverability)

`validate_plugin.py --marketplace` enforces these stricter checks.

---

## Reviewing plugins (the HTML viewer)

For larger plugins or when the user wants a "what's in this thing?" overview, generate a static HTML review:

```bash
python -m scripts.generate_review <plugin-root> --output /tmp/plugin_review.html
open /tmp/plugin_review.html
```

The viewer renders:

- Manifest (pretty-printed, with each field annotated)
- Component tree with file counts
- Each skill's frontmatter + first 80 lines of body
- Each agent's frontmatter + first 80 lines of body
- Hooks: a table of `event → matcher → command` rows
- MCP/LSP/monitors/themes: a table of declared entries with the resolved path
- Validation summary (errors/warnings inline)

Use this when:

- The plugin has more than ~5 components
- You're reviewing somebody else's plugin
- The user wants to share a "what's in here" link with a teammate

The viewer is a single self-contained HTML file — no server. The user can email it or commit it to the plugin repo as `docs/overview.html`.

---

## Subagents

The `agents/` directory contains specialized subagent prompts. Read them when spawning the relevant subagent (or when running inline).

- `agents/component-author.md` — Author a single component (skill / agent / hook / mcp / lsp / monitor / theme) given a one-line spec. Use this when you want to delegate component drafting in parallel.
- `agents/manifest-reviewer.md` — Review a `.claude-plugin/plugin.json` for schema correctness, naming, and marketplace-readiness. Returns a structured list of issues.
- `agents/plugin-analyzer.md` — Read an entire plugin and surface design-level observations: missing complementary components, redundant skills, hook coverage gaps, version-bump risk areas.
- `agents/bundle-advisor.md` — Given a folder of standalone skills and the heuristic JSON from `recommend_bundles.py`, decide which clusters to accept / split / merge / reject and which singletons should become solo plugins.

Spawn pattern:

```
Read <skill-creator-or-plugin-creator-path>/agents/<agent-name>.md and follow it.
Inputs:
- plugin_root: <path>
- (other agent-specific inputs)
Output to: <path>
```

Agents return JSON; read the file when they finish and act on the structured output.

---

## Reference files

The `references/` directory holds the authoritative deep-dive material. Load these into context only when needed (progressive disclosure).

- `references/manifest_schema.md` — every field in `.claude-plugin/plugin.json`, with examples and constraints
- `references/components.md` — canonical layouts and field rules for each component type
- `references/hooks_events.md` — every hook event, when it fires, and what payload it receives
- `references/cli_commands.md` — `claude plugin install / uninstall / enable / disable / update / list / details / prune / tag` with flags
- `references/version_management.md` — SemVer rules for plugins, when to bump major/minor/patch, marketplace tagging strategy
- `references/bundling_heuristics.md` — how `recommend_bundles.py` picks clusters: tokenization rules, Jaccard thresholds, calibration table, and known failure modes

---

## Cowork-specific instructions

If you're in Cowork:

- Subagents work, so component-author / manifest-reviewer / plugin-analyzer can run in parallel.
- No browser — when generating the HTML review, write to a file with `--output` and proffer the link.
- `package_plugin.py` works fine (Python + filesystem).
- `validate_plugin.py` works fine.

---

## Claude.ai-specific instructions

Without subagents:

- Author components inline, one at a time.
- Skip parallel review; just walk through validation output sequentially.
- The HTML review still works — open it via `open` or `xdg-open` if available, otherwise hand the user the path.

---

## Updating an installed plugin

If the user is asking you to update a plugin that's already installed:

- **Preserve the original `name`.** The directory and the `name` field must stay the same.
- **Copy to a writeable location before editing.** Installed plugin paths may be read-only. Copy to `/tmp/<plugin-name>/`, edit there, validate, then advise on reinstallation.
- **Bump the version.** Even a one-character fix gets a `patch` bump. `claude plugin update` won't pick up changes to the same version.
- **Repackage from `/tmp/`** with `package_plugin.py` if you need a redistributable artifact.

---

Repeating the core loop one more time:

- Capture intent (role, components, distribution, versioning)
- Scaffold (`scripts/scaffold_plugin.py`)
- Author components (inline / `skill-creator` / `add_component.py` / subagent)
- Validate (`scripts/validate_plugin.py`)
- Bump version (`scripts/bump_version.py`)
- Package (`scripts/package_plugin.py`)
- Present + iterate

Add steps to your TodoList so you don't lose the thread, especially around validation (it's the most-often-skipped step) and version bumps (most-often-forgotten).

Good luck!
