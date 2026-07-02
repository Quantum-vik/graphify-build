"""Query, path, explain, affected — thin wrappers around the graphify CLI."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .utils import find_graphify_binary


def _run(args: list[str]) -> str:
    binary = find_graphify_binary()
    try:
        result = subprocess.run([binary] + args, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            "graphify CLI not found. Install with:  uv tool install graphifyy  (or: pip install graphifyy)"
        )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def query(
    graph_json: str | Path,
    question: str,
    *,
    dfs: bool = False,
    budget: int = 2000,
) -> str:
    """BFS (default) or DFS traversal of graph.json to answer a question."""
    args = ["query", question, "--graph", str(graph_json), "--budget", str(budget)]
    if dfs:
        args.append("--dfs")
    return _run(args)


def shortest_path(graph_json: str | Path, node_a: str, node_b: str) -> str:
    """Find the shortest path between two nodes in the graph."""
    return _run(["path", node_a, node_b, "--graph", str(graph_json)])


def explain(graph_json: str | Path, node_name: str) -> str:
    """Plain-language explanation of a node and its immediate neighbors."""
    return _run(["explain", node_name, "--graph", str(graph_json)])


def affected(
    graph_json: str | Path,
    node: str,
    *,
    depth: int = 2,
    relations: str | None = None,
) -> str:
    """
    BFS reverse traversal — find all nodes impacted by a change to `node`.
    Useful for blast-radius analysis before touching a god node.
    """
    args = ["affected", node, "--graph", str(graph_json), "--depth", str(depth)]
    if relations:
        args += ["--relations", relations]
    return _run(args)
