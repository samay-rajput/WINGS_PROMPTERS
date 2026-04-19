"""
github_service.py  (RAG pipeline)
----------------------------------
Fetches source files from GitHub for the RAG indexing pipeline.

Uses the git-trees API (recursive) + individual file fetches — NOT the zipball.
The zipball for repos like Linux kernel (~220MB) is completely unworkable on
free tier; the tree API gives us precisely the files we choose, fast.

Key constraints:
  MAX_FILES   = 100  — only the top-scored files are fetched
  Concurrency = 8    — 8 simultaneous file fetches to stay within rate limits
"""

import base64
import re
import os
import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
    ".swift", ".kt", ".dart", ".scala",
    ".sh", ".bash", ".yaml", ".yml", ".toml",
}

IGNORED_DIRS = {
    "node_modules", "dist", "build", ".git", "venv", "__pycache__",
    ".next", ".venv", "env", "target", "out", "vendor",
    "third_party", "third-party", "test", "tests", "testdata",
    "docs", "documentation", "examples", "samples", "fixtures",
    "benchmark", "benchmarks",
}

# Prefix-based ignores for large generated/build dirs
IGNORED_PREFIXES = ("bazel-", "cmake_", "cmakefiles")

# Architecture-relevant keywords — files containing these score higher
_ARCH_KEYWORDS = {
    "main", "server", "app", "core", "service", "controller",
    "handler", "router", "api", "manager", "provider", "config",
    "init", "cmd", "entry",
}

MAX_FILES = 100          # hard cap — only fetch the best files
MAX_FILE_BYTES = 300_000  # skip files > 300 KB
FETCH_CONCURRENCY = 8    # parallel HTTP requests
FETCH_TIMEOUT = 20       # seconds per file fetch

GITHUB_API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    """RAG-specific GitHub token, falls back to shared GITHUB_TOKEN."""
    token = (
        os.getenv("GITHUB_TOKEN_RAG", "").strip()
        or os.getenv("GITHUB_TOKEN", "").strip()
    )
    headers = {"Accept": "application/vnd.github+json"}
    if token and token not in ("your_github_token_here", ""):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _check_api_error(response: requests.Response) -> None:
    if response.status_code == 401:
        raise PermissionError("GitHub Token is invalid or unauthorized (401).")
    if response.status_code == 403:
        raise PermissionError("GitHub API rate limit exceeded (403).")
    if response.status_code == 404:
        raise ValueError("GitHub repository or resource not found (404).")
    response.raise_for_status()


def _is_ignored(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    for p in parts:
        pl = p.lower()
        if pl in IGNORED_DIRS:
            return True
        if any(pl.startswith(pfx) for pfx in IGNORED_PREFIXES):
            return True
    return False


def _is_allowed(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in ALLOWED_EXTENSIONS


def _score_path(path: str) -> int:
    """Higher = more architecturally relevant."""
    score = 0
    norm = path.replace("\\", "/").lower()
    parts = norm.split("/")
    name_no_ext = os.path.splitext(parts[-1])[0]

    for kw in _ARCH_KEYWORDS:
        if kw in name_no_ext:
            score += 5
            break

    # Shallow files score higher
    score += max(0, 4 - len(parts))

    # Top-level src/cmd/pkg/internal bonus (Go pattern)
    if parts[0] in {"src", "cmd", "pkg", "internal", "lib", "app", "core"}:
        score += 3

    return score


def parse_github_url(url: str) -> tuple[str, str, Optional[str]]:
    pattern = r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/.*)?$"
    match = re.match(pattern, url.rstrip("/"))
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url!r}")
    return match.group(1), match.group(2), match.group(3)


def get_default_branch(owner: str, repo: str) -> str:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    resp = requests.get(url, headers=_get_headers(), timeout=15)
    _check_api_error(resp)
    return resp.json()["default_branch"]


# ---------------------------------------------------------------------------
# File fetch (single file via contents API)
# ---------------------------------------------------------------------------

def _fetch_file(owner: str, repo: str, path: str, size: int) -> Optional[dict]:
    """
    Fetch a single file's content via the GitHub contents API.
    Returns {"path": ..., "content": ...} or None on failure.
    """
    if size > MAX_FILE_BYTES:
        return None

    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=FETCH_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(5)
            resp = requests.get(url, headers=_get_headers(), timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        encoded = data.get("content", "")
        content = base64.b64decode(encoded).decode("utf-8", errors="replace")
        return {"path": path, "content": content}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_repository_files(github_url: str) -> tuple[list[dict], dict]:
    """
    1. Resolve default branch.
    2. Fetch recursive git-tree (lightweight — JSON only, no file contents).
    3. Filter + score candidate files.
    4. Concurrently fetch top MAX_FILES files via the contents API.

    Returns (files_list, meta_dict).
    """
    owner, repo, branch = parse_github_url(github_url)
    if not branch:
        branch = get_default_branch(owner, repo)

    # --- Step 1: Get full tree (JSON, fast even for Linux kernel) ---
    tree_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    print(f"[RAG] Fetching file tree for {owner}/{repo}@{branch}...")
    resp = requests.get(tree_url, headers=_get_headers(), timeout=60)
    _check_api_error(resp)
    tree_data = resp.json()

    tree_items = tree_data.get("tree", [])
    if tree_data.get("truncated"):
        print(f"[RAG] Tree truncated at {len(tree_items)} entries — large repo. Proceeding with what we have.")

    # --- Step 2: Filter blobs ---
    candidates = []
    for item in tree_items:
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        size = item.get("size", 0)
        if _is_ignored(path) or not _is_allowed(path) or size > MAX_FILE_BYTES:
            continue
        candidates.append((path, size, _score_path(path)))

    if not candidates:
        raise ValueError(f"No indexable source files found in: {github_url}")

    # --- Step 3: Take top MAX_FILES by score ---
    candidates.sort(key=lambda x: x[2], reverse=True)
    top = candidates[:MAX_FILES]
    print(f"[RAG] Selected {len(top)} files from {len(candidates)} candidates.")

    # --- Step 4: Concurrent fetch ---
    files: list[dict] = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as executor:
        futures = {
            executor.submit(_fetch_file, owner, repo, path, size): path
            for path, size, _ in top
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                files.append(result)

    print(f"[RAG] Successfully fetched {len(files)}/{len(top)} files.")

    if not files:
        raise ValueError("All file fetches failed — check GitHub token and rate limits.")

    meta = {"owner": owner, "repo": repo, "branch": branch, "files_fetched": len(files)}
    return files, meta
