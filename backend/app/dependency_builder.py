"""
dependency_builder.py
─────────────────────
Pure-Python dependency graph construction.
Refactored to build a noise-filtered, clean architectural dependency graph.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.models import GraphNode, GraphEdge

logger = logging.getLogger(__name__)

# ── 1. Import extraction regexes ──────────────────────────────────────────

_JS_IMPORT = re.compile(
    r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)

_PY_IMPORT = re.compile(
    r"""(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))""",
    re.MULTILINE,
)

_JAVA_IMPORT = re.compile(r"import\s+([\w.]+);", re.MULTILINE)
_PHP_IMPORT = re.compile(
    r"""(?:include|include_once|require|require_once)\s*(?:\(\s*)?['"]([^'"]+)['"]""",
    re.IGNORECASE | re.MULTILINE,
)


# ── 2. Layer inference & Scoring ──────────────────────────────────────────

_LAYER_KEYWORDS: list[tuple[str, str]] = [
    ("route",      "route"),
    ("controller", "controller"),
    ("service",    "service"),
    ("model",      "model"),
    ("api",        "api"),
    ("store",      "store"),
    ("context",    "context"),
    ("core",       "core"),
    ("component",  "ui"),
    ("view",       "ui"),
    ("page",       "ui"),
    ("middleware", "middleware"),
]

def _infer_layer(path: str) -> str:
    lower = path.lower()
    for keyword, layer in _LAYER_KEYWORDS:
        if keyword in lower:
            return layer
    return "unknown"

def architectural_scorer(path: str) -> int:
    """Step 2: Assign architectural relevance score."""
    score = 0
    normalised = path.replace("\\", "/").lower()
    
    # +5 for architectural keywords
    for keyword, _ in _LAYER_KEYWORDS:
        if keyword in normalised:
            score += 5
            break  # only award once
            
    parts = normalised.split("/")
    
    # +3 if inside key directories
    if len(parts) > 0 and parts[0] in {"src", "server", "backend", "app"}:
        score += 3
        
    # +2 if shallow depth (closer to root)
    if len(parts) <= 2:
        score += 2
        
    return score


# ── 3. Noise Filter ───────────────────────────────────────────────────────

_NOISE_EXTENSIONS = {
    ".css", ".scss", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico"
}

def noise_filter(path: str) -> bool:
    """Step 1: Return True if path should be PRESERVED, False if it is NOISE."""
    lower = path.replace("\\", "/").lower()
    
    # Check simple extensions
    _, ext = os.path.splitext(lower)
    if ext in _NOISE_EXTENSIONS:
        return False
        
    # Check compound extensions
    if lower.endswith(".module.css") or lower.endswith(".module.scss"):
        return False
        
    if lower.endswith(".json"):
        if not ("config" in lower or "core" in lower):
            return False
            
    # Ignore test/storybook files
    if "test" in lower or "spec" in lower or "storybook" in lower or "stories." in lower:
        return False
        
    # Ignore pure UI style helper files
    if "style" in lower or "theme" in lower:
        return False
        
    return True


# ── 4. Import extraction & resolution ─────────────────────────────────────

def _resolve_js_import(raw: str, file_dir: str, all_paths_set: set[str]) -> str | None:
    if not raw.startswith("."):
        return None
    joined = os.path.normpath(os.path.join(file_dir, raw)).replace("\\", "/")
    for suffix in ("", ".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
        candidate = joined + suffix
        if candidate in all_paths_set:
            return candidate
    return None

def _resolve_py_import(raw: str, all_paths_set: set[str]) -> str | None:
    as_path = raw.replace(".", "/")
    for suffix in (".py", "/__init__.py"):
        candidate = as_path + suffix
        if candidate in all_paths_set:
            return candidate
    return None

def _resolve_java_import(raw: str, all_paths_set: set[str]) -> str | None:
    as_path = raw.replace(".", "/") + ".java"
    for prefix in ("", "src/main/java/"):
        candidate = prefix + as_path
        if candidate in all_paths_set:
            return candidate
    return None

def _resolve_php_import(raw: str, file_dir: str, all_paths_set: set[str]) -> str | None:
    normalized_raw = raw.replace("\\", "/").strip()
    candidates: list[str] = []

    if normalized_raw.startswith("."):
        candidates.append(os.path.normpath(os.path.join(file_dir, normalized_raw)).replace("\\", "/"))
    else:
        candidates.append(normalized_raw)
        candidates.append(os.path.normpath(os.path.join(file_dir, normalized_raw)).replace("\\", "/"))

    for candidate in candidates:
        if candidate in all_paths_set:
            return candidate
    return None

def import_extractor(content: str, path: str, all_paths_set: set[str]) -> list[str]:
    """Extract and resolve imports for a given file."""
    ext = os.path.splitext(path)[1].lower()
    file_dir = os.path.dirname(path).replace("\\", "/")
    deps: list[str | None] = []
    
    if ext in {".js", ".ts", ".jsx", ".tsx"}:
        for m in _JS_IMPORT.finditer(content):
            raw = m.group(1) or m.group(2)
            deps.append(_resolve_js_import(raw, file_dir, all_paths_set))
    elif ext == ".py":
        for m in _PY_IMPORT.finditer(content):
            raw = m.group(1) or m.group(2)
            deps.append(_resolve_py_import(raw, all_paths_set))
    elif ext == ".java":
        for m in _JAVA_IMPORT.finditer(content):
            raw = m.group(1)
            deps.append(_resolve_java_import(raw, all_paths_set))
    elif ext == ".php":
        for m in _PHP_IMPORT.finditer(content):
            raw = m.group(1)
            deps.append(_resolve_php_import(raw, file_dir, all_paths_set))
            
    return [d for d in deps if d is not None and noise_filter(d)]


# ── 5. Graph Pruning & Formatting ─────────────────────────────────────────

def graph_pruner(adjacency: dict[str, list[str]]) -> tuple[dict[str, GraphNode], list[GraphEdge]]:
    """Step 3 & 4: Sort by score, keep top 50 nodes, and prune edges to match.
    By strictly discarding unselected nodes, nested component chains naturally
    collapse or end at their highest architectural representation.
    """
    unique_paths = set(adjacency.keys())
    for deps in adjacency.values():
        unique_paths.update(deps)
        
    unique_paths = {p for p in unique_paths if noise_filter(p)}
    
    scored = [(p, architectural_scorer(p)) for p in unique_paths]
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # Keep top 50
    top_paths = {p for p, _ in scored[:50]}
    
    nodes_map: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    
    for path in top_paths:
        nodes_map[path] = GraphNode(
            id=path,
            label=os.path.basename(path),
            layer=_infer_layer(path)
        )
        
    for source in top_paths:
        if source in adjacency:
            for target in adjacency[source]:
                if target in top_paths:
                    edges.append(GraphEdge(source=source, target=target))
                    
    return nodes_map, edges

def _generate_architecture_summary(nodes: list[GraphNode]) -> str:
    """Step 6: Optional architecture summary generation."""
    layers = {n.layer for n in nodes if n.layer != "unknown"}
    if "ui" in layers and not ("controller" in layers or "route" in layers):
        return "This project uses component-driven frontend architecture with centralized modules."
    if "route" in layers or "controller" in layers or "service" in layers:
        return "This project follows layered backend architecture with route, controller, and/or service patterns."
    return "This project employs a modular architectural style based on structured directory separation."

def build_dependency_graph(
    file_contents: dict[str, str],
    all_tree_paths: list[str],
) -> tuple[list[GraphNode], list[GraphEdge], str]:
    """Main pipeline execution for dependency graph."""
    all_paths_set = set(all_tree_paths)
    adjacency: dict[str, list[str]] = {}
    
    for path, content in file_contents.items():
        if not noise_filter(path):
            continue
        deps = import_extractor(content, path, all_paths_set)
        adjacency[path] = deps
        
    nodes_map, edges = graph_pruner(adjacency)
    nodes_list = list(nodes_map.values())
    
    summary = _generate_architecture_summary(nodes_list)
    
    logger.info("Dependency graph pruned to %d nodes, %d edges", len(nodes_list), len(edges))
    return nodes_list, edges, summary
