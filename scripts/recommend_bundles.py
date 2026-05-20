#!/usr/bin/env python3
"""
Recommend how to group a folder of standalone skills into Claude Code plugins.

Usage:
    python -m scripts.recommend_bundles <skills-dir> \
        [--threshold 0.18] \
        [--min-bundle 2] \
        [--output-md report.md] \
        [--output-json report.json]

The recommender:
1. Reads every SKILL.md under <skills-dir> (recursively or one level deep).
2. Tokenizes name + description + body preview, drops stopwords + plumbing words.
3. Computes pairwise Jaccard similarity between skills.
4. Builds an undirected graph with edges where similarity >= threshold.
5. Connected components become "bundles" (plugin candidates).
6. Singletons (no edge above threshold) are flagged "ship standalone".

For each bundle it proposes:
- A plugin name (kebab-case, derived from the most-common shared token).
- A rationale (the top shared tokens).
- The cohesion score (mean intra-cluster Jaccard).

For each singleton it explains why no good cluster was found and suggests
a minimal manifest if the user wants to ship it solo.

Output:
- Markdown report (human-readable; default: print to stdout).
- JSON report (machine-readable; --output-json).

This is heuristic-only — there's no LLM in the loop. For qualitative review,
spawn the `bundle-advisor` subagent (see agents/bundle-advisor.md) and pass it
this report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from scripts.utils import parse_frontmatter

# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

# English stopwords — small list, enough for description-level signal.
STOPWORDS = {
    "a", "an", "and", "the", "of", "to", "in", "on", "for", "with", "by",
    "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "it", "its", "as", "at", "or", "but", "if", "so",
    "than", "then", "from", "into", "about", "after", "before", "when",
    "while", "until", "use", "uses", "using", "used", "user", "users",
    "do", "does", "did", "done", "get", "gets", "got", "make", "makes",
    "made", "any", "all", "some", "each", "every", "no", "not", "only",
    "very", "more", "most", "less", "least", "such", "also", "even",
    "i", "you", "we", "they", "them", "us", "our", "your", "their",
    "want", "wants", "wanted", "need", "needs", "needed", "should",
    "could", "would", "may", "might", "can", "will", "shall",
    "task", "tasks", "thing", "things", "way", "ways", "step", "steps",
    "skill", "skills", "claude", "code", "tool", "tools", "input",
    "output", "file", "files", "data", "result", "results", "process",
    "processes", "processing", "invoke", "invoked", "trigger", "triggered",
    "run", "runs", "running", "executes", "executed", "execution",
}

# Domain words that stay (we don't want to filter "pdf", "csv", "react", ...).
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+]+")


def tokenize(text: str) -> set[str]:
    out = set()
    for m in TOKEN_RE.finditer(text):
        t = m.group(0).lower()
        if len(t) <= 2:
            continue
        if t in STOPWORDS:
            continue
        out.add(t)
    return out


# ---------------------------------------------------------------------------
# Skill record
# ---------------------------------------------------------------------------


@dataclass
class SkillRec:
    path: Path
    name: str
    description: str
    body_preview: str
    tokens: set[str] = field(default_factory=set)

    def signal_text(self) -> str:
        # Names + description carry stronger signal than the body, so weight
        # them by repetition.
        return f"{self.name} {self.name} {self.description} {self.description} {self.body_preview}"


def discover_skills(skills_dir: Path) -> list[SkillRec]:
    """Find every SKILL.md under skills_dir and return SkillRec instances."""
    skills_dir = skills_dir.resolve()
    out: list[SkillRec] = []
    if not skills_dir.is_dir():
        raise SystemExit(f"not a directory: {skills_dir}")
    for skill_md in skills_dir.rglob("SKILL.md"):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        name = str(fm.get("name") or skill_md.parent.name)
        desc = str(fm.get("description") or "")
        body_preview = "\n".join(body.splitlines()[:80])
        rec = SkillRec(
            path=skill_md,
            name=name,
            description=desc,
            body_preview=body_preview,
        )
        rec.tokens = tokenize(rec.signal_text())
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Similarity + clustering
# ---------------------------------------------------------------------------


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass
class Edge:
    i: int
    j: int
    score: float
    shared: list[str]


def build_edges(skills: list[SkillRec], threshold: float) -> list[Edge]:
    edges: list[Edge] = []
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            s = jaccard(skills[i].tokens, skills[j].tokens)
            if s >= threshold:
                shared = sorted(skills[i].tokens & skills[j].tokens)
                edges.append(Edge(i, j, s, shared))
    return edges


def connected_components(n: int, edges: list[Edge]) -> list[list[int]]:
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in edges:
        union(e.i, e.j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


# ---------------------------------------------------------------------------
# Bundle synthesis
# ---------------------------------------------------------------------------


@dataclass
class Bundle:
    members: list[SkillRec]
    proposed_name: str
    rationale: str
    cohesion: float
    top_shared_tokens: list[str]
    edges: list[Edge]


def propose_plugin_name(top_tokens: list[str], existing: set[str]) -> str:
    """Derive a kebab-case plugin name from the cluster's top shared tokens."""
    base = top_tokens[0] if top_tokens else "bundle"
    # If two tokens are very informative, combine them
    if len(top_tokens) >= 2 and len(top_tokens[0]) <= 6 and len(top_tokens[1]) <= 8:
        candidate = f"{top_tokens[0]}-{top_tokens[1]}"
    else:
        candidate = f"{base}-plugin"
    # Disambiguate
    n = candidate
    suffix = 2
    while n in existing:
        n = f"{candidate}-{suffix}"
        suffix += 1
    return n


