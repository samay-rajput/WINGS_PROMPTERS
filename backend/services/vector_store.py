"""
vector_store.py
---------------
Singleton in-memory FAISS vector store backed by a local sentence-transformer model.

One store exists per running process. Calling `build()` replaces the previous
store, allowing the same server instance to be re-indexed for a different
repository without restarting.

No threading or key rotation needed: the local model has no rate limits.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

# ---------------------------------------------------------------------------
# Module-level state (in-memory singleton)
# ---------------------------------------------------------------------------

_store: Optional[FAISS] = None
_stats: dict = {"files_indexed": 0, "chunks_indexed": 0}


def _is_truthy(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _should_persist() -> bool:
    # Enabled by default for continuity across restarts.
    return _is_truthy(os.getenv("RAG_PERSIST_INDEX", "1"))


def _get_persist_directory() -> str:
    """
    Keep persisted FAISS artifacts outside the project tree by default.

    This avoids frontend auto-reload tools (for example VS Code Live Server)
    resetting the UI when /rag/index writes index files.
    """
    configured = os.getenv("RAG_FAISS_DIR", "").strip()
    if configured:
        return os.path.normpath(configured)

    return os.path.normpath(
        os.path.join(os.path.expanduser("~"), ".navigit", "faiss_index")
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build(documents: list[Document], embeddings: HuggingFaceEmbeddings) -> None:
    """
    (Re)build the FAISS index from the provided documents.

    Uses the local sentence-transformer model: no API calls, no rate limits,
    no threading complexity needed.
    """
    global _store, _stats

    if not documents:
        raise ValueError("Cannot build vector store: no documents provided.")

    print(f"[RAG] Building FAISS index for {len(documents)} chunks...")
    t_start = time.time()

    _store = FAISS.from_documents(documents, embeddings)

    elapsed = time.time() - t_start
    print(f"[RAG] FAISS index built in {elapsed:.1f}s.")

    if _should_persist():
        persist_directory = _get_persist_directory()
        os.makedirs(persist_directory, exist_ok=True)
        _store.save_local(persist_directory)
        print(f"[RAG] Index saved to: {persist_directory}")
    else:
        print("[RAG] Index persistence disabled (RAG_PERSIST_INDEX=0).")

    unique_files = {doc.metadata.get("file_path", "") for doc in documents}
    _stats = {
        "files_indexed": len(unique_files),
        "chunks_indexed": len(documents),
    }


def search(query: str, embeddings: HuggingFaceEmbeddings, k: int = 20) -> list[Document]:
    """
    Embed *query* and return the top-k most similar Documents.
    Raises RuntimeError if no repository has been indexed yet.
    """
    if _store is None:
        raise RuntimeError(
            "No repository has been indexed yet. "
            "Please call POST /rag/index first."
        )
    return _store.similarity_search(query, k=k)


def get_stats() -> dict:
    """Return indexing statistics for the currently loaded repository."""
    return _stats.copy()


def is_ready() -> bool:
    """Return True if a repository is currently indexed."""
    return _store is not None
