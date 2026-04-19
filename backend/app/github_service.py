"""
github_service.py
─────────────────
Handles all communication with the GitHub REST API.

Responsibilities:
  • Parse owner/repo from URL
  • Fetch repository metadata (default branch)
  • Fetch recursive file tree (with truncation handling for giant repos)
  • Fetch individual file contents (base64 decode)
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

from app.config import GITHUB_TOKEN, GITHUB_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://api.github.com"

def _get_headers() -> dict[str, str]:
    """Build request headers. Uses token if available, falls back to unauthenticated."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = GITHUB_TOKEN.strip() if GITHUB_TOKEN else ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning("No GITHUB_TOKEN set — using unauthenticated requests (60 req/hr limit)")
    return headers

def _handle_github_error(resp: httpx.Response, url: str) -> None:
    """Raise a clear, human-readable error for GitHub API failures."""
    if resp.status_code == 401:
        raise PermissionError(
            "GitHub token is invalid or expired (401). "
            "Please update GITHUB_TOKEN in backend/.env with a fresh token from "
            "https://github.com/settings/tokens — or remove it to use unauthenticated access."
        )
    if resp.status_code == 403:
        raise PermissionError(
            "GitHub API rate limit exceeded or access forbidden (403). "
            "Add a valid GITHUB_TOKEN in backend/.env to increase rate limits."
        )
    if resp.status_code == 404:
        raise ValueError(f"Repository not found (404): {url}. Check the URL is correct and the repo is public.")
    resp.raise_for_status()


# ── Helpers ─────────────────────────────────────────────────────────────────

def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.  Raises ValueError on bad input."""
    pattern = r"github\.com/([^/]+)/([^/\s?#]+)"
    match = re.search(pattern, url.strip().rstrip("/"))
    if not match:
        raise ValueError(f"Cannot parse GitHub owner/repo from URL: {url}")
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


# ── API calls ──────────────────────────────────────────────────────────────

async def fetch_repo_metadata(owner: str, repo: str) -> dict[str, Any]:
    """GET /repos/{owner}/{repo}  →  full repo metadata JSON."""
    url = f"{_BASE}/repos/{owner}/{repo}"
    logger.info("Fetching repo metadata: %s/%s", owner, repo)
    async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
        resp = await client.get(url, headers=_get_headers())
        _handle_github_error(resp, url)
        return resp.json()


async def fetch_repo_tree(owner: str, repo: str, branch: str) -> list[dict[str, Any]]:
    """GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1  →  flat file list.

    For very large repos (Linux, Kubernetes, LLVM) GitHub truncates the recursive
    tree at ~100 000 entries.  When truncation is detected we perform a non-recursive
    walk of the top-level tree so analysis still gets a representative snapshot
    rather than silently working with an empty or incomplete list.
    """
    url = f"{_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    logger.info("Fetching full tree for %s/%s@%s", owner, repo, branch)
    # Use a longer timeout for giant repos
    tree_timeout = max(GITHUB_REQUEST_TIMEOUT, 60.0)
    async with httpx.AsyncClient(timeout=tree_timeout) as client:
        resp = await client.get(url, headers=_get_headers())
        _handle_github_error(resp, url)
        data = resp.json()

    tree: list[dict[str, Any]] = data.get("tree", [])

    if data.get("truncated"):
        logger.warning(
            "GitHub truncated the recursive tree for %s/%s at %d entries — "
            "repo is extremely large. Performing shallow top-level walk instead.",
            owner, repo, len(tree),
        )
        # Fall back: fetch the top-level (non-recursive) tree — gives at least
        # the root files and top-level dir SHAs we can work with.
        shallow_url = f"{_BASE}/repos/{owner}/{repo}/git/trees/{branch}"
        async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
            shallow_resp = await client.get(shallow_url, headers=_get_headers())
            if shallow_resp.status_code == 200:
                shallow_data = shallow_resp.json()
                shallow_items: list[dict[str, Any]] = shallow_data.get("tree", [])
                # Merge: keep all non-truncated recursive entries we already have,
                # then add any root-level items not already present.
                existing_paths = {item["path"] for item in tree}
                for item in shallow_items:
                    if item["path"] not in existing_paths:
                        tree.append(item)
                logger.info(
                    "After shallow merge: %d tree entries available for %s/%s",
                    len(tree), owner, repo,
                )

    return tree


async def fetch_file_content(owner: str, repo: str, path: str) -> str | None:
    """GET /repos/{owner}/{repo}/contents/{path}  →  decoded UTF-8 text.

    Returns None on any failure (404, decode error, etc.).
    """
    url = f"{_BASE}/repos/{owner}/{repo}/contents/{path}"
    logger.debug("Fetching file content: %s", path)
    try:
        async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=_get_headers())
            resp.raise_for_status()
            data = resp.json()
            encoded = data.get("content", "")
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Could not fetch %s: %s", path, exc)
        return None