def synthesize_bundle(
    indices: list[int],
    skills: list[SkillRec],
    edges: list[Edge],
    existing_names: set[str],
) -> Bundle:
    members = [skills[i] for i in indices]
    member_idx = set(indices)
    bundle_edges = [e for e in edges if e.i in member_idx and e.j in member_idx]

    # Top shared tokens across the whole bundle
    counter: Counter[str] = Counter()
    for e in bundle_edges:
        counter.update(e.shared)
    # Tie-break: tokens that appear in more pairs win
    top_shared = [tok for tok, _ in counter.most_common(8)]

    # Cohesion = mean similarity across all pairs in the bundle
    cohesion = (
        sum(e.score for e in bundle_edges) / len(bundle_edges)
        if bundle_edges
        else 1.0
    )

    rationale_bits: list[str] = []
    if top_shared:
        rationale_bits.append(
            f"shared vocabulary: {', '.join(top_shared[:5])}"
        )
    rationale_bits.append(f"mean cohesion (Jaccard): {cohesion:.2f}")
    rationale_bits.append(
        f"{len(bundle_edges)} above-threshold pair(s) out of "
        f"{len(members) * (len(members) - 1) // 2}"
    )

    name = propose_plugin_name(top_shared, existing_names)
    existing_names.add(name)

    return Bundle(
        members=members,
        proposed_name=name,
        rationale="; ".join(rationale_bits),
        cohesion=cohesion,
        top_shared_tokens=top_shared,
        edges=bundle_edges,
    )


# ---------------------------------------------------------------------------
# Singleton analysis
# ---------------------------------------------------------------------------


@dataclass
class Singleton:
    skill: SkillRec
    nearest: SkillRec | None
    nearest_score: float
    reason: str


