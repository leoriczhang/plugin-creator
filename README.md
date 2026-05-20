# plugin-creator

A Claude Code **skill** for creating, validating, packaging, and version-managing Claude Code **plugins** — and for advising on how to group a pile of standalone skills into coherent plugins.

This skill is the plugin-level analog of [`skill-creator`](../skill-creator/): where `skill-creator` produces a single `SKILL.md` with companion files, `plugin-creator` produces a *bundle* of components (skills, agents, hooks, MCP servers, LSP servers, monitors, themes) wired together by a `.claude-plugin/plugin.json` manifest, ready to install with `claude plugin install`.

Grounded in the official reference: <https://code.claude.com/docs/en/plugins-reference>.

---

## What this skill does

- **Scaffold** a new plugin tree with exactly the components you need.
- **Author** components inline, via subagents, or by delegating individual skills to `skill-creator`.
- **Validate** the manifest and every component against the official schema (28 hook events, MCP/LSP shapes, `${CLAUDE_PLUGIN_ROOT}` quoting, JSON hygiene, marketplace strict mode, etc.).
- **Bump** versions following SemVer (`major` / `minor` / `patch` / `set:X.Y.Z`).
- **Package** into a `.zip` distributable, with a pre-flight validation gate.
- **Recommend bundles** — given a folder of standalone skills, suggest which ones to merge into one plugin and which to ship solo.
- **Review** existing plugins: a static HTML overview, a manifest reviewer subagent, and a design-level analyzer.

---

## When to invoke

This skill is autoloaded when the user is working on Claude Code plugin tasks. Concretely, it should activate when the user asks to:

- "Create a plugin for X" / "make a Claude Code plugin"
- "Validate this plugin / fix my manifest"
- "Bundle these skills into a plugin"
- "Bump the version" / "package this for the marketplace"
- "I have a bunch of skills, which ones should be one plugin?"
- "Add a hook / MCP server / LSP server / monitor / theme to my plugin"

---

## Directory layout

```
plugin-creator/
├── SKILL.md                       # The orchestrator prompt Claude reads
├── README.md                      # This file (English)
├── README.zh-CN.md                # 简体中文版
├── LICENSE.txt
│
├── agents/                        # Subagent prompts for parallel work
│   ├── component-author.md        # Author a single component from a one-line spec
│   ├── manifest-reviewer.md       # Lint a plugin.json against schema + marketplace rules
│   ├── plugin-analyzer.md         # Design-level review of an entire plugin
│   └── bundle-advisor.md          # Refine heuristic clusters with role/job-to-be-done tests
│
├── scripts/                       # Deterministic Python tooling (no LLM)
│   ├── __init__.py
│   ├── utils.py                   # Issue/Report dataclasses, frontmatter parsing, etc.
│   ├── scaffold_plugin.py         # Lay down a new plugin tree
│   ├── add_component.py           # Add one component (skill/command/agent/hook/mcp/lsp/monitor/theme)
│   ├── validate_plugin.py         # Full validation, with --marketplace strict mode and --json output
│   ├── bump_version.py            # SemVer bump with CHANGELOG seeding
│   ├── package_plugin.py          # Validate then zip
│   ├── generate_review.py         # Static HTML overview
│   └── recommend_bundles.py       # Heuristic Jaccard clustering of standalone skills
│
└── references/                    # Progressive-disclosure deep-dive material
    ├── manifest_schema.md         # Every field in plugin.json
    ├── components.md              # Canonical layouts and field rules
    ├── hooks_events.md            # All 28 hook events
    ├── cli_commands.md            # `claude plugin ...` reference
    ├── version_management.md      # SemVer rules + marketplace tagging
    └── bundling_heuristics.md     # How recommend_bundles.py picks clusters
```

---

## Installation

### Option 1: Clone to user-level skills directory

```bash
git clone https://github.com/leoriczhang/plugin-creator.git ~/.claude/skills/plugin-creator
```

### Option 2: Clone to a project-level skills directory

```bash
git clone https://github.com/leoriczhang/plugin-creator.git .claude/skills/plugin-creator
```

### Option 3: Install as a Claude Code plugin

```bash
claude plugin install https://github.com/leoriczhang/plugin-creator
```

No dependencies required — all scripts are pure Python 3.8+ with zero third-party packages.

## Quick start

After install, ask Claude any of:

- "Create a plugin called `pdf-tools` with one skill and one MCP server."
- "Validate the plugin in `~/work/legal-pack/`."
- "I have a folder of skills at `~/work/skills-standalone/` — recommend how to bundle them into plugins."
- "Bump the version of this plugin to a minor release and package it."

Claude will read `SKILL.md`, plan the work, and call the right scripts/subagents.

