"""
github_service.py
─────────────────
Handles all communication with the GitHub REST API.

Responsibilities:
  • Parse owner/repo from URL
  • Fetch repository metadata (default branch)
  • Fetch recursive file tree
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
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}


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
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()


async def fetch_repo_tree(owner: str, repo: str, branch: str) -> list[dict[str, Any]]:
    """GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1  →  flat file list."""
    url = f"{_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    logger.info("Fetching full tree for %s/%s@%s", owner, repo, branch)
    async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        if data.get("truncated"):
            logger.warning("Tree was truncated by GitHub — very large repo")
        return data.get("tree", [])


async def fetch_file_content(owner: str, repo: str, path: str) -> str | None:
    """GET /repos/{owner}/{repo}/contents/{path}  →  decoded UTF-8 text.

    Returns None on any failure (404, decode error, etc.).
    """
    url = f"{_BASE}/repos/{owner}/{repo}/contents/{path}"
    logger.debug("Fetching file content: %s", path)
    try:
        async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
            encoded = data.get("content", "")
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Could not fetch %s: %s", path, exc)
        return None
