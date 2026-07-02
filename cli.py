#!/usr/bin/env python3
"""
graphify-build CLI
==================
Run with the Python that has graphifyy installed:
  ~/.local/share/uv/tools/graphifyy/bin/python cli.py <command> ...

Output resolution for build / update
--------------------------------------
  --name doc   →  graphify-out-repos/graphify-out-doc/       (recommended)
  --out <path> →  exactly that path                           (full control)
  (neither)    →  graphify-out-repos/graphify-out-<RepoFolder>/

Commands
--------
  build    <repo> [--name N] [--out DIR] [--base DIR] [--venv DIR ...] [--force]
  update   <repo> [--name N] [--out DIR] [--base DIR] [--force]
  cluster  <graph_json>
  wiki     <graph_dir>
  query    <graph_json> "<question>" [--dfs] [--budget N]
  path     <graph_json> "NodeA" "NodeB"
  explain  <graph_json> "NodeName"
  affected <graph_json> "NodeName" [--depth N] [--relations calls,imports]
  label    <graph_dir>
  hook     install|uninstall <repo_path>
  list     [--base DIR]  List all graphs in graphify-out-repos/

Examples (run from your project root)
----------------------------------------
  python graphify-build/cli.py build MyBackend --name mybackend
  python graphify-build/cli.py build MyFrontend --name frontend
  python graphify-build/cli.py update MyBackend --name mybackend
  python graphify-build/cli.py cluster graphify-out-repos/graphify-out-mybackend/graph.json
  python graphify-build/cli.py wiki graphify-out-repos/graphify-out-mybackend
  python graphify-build/cli.py query graphify-out-repos/graphify-out-mybackend/graph.json "how does auth work?"
  python graphify-build/cli.py path graphify-out-repos/graphify-out-mybackend/graph.json "AuthService" "UserModel"
  python graphify-build/cli.py explain graphify-out-repos/graphify-out-mybackend/graph.json "AuthService"
  python graphify-build/cli.py affected graphify-out-repos/graphify-out-mybackend/graph.json "AuthService" --depth 2
  python graphify-build/cli.py label graphify-out-repos/graphify-out-mybackend
  python graphify-build/cli.py hook install MyBackend
"""
import argparse
import sys


