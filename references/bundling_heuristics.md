# Bundling Heuristics

How `scripts/recommend_bundles.py` decides which skills cluster together, and how to read its output critically.

---

## The signal

Each `SKILL.md` is reduced to a **token bag**: every alphanumeric word ≥ 3 chars from the skill's `name`, `description`, and the first ~80 lines of body. Common stopwords plus skill-plumbing words (`skill`, `claude`, `invoke`, `task`, …) are filtered out so they don't drown the signal.

Names and descriptions are repeated twice in the bag before tokenization, so they weigh roughly 3× as heavily as body content. This is intentional: the description is the primary trigger surface, so vocabulary overlap there is the strongest signal that two skills serve the same purpose.

## The metric

We use **Jaccard similarity** on token sets:

```
jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

- Range: `[0, 1]` (1 = identical token bags, 0 = no overlap)
- Insensitive to skill length (unlike raw overlap counts)
- Cheap: O(n²) over the corpus, fine up to a few hundred skills

We do *not* use TF-IDF or embeddings. They would be more accurate, but:

1. Bundle decisions are sensitive to context the model can't see (org structure, deployment policy). The heuristic is meant as a *first cut*, not a final verdict.
2. Embedding requires a model call per skill and a vector store. Token overlap runs in milliseconds with zero dependencies.
3. The output is meant to be reviewed by `bundle-advisor`, which *does* read the full SKILL.md content qualitatively.

## The threshold

Default: **0.18**.

Calibration heuristic, based on rough corpus testing:

| Jaccard | Interpretation |
|---|---|
| `≥ 0.40` | Almost certainly the same role/job; bundle without thinking |
| `0.20–0.40` | Likely related; bundling sensible |
| `0.12–0.20` | Plausible relation; needs human review |
| `0.08–0.12` | Weak signal; usually too thin to bundle |
| `< 0.08` | Unrelated |

Lower the threshold (e.g. `--threshold 0.12`) if you have a small corpus where signals are diluted. Raise it (e.g. `--threshold 0.25`) if you want only the most confident bundles and don't mind more singletons.

## The clustering

After scoring all pairs:

1. Build an undirected graph: nodes = skills, edges = pairs above threshold.
2. Find connected components (union-find).
3. Components of size ≥ `--min-bundle` (default 2) become **bundles**.
4. Singletons go into the standalone list.

This is **transitive**: if A↔B and B↔C are both above threshold but A↔C is not, all three still cluster together. This is usually what you want (a plugin can hold related-but-not-pairwise-similar skills) but occasionally produces "chain" clusters that don't actually cohere — which is why the qualitative review step exists.

## Plugin name proposal

The heuristic picks the **two most-shared tokens across all bundle pairs** and joins them with a hyphen. This works surprisingly often (`pdf-extract`, `legal-review`) but produces clunky results when the shared vocabulary is generic (`data-process-plugin`).

**Always rename.** The qualitative reviewer (`bundle-advisor`) replaces these with role+job names. A good plugin name is the plugin's elevator pitch.

## Cohesion score

Each bundle reports `cohesion` = mean Jaccard score across all above-threshold pairs in the bundle.

- `cohesion ≥ 0.30` — strong; the bundle is tight
- `cohesion 0.20–0.30` — average
- `cohesion 0.15–0.20` — borderline; consider splitting

Low cohesion in a *large* bundle (≥ 5 skills) is a strong signal that the heuristic chained unrelated skills via shared plumbing words. Inspect manually.

## What the heuristic gets wrong

- **Same job, different vocabulary.** Two skills that both "summarize a document" but one says "summary" and the other says "abstract" will not cluster. Remedy: have authors borrow each other's vocabulary, or run `bundle-advisor` to spot near-misses qualitatively.
- **Different jobs, shared domain.** "PDF redaction" and "PDF page-counting" both talk about PDFs but serve completely different roles. The clusterer happily groups them; the advisor must split.
- **One-pager skills.** A 20-line skill has a tiny token bag and rarely meets threshold with anyone. It looks like a singleton. The advisor decides whether it should be merged in or dropped.
- **Generic plumbing skills.** A `format-output` helper that's used by every other skill will cluster with whichever skill happens to share its terminology. Often best to either inline it or document it as a standalone utility.

## How to use the report

1. Run `recommend_bundles.py` first — it's free.
2. **Read the markdown report yourself.** Even before involving an agent, a 3-minute skim will tell you which bundles look obviously right/wrong.
3. For ambiguous cases, hand the JSON output to `bundle-advisor`. It reads the actual SKILL.md content and overrides the heuristic.
4. Use the advisor's output as the actionable plan — feed each accepted bundle into `scaffold_plugin.py` + `add_component.py`, validate, package.

The full pipeline:

```bash
python -m scripts.recommend_bundles ./my-skills \
  --output-md /tmp/bundles.md --output-json /tmp/bundles.json
# review /tmp/bundles.md, then invoke bundle-advisor with /tmp/bundles.json
```
