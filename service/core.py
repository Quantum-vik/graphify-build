"""Build, update, cluster-only, and wiki pipelines."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .utils import (
    ensure_graphify_importable,
    create_graphifyignore,
    update_gitignore,
    detect_venv_dirs,
    load_graph_json,
    communities_from_graph,
    node_labels_from_graph,
)


# ── artifact helpers ──────────────────────────────────────────────────────────

def _load_labels(communities: dict) -> dict[int, str]:
    """
    Return community labels. Always generates fresh 'Community N' labels for AST-only builds.
    Leiden community IDs are non-deterministic — they reshuffle on every re-cluster run,
    so reusing saved labels from a previous run would silently apply wrong names to wrong groups.
    Real semantic names (e.g. 'Database Migrations') require an LLM labeling pass.
    """
    return {c: f"Community {c}" for c in communities}


def _save_labels(out: Path, labels: dict[int, str]) -> None:
    (out / ".graphify_labels.json").write_text(
        json.dumps({str(k): v for k, v in labels.items()}, indent=2), encoding="utf-8"
    )


def _save_analysis(out: Path, communities, cohesion, gods, surprises, questions) -> None:
    (out / ".graphify_analysis.json").write_text(
        json.dumps({
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion":    {str(k): v for k, v in cohesion.items()},
            "gods":        gods,
            "surprises":   surprises,
            "questions":   questions,
        }, indent=2),
        encoding="utf-8",
    )


def _update_cost(out: Path, n_files: int, input_tokens: int = 0, output_tokens: int = 0) -> None:
    cost_path = out / "cost.json"
    data: dict = {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0}
    if cost_path.exists():
        try:
            data = json.loads(cost_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["runs"].append({
        "date":          datetime.now(timezone.utc).isoformat(),
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "files":         n_files,
    })
    data["total_input_tokens"]  = sum(r["input_tokens"]  for r in data["runs"])
    data["total_output_tokens"] = sum(r["output_tokens"] for r in data["runs"])
    cost_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _prompt_labeling(out: Path, communities: dict, G, labels: dict) -> None:
    """
    After build: print a self-contained, data-rich LLM prompt for semantic labeling.
    Community members are embedded directly — the LLM needs no exploration, no commands.
    """
    n        = len(communities)
    est_cost = (n * 50 / 1_000_000 * 3) + (n * 5 / 1_000_000 * 15)

    # Pre-extract community data so the LLM prompt is fully self-contained.
    # Build node label lookup from graph.json for human-readable names.
    graph_path = out / "graph.json"
    node_labels: dict[str, str] = {}
    if graph_path.exists():
        node_labels = node_labels_from_graph(load_graph_json(graph_path))

    # Format each community: show up to 12 human-readable member names.
    community_lines = []
    for cid, members in sorted(communities.items(), key=lambda x: -len(x[1])):
        names = [node_labels.get(m, m) for m in members[:12]]
        # Filter out __init__.py noise for display
        clean = [nm for nm in names if nm not in ("__init__.py", "__init__")
                 and not nm.startswith("__")]
        display = clean[:10] if clean else names[:8]
        community_lines.append(f"  C{cid} ({len(members)} nodes): {display}")

    community_data = "\n".join(community_lines)

    # Resolve the exact Python interpreter that has graphify installed
    python_file = out / ".graphify_python"
    python_bin  = python_file.read_text(encoding="utf-8").strip() if python_file.exists() else sys.executable

    # Write the prompt to a file so it's easy to copy even for large graphs
    # Use POSIX paths in embedded scripts — forward slashes work on all platforms
    # including Windows (Python's pathlib accepts them universally).
    from .llm_build_prompt import build_label_prompt

    out_posix        = out.as_posix()
    n_nodes          = G.number_of_nodes()
    n_edges          = G.number_of_edges()
    graph_short_name = out.name.replace("graphify-out-", "")
    base_posix       = out.parent.parent.as_posix()
    claude_md        = (Path.home() / ".claude" / "CLAUDE.md").as_posix()

    prompt_path = out / ".graphify_label_prompt.txt"
    prompt_text = build_label_prompt(
        n=n,
        out=out,
        python_bin=python_bin,
        community_data=community_data,
        out_posix=out_posix,
        n_nodes=n_nodes,
        n_edges=n_edges,
        graph_short_name=graph_short_name,
        base_posix=base_posix,
        claude_md=claude_md,
    )
    prompt_path.write_text(prompt_text, encoding="utf-8")

    print("\n" + "━" * 60)
    print(f"  NEXT: ADD SEMANTIC COMMUNITY LABELS ({n} communities)")
    print()
    print(f"  A self-contained prompt has been written to:")
    print(f"  {prompt_path}")
    print()
    print(f"  Paste it into any LLM (Claude, GPT-4, Gemini, Cursor, Copilot).")
    print(f"  The prompt includes all community data — the LLM needs no extra")
    print(f"  commands or file access to generate the labels.")
    print()
    print(f"  Or automate it:")
    print(f"  ANTHROPIC_API_KEY=<key> python cli.py label {out}")
    print(f"  (~${est_cost:.2f} at Sonnet pricing)")
    print("━" * 60)

    # If API key is set and we're in a TTY, offer to run now
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not (sys.stdin.isatty() and api_key):
        print()
        return

    try:
        answer = input("\n  ANTHROPIC_API_KEY detected — run automated labeling now? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Skipped.")
        return

    if answer in ("y", "yes"):
        _run_labeling(out, communities, G, labels, api_key)
    else:
        print(f"  Skipped. Prompt saved at {prompt_path}\n")


def _run_labeling(out: Path, communities: dict, G, labels: dict, api_key: str) -> None:
    """
    Call Claude API to generate 2-5 word semantic names for each community.
    Batches 100 communities per API call. Updates labels, report, and HTML.
    """
    import re
    import anthropic

    from graphify.analyze import suggest_questions
    from graphify.report import generate
    from graphify.export import to_html

    # Build node label lookup from graph.json for richer context
    graph_path = out / "graph.json"
    node_labels: dict[str, str] = {}
    if graph_path.exists():
        node_labels = node_labels_from_graph(load_graph_json(graph_path))

    client      = anthropic.Anthropic(api_key=api_key)
    batch_size  = 100
    cids        = list(communities.keys())
    new_labels  = dict(labels)   # start from existing
    total_in    = 0
    total_out   = 0
    total_batches = (len(cids) + batch_size - 1) // batch_size

    print()
    for batch_num, i in enumerate(range(0, len(cids), batch_size), 1):
        batch = cids[i : i + batch_size]
        print(f"  Labeling batch {batch_num}/{total_batches} ({len(batch)} communities)...")

        lines = []
        for cid in batch:
            members   = communities[cid][:12]
            names     = [node_labels.get(nid, nid) for nid in members]
            lines.append(f'"{cid}": [{", ".join(names)}]')

        prompt = (
            "Name each code community with a 2–5 word plain-language label. "
            "Describe what the code DOES (e.g. 'Database Migrations', 'Auth & Permissions'). "
            "Return ONLY valid JSON mapping id→name, no extra text.\n\n"
            + "{\n" + ",\n".join(lines) + "\n}"
        )

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        total_in  += resp.usage.input_tokens
        total_out += resp.usage.output_tokens

        text = resp.content[0].text.strip()
        m    = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            new_labels.update(json.loads(m.group()))

    # Persist labels
    int_labels = {int(k): v for k, v in new_labels.items()}
    _save_labels(out, int_labels)

    # Reload analysis and regenerate report + HTML with real labels
    analysis_path = out / ".graphify_analysis.json"
    if analysis_path.exists():
        analysis  = json.loads(analysis_path.read_text(encoding="utf-8"))
        cohesion  = {int(k): v for k, v in analysis["cohesion"].items()}
        gods      = analysis["gods"]
        surprises = analysis["surprises"]
        questions = suggest_questions(G, communities, int_labels)
        report    = generate(
            G, communities, cohesion, int_labels, gods, surprises,
            {"warning": "labels updated post-build"},
            {"input": total_in, "output": total_out},
            str(out),
            suggested_questions=questions,
        )
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        try:
            to_html(G, communities, str(out / "graph.html"), community_labels=int_labels)
        except ValueError:
            pass  # too large for viz — skip

    _update_cost(out, 0, total_in, total_out)
    print(f"\n  Done: {len(new_labels)} communities labeled")
    print(f"  Tokens: {total_in:,} input + {total_out:,} output  (~${(total_in/1e6*3 + total_out/1e6*15):.3f})\n")


def _warn_sensitive(detect_result: dict) -> None:
    skipped = detect_result.get("skipped_sensitive", [])
    if skipped:
        print(f"\n  WARNING: {len(skipped)} sensitive file(s) skipped (credentials/tokens):")
        for f in skipped[:5]:
            print(f"    {f}")
        if len(skipped) > 5:
            print(f"    ... and {len(skipped) - 5} more")
        print()


# ── full pipeline ─────────────────────────────────────────────────────────────

def _run_pipeline(repo: Path, out: Path, *, force: bool = False) -> dict:
    """
    Core pipeline: detect → extract → validate → build → cluster → export all artifacts.
    Must be called with cwd == repo.parent (so .graphifyignore is found).
    `repo` and `out` are relative paths from cwd.
    """
    from graphify.detect import detect
    from graphify.extract import collect_files, extract
    from graphify.validate import validate_extraction
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.manifest import save_manifest
    from graphify.report import generate
    from graphify.export import to_json, to_html

    out_abs = Path(out).resolve()
    out_abs.mkdir(parents=True, exist_ok=True)

    # 1. Detect files — discovers all files + sensitive skips
    print(f"  Detecting files in {repo}...")
    detect_result = detect(repo)
    (out_abs / ".graphify_detect.json").write_text(
        json.dumps(detect_result, indent=2, default=str), encoding="utf-8"
    )
    _warn_sensitive(detect_result)

    # 2. Collect + AST extract
    files = list(collect_files(repo))
    print(f"  {len(files)} code files — AST extraction (no LLM)...")
    ast = extract(files, cache_root=Path(out).parent)

    # 3. Validate extraction
    errors = validate_extraction(ast)
    if errors:
        print(f"  WARNING: {len(errors)} extraction issue(s) — first 5:")
        for e in errors[:5]:
            print(f"    {e}")

    # 4. Build NetworkX graph
    print("  Building graph...")
    G = build_from_json(ast)

    # 5. Cluster + analyze
    print("  Detecting communities...")
    communities = cluster(G)
    cohesion    = score_all(G, communities)
    labels      = _load_labels(communities)
    gods        = god_nodes(G)
    surprises   = surprising_connections(G, communities)
    questions   = suggest_questions(G, communities, labels)

    # 6. Save all artifacts
    _save_labels(out_abs, labels)
    _save_analysis(out_abs, communities, cohesion, gods, surprises, questions)
    _update_cost(out_abs, len(files))

    # Save manifest — enables true incremental update next run
    save_manifest(
        detect_result.get("files", {"code": [str(f) for f in files]}),
        str(out_abs / "manifest.json"),
    )

    # Save raw AST — enables re-cluster without re-extraction
    (out_abs / ".graphify_ast.json").write_text(json.dumps(ast, indent=2), encoding="utf-8")

    # Store interpreter for future runs
    (out_abs / ".graphify_python").write_text(sys.executable, encoding="utf-8")

    # 7. Generate report
    report = generate(
        G, communities, cohesion, labels, gods, surprises,
        {"total_files": len(files), "total_words": detect_result.get("total_words", 0)},
        {"input": 0, "output": 0},
        str(out),
        suggested_questions=questions,
    )
    (out_abs / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

    # 8. Export graph.json + HTML
    print("  Writing graph.json...")
    to_json(G, communities, str(out_abs / "graph.json"), force=force)

    try:
        to_html(G, communities, str(out_abs / "graph.html"), community_labels=labels)
        html = "generated"
    except ValueError:
        html = "skipped (graph too large for viz)"

    stats = {
        "nodes":       G.number_of_nodes(),
        "edges":       G.number_of_edges(),
        "communities": len(communities),
        "files":       len(files),
        "html":        html,
    }
    print(
        f"\n  Done: {stats['nodes']:,} nodes · {stats['edges']:,} edges · "
        f"{stats['communities']} communities | HTML: {html}"
    )

    # 9. Interactive semantic labeling prompt (skipped in CI / non-TTY)
    _prompt_labeling(out_abs, communities, G, labels)
    return stats


# ── public API ────────────────────────────────────────────────────────────────

def build(
    repo_path: str | Path,
    out_dir:   str | Path | None = None,
    *,
    base_dir:        str | Path | None = None,
    venv_dirs:       list[str] | None  = None,
    setup_ignore:    bool = True,
    setup_gitignore: bool = True,
    force:           bool = False,
) -> dict:
    """
    Full build: .graphifyignore setup → detect → AST extract → validate →
    cluster → save analysis + labels + manifest → export graph + HTML + report.

    Args:
        repo_path:       Repo path (absolute, or relative to base_dir/cwd).
        out_dir:         Output dir. Defaults to graphify-out-repos/graphify-out-<name>/.
        base_dir:        Working dir. Defaults to cwd.
        venv_dirs:       Virtualenv dirs to exclude (auto-detected if None).
        setup_ignore:    Write .graphifyignore if missing.
        setup_gitignore: Append graphify entries to .gitignore.
        force:           Overwrite graph.json even if rebuild has fewer nodes.
    """
    ensure_graphify_importable()

    base = Path(base_dir).resolve() if base_dir else Path.cwd()
    repo = (base / repo_path).resolve()
    if not repo.exists():
        raise FileNotFoundError(f"Repo not found: {repo}")
    out = (base / out_dir).resolve() if out_dir else base / "graphify-out-repos" / f"graphify-out-{repo.name}"

    print(f"\n[graphify-build] Building: {repo}")
    print(f"[graphify-build] Output:   {out}\n")

    if setup_ignore and not (repo / ".graphifyignore").exists():
        create_graphifyignore(repo, venv_dirs if venv_dirs is not None else detect_venv_dirs(repo))
    if setup_gitignore:
        update_gitignore(repo)

    saved_cwd = os.getcwd()
    try:
        os.chdir(base)
        return _run_pipeline(repo.relative_to(base), out.relative_to(base), force=force)
    finally:
        os.chdir(saved_cwd)


def update(
    repo_path: str | Path,
    out_dir:   str | Path | None = None,
    *,
    base_dir: str | Path | None = None,
    force:    bool = False,
) -> dict:
    """
    Incremental update: re-extract only changed/new files, prune deleted-file nodes,
    merge into existing graph. Falls back to full build if no manifest exists.

    Much faster than full build for large repos — only touches changed files.
    """
    ensure_graphify_importable()

    base = Path(base_dir).resolve() if base_dir else Path.cwd()
    repo = (base / repo_path).resolve()
    if not repo.exists():
        raise FileNotFoundError(f"Repo not found: {repo}")
    out = (base / out_dir).resolve() if out_dir else base / "graphify-out-repos" / f"graphify-out-{repo.name}"

    print(f"\n[graphify-build] Updating: {repo}")
    print(f"[graphify-build] Output:   {out}\n")

    manifest_path = out / "manifest.json"
    graph_path    = out / "graph.json"

    # Fall back to full build if nothing exists yet
    if not graph_path.exists() or not manifest_path.exists():
        print("  No existing graph/manifest found — running full build...")
        return build(repo_path, out_dir, base_dir=base_dir,
                     setup_ignore=False, setup_gitignore=False, force=force)

    saved_cwd = os.getcwd()
    try:
        os.chdir(base)
        repo_rel = repo.relative_to(base)

        from graphify.manifest import detect_incremental, load_manifest, save_manifest
        from graphify.detect import detect
        from graphify.extract import collect_files, extract
        from graphify.validate import validate_extraction
        from graphify.build import build_from_json, build_merge
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions, graph_diff
        from graphify.report import generate
        from graphify.export import to_json, to_html

        # Detect only what changed since last run
        print("  Checking for changes via manifest...")
        changed = detect_incremental(repo_rel, str(manifest_path))

        # Find deleted files — in old manifest but no longer on disk
        old_manifest     = load_manifest(str(manifest_path))
        current_files    = list(collect_files(repo_rel))
        current_file_set = {str(f) for f in current_files}
        deleted          = [f for f in old_manifest if f not in current_file_set]
        new_or_modified  = [f for cat in changed.get("files", {}).values() for f in cat]

        if not new_or_modified and not deleted:
            print("  Nothing changed — graph is already up to date.\n")
            return {"status": "up_to_date"}

        print(f"  Changed: {len(new_or_modified)} file(s)  |  Deleted: {len(deleted)} file(s)")

        # Load old graph for diff comparison
        old_raw = json.loads(graph_path.read_text(encoding="utf-8"))
        G_old   = build_from_json(old_raw)

        # Extract only changed files
        if new_or_modified:
            print(f"  Extracting {len(new_or_modified)} changed file(s)...")
            new_chunks = extract([Path(f) for f in new_or_modified], cache_root=out.parent)
            errors = validate_extraction(new_chunks)
            if errors:
                print(f"  WARNING: {len(errors)} validation issue(s) in changed files")
            G = build_merge([new_chunks], graph_path=str(graph_path),
                            prune_sources=deleted or None)
        else:
            G = build_merge([], graph_path=str(graph_path), prune_sources=deleted)

        # Show what changed
        diff = graph_diff(G_old, G)
        print(f"  Graph diff: {diff['summary']}")

        # Re-cluster + analyze, preserving any existing semantic labels
        print("  Re-clustering...")
        communities = cluster(G)
        cohesion    = score_all(G, communities)
        labels      = _load_labels(communities)
        labels_path = out / ".graphify_labels.json"
        if labels_path.exists():
            saved = json.loads(labels_path.read_text(encoding="utf-8"))
            for cid in communities:
                if str(cid) in saved:
                    labels[cid] = saved[str(cid)]
        gods      = god_nodes(G)
        surprises = surprising_connections(G, communities)
        questions = suggest_questions(G, communities, labels)

        # Save artifacts
        _save_labels(out, labels)
        _save_analysis(out, communities, cohesion, gods, surprises, questions)
        _update_cost(out, len(current_files))

        # Update manifest + detect
        detect_result = detect(repo_rel)
        (out / ".graphify_detect.json").write_text(
            json.dumps(detect_result, indent=2, default=str), encoding="utf-8"
        )
        _warn_sensitive(detect_result)
        save_manifest(
            detect_result.get("files", {"code": [str(f) for f in current_files]}),
            str(manifest_path),
        )

        # Export
        report = generate(
            G, communities, cohesion, labels, gods, surprises,
            {"total_files": len(current_files), "total_words": detect_result.get("total_words", 0)},
            {"input": 0, "output": 0},
            str(out.relative_to(base)),
            suggested_questions=questions,
        )
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        to_json(G, communities, str(out / "graph.json"), force=True)

        try:
            to_html(G, communities, str(out / "graph.html"), community_labels=labels)
            html = "generated"
        except ValueError:
            html = "skipped"

        stats = {
            "nodes":         G.number_of_nodes(),
            "edges":         G.number_of_edges(),
            "communities":   len(communities),
            "files_total":   len(current_files),
            "files_changed": len(new_or_modified),
            "files_deleted": len(deleted),
            "diff":          diff["summary"],
            "html":          html,
        }
        print(
            f"\n  Done: {stats['nodes']:,} nodes · {stats['edges']:,} edges · "
            f"{stats['communities']} communities | {diff['summary']} | HTML: {html}"
        )
        # Only prompt if labels are still generic (no semantic labels survived re-cluster)
        generic = sum(1 for v in labels.values() if v.startswith("Community "))
        if generic == len(labels):
            _prompt_labeling(out, communities, G, labels)
        return stats

    finally:
        os.chdir(saved_cwd)


def cluster_only(graph_json: str | Path) -> dict:
    """
    Re-run community detection on an existing graph.json without re-extracting.
    Preserves existing semantic labels where community IDs match.
    """
    ensure_graphify_importable()

    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json, to_html

    graph_path = Path(graph_json).resolve()
    out        = graph_path.parent

    print(f"\n[graphify-build] Re-clustering: {graph_path}\n")
    raw = load_graph_json(graph_path)
    G   = build_from_json(raw)
    print(f"  Loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    communities = cluster(G)
    cohesion    = score_all(G, communities)
    # Preserve existing semantic labels for community IDs that survived re-cluster
    labels = _load_labels(communities)
    labels_path = out / ".graphify_labels.json"
    if labels_path.exists():
        saved = json.loads(labels_path.read_text(encoding="utf-8"))
        for cid in communities:
            if str(cid) in saved:
                labels[cid] = saved[str(cid)]
    gods      = god_nodes(G)
    surprises = surprising_connections(G, communities)
    questions = suggest_questions(G, communities, labels)

    _save_labels(out, labels)
    _save_analysis(out, communities, cohesion, gods, surprises, questions)

    report = generate(
        G, communities, cohesion, labels, gods, surprises,
        {"warning": "cluster-only — no file stats"},
        {"input": 0, "output": 0},
        str(out),
        suggested_questions=questions,
    )
    (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(out / "graph.json"), force=True)

    try:
        to_html(G, communities, str(out / "graph.html"), community_labels=labels)
        html = "generated"
    except ValueError:
        html = "skipped"

    stats = {
        "nodes":       G.number_of_nodes(),
        "edges":       G.number_of_edges(),
        "communities": len(communities),
        "html":        html,
    }
    print(f"  Done: {stats['nodes']:,} nodes · {stats['communities']} communities | HTML: {html}")
    _prompt_labeling(out, communities, G, labels)
    return stats


def label_communities(graph_dir: str | Path) -> dict:
    """
    Standalone semantic labeling: read analysis.json + graph.json, call Claude,
    write .graphify_labels.json, regenerate GRAPH_REPORT.md and graph.html.
    Requires ANTHROPIC_API_KEY env var.
    """
    ensure_graphify_importable()

    from graphify.build import build_from_json

    out        = Path(graph_dir).resolve()
    graph_path = out / "graph.json"
    analysis_path = out / ".graphify_analysis.json"

    if not graph_path.exists():
        raise FileNotFoundError(f"graph.json not found in {out}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY env var is not set")

    raw = load_graph_json(graph_path)
    G   = build_from_json(raw)

    # Prefer analysis.json (new pipeline); fall back to community IDs in graph.json nodes
    if analysis_path.exists():
        analysis    = json.loads(analysis_path.read_text(encoding="utf-8"))
        communities = {int(k): v for k, v in analysis["communities"].items()}
    else:
        communities = communities_from_graph(raw)

    labels = _load_labels(communities)   # generic fallback

    print(f"\n[graphify-build] Semantic labeling: {out}")
    print(f"  {len(communities)} communities to label\n")
    _run_labeling(out, communities, G, labels, api_key)
    return {"communities": len(communities)}


def wiki(graph_dir: str | Path) -> int:
    """
    Generate a Wikipedia-style wiki from an existing graph.
    Writes graphify-out-<name>/wiki/index.md + one article per community + one per god node.
    Agent-crawlable — structured for AI assistants to navigate.
    Uses community IDs already stored in graph.json nodes (stable across runs).
    """
    ensure_graphify_importable()

    from graphify.build import build_from_json
    from graphify.analyze import god_nodes
    from graphify.wiki import to_wiki

    out        = Path(graph_dir).resolve()
    graph_path = out / "graph.json"
    if not graph_path.exists():
        raise FileNotFoundError(f"graph.json not found in {out}")

    print(f"\n[graphify-build] Generating wiki: {out}\n")
    raw         = load_graph_json(graph_path)
    G           = build_from_json(raw)
    # Use communities already embedded in graph.json — never re-cluster here,
    # Leiden IDs are non-deterministic and would invalidate saved labels.
    communities = communities_from_graph(raw)
    labels      = _load_labels(communities)
    # Load saved semantic labels if they exist
    labels_path = out / ".graphify_labels.json"
    if labels_path.exists():
        saved = json.loads(labels_path.read_text(encoding="utf-8"))
        labels = {int(k): v for k, v in saved.items() if int(k) in communities}
    gods        = god_nodes(G)

    wiki_dir = out / "wiki"
    n = to_wiki(G, communities, wiki_dir, community_labels=labels, god_nodes_data=gods)
    print(f"  {n} articles written → {wiki_dir}/")
    return n
