"""
github_service.py
-----------------
Handles all interactions with the GitHub REST API:
  - Parse any github.com URL into owner / repo / desired branch
  - Resolve the default branch
  - Walk the full recursive git-tree
  - Filter files by extension and ignore-list
  - Fetch and decode file contents
"""

import base64
import re
from typing import Optional
import os
import requests
import zipfile
import io

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".sh", ".bash", ".zsh", ".bat", ".ps1",
    ".html", ".css", ".scss", ".less", ".sql", ".csv"
}

ALLOWED_FILENAMES = {
    "makefile", "dockerfile", "cmakelists.txt"
}

IGNORED_DIRS = {
    "node_modules",
    "dist",
    "build",
    ".git",
    "venv",
    "__pycache__",
    ".next",
    ".venv",
    "env",
    "target",        # Java build output
    "out",
}

MAX_FILES = 200
MAX_FILE_BYTES = 500 * 1024  # 500 KB

GITHUB_API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    """Build request headers, injecting GitHub token when available."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json"}
    if token and token != "your_github_token_here":
        headers["Authorization"] = f"Bearer {token}"
    return headers

def _check_api_error(response: requests.Response) -> None:
    """Raise clean exceptions for common GitHub API errors before raise_for_status."""
    if response.status_code == 401:
        raise PermissionError("GitHub Token is invalid or unauthorized (401). Please check your .env file.")
    if response.status_code == 403:
        raise PermissionError("GitHub API rate limit exceeded or access denied (403).")
    if response.status_code == 404:
        raise ValueError("GitHub repository or resource not found (404).")
    response.raise_for_status()


def _is_ignored(path: str) -> bool:
    """Return True if any path segment belongs to the ignore list."""
    parts = path.replace("\\", "/").split("/")
    return any(part in IGNORED_DIRS for part in parts)


def _is_allowed(path: str) -> bool:
    """Return True if the file extension or exact filename is in the allowed set."""
    basename = os.path.basename(path).lower()
    if basename in ALLOWED_FILENAMES:
        return True
    _, ext = os.path.splitext(basename)
    return ext in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_github_url(url: str) -> tuple[str, str, Optional[str]]:
    """
    Parse a GitHub URL and return (owner, repo, branch).
    branch may be None when not specified — caller should resolve it.

    Supports:
      https://github.com/owner/repo
      https://github.com/owner/repo/tree/branch-name
    """
    pattern = r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?(?:/.*)?$"
    match = re.match(pattern, url.rstrip("/"))
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url!r}")
    owner, repo, branch = match.group(1), match.group(2), match.group(3)
    return owner, repo, branch


def get_default_branch(owner: str, repo: str) -> str:
    """Fetch the repository's default branch name from the GitHub API."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    response = requests.get(url, headers=_get_headers(), timeout=15)
    _check_api_error(response)
    return response.json()["default_branch"]


def fetch_repository_files(github_url: str) -> tuple[list[dict], dict]:
    """
    High-level entry point: given a GitHub URL, return:
      - files: list of {"path": str, "content": str}
      - meta:  {"owner", "repo", "branch", "files_fetched"}

    Downloads the entire repository as a single ZIP payload from GitHub,
    which is enormously faster than requesting 200+ files individually.
    """
    owner, repo, branch = parse_github_url(github_url)
    if not branch:
        branch = get_default_branch(owner, repo)

    # 1. Fetch entire repository as a single ZIP file
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/zipball/{branch}"
    response = requests.get(url, headers=_get_headers(), stream=True, timeout=30)
    _check_api_error(response)

    files = []
    
    # 2. Unzip instantly in memory
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
                
            # Strip the root folder name wrapper that GitHub adds (e.g. 'owner-repo-commitHash/')
            parts = info.filename.replace('\\', '/').split('/', 1)
            if len(parts) == 1:
                continue
            path = parts[1]
            
            # Filter identical to before
            if _is_ignored(path):
                continue
            if not _is_allowed(path):
                continue
            if info.file_size > MAX_FILE_BYTES:
                continue

            # Read content bytes safely
            raw_bytes = z.read(info.filename)
            try:
                content_str = raw_bytes.decode("utf-8")
                files.append({"path": path, "content": content_str})
            except UnicodeDecodeError:
                pass  # Skip binary junk
                
            if len(files) >= MAX_FILES:
                break

    meta = {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "files_fetched": len(files),
    }
    return files, meta
