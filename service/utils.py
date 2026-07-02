"""Python detection, .graphifyignore, and .gitignore helpers."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ── Python / graphify detection ───────────────────────────────────────────────

def find_graphify_python() -> str | None:
    """Return path to the Python interpreter that has graphify installed."""
    system = platform.system()

    if system == "Windows":
        candidates = [
            Path.home() / "AppData" / "Roaming" / "uv" / "tools" / "graphifyy" / "Scripts" / "python.exe",
            Path.home() / ".local" / "share"  / "uv" / "tools" / "graphifyy" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            Path.home() / ".local" / "share" / "uv" / "tools" / "graphifyy" / "bin" / "python",
            Path.home() / ".local" / "share" / "uv" / "tools" / "graphifyy" / "bin" / "python3",
        ]

    for p in candidates:
        if p.exists():
            return str(p)

    # Fall back: read shebang from `graphify` binary
    which_cmd = "where" if system == "Windows" else "which"
    try:
        r = subprocess.run([which_cmd, "graphify"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            # Windows `where` can return multiple matches — take the first line.
            bin_path = r.stdout.strip().splitlines()[0].strip()
            with open(bin_path, encoding="utf-8", errors="ignore") as f:
                first = f.readline().strip()
            if first.startswith("#!"):
                interp = first[2:].strip().split()[0]
                if Path(interp).exists():
                    return interp
    except Exception:
        pass

    return None


def find_graphify_binary() -> str:
    """Return path to the graphify CLI binary."""
    system = platform.system()
    exe    = "graphify.exe" if system == "Windows" else "graphify"

    # Next to the running interpreter first — covers venvs, conda, and running
    # cli.py directly with the uv-tool Python on any OS.
    sibling = Path(sys.executable).parent / exe
    if sibling.exists():
        return str(sibling)

    if system == "Windows":
        candidates = [
            Path.home() / "AppData" / "Roaming" / "uv" / "tools" / "graphifyy" / "Scripts" / "graphify.exe",
            Path.home() / ".local" / "share"  / "uv" / "tools" / "graphifyy" / "Scripts" / "graphify.exe",
        ]
    else:
        candidates = [
            Path.home() / ".local" / "bin" / "graphify",
            Path.home() / ".local" / "share" / "uv" / "tools" / "graphifyy" / "bin" / "graphify",
        ]
    for p in candidates:
        if p.exists():
            return str(p)

    # PATH lookup (shutil.which handles PATHEXT on Windows)
    return shutil.which("graphify") or "graphify"


def ensure_graphify_importable() -> None:
    """Patch sys.path so `import graphify` works regardless of active Python."""
    try:
        import graphify  # noqa: F401
        return
    except ImportError:
        pass

    python = find_graphify_python()
    if not python:
        raise RuntimeError(
            "graphifyy not installed.\n"
            "Install with:  uv tool install graphifyy\n"
            "       or:     pip install graphifyy"
        )

    r = subprocess.run(
        [python, "-c", "import site, json; print(json.dumps(site.getsitepackages()))"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Could not get site-packages from {python}: {r.stderr}")

    for sp in json.loads(r.stdout.strip()):
        if sp not in sys.path:
            sys.path.insert(0, sp)

    try:
        import graphify  # noqa: F401
    except ImportError:
        raise RuntimeError(f"graphifyy at {python} is still not importable after patching sys.path")


# ── graph.json helpers ───────────────────────────────────────────────────────

def load_graph_json(graph_path: str | Path) -> dict:
    """Read and parse graph.json, raise FileNotFoundError if missing."""
    p = Path(graph_path)
    if not p.exists():
        raise FileNotFoundError(f"graph.json not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def communities_from_graph(graph_data: dict) -> dict[int, list[str]]:
    """
    Reconstruct {community_id: [node_id, ...]} from graph.json node attributes.
    Used when .graphify_analysis.json is absent (graphs built before v2 pipeline).
    """
    from collections import defaultdict
    result: dict[int, list[str]] = defaultdict(list)
    for node in graph_data.get("nodes", []):
        c = node.get("community")
        if c is not None:
            result[int(c)].append(node["id"])
    return dict(result)


def node_labels_from_graph(graph_data: dict) -> dict[str, str]:
    """Return {node_id: human_label} from graph.json nodes."""
    return {n["id"]: n.get("label", n["id"]) for n in graph_data.get("nodes", [])}


# ── .graphifyignore ───────────────────────────────────────────────────────────

_DEFAULT_IGNORE = """\
# graphify ignore — code-only graph, zero LLM cost
*.pdf
*.html
*.txt
*.md
*.yml
*.yaml
*.log
*.png
*.jpg
*.jpeg
*.svg
*.gif
*.json
*.sh
*.toml
*.ini
*.xml
*.csv
*.parquet
*.db
*.sqlite3
*.pem
*.key
*.cert
*.zip
*.tar.gz
*.whl
*.egg-info
# Always-noise: minified bundles and source maps (project-type independent)
*.min.js
*.min.css
*.map
# Compiled output and vendor deps — never source code
node_modules/
dist/
build/
.next/
.nuxt/
out/
__pycache__/
*.pyc
"""

_GITIGNORE_LINES = ["graphify-out*/", ".graphifyignore"]


def create_graphifyignore(repo: Path, venv_dirs: list[str]) -> None:
    target = repo / ".graphifyignore"
    content = _DEFAULT_IGNORE
    if venv_dirs:
        content += "\n# Virtualenv / deps\n" + "".join(f"{d}\n" for d in venv_dirs)
    target.write_text(content, encoding="utf-8")
    print(f"  Created {target}")


def update_gitignore(repo: Path) -> None:
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    additions = [ln for ln in _GITIGNORE_LINES if ln not in existing]
    if additions:
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n# graphify\n" + "".join(f"{ln}\n" for ln in additions))
        print(f"  Updated {gitignore}")


def detect_venv_dirs(repo: Path) -> list[str]:
    """Auto-detect virtualenv directories to exclude."""
    common = ["venv", ".venv", "env", "node_modules", ".tox", "site-packages"]
    found = [d + "/" for d in common if (repo / d).is_dir()]
    for child in repo.iterdir():
        if child.is_dir() and (child / "pyvenv.cfg").exists():
            entry = child.name + "/"
            if entry not in found:
                found.append(entry)
    return found
