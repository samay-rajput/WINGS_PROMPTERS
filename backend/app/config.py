"""
Centralised configuration — loads environment variables once and exposes them
as module-level constants.  All secrets stay in .env; nothing is hard-coded.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

# LLM Providers
GEMINI_API_KEY_PRIMARY: str = (
    os.getenv("GEMINI_API_KEY_PRIMARY")
    or os.getenv("GEMINI_API_KEY_RAG")
    or os.getenv("GEMINI_API_KEY", "")
)
GEMINI_API_KEY_SECONDARY: str = os.getenv("GEMINI_API_KEY_SECONDARY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY_RAG", "")

# ── Tunables ────────────────────────────────────────────────────────────────
MAX_FILES_TO_PROCESS: int = 150          # cap after priority scoring
GITHUB_REQUEST_TIMEOUT: float = 30.0     # seconds per GitHub API call
LLM_REQUEST_TIMEOUT: float = 120.0       # seconds for tracking LLM timeouts
MAX_FILE_SIZE_BYTES: int = 500_000       # skip files larger than ~500 KB

# ── LLM Configuration ──────────────────────────────────────────────────────
GEMINI_MODEL: str = "gemini-2.5-flash"
GROQ_MODEL: str = "llama-3.1-8b-instant"

# ── Allowed extensions ──────────────────────────────────────────────────────
ALLOWED_EXTENSIONS: set[str] = {
    ".js", ".ts", ".jsx", ".tsx",
    ".py",
    ".java",
    ".php",
}

# ── Ignored directories ────────────────────────────────────────────────────
IGNORED_DIRS: set[str] = {
    "node_modules", "dist", "build", ".git", ".venv",
    "__pycache__", ".next", "out", ".tox", ".mypy_cache",
    "vendor", "target", ".gradle",
}
