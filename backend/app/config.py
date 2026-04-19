"""
Centralised configuration — loads environment variables once and exposes them
as module-level constants.  All secrets stay in .env; nothing is hard-coded.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

# ── Main Analysis Pipeline LLM keys (M1 / M2 / M3 only) ────────────────────
GEMINI_API_KEY_PRIMARY: str = (
    os.getenv("GEMINI_API_KEY_PRIMARY")
    or os.getenv("GEMINI_API_KEY", "")
)
GEMINI_API_KEY_SECONDARY: str = os.getenv("GEMINI_API_KEY_SECONDARY", "")
# Strictly isolated from RAG pipeline — do NOT read GROQ_API_KEY_RAG here
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ── Tunables ────────────────────────────────────────────────────────────────
MAX_FILES_TO_PROCESS: int = 200          # cap after priority scoring
GITHUB_REQUEST_TIMEOUT: float = 30.0    # seconds per GitHub API call
LLM_REQUEST_TIMEOUT: float = 120.0      # seconds for tracking LLM timeouts
MAX_FILE_SIZE_BYTES: int = 500_000      # skip files larger than ~500 KB

# ── LLM Configuration ──────────────────────────────────────────────────────
GEMINI_MODEL: str = "gemini-2.5-flash"
GROQ_MODEL: str = "llama-3.1-8b-instant"

# ── Allowed extensions — covers all benchmark languages ─────────────────────
ALLOWED_EXTENSIONS: set[str] = {
    # Web / Node
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    # Python
    ".py",
    # JVM
    ".java", ".kt", ".scala", ".groovy",
    # C / C++ / Systems
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh",
    # C# / .NET
    ".cs",
    # Go
    ".go",
    # Rust
    ".rs",
    # Dart / Flutter
    ".dart",
    # Ruby
    ".rb",
    # PHP
    ".php",
    # Swift
    ".swift",
    # Shell / Scripting
    ".sh", ".bash", ".zsh", ".ps1", ".bat",
    # Config / Build
    ".yaml", ".yml", ".toml", ".json", ".xml",
    ".cmake", ".bazel", ".bzl", ".gradle", ".mk",
    # Docs  (limited — for entry detection context)
    ".md",
}

# ── Ignored directories ────────────────────────────────────────────────────
IGNORED_DIRS: set[str] = {
    # JS/TS
    "node_modules", ".next", "dist", "build", "out", ".turbo",
    # Python
    "venv", ".venv", "env", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", "*.egg-info",
    # Java / JVM
    "target", ".gradle", ".idea",
    # Go
    "vendor",
    # C / C++ / Build systems
    "cmake_files", "cmakefiles",   # case-insensitive handled below
    # Rust
    "target",                      # same name, already listed
    # Large monorepo artifacts
    "third_party", "third-party", "thirdparty",
    "bazel-bin", "bazel-out", "bazel-testlogs", "bazel-genfiles",
    ".cache", ".git", ".github", ".vscode", ".vs",
    # Docs / assets
    "docs", "documentation", "examples", "samples", "test", "tests",
    "testdata", "fixture", "fixtures", "mocks", "__mocks__",
    "benchmark", "benchmarks",
}
