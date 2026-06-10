"""Self-contained LLM prompt for semantic community labeling after a graph build."""
from __future__ import annotations


def build_label_prompt(
    *,
    n:                int,
    out:              object,   # pathlib.Path
    python_bin:       str,
    community_data:   str,
    out_posix:        str,
    n_nodes:          int,
    n_edges:          int,
    graph_short_name: str,
    base_posix:       str,
    claude_md:        str,
) -> str:
    """Return the full labeling prompt with all community data pre-embedded."""
    return f"""\
TASK: Label the {n} code communities in this knowledge graph with semantic names.

GRAPH DIR: {out}
LABELS FILE TO WRITE: {out}/.graphify_labels.json
PYTHON TO USE: {python_bin}
  (graphify is installed here — use this exact interpreter for the regeneration step)

━━━ COMMUNITY DATA (already extracted — no commands needed) ━━━
Each line: C<id> (<size> nodes): [top member names]
Bigger communities matter more — focus naming energy there.

{community_data}

━━━ NAMING RULES ━━━
• 2–5 words, plain English, describes what the code DOES
• Good: "Auth & Permissions", "DB Migrations", "PDF Text Extraction"
• Bad:  "Community 3", "Misc Utils", "Various Functions"
• Small communities (1–2 nodes): derive the label from the actual filename/content
  e.g. C17 (2): ["0001_initial.py", "Migration"] → "Initial DB Migration"
  e.g. C28 (1): ["__init__.py"] → "auth.init" (use parent package, not generic name)
• EVERY label must be unique — duplicate labels collapse sections in the report.
  Never use "Module Initializer" for more than one community. Use the package
  name instead: "models.init", "auth.init", "api.init", etc.

━━━ OUTPUT FORMAT ━━━
Write exactly this JSON to {out}/.graphify_labels.json:
{{
  "0": "Your Label Here",
  "1": "Your Label Here",
  ... (one entry per community id, keys must be strings)
}}
All {n} IDs (0 through {n - 1}) must be present. No gaps.

━━━ REGENERATE REPORT AFTER WRITING LABELS ━━━
Run this with the exact Python above (do NOT use `graphify cluster` — it
reshuffles community IDs and breaks your labels):

  {python_bin} -c "
import json
from pathlib import Path
from collections import defaultdict
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_html

out = Path('{out_posix}')
raw = json.loads((out / 'graph.json').read_text())
G   = build_from_json(raw)
c   = defaultdict(list)
for node_id, data in G.nodes(data=True):
    cid = data.get('community')
    if cid is not None:
        c[int(cid)].append(node_id)
labels    = {{int(k): v for k, v in json.loads((out / '.graphify_labels.json').read_text()).items()}}
cohesion  = score_all(G, c)
gods      = god_nodes(G)
surprises = surprising_connections(G, c)
questions = suggest_questions(G, c, labels)
report    = generate(G, c, cohesion, labels, gods, surprises,
    {{'total_files': {n}, 'total_words': 0}}, {{'input': 0, 'output': 0}},
    str(out), suggested_questions=questions)
(out / 'GRAPH_REPORT.md').write_text(report)
try:
    to_html(G, c, str(out / 'graph.html'), community_labels=labels)
except ValueError:
    pass
print('Done — labels applied to GRAPH_REPORT.md and graph.html')
  "

━━━ CRITICAL: DO NOT re-cluster ━━━
Do NOT call graphify's cluster() or run `graphify cluster`.
It re-runs Leiden community detection, reshuffles all IDs, and your
labels will point to the wrong communities. The regeneration script
above reads community assignments already embedded in graph.json nodes.

━━━ FINAL STEP: REGISTER THIS GRAPH IN CLAUDE.md ━━━
This prompt covers a 4-step post-build flow. Steps 1–3 are above; this is step 4:
  1. ✓ Write .graphify_labels.json — semantic names for all {n} communities (done above)
  2. ✓ Run regeneration script — rebuilds GRAPH_REPORT.md and graph.html (done above)
  3. ✓ Do NOT re-cluster — community IDs in graph.json are stable; re-clustering breaks labels
  4. → Update {claude_md} so Claude Code automatically routes codebase questions to this graph

Read {claude_md} first to see the exact current content and formatting.
Then make FOUR insertions so Claude Code routes codebase questions here.

THIS GRAPH (pre-computed — do not re-read graph.json):
  graph.json  : {out_posix}/graph.json
  short name  : {graph_short_name}
  stats       : {n_nodes:,} nodes · {n_edges:,} edges
  base dir    : {base_posix}

Values to insert (use these exactly):
  RELATIVE PATH : graphify-out-repos/{out.name}/graph.json
  BULLET PATH   : {out.name}/graph.json
  CACHE ABS     : {base_posix}/graphify-out-repos/{out.name}/cache
  CACHE REL     : graphify-out-repos/{out.name}/cache/

── 1. ROUTING TABLE ──────────────────────────────────────────────────────────
Find the markdown table whose right-column header is "Graph to query".
Add ONE row at the bottom of that table:
  | <keywords> | `graphify-out-repos/{out.name}/graph.json` |
Keywords: 8–12 comma-separated terms from your top 8 largest community labels
(module names, domain concepts, key class names — what a user would say).

── 2. "WHENEVER YOU QUERY" SENTENCE ──────────────────────────────────────────
Find the sentence starting with "Whenever you query a graph.json, explicitly
tell the user...". It lists graph paths separated by ", " and ends with "so
they always know which graph was used."
Append to its list (before the closing "so they always..."):
  , "Using graphify-out-repos/{out.name}/graph.json"

── 3. GRAPH LOCATIONS BULLET LIST ───────────────────────────────────────────
Find the bullet list whose items match:  - `graphify-out-*/graph.json` — ...
Add ONE bullet at the end of that list:
  - `{out.name}/graph.json` — <repo display name> ({n_nodes:,} nodes, {n_edges:,} edges)
<repo display name>: short human name inferred from your top community labels.

── 4. CACHE CLEANUP ──────────────────────────────────────────────────────────
Find the `rm -rf` line (it has multiple absolute cache paths separated by spaces).
Append before the closing backtick:   {base_posix}/graphify-out-repos/{out.name}/cache

Find the "Cache folders to watch" line (comma-separated backtick paths).
Append:   `graphify-out-repos/{out.name}/cache/`

If this graph already exists in CLAUDE.md, only update its node/edge count.
Do not remove or reformat any existing entries.
"""
