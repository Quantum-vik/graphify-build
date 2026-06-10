# graphify-build

A structured wrapper around [graphifyy](https://pypi.org/project/graphifyy/) that turns any codebase into a queryable knowledge graph — with a clean CLI, incremental updates, semantic community labeling, and centralized multi-repo graph storage.

Built for teams who need persistent, LLM-navigable architecture maps across multiple repositories without re-reading source files on every question.

---

## What it does

- **Full build** — AST-extract all code, detect communities, export `graph.json` + `graph.html` + `GRAPH_REPORT.md`
- **Incremental update** — re-extract only changed files, prune deleted nodes, preserve existing semantic labels
- **Semantic labeling** — replace generic "Community 0" with real names like "Auth & Permissions" via any LLM (no API key needed — paste the generated prompt)
- **Query / path / explain / affected** — answer codebase questions via BFS/DFS graph traversal
- **Wiki** — generate an agent-crawlable wiki (one article per community + god node)
- **Centralized output** — all graphs live in one `graphify-out-repos/` directory, named `graphify-out-<name>/`
- **Auto-registers in `~/.claude/CLAUDE.md`** — the labeling prompt instructs the LLM to add the new graph to Claude Code's routing table so future codebase questions are answered automatically

---

## Why graphify-build over the graphify skill

The graphify skill is a session tool — it builds a graph, you use it, you close Claude, it's gone. graphify-build is a persistent team asset. Here's what that means on a real large repo (NimbusVault: 17,256 nodes, 863 communities).

### Day 1 — Labeling 863 communities

**Skill:** Claude explores live — runs bash commands to find community data, discovers the Python path, reads files. 2–3 minutes of tool calls just to gather what it needs. Labels exist only for this session. Next session: gone.

**graphify-build:** `.graphify_label_prompt.txt` is written at build time with all 863 communities pre-embedded. Paste it into any LLM → labels written to `.graphify_labels.json`, report regenerated, graph registered in `~/.claude/CLAUDE.md`. Next session: labels still there, Claude routes questions automatically.

### Day 2 — You changed 5 files

**Skill:** Full rebuild — 15–20 minutes again. All 863 labels reset to "Community 0", "Community 1". You start over.

**graphify-build:** `update NimbusVaultBackend --name nimbus` — only 5 files re-extracted, ~45 seconds. Labels survive. CLAUDE.md routing survives.

### Week 2 — A new developer joins

**Skill:** They run `/graphify` from scratch. Another 20 minutes. No shared labels, no shared routing.

**graphify-build:** They clone the repo. `graphify-out-repos/` is already there with `graph.json` and `.graphify_labels.json`. They ask Claude "how does auth work?" — Claude queries the pre-built graph in 3 seconds. Zero rebuild.

### Month 2 — You add a second repo

**Skill:** Run `/graphify` again. Output lands wherever graphify defaults. You manually tell Claude which graph is which every session.

**graphify-build:** `build DocSearch --name doc` → lands next to the first graph. Label it → CLAUDE.md auto-gains a new routing row. Claude now picks the right graph automatically based on the question.

### The one thing the skill still does that graphify-build doesn't

The graphify skill handles **mixed-media corpora** — PDFs, images, video transcription, papers — via semantic subagents. graphify-build is **code-only** (AST extraction). For a codebase: graphify-build. For a research corpus or mixed-media vault: the skill.

---

## Requirements

- Python 3.10+
- `uv` (recommended) or `pip`
- `graphifyy` installed in a reachable Python environment

```bash
# Recommended — installs graphifyy as a managed tool
uv tool install graphifyy --with anthropic

# Or pip
pip install graphifyy anthropic
```

---

## Installation

```bash
git clone <this-repo> graphify-build
cd graphify-build
pip install -r requirements.txt   # only needed if not using uv tool install
```

Run all commands with the Python that has graphifyy installed:

```bash
# Mac/Linux (uv tool install)
~/.local/share/uv/tools/graphifyy/bin/python cli.py <command>

# Windows (uv tool install) — use PowerShell
$env:APPDATA\uv\tools\graphifyy\Scripts\python.exe cli.py <command>

# If graphify is already on PATH (any OS)
python cli.py <command>
```

> **Cross-platform note**: All path handling inside graphify-build uses Python's `pathlib`
> — forward slashes, backslashes, and `~` expansion all work correctly on Mac, Linux, and Windows.

---

## Quick Start

```bash
# From your Solytics/ (or any parent) directory:

# Build a graph for the first time
python graphify-build/cli.py build MyRepo --name myrepo

# Output lands in: graphify-out-repos/graphify-out-myrepo/
#   graph.json          — queryable persistent graph
#   graph.html          — interactive D3 visualization
#   GRAPH_REPORT.md     — god nodes, communities, surprising connections
#   .graphify_labels.json        — community labels
#   .graphify_analysis.json      — cohesion, god nodes, questions
#   .graphify_label_prompt.txt   — ready-to-paste LLM prompt for semantic labeling
#   manifest.json       — tracks file state for incremental updates
#   cost.json           — token usage log across all runs
```

---

## Commands

### `build` — full graph from scratch

```bash
python cli.py build <repo> [--name NAME] [--out DIR] [--base DIR] [--venv DIR ...] [--force]
```

| Flag | Description |
|------|-------------|
| `--name doc` | Output → `graphify-out-repos/graphify-out-doc/` |
| `--out /path` | Custom output path (overrides `--name`) |
| `--base /path` | Working directory (default: cwd) |
| `--venv myenv` | Virtualenv dirs to exclude (auto-detected if omitted) |
| `--force` | Overwrite `graph.json` even if rebuild has fewer nodes |

```bash
python graphify-build/cli.py build NimbusVaultBackend --name nimbus
python graphify-build/cli.py build DocSearch --name doc
python graphify-build/cli.py build enterprise-rag --name rag
```

---

### `update` — incremental (changed files only)

```bash
python cli.py update <repo> [--name NAME] [--out DIR] [--base DIR] [--force]
```

Re-extracts only files that changed since the last build. Preserves existing semantic labels. Falls back to full build if no manifest exists.

```bash
python graphify-build/cli.py update NimbusVaultBackend --name nimbus
```

---

### `label` — semantic community names (CI / automation)

```bash
ANTHROPIC_API_KEY=<key> python cli.py label <graph_dir>
```

Calls Claude API in batches of 100 communities. Regenerates `GRAPH_REPORT.md` and `graph.html` with real names.

**No API key? Use Option A instead** — after every build, a self-contained prompt is written to `.graphify_label_prompt.txt`. Paste it into any LLM (Claude Code, ChatGPT, Gemini, Cursor). The prompt includes all community data — the LLM needs no extra commands.

---

### `cluster` — re-cluster without re-extracting

```bash
python cli.py cluster <graph_dir>/graph.json
```

Reruns Leiden community detection on the existing graph. Preserves semantic labels for community IDs that survive. Use when you want tighter or looser communities without paying for re-extraction.

---

### `wiki` — agent-crawlable wiki

```bash
python cli.py wiki <graph_dir>
```

Generates `<graph_dir>/wiki/index.md` + one article per community + one per god node. Uses stable community IDs from `graph.json` — never re-clusters.

---

### `query` — answer a question via graph traversal

```bash
python cli.py query <graph_dir>/graph.json "how does auth work?"
python cli.py query <graph_dir>/graph.json "what calls VaultManagement?" --dfs
python cli.py query <graph_dir>/graph.json "where is rate limiting applied?" --budget 3000
```

This is the canonical way to query a graph — including from Claude Code (via Bash tool). Never read `graph.json` directly; files can be 50–500 MB.

---

### `path` — shortest path between two nodes

```bash
python cli.py path <graph_dir>/graph.json "OrchestratorRegistry" "ModelIdService"
```

---

### `explain` — explain a node and its neighbors

```bash
python cli.py explain <graph_dir>/graph.json "FormulaEngine"
```

---

### `affected` — blast-radius analysis

```bash
python cli.py affected <graph_dir>/graph.json "OrchestratorRegistry" --depth 2
python cli.py affected <graph_dir>/graph.json "AuthMiddleware" --relations calls,imports
```

Find every node impacted by a change to a given node. Essential before touching a god node.

---

### `hook` — auto-update graph on every git commit

```bash
python cli.py hook install NimbusVaultBackend
python cli.py hook uninstall NimbusVaultBackend
```

Installs a git post-commit hook that runs `update` automatically.

---

## Semantic Community Labeling

After every build, graphify-build writes `.graphify_label_prompt.txt` into the graph output directory. This prompt is fully self-contained — it embeds all community data, naming rules, node/edge counts, the exact Python regeneration script, a warning not to re-cluster, and a **final step to register the new graph in `~/.claude/CLAUDE.md`** so Claude Code routes questions to it automatically.

**Option A — any LLM, no API key:**
```bash
cat graphify-out-repos/graphify-out-doc/.graphify_label_prompt.txt
# paste contents into Claude Code, ChatGPT, Cursor, Copilot, etc.
```

The LLM will:
1. Write semantic labels to `.graphify_labels.json`
2. Run the embedded regeneration script to rebuild `GRAPH_REPORT.md` and `graph.html`
3. Register the graph in `~/.claude/CLAUDE.md` — routing table, locations list, and cache cleanup lines

**Option B — automated via CLI:**
```bash
# Mac/Linux
ANTHROPIC_API_KEY=sk-ant-... python graphify-build/cli.py label graphify-out-repos/graphify-out-doc

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY="sk-ant-..."; python graphify-build\cli.py label graphify-out-repos\graphify-out-doc
```

Labels are written to `.graphify_labels.json`. On the next `update`, existing labels are preserved for community IDs that survive re-clustering.

---

## .graphifyignore

graphify-build creates a `.graphifyignore` in each repo on first build. It excludes non-code files so graphify uses AST-only extraction (zero LLM calls, zero cost).

**Default excludes** (always, regardless of project type):
```
*.min.js  *.min.css  *.map      # minified bundles
node_modules/  dist/  build/    # compiled output
__pycache__/  *.pyc             # Python bytecode
*.pdf  *.png  *.jpg  *.csv  ... # binary/data files
```

**For Python backend repos** — add to `.graphifyignore` manually if you have a static JS folder:
```
*.js
*.css
```

**Frontend repos** — leave `*.js`/`*.ts` out of `.graphifyignore` so your source code is included.

---

## Output directory layout

```
graphify-out-repos/
├── graphify-out-nimbus/
│   ├── graph.json                  # queryable persistent graph
│   ├── graph.html                  # interactive D3 visualization
│   ├── GRAPH_REPORT.md             # architecture report
│   ├── .graphify_labels.json       # community labels (generic or semantic)
│   ├── .graphify_analysis.json     # cohesion, god nodes, questions
│   ├── .graphify_label_prompt.txt  # paste into any LLM to get semantic names
│   ├── .graphify_detect.json       # last detection result
│   ├── .graphify_ast.json          # raw AST extraction
│   ├── .graphify_python            # exact Python interpreter used
│   ├── manifest.json               # file state for incremental updates
│   ├── cost.json                   # token usage per run
│   └── wiki/                       # agent-crawlable wiki (if generated)
├── graphify-out-doc/
└── graphify-out-rag/
```

---

## Docker

Build the image:
```bash
docker build -t graphify-build .
```

Run a full build (mount your repos and output directory):
```bash
docker run --rm \
  -v /path/to/your/repos:/repos \
  -v /path/to/graphify-out-repos:/graphs \
  graphify-build build /repos/MyRepo --out /graphs/graphify-out-myrepo
```

Run a query:
```bash
docker run --rm \
  -v /path/to/graphify-out-repos:/graphs \
  graphify-build query /graphs/graphify-out-myrepo/graph.json "how does auth work?"
```

Run semantic labeling:
```bash
docker run --rm \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v /path/to/graphify-out-repos:/graphs \
  graphify-build label /graphs/graphify-out-myrepo
```

---

## How it works

```
build <repo>
  │
  ├── 1. detect()              — discover all code files, flag sensitive skips
  ├── 2. collect_files()       — collect paths respecting .graphifyignore
  ├── 3. extract()             — AST extraction (zero LLM, zero cost)
  ├── 4. validate_extraction() — schema-check nodes and edges
  ├── 5. build_from_json()     — construct NetworkX graph
  ├── 6. cluster()             — Leiden community detection
  ├── 7. score_all()           — cohesion score per community
  ├── 8. god_nodes()           — highest betweenness centrality nodes
  ├── 9. surprising_connections() — cross-community edges
  ├── 10. save artifacts       — labels, analysis, manifest, AST, cost
  ├── 11. generate()           — GRAPH_REPORT.md
  ├── 12. to_json()            — graph.json
  ├── 13. to_html()            — graph.html (skipped for graphs >10k nodes)
  └── 14. _prompt_labeling()   — write .graphify_label_prompt.txt (includes CLAUDE.md registration step)
```

`update` is the same pipeline but steps 1-3 only process changed files, using `detect_incremental()` + `build_merge()` to merge into the existing graph.

---

## Python API

```python
from service import build, update, cluster_only, wiki, label_communities
from service import query, shortest_path, explain, affected
from service import load_graph_json, communities_from_graph, node_labels_from_graph

# Build
build("MyRepo", out_dir="graphify-out-repos/graphify-out-myrepo", base_dir="/path/to/solytics")

# Incremental update
update("MyRepo", out_dir="graphify-out-repos/graphify-out-myrepo", base_dir="/path/to/solytics")

# Query
answer = query("graphify-out-repos/graphify-out-myrepo/graph.json", "how does auth work?")

# Blast-radius
impact = affected("graphify-out-repos/graphify-out-myrepo/graph.json", "AuthMiddleware", depth=3)

# Read graph.json utilities
raw         = load_graph_json("graphify-out-repos/graphify-out-myrepo/graph.json")
communities = communities_from_graph(raw)   # {community_id: [node_id, ...]}
node_labels = node_labels_from_graph(raw)   # {node_id: human_label}
```

---

## Known graphifyy limitations

| Issue | Workaround |
|-------|-----------|
| `update` leaves ghost nodes for deleted files | Pass deleted file list to `build_merge(prune_sources=deleted)` — handled automatically by graphify-build |
| Leiden community IDs reshuffle on every re-cluster | Never call `cluster()` on an existing labeled graph — use `communities_from_graph()` to read stable IDs from `graph.json` |
| HTML viz crashes for graphs >10k nodes | graphify-build catches `ValueError` and skips HTML silently |
| Repeated community labels collapse in `GRAPH_REPORT.md` | Label prompt explicitly requires unique labels per community |

---

## Repo structure

```
graphify-build/
├── cli.py              # entry point — all commands
├── service/
│   ├── __init__.py          # public API exports
│   ├── core.py              # build, update, cluster_only, wiki, label_communities pipelines
│   ├── llm_build_prompt.py  # build_label_prompt() — the self-contained LLM labeling prompt
│   ├── queries.py           # query, path, explain, affected — thin wrappers around graphify CLI
│   └── utils.py             # Python detection, .graphifyignore, graph.json helpers
├── requirements.txt
├── Dockerfile
└── pyrightconfig.json  # suppresses Pylance false positives (reportMissingImports/ModuleSource)
```
