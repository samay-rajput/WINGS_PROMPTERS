"""
file_filter_service.py
──────────────────────
Filters and priority-scores the flat file tree returned by GitHub.

Scoring heuristic (per spec):
  +5  path starts with  src/
  +3  path segment contains  controller / service / model / route / api / handler
  +2  shallow depth (≤ 2 segments)
  +2  inside backend-like folder (server, app, core, backend, lib)

After scoring, returns the top MAX_FILES_TO_PROCESS paths.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import ALLOWED_EXTENSIONS, IGNORED_DIRS, MAX_FILES_TO_PROCESS

logger = logging.getLogger(__name__)

_ARCH_KEYWORDS = {
    "controller", "service", "model", "route", "api", "handler",
    "middleware", "util", "helper", "repository", "manager", "provider",
    "factory", "resolver", "dispatcher", "registry",
}
_BACKEND_FOLDERS = {"server", "app", "core", "backend", "lib", "src", "cmd", "pkg", "internal"}

# Lowercased ignored set for O(1) lookup
_IGNORED_LOWER = {d.lower() for d in IGNORED_DIRS}
# Prefixes for wildcard-style ignores (e.g. "bazel-" covers bazel-bin, bazel-out, etc.)
_IGNORED_PREFIXES = ("bazel-", "cmake_", "cmakefiles")


def _is_ignored(path: str) -> bool:
    """Return True if any path segment matches the ignored set (case-insensitive)."""
    parts = path.replace("\\", "/").split("/")
    for p in parts:
        pl = p.lower()
        if pl in _IGNORED_LOWER:
            return True
        if any(pl.startswith(prefix) for prefix in _IGNORED_PREFIXES):
            return True
    return False


def _has_allowed_ext(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in ALLOWED_EXTENSIONS


def _score(path: str) -> int:
    """Compute priority score for a single file path."""
    score = 0
    normalised = path.replace("\\", "/").lower()
    parts = normalised.split("/")

    if normalised.startswith("src/"):
        score += 5

    for part in parts:
        name_no_ext = os.path.splitext(part)[0].lower()
        for kw in _ARCH_KEYWORDS:
            if kw in name_no_ext:
                score += 3
                break  # only award once per segment

    if len(parts) <= 2:
        score += 2

    if parts[0] in _BACKEND_FOLDERS:
        score += 2

    return score


def filter_and_rank(tree: list[dict[str, Any]]) -> list[str]:
    """Accept the raw tree from GitHub and return a ranked list of file paths."""
    blobs = [
        item["path"]
        for item in tree
        if item.get("type") == "blob"
        and _has_allowed_ext(item["path"])
        and not _is_ignored(item["path"])
    ]
    logger.info("After extension / ignore filter: %d files", len(blobs))

    scored = sorted(blobs, key=_score, reverse=True)
    top = scored[:MAX_FILES_TO_PROCESS]
    logger.info("Top %d files selected for analysis", len(top))
    return top