def analyze_singleton(
    rec: SkillRec, idx: int, skills: list[SkillRec], threshold: float
) -> Singleton:
    best_other: SkillRec | None = None
    best_score = 0.0
    for j, other in enumerate(skills):
        if j == idx:
            continue
        s = jaccard(rec.tokens, other.tokens)
        if s > best_score:
            best_score = s
            best_other = other
    if best_other is None:
        reason = "Only skill in the corpus."
    elif best_score < threshold * 0.5:
        reason = (
            f"Closest skill '{best_other.name}' shares almost nothing "
            f"(Jaccard {best_score:.2f}). Ship as a one-skill plugin."
        )
    else:
        reason = (
            f"Closest skill '{best_other.name}' is below threshold "
            f"({best_score:.2f} < {threshold}). Either ship solo or "
            f"strengthen vocabulary overlap with shared terms before bundling."
        )
    return Singleton(
        skill=rec,
        nearest=best_other,
        nearest_score=best_score,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_markdown(
    bundles: list[Bundle],
    singletons: list[Singleton],
    threshold: float,
    skills_dir: Path,
    total_skills: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# Bundle recommendations for `{skills_dir}`\n")
    lines.append(
        f"Analyzed **{total_skills}** skill(s) at Jaccard threshold "
        f"`{threshold}`. Found **{len(bundles)}** bundle(s) and "
        f"**{len(singletons)}** standalone candidate(s).\n"
    )
    if bundles:
        lines.append("## Recommended bundles\n")
        for i, b in enumerate(bundles, 1):
            lines.append(f"### {i}. `{b.proposed_name}` ({len(b.members)} skills)\n")
            lines.append(f"_{b.rationale}_\n")
            lines.append("**Members:**\n")
            for m in b.members:
                desc = (m.description or "").replace("\n", " ").strip()
                if len(desc) > 140:
                    desc = desc[:137] + "..."
                lines.append(f"- `{m.name}` — {desc}")
                lines.append(f"  - path: `{m.path}`")
            lines.append("")
            if b.top_shared_tokens:
                lines.append(
                    "**Top shared vocabulary:** "
                    + ", ".join(f"`{t}`" for t in b.top_shared_tokens)
                    + "\n"
                )
            lines.append("**Suggested next step:**")
            lines.append("```bash")
            lines.append(
                f"python -m scripts.scaffold_plugin <out>/{b.proposed_name} \\\n"
                f"  --name {b.proposed_name} --version 0.1.0 \\\n"
                f"  --description '<one-line plugin description>' \\\n"
                f"  --author '<your name>' \\\n"
                f"  --components skills"
            )
            for m in b.members:
                lines.append(
                    f"# then move {m.path.parent.name}/ into "
                    f"<out>/{b.proposed_name}/skills/"
                )
            lines.append("```\n")
    if singletons:
        lines.append("## Skills that should ship standalone\n")
        for s in singletons:
            desc = (s.skill.description or "").replace("\n", " ").strip()
            if len(desc) > 140:
                desc = desc[:137] + "..."
            lines.append(f"- `{s.skill.name}` — {desc}")
            lines.append(f"  - path: `{s.skill.path}`")
            lines.append(f"  - reason: {s.reason}")
        lines.append("")
    if not bundles and not singletons:
        lines.append("(no skills found)\n")
    lines.append("---\n")
    lines.append(
        "_This report is heuristic. For a qualitative review, pass it to the_\n"
        "_`bundle-advisor` subagent (see `agents/bundle-advisor.md`)._\n"
    )
    return "\n".join(lines)


def render_json(
    bundles: list[Bundle],
    singletons: list[Singleton],
    threshold: float,
    skills_dir: Path,
) -> dict:
    return {
        "skills_dir": str(skills_dir),
        "threshold": threshold,
        "bundles": [
            {
                "proposed_name": b.proposed_name,
                "rationale": b.rationale,
                "cohesion": round(b.cohesion, 4),
                "top_shared_tokens": b.top_shared_tokens,
                "members": [
                    {
                        "name": m.name,
                        "path": str(m.path),
                        "description": m.description,
                    }
                    for m in b.members
                ],
                "edges": [
                    {
                        "a": b.members[ix_a].name,
                        "b": b.members[ix_b].name,
                        "score": round(score, 4),
                        "shared": shared,
                    }
                    for ix_a, ix_b, score, shared in _edges_in_bundle(b)
                ],
            }
            for b in bundles
        ],
        "singletons": [
            {
                "name": s.skill.name,
                "path": str(s.skill.path),
                "description": s.skill.description,
                "nearest": s.nearest.name if s.nearest else None,
                "nearest_score": round(s.nearest_score, 4),
                "reason": s.reason,
            }
            for s in singletons
        ],
    }


def _edges_in_bundle(b: Bundle) -> Iterable[tuple[int, int, float, list[str]]]:
    name_to_local = {m.name: i for i, m in enumerate(b.members)}
    paths = {m.path: m.name for m in b.members}
    for e in b.edges:
        # We know e.i and e.j refer to global indices, but we kept the
        # original SkillRec list. Recover local indices via path lookup.
        # Each edge keeps the global pair only — re-resolve via path.
        # (b.members already filtered by global indices, so order matches.)
        # Simpler: re-derive shared tokens from members' tokens
        pass
    # Recompute pairwise edges scoped to the bundle for the JSON output
    n = len(b.members)
    for i in range(n):
        for j in range(i + 1, n):
            s = jaccard(b.members[i].tokens, b.members[j].tokens)
            if s > 0:
                shared = sorted(b.members[i].tokens & b.members[j].tokens)
                yield i, j, s, shared


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def recommend(
    skills_dir: Path,
    threshold: float,
    min_bundle: int,
) -> tuple[list[Bundle], list[Singleton], int]:
    skills = discover_skills(skills_dir)
    if not skills:
        return [], [], 0

    edges = build_edges(skills, threshold)
    components = connected_components(len(skills), edges)

    bundles: list[Bundle] = []
    singletons: list[Singleton] = []
    existing_names: set[str] = set()

    for comp in components:
        if len(comp) >= min_bundle:
            bundles.append(synthesize_bundle(comp, skills, edges, existing_names))
        else:
            for idx in comp:
                singletons.append(analyze_singleton(skills[idx], idx, skills, threshold))

    # Sort: bundles by size desc, singletons alpha
    bundles.sort(key=lambda b: (-len(b.members), -b.cohesion))
    singletons.sort(key=lambda s: s.skill.name.lower())

    return bundles, singletons, len(skills)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Recommend plugin bundles for a folder of standalone skills."
    )
    p.add_argument("skills_dir", type=Path, help="Directory containing one or more SKILL.md files.")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.18,
        help="Jaccard similarity threshold for bundling (default: 0.18).",
    )
    p.add_argument(
        "--min-bundle",
        type=int,
        default=2,
        help="Minimum skills to call something a bundle (default: 2).",
    )
    p.add_argument("--output-md", type=Path, help="Write markdown report here (default: stdout).")
    p.add_argument("--output-json", type=Path, help="Write JSON report here (optional).")
    args = p.parse_args(argv)

    bundles, singletons, total = recommend(args.skills_dir, args.threshold, args.min_bundle)

    md = render_markdown(bundles, singletons, args.threshold, args.skills_dir.resolve(), total)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md, encoding="utf-8")
        print(f"✅ Wrote markdown report: {args.output_md}")
    else:
        print(md)

    if args.output_json:
        data = render_json(bundles, singletons, args.threshold, args.skills_dir.resolve())
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"✅ Wrote JSON report: {args.output_json}")

    if total == 0:
        print("⚠️  No SKILL.md files found.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