def _safe_console() -> None:
    # Windows cp1252 consoles/redirects can't encode pipeline chars (━, ·) — degrade gracefully.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _safe_console()
    parser = argparse.ArgumentParser(
        prog="graphify-build",
        description="Build and query graphify knowledge graphs for any repo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    from service import __version__
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ── build ─────────────────────────────────────────────────────────────────
    p = sub.add_parser("build", help="Full build: detect + extract + cluster + export all artifacts")
    p.add_argument("repo",   help="Path to repo (absolute, or relative to --base/cwd)")
    p.add_argument("--name", help="Short name → graphify-out-repos/graphify-out-<name>/")
    p.add_argument("--out",  help="Full custom output path (overrides --name and default)")
    p.add_argument("--base", help="Working directory (default: cwd)")
    p.add_argument("--venv", nargs="*", metavar="DIR",
                   help="Virtualenv dir names to exclude (auto-detected if omitted)")
    p.add_argument("--force", action="store_true",
                   help="Overwrite graph.json even if rebuild has fewer nodes")
    p.add_argument("--no-register", action="store_true",
                   help="Skip registering the graph in ~/.claude/CLAUDE.md")

    # ── update ────────────────────────────────────────────────────────────────
    p = sub.add_parser("update",
                        help="Incremental update: re-extract only changed files, prune deleted nodes")
    p.add_argument("repo",   help="Path to repo")
    p.add_argument("--name", help="Short name → graphify-out-repos/graphify-out-<name>/")
    p.add_argument("--out",  help="Full custom output path")
    p.add_argument("--base", help="Working directory (default: cwd)")
    p.add_argument("--force", action="store_true",
                   help="Force graph.json overwrite even when node count drops")
    p.add_argument("--no-register", action="store_true",
                   help="Skip registering the graph in ~/.claude/CLAUDE.md")

    # ── cluster ───────────────────────────────────────────────────────────────
    p = sub.add_parser("cluster",
                        help="Re-run community detection on existing graph.json (no re-extraction)")
    p.add_argument("graph", help="Path to graph.json")

    # ── wiki ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("wiki",
                        help="Generate agent-crawlable wiki (index.md + one article per community + god node)")
    p.add_argument("graph_dir", help="Path to graphify-out-<name>/ directory (not graph.json)")

    # ── query ─────────────────────────────────────────────────────────────────
    p = sub.add_parser("query", help="BFS/DFS traversal to answer a natural-language question")
    p.add_argument("graph",    help="Path to graph.json")
    p.add_argument("question", help="Natural-language question")
    p.add_argument("--dfs", action="store_true", help="Depth-first instead of breadth-first")
    p.add_argument("--budget", type=int, default=2000, metavar="N",
                   help="Token budget for the answer (default: 2000)")

    # ── path ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("path", help="Shortest path between two nodes")
    p.add_argument("graph",  help="Path to graph.json")
    p.add_argument("node_a", help="Source node label")
    p.add_argument("node_b", help="Target node label")

    # ── explain ───────────────────────────────────────────────────────────────
    p = sub.add_parser("explain", help="Plain-language explanation of a node and its neighbors")
    p.add_argument("graph", help="Path to graph.json")
    p.add_argument("node",  help="Node label to explain")

    # ── affected ──────────────────────────────────────────────────────────────
    p = sub.add_parser("affected",
                        help="Blast-radius: find all nodes impacted by changing a given node")
    p.add_argument("graph", help="Path to graph.json")
    p.add_argument("node",  help="Node label to analyse")
    p.add_argument("--depth", type=int, default=2,
                   help="BFS traversal depth (default: 2)")
    p.add_argument("--relations", metavar="R1,R2",
                   help="Filter by relation types e.g. calls,imports")

    # ── label ─────────────────────────────────────────────────────────────────
    p = sub.add_parser("label",
                        help="Semantically label communities using Claude (requires ANTHROPIC_API_KEY)")
    p.add_argument("graph_dir", help="Path to graphify-out-<name>/ directory")

    # ── hook ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("hook",
                        help="Install/uninstall git hooks that auto-update the graph on every commit")
    p.add_argument("action", choices=["install", "uninstall"])
    p.add_argument("repo",   help="Path to the repo to install hooks in")

    # ── list ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("list",
                        help="List all graphs in graphify-out-repos/ (size, labels, last update)")
    p.add_argument("--base", help="Working directory (default: cwd)")

    args = parser.parse_args()

    from service import build, update, cluster_only, wiki, label_communities, list_graphs
    from service.queries import query, shortest_path, explain, affected
    from service.utils import find_graphify_binary
    import subprocess

    def _resolve_out(args) -> str | None:
        if args.out:
            return args.out
        if hasattr(args, "name") and args.name:
            return f"graphify-out-repos/graphify-out-{args.name}"
        return None

    try:
        if args.cmd == "build":
            build(args.repo, _resolve_out(args), base_dir=args.base,
                  venv_dirs=args.venv, force=args.force,
                  register=not args.no_register)

        elif args.cmd == "update":
            update(args.repo, _resolve_out(args), base_dir=args.base, force=args.force,
                   register=not args.no_register)

        elif args.cmd == "cluster":
            cluster_only(args.graph)

        elif args.cmd == "wiki":
            wiki(args.graph_dir)

        elif args.cmd == "query":
            print(query(args.graph, args.question, dfs=args.dfs, budget=args.budget))

        elif args.cmd == "path":
            print(shortest_path(args.graph, args.node_a, args.node_b))

        elif args.cmd == "explain":
            print(explain(args.graph, args.node))

        elif args.cmd == "affected":
            print(affected(args.graph, args.node, depth=args.depth,
                           relations=args.relations))

        elif args.cmd == "label":
            label_communities(args.graph_dir)

        elif args.cmd == "hook":
            binary = find_graphify_binary()
            result = subprocess.run(
                [binary, "hook", args.action],
                cwd=args.repo, capture_output=False,
            )
            sys.exit(result.returncode)

        elif args.cmd == "list":
            list_graphs(args.base)

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