---

## The two-stage bundle recommender

This is the headline new feature for users with a pile of standalone skills.

**Stage 1 — heuristic clustering (deterministic, zero dependencies):**

```bash
python -m scripts.recommend_bundles <skills-dir> \
  --threshold 0.18 \
  --min-bundle 2 \
  --output-md /tmp/bundle_report.md \
  --output-json /tmp/bundle_report.json
```

The script tokenizes each `SKILL.md`'s `name` + `description` (weighted 2x), strips stopwords and plumbing words, computes pairwise Jaccard similarity, and turns connected components above the threshold into candidate **bundles**. Isolated skills become **singletons**, with a one-line explanation of why they didn't cluster.

Threshold calibration table (full discussion in [references/bundling_heuristics.md](references/bundling_heuristics.md)):

| Jaccard | Meaning |
|---|---|
| ≥ 0.40 | Confident bundle |
| 0.20 – 0.40 | Likely related, review |
| 0.12 – 0.20 | Needs human/LLM review |
| < 0.08 | Probably unrelated |

**Stage 2 — qualitative review (LLM subagent):**

Spawn `bundle-advisor` and feed it the JSON. It opens each `SKILL.md`, applies four coherence tests (role overlap, job-to-be-done, cold-start, trigger-context) and returns a structured plan:

- For each candidate bundle: `accept` / `split` / `merge` / `reject`, with a *renamed* plugin name reflecting the actual role+job.
- For each singleton: `solo-plugin` / `merge-into:<bundle>` / `drop`.
- A short rationale per decision.

Then act on the plan: scaffold each accepted bundle, drop member skills into `skills/`, validate, bump to `0.1.0`, and package.

---

## Other scripts at a glance

| Script | What it does |
|---|---|
| `scaffold_plugin.py` | Create the tree (`.claude-plugin/plugin.json`, plus only the component dirs you ask for) |
| `add_component.py` | Add one component with a valid stub; updates manifest if needed |
| `validate_plugin.py` | Schema + path + JSON-hygiene checks; `--marketplace` for strict mode; `--json` for machine output |
| `bump_version.py` | SemVer bump (`major` / `minor` / `patch` / `set:X.Y.Z`); seeds a CHANGELOG entry |
| `package_plugin.py` | Validates then zips |
| `generate_review.py` | One-page HTML overview of the plugin (manifest, components, validation summary) |
| `recommend_bundles.py` | Heuristic clustering of a folder of standalone skills |

All scripts are pure Python 3.8+ with **no third-party dependencies** — including a hand-rolled minimal YAML parser in `utils.py` to avoid pulling PyYAML.

---

## Subagents

| Agent | Use it when |
|---|---|
| [`component-author`](agents/component-author.md) | You want to draft a single component (skill / agent / hook / mcp / lsp / monitor / theme) in parallel with other work |
| [`manifest-reviewer`](agents/manifest-reviewer.md) | You want a structured lint of `.claude-plugin/plugin.json` (schema + naming + marketplace-readiness) |
| [`plugin-analyzer`](agents/plugin-analyzer.md) | You want design-level observations: missing complementary components, redundant skills, hook coverage gaps, recommended SemVer bump |
| [`bundle-advisor`](agents/bundle-advisor.md) | You have a folder of standalone skills and want a coherent plan for which to bundle into which plugin |

Standard spawn pattern:

```
Read <plugin-creator-path>/agents/<agent-name>.md and follow it.
Inputs:
- <agent-specific inputs>
Output to: <path>
```

Agents return JSON; read the file when they finish and act on the structured output.

---

## Design notes

- **Progressive disclosure.** The orchestrator (`SKILL.md`) is the only thing Claude reads on autoload. Reference files in `references/` are loaded only when the relevant decision shows up. This keeps token cost low and lets the skill scale.
- **Heuristic + LLM, not LLM alone.** Bundling, validation, version bumping, and packaging are all done by deterministic scripts so the same input always produces the same output. The LLM is reserved for genuinely qualitative work (component drafting, bundle review, design analysis).
- **No third-party dependencies.** Every script runs on a clean Python 3.8+ install. Drop the folder anywhere; it works.
- **Validator is the gatekeeper.** `package_plugin.py` calls `validate_plugin.py` first and refuses to package an invalid plugin. This makes "looks good, ship it" claims trustworthy.

---

## Reference

- Plugins reference: <https://code.claude.com/docs/en/plugins-reference>
- Plugin marketplaces: <https://code.claude.com/docs/en/plugin-marketplaces>
- Sibling skill: [`skill-creator`](../skill-creator/) — for the single-skill (no plugin) case

---

## License

MIT — see [LICENSE.txt](LICENSE.txt).
