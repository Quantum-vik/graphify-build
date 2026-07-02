---
name: graphify-build
description: Build a persistent, queryable knowledge graph of any codebase using graphify-build. Handles everything end to end - checks prerequisites and installs graphifyy into a local venv if missing, locates the graphify-build tooling (or clones it into a SIBLING directory when run from elsewhere), builds or incrementally updates the graph, then briefs the user on what was done and how to use it. Use when the user asks to graph a codebase, build/create a knowledge graph, index a repo with graphify, or run graphify-build.
---

# graphify-build — end-to-end codebase graphing

You are driving the graphify-build pipeline for the user. Do all steps yourself —
the user should only have to answer "which repo do you want graphed?" (and only
if that is ambiguous). Finish with the briefing in Step 6; it is not optional.

Throughout: `TOOL` = absolute path of the graphify-build repo (contains `cli.py`
and `service/core.py`). `TARGET` = absolute path of the repo being graphed.
`BASE` = parent directory of `TARGET`. `NAME` = short lowercase name for the
graph (default: target repo folder name, lowercased).

## Step 1 — Identify the target repo

- If the current directory is a normal code repo (not graphify-build itself),
  default `TARGET` to it, but confirm with the user when their request didn't
  name one.
- If the current directory IS the graphify-build repo (has `cli.py` AND
  `service/core.py` AND `service/llm_build_prompt.py`), ask the user which repo
  to graph (list sibling directories of the repo as candidates).
- The user may also name any path explicitly — resolve it to `TARGET`.

## Step 2 — Locate (or clone) the graphify-build tooling

Check in this order, stopping at the first hit (a hit = directory containing
both `cli.py` and `service/core.py`):

1. The current directory itself
2. `./graphify-build`
3. `../graphify-build` (sibling of cwd)
4. `<BASE>/graphify-build` (sibling of the target repo)

If none exist, clone it as a **sibling of the target repo — NEVER inside it**:

```bash
git clone https://github.com/Quantum-vik/graphify-build.git "<BASE>/graphify-build"
```

Set `TOOL` to the result. Sanity-check: `TOOL/cli.py` exists.

## Step 3 — Prerequisites (install only what's missing)

1. **Python 3.10+** — check `python --version` (try `python3` on Unix if
   `python` is missing or is Python 2). If no Python 3.10+ exists at all, stop
   and tell the user to install Python; do not attempt an OS-level install.

2. **Find a Python that can import graphify.** Try, in order:
   - `TOOL/.venv` from a previous run:
     Windows `TOOL/.venv/Scripts/python.exe`, Unix `TOOL/.venv/bin/python`
   - uv tool installs:
     Windows `%APPDATA%/uv/tools/graphifyy/Scripts/python.exe`,
     Unix `~/.local/share/uv/tools/graphifyy/bin/python`
   - the system `python`
   A candidate qualifies if `<candidate> -c "import graphify"` exits 0.

3. **If none qualify, create a venv inside the tooling repo and install:**

   ```bash
   python -m venv "<TOOL>/.venv"
   # Windows:
   "<TOOL>/.venv/Scripts/python.exe" -m pip install --quiet graphifyy
   # macOS/Linux:
   "<TOOL>/.venv/bin/python" -m pip install --quiet graphifyy
   ```

   Also install `anthropic` only if the user wants automated labeling
   (`label` command). The install can take a few minutes — run it in the
   background if long.

Record the qualifying interpreter as `PY` and use it for every command below.
Do not mix interpreters between steps.

## Step 4 — Build (or incrementally update) the graph

Run from anywhere; pass `--base` explicitly so cwd doesn't matter:

- If `<BASE>/graphify-out-repos/graphify-out-<NAME>/manifest.json` already
  exists, the graph was built before — run the fast incremental path:

  ```bash
  "$PY" "<TOOL>/cli.py" update "<TARGET folder name>" --name "<NAME>" --base "<BASE>"
  ```

- Otherwise run a full build:

  ```bash
  "$PY" "<TOOL>/cli.py" build "<TARGET folder name>" --name "<NAME>" --base "<BASE>"
  ```

Notes:
- The build is AST-only — zero LLM calls, zero cost. Expect seconds for small
  repos, ~15–20 min for very large ones (17k+ nodes); use a generous timeout
  or a background task for large repos.
- On first build it writes a `.graphifyignore` into the target repo
  (auto-detecting venvs) and appends graph entries to its `.gitignore` —
  mention this in the briefing.
- "Nothing changed — graph is already up to date." from `update` is success.

## Step 5 — Verify

1. `"$PY" "<TOOL>/cli.py" list --base "<BASE>"` — the new graph must appear
   with node/edge/community counts.
2. Spot-check with one real query (pick a plausible term from the repo):

   ```bash
   "$PY" "<TOOL>/cli.py" query "<BASE>/graphify-out-repos/graphify-out-<NAME>/graph.json" "how does <something> work?"
   ```

Never read `graph.json` directly — it can be 50–500 MB. Read `stats.json`
instead if you need counts.

## Step 6 — Brief the user (mandatory)

End with a plain-language briefing covering:

1. **What was set up** — which Python/venv was used or created, whether
   graphify-build was found or freshly cloned (and where), what got installed.
2. **What the pipeline did** — discovered code files (respecting
   `.graphifyignore`) → AST extraction (no LLM) → NetworkX graph → Leiden
   community detection → cohesion/god-node analysis → wrote artifacts.
3. **What exists now and where** — the `graphify-out-repos/graphify-out-<NAME>/`
   directory: `graph.json` (the queryable graph), `graph.html` (interactive
   viz), `GRAPH_REPORT.md` (architecture report), `stats.json`, `manifest.json`
   (enables incremental updates), `.graphify_label_prompt.txt`.
4. **The numbers** — nodes, edges, communities from the build output.
5. **How to use it day to day** — three copy-pasteable commands using the real
   paths: a `query`, an `affected` (blast-radius), and `update` after edits.
6. **Next step: semantic labels** — communities are currently "Community 0,
   1, …". Offer the two options: paste
   `.graphify_label_prompt.txt` into any LLM (free, no key), or
   `ANTHROPIC_API_KEY=... "$PY" cli.py label <graph dir>` for automated
   labeling. Offer to do the labeling now.

## Failure handling

- `pip install graphifyy` fails → retry once; if it still fails show the error
  and stop (likely network/proxy).
- Build fails mid-pipeline → rerun with output captured, show the last ~20
  lines; a corrupt previous output dir can be fixed by deleting
  `graphify-out-repos/graphify-out-<NAME>/` and rebuilding.
- `query` says the graphify CLI is missing → the binary lives next to `PY`
  (venv `Scripts`/`bin`); re-check Step 3 picked the right interpreter.
- Garbled `?`/`━` characters in output on Windows are cosmetic (console
  encoding), not an error.
