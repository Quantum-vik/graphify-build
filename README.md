<div align="center">

# graphify-build

**Persistent knowledge graph infrastructure for codebases.**
Build once. Query forever. Labels survive. Teams share.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-mac%20%7C%20linux%20%7C%20windows-lightgrey?style=flat-square)]()
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)]()
[![PyPI](https://img.shields.io/badge/powered%20by-graphifyy-orange?style=flat-square)](https://pypi.org/project/graphifyy/)

</div>

---

A structured wrapper around [graphifyy](https://pypi.org/project/graphifyy/) that turns any codebase into a queryable knowledge graph — with incremental updates, semantic community labeling, multi-repo centralized storage, and automatic Claude Code integration.

---

## Table of Contents

- [Why graphify-build](#why-graphify-build-over-the-graphify-skill)
- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Semantic Labeling](#semantic-community-labeling)
- [.graphifyignore](#graphifyignore)
- [Output Layout](#output-directory-layout)
- [Docker](#docker)
- [How it works](#how-it-works)
- [Python API](#python-api)
- [Limitations](#known-graphifyy-limitations)
- [Repo Structure](#repo-structure)

---

## Why graphify-build over the graphify skill

> The graphify skill is a **session tool** — it builds a graph, you use it, you close Claude, it's gone.
> graphify-build is a **persistent team asset**.

Here's what that means on a real large repo — 17,000+ nodes, 800+ communities.

### Day 1 — Labeling 800+ communities

| | graphify skill | graphify-build |
|--|----------------|----------------|
| How | Claude explores live — runs bash commands to find community data, discovers Python path, reads files. 2–3 min of tool calls | `.graphify_label_prompt.txt` written at build time with all communities pre-embedded. Paste into any LLM — done in one pass |
| Labels persist? | No — gone when session closes | Yes — written to `.graphify_labels.json` |
| Claude routing? | Manual every session | Auto-registered in `~/.claude/CLAUDE.md` |

### Day 2 — You changed 5 files

| | graphify skill | graphify-build |
|--|----------------|----------------|
| Time | Full rebuild — 15–20 min again | `update` — only 5 files re-extracted, ~45 sec |
| Labels | Reset to "Community 0", "Community 1" | Preserved |

### Week 2 — A new developer joins

| | graphify skill | graphify-build |
|--|----------------|----------------|
| Setup | Run `/graphify` from scratch — 20 min, no shared labels | Clone repo — `graph.json` + labels already there, Claude queries in 3 sec |

### Month 2 — You add a second repo

| | graphify skill | graphify-build |
|--|----------------|----------------|
| Multi-repo | Output lands wherever graphify defaults, manual routing each session | `build <repo-2> --name <name-2>` → lands next to first graph, CLAUDE.md auto-gains a new routing row |

> **One thing the skill still does that graphify-build doesn't:**
> The graphify skill handles mixed-media corpora — PDFs, images, video, papers — via semantic subagents.
> graphify-build is code-only (AST extraction). For a codebase: graphify-build. For a research corpus: the skill.

---

## What it does

| Feature | Description |
|---------|-------------|
| **Full build** | AST-extract all code, detect communities, export `graph.json` + `graph.html` + `GRAPH_REPORT.md` |
| **Incremental update** | Re-extract only changed files, prune deleted nodes, preserve existing semantic labels |
| **Semantic labeling** | Replace "Community 0" with "Auth & Permissions" via any LLM — no API key needed |
| **Query / path / explain / affected** | Answer codebase questions via BFS/DFS graph traversal |
| **Wiki** | Generate an agent-crawlable wiki — one article per community + god node |
| **Centralized output** | All graphs in one `graphify-out-repos/` directory, named `graphify-out-<name>/` |
| **Auto CLAUDE.md registration** | Labeling prompt tells the LLM to register the graph in Claude Code's routing table |

---

## Requirements

- Python 3.10+
- `uv` (recommended) or `pip`

```bash
# Recommended — installs graphifyy as a managed tool
uv tool install graphifyy --with anthropic

# Or pip
pip install graphifyy anthropic
```

---

## Installation

```bash
git clone https://github.com/Quantum-vik/graphify-build.git
cd graphify-build
```

Run all commands with the Python that has graphifyy installed:

```bash
# Mac / Linux
~/.local/share/uv/tools/graphifyy/bin/python cli.py <command>

# Windows (PowerShell)
$env:APPDATA\uv\tools\graphifyy\Scripts\python.exe cli.py <command>

# If graphify is on PATH (any OS)
python cli.py <command>
```

> **Cross-platform:** All path handling uses Python's `pathlib` — forward slashes, backslashes,
> and `~` expansion work correctly on Mac, Linux, and Windows.

---

## Quick Start

```bash
# Run from your project root (parent of the repos you want to graph)

# 1. Build a graph
python graphify-build/cli.py build <repo-name> --name <name>

# 2. Query it
python graphify-build/cli.py query graphify-out-repos/graphify-out-<name>/graph.json "how does auth work?"

# 3. Label communities (paste the generated prompt into any LLM)
cat graphify-out-repos/graphify-out-<name>/.graphify_label_prompt.txt
```

**Output lands in** `graphify-out-repos/graphify-out-<name>/`:

```
graph.json                 — queryable persistent graph
graph.html                 — interactive D3 visualization
GRAPH_REPORT.md            — architecture report
.graphify_labels.json      — community labels
.graphify_analysis.json    — cohesion, god nodes, questions
.graphify_label_prompt.txt — self-contained LLM prompt for labeling
manifest.json              — file state for incremental updates
cost.json                  — token usage log across all runs
```

---

## Commands

### `build` — full graph from scratch

```bash
python cli.py build <repo-name> [--name NAME] [--out DIR] [--base DIR] [--venv DIR ...] [--force]
```

| Flag | Description |
|------|-------------|
| `--name <name>` | Output → `graphify-out-repos/graphify-out-<name>/` |
| `--out /path` | Custom output path (overrides `--name`) |
| `--base /path` | Working directory (default: cwd) |
| `--venv <dir>` | Virtualenv dirs to exclude (auto-detected if omitted) |
| `--force` | Overwrite `graph.json` even if rebuild has fewer nodes |

```bash
python graphify-build/cli.py build <repo-1> --name <name-1>
python graphify-build/cli.py build <repo-2> --name <name-2>
```

---

### `update` — incremental (changed files only)

```bash
python cli.py update <repo-name> [--name NAME] [--out DIR] [--base DIR] [--force]
```

Re-extracts only files changed since last build. Preserves semantic labels. Falls back to full build if no manifest exists.

```bash
python graphify-build/cli.py update <repo-name> --name <name>
```

---

### `query` — answer a codebase question

```bash
python cli.py query <graph.json> "<question>" [--dfs] [--budget N]
```

> Never read `graph.json` directly — files are 50–500 MB. Always use `query`.

```bash
python cli.py query graphify-out-repos/graphify-out-<name>/graph.json "how does auth work?"
python cli.py query graphify-out-repos/graphify-out-<name>/graph.json "what calls <ServiceName>?" --dfs
python cli.py query graphify-out-repos/graphify-out-<name>/graph.json "where is rate limiting?" --budget 3000
```

---

### `path` — shortest path between two nodes

```bash
python cli.py path <graph.json> "<NodeA>" "<NodeB>"
```

---

### `explain` — explain a node and its neighbors

```bash
python cli.py explain <graph.json> "<NodeName>"
```

---

### `affected` — blast-radius analysis

```bash
python cli.py affected <graph.json> "<NodeName>" [--depth N] [--relations calls,imports]
```

Find every node impacted by changing a given node. Essential before touching a god node.

```bash
python cli.py affected graphify-out-repos/graphify-out-<name>/graph.json "<NodeName>" --depth 2
```

---

### `label` — automated semantic labeling via Claude API

```bash
# Mac/Linux
ANTHROPIC_API_KEY=sk-ant-... python cli.py label graphify-out-repos/graphify-out-<name>

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY="sk-ant-..."; python cli.py label graphify-out-repos\graphify-out-<name>
```

Calls Claude API in batches of 100 communities. Regenerates `GRAPH_REPORT.md` and `graph.html`.

---

### `cluster` — re-cluster without re-extracting

```bash
python cli.py cluster graphify-out-repos/graphify-out-<name>/graph.json
```

Reruns Leiden community detection on the existing graph. Preserves semantic labels for community IDs that survive.

---

### `wiki` — agent-crawlable wiki

```bash
python cli.py wiki graphify-out-repos/graphify-out-<name>
```

Generates `wiki/index.md` + one article per community + one per god node. Uses stable IDs from `graph.json` — never re-clusters.

---

### `hook` — auto-update on every git commit

```bash
python cli.py hook install   <repo-path>
python cli.py hook uninstall <repo-path>
```

---

## Semantic Community Labeling

After every build, graphify-build writes `.graphify_label_prompt.txt` — a fully self-contained prompt with all community data, naming rules, node/edge counts, exact regeneration script, and a final step to register the graph in `~/.claude/CLAUDE.md`.

**Option A — any LLM, no API key:**

```bash
cat graphify-out-repos/graphify-out-<name>/.graphify_label_prompt.txt
# paste into Claude Code, ChatGPT, Cursor, Copilot, etc.
```

The LLM completes all four steps:
1. Write `.graphify_labels.json` with semantic names
2. Run the embedded regeneration script → rebuild `GRAPH_REPORT.md` + `graph.html`
3. Skip re-clustering (community IDs are stable in `graph.json`)
4. Update `~/.claude/CLAUDE.md` — routing table, locations list, cache cleanup

**Option B — automated via CLI (requires API key):**

```bash
ANTHROPIC_API_KEY=sk-ant-... python graphify-build/cli.py label graphify-out-repos/graphify-out-<name>
```

Labels survive the next `update` — community IDs that carry over keep their semantic names.

---

## .graphifyignore

graphify-build creates a `.graphifyignore` in each repo on first build. Excludes non-code files so graphify uses AST-only extraction — zero LLM calls, zero cost.

**Always excluded (all project types):**

```
*.min.js  *.min.css  *.map          # minified bundles
node_modules/  dist/  build/        # compiled output
__pycache__/   *.pyc                # Python bytecode
*.pdf  *.png  *.jpg  *.csv  ...     # binary / data files
```

**Python backend repos** — add manually if you have a static JS folder:

```
*.js
*.css
```

**Frontend repos** — leave `*.js` / `*.ts` out so your source is included.

---

## Output Directory Layout

```
graphify-out-repos/
├── graphify-out-<name>/
│   ├── graph.json                  # queryable persistent graph
│   ├── graph.html                  # interactive D3 visualization
│   ├── GRAPH_REPORT.md             # architecture report
│   ├── .graphify_labels.json       # community labels (generic or semantic)
│   ├── .graphify_analysis.json     # cohesion, god nodes, questions
│   ├── .graphify_label_prompt.txt  # self-contained LLM labeling prompt
│   ├── .graphify_detect.json       # last detection result
│   ├── .graphify_ast.json          # raw AST extraction
│   ├── .graphify_python            # exact Python interpreter used during build
│   ├── manifest.json               # file state for incremental updates
│   ├── cost.json                   # token usage per run
│   └── wiki/                       # agent-crawlable wiki (if generated)
├── graphify-out-<name-2>/
└── graphify-out-<name-3>/
```

---

## Docker

```bash
# Build image
docker build -t graphify-build .

# Full build
docker run --rm \
  -v /path/to/repos:/repos \
  -v /path/to/graphify-out-repos:/graphs \
  graphify-build build /repos/<repo-name> --out /graphs/graphify-out-<name>

# Query
docker run --rm \
  -v /path/to/graphify-out-repos:/graphs \
  graphify-build query /graphs/graphify-out-<name>/graph.json "how does auth work?"

# Label
docker run --rm \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v /path/to/graphify-out-repos:/graphs \
  graphify-build label /graphs/graphify-out-<name>
```

---

## How it works

```
build <repo-name>
  │
  ├──  1. detect()                — discover all code files, flag sensitive skips
  ├──  2. collect_files()         — collect paths respecting .graphifyignore
  ├──  3. extract()               — AST extraction (zero LLM, zero cost)
  ├──  4. validate_extraction()   — schema-check nodes and edges
  ├──  5. build_from_json()       — construct NetworkX graph
  ├──  6. cluster()               — Leiden community detection
  ├──  7. score_all()             — cohesion score per community
  ├──  8. god_nodes()             — highest betweenness centrality nodes
  ├──  9. surprising_connections()— cross-community edges
  ├── 10. save artifacts          — labels, analysis, manifest, AST, cost
  ├── 11. generate()              — GRAPH_REPORT.md
  ├── 12. to_json()               — graph.json
  ├── 13. to_html()               — graph.html (skipped for graphs >10k nodes)
  └── 14. _prompt_labeling()      — write .graphify_label_prompt.txt
                                    (includes CLAUDE.md registration step)
```

`update` runs the same pipeline but steps 1–3 only process changed files, using `detect_incremental()` + `build_merge()` to merge into the existing graph.

---

## Python API

```python
from service import build, update, cluster_only, wiki, label_communities
from service import query, shortest_path, explain, affected
from service import load_graph_json, communities_from_graph, node_labels_from_graph

# Build
build("<repo-name>", out_dir="graphify-out-repos/graphify-out-<name>", base_dir="/path/to/root")

# Incremental update
update("<repo-name>", out_dir="graphify-out-repos/graphify-out-<name>", base_dir="/path/to/root")

# Query
answer = query("graphify-out-repos/graphify-out-<name>/graph.json", "how does auth work?")

# Blast-radius
impact = affected("graphify-out-repos/graphify-out-<name>/graph.json", "<NodeName>", depth=3)

# Graph utilities
raw         = load_graph_json("graphify-out-repos/graphify-out-<name>/graph.json")
communities = communities_from_graph(raw)   # {community_id: [node_id, ...]}
node_labels = node_labels_from_graph(raw)   # {node_id: human_label}
```

---

## Known graphifyy Limitations

| Issue | Workaround |
|-------|------------|
| Ghost nodes for deleted files after `update` | `build_merge(prune_sources=deleted)` — handled automatically |
| Leiden community IDs reshuffle on every re-cluster | Never call `cluster()` on a labeled graph — use `communities_from_graph()` to read stable IDs |
| HTML viz crashes for graphs > 10k nodes | graphify-build catches `ValueError` and skips HTML silently |
| Duplicate labels collapse sections in `GRAPH_REPORT.md` | Label prompt requires unique labels per community |

---

## Repo Structure

```
graphify-build/
├── cli.py                       # entry point — all commands
├── service/
│   ├── __init__.py              # public API exports
│   ├── core.py                  # build, update, cluster_only, wiki, label_communities
│   ├── llm_build_prompt.py      # build_label_prompt() — self-contained LLM labeling prompt
│   ├── queries.py               # query, path, explain, affected
│   └── utils.py                 # Python detection, .graphifyignore, graph.json helpers
├── requirements.txt
├── Dockerfile
└── pyrightconfig.json           # suppresses Pylance false positives
```

---

<div align="center">

Built on top of [graphifyy](https://pypi.org/project/graphifyy/) &nbsp;·&nbsp; Maintained by [@Quantum-vik](https://github.com/Quantum-vik)

</div>
