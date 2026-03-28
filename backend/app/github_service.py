"""
github_service.py
Handles all communication with the GitHub REST API.

Responsibilities:
  - Parse owner/repo from URL
  - Fetch repository metadata (default branch)
  - Fetch recursive file tree
  - Fetch individual file contents (base64 decode)
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


class GitHubServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL. Raises ValueError on bad input."""
    pattern = r"github\.com/([^/]+)/([^/\s?#]+)"
    match = re.search(pattern, url.strip().rstrip("/"))
    if not match:
        raise ValueError(f"Cannot parse GitHub owner/repo from URL: {url}")
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def _raise_for_github_error(resp: httpx.Response, owner: str, repo: str) -> None:
    status = resp.status_code
    message = ""

    try:
        payload = resp.json()
        message = str(payload.get("message", "")).strip()
    except Exception:
        message = ""

    if status == 404:
        raise GitHubServiceError(
            f"Repository '{owner}/{repo}' is private, unavailable, or your GitHub token does not have access to it.",
            status_code=404,
        )

    if status == 403 and "rate limit" in message.lower():
        raise GitHubServiceError(
            "GitHub API rate limit reached. Please try again later or use a valid GitHub token with remaining quota.",
            status_code=403,
        )

    if status == 403:
        raise GitHubServiceError(
            f"Access to repository '{owner}/{repo}' was denied by GitHub.",
            status_code=403,
        )

    detail = f"GitHub API request failed for '{owner}/{repo}'"
    if message:
        detail += f": {message}"
    raise GitHubServiceError(detail, status_code=status if status >= 400 else 502)


async def fetch_repo_metadata(owner: str, repo: str) -> dict[str, Any]:
    """GET /repos/{owner}/{repo} -> full repo metadata JSON."""
    url = f"{_BASE}/repos/{owner}/{repo}"
    logger.info("Fetching repo metadata: %s/%s", owner, repo)
    async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=_HEADERS)
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"Could not reach GitHub while fetching '{owner}/{repo}': {exc}") from exc

        if resp.is_error:
            _raise_for_github_error(resp, owner, repo)

        return resp.json()


async def fetch_repo_tree(owner: str, repo: str, branch: str) -> list[dict[str, Any]]:
    """GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1 -> flat file list."""
    url = f"{_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    logger.info("Fetching full tree for %s/%s@%s", owner, repo, branch)
    async with httpx.AsyncClient(timeout=GITHUB_REQUEST_TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=_HEADERS)
        except httpx.HTTPError as exc:
            raise GitHubServiceError(
                f"Could not reach GitHub while loading the file tree for '{owner}/{repo}': {exc}"
            ) from exc

        if resp.is_error:
            _raise_for_github_error(resp, owner, repo)

        data = resp.json()
        if data.get("truncated"):
            logger.warning("Tree was truncated by GitHub - very large repo")
        return data.get("tree", [])


async def fetch_file_content(owner: str, repo: str, path: str) -> str | None:
    """GET /repos/{owner}/{repo}/contents/{path} -> decoded UTF-8 text."""
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
