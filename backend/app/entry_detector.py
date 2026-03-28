"""
entry_detector.py
─────────────────
Robust deterministic entry-point detection across backend, frontend,
static-site and multi-language repositories.

Design principles:
• Only runtime-eligible files are considered
• Infra / docs / metadata files are excluded early
• Repository type heuristic influences scoring
• Safe fallback returns ENTRY_NOT_FOUND (never random file)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional, Tuple

from app.github_service import fetch_file_content

logger = logging.getLogger(__name__)


# ───────────────── Runtime-eligible extensions ─────────────────

_RUNTIME_EXT = {
    ".js", ".ts", ".jsx", ".tsx",
    ".py",
    ".java",
    ".html",
    ".php",
}

_EXCLUDED_EXT = {
    ".md", ".yaml", ".yml", ".txt",
    ".css", ".scss", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
}

# ───────────────── Conventional starter basenames ─────────────────

_CONVENTIONAL = {
    # Node backend
    "server.js", "app.js", "index.js",
    "server.ts", "app.ts", "index.ts",

    # Python
    "main.py", "app.py", "run.py", "manage.py", "wsgi.py", "asgi.py",

    # Java
    "application.java",

    # Frontend SPA
    "main.jsx", "main.tsx", "index.jsx", "index.tsx",

    # Static / framework bootstrap
    "docusaurus.config.js",
    "vite.config.js",
    "next.config.js",
    "webpack.config.js",

    # PHP
    "index.php",
    "app.php",
}

# ───────────────── Repo-type detection ─────────────────

def _detect_repo_type(paths: List[str]) -> str:
    lower = [p.lower() for p in paths]

    if any("docusaurus.config" in p for p in lower):
        return "static_site"

    if any("vite.config" in p or "next.config" in p for p in lower):
        return "frontend"

    if any(p.endswith("server.js") or p.endswith("app.py") for p in lower):
        return "backend"

    if any(p.endswith(".php") for p in lower):
        return "php_web"

    return "generic"


# ───────────────── Runtime candidate filter ─────────────────

def _is_runtime_candidate(path: str) -> bool:
    path_lower = path.lower()

    # ignore hidden / infra files
    if path_lower.startswith("."):
        return False

    ext = os.path.splitext(path_lower)[1]

    if ext in _EXCLUDED_EXT:
        return False

    if ext in _RUNTIME_EXT:
        return True

    # allow known framework config even without runtime ext rule
    if os.path.basename(path_lower) in _CONVENTIONAL:
        return True

    return False


# ───────────────── package.json parsing ─────────────────

async def _parse_package_json(owner: str, repo: str, tree_paths: List[str]) -> Optional[str]:
    if "package.json" not in tree_paths:
        return None

    content = await fetch_file_content(owner, repo, "package.json")
    if not content:
        return None

    try:
        pkg = json.loads(content)
    except json.JSONDecodeError:
        return None

    if pkg.get("main"):
        return pkg["main"]

    start_script = pkg.get("scripts", {}).get("start", "")
    match = re.search(r"(?:node|nodemon|ts-node|tsx|vite)\s+(\S+\.(?:js|ts|mjs|jsx|tsx))", start_script)
    if match:
        return match.group(1)

    return None


# ───────────────── Candidate scoring ─────────────────

def _score_candidate(
    path: str,
    repo_type: str,
    config_entry: Optional[str],
) -> int:
    score = 0
    norm = path.replace("\\", "/")
    base = os.path.basename(norm).lower()
    depth = len(norm.split("/"))

    # config reference boost
    if config_entry:
        config_norm = config_entry.replace("\\", "/").strip("./")
        if norm.endswith(config_norm):
            score += 10

    # repo-type specific boost
    if repo_type == "backend" and base in {
        "server.js", "app.js", "main.py", "run.py", "application.java"
    }:
        score += 8

    if repo_type == "static_site" and base == "docusaurus.config.js":
        score += 10

    if repo_type == "frontend" and base in {
        "vite.config.js", "next.config.js", "webpack.config.js"
    }:
        score += 8

    if repo_type == "php_web":
        if base == "index.php":
            score += 10
        if norm == "public/index.php":
            score += 8
        if "/admin/" in f"/{norm}":
            score -= 2

    # shallow depth preferred
    score += max(0, 5 - depth)

    # conventional name bonus
    if base in _CONVENTIONAL:
        score += 4

    # inside src bonus
    if norm.lower().startswith("src/"):
        score += 3

    return score


# ───────────────── Public API ─────────────────

async def detect_entry_point(
    owner: str,
    repo: str,
    tree_paths: List[str],
) -> str:
    if not tree_paths:
        return "ENTRY_NOT_FOUND"

    repo_type = _detect_repo_type(tree_paths)
    logger.info("Repo classified as: %s", repo_type)

    config_entry = await _parse_package_json(owner, repo, tree_paths)

    candidates: List[Tuple[str, int]] = []

    for path in tree_paths:
        if not _is_runtime_candidate(path):
            continue

        score = _score_candidate(path, repo_type, config_entry)
        if score > 0:
            candidates.append((path, score))

    if not candidates:
        logger.warning("No runtime entry candidates found.")
        return "ENTRY_NOT_FOUND"

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_path, best_score = candidates[0]

    logger.info("Detected entry point: %s (score=%d)", best_path, best_score)
    return best_path
