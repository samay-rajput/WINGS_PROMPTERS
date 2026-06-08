"""
vector_store.py
----------------
Singleton in-memory FAISS vector store.

One store exists per running process.  Calling `build()` replaces the
previous store, allowing the same server instance to be re-indexed for a
different repository without restarting.
"""

from __future__ import annotations

import os
import time
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# ---------------------------------------------------------------------------
# Module-level state (in-memory singleton)
# ---------------------------------------------------------------------------

_store: Optional[FAISS] = None
_stats: dict = {"files_indexed": 0, "chunks_indexed": 0}

PERSIST_DIRECTORY = "faiss_index"


def _get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """Helper to get a model instance for loading."""
    from services.embedding_service import get_all_embeddings
    return get_all_embeddings()[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build(documents: list[Document], embeddings_list: list[GoogleGenerativeAIEmbeddings]) -> None:
    """
    (Re)build the FAISS index from the provided documents.
    Uses parallel threading across ALL provided API keys to maximize indexing speed.
    """
    global _store, _stats

    if not documents:
        raise ValueError("Cannot build vector store: no documents provided.")

    # Reset store for fresh build
    _store = None
    
    BATCH_SIZE = 20
    batches = [documents[i:i + BATCH_SIZE] for i in range(0, len(documents), BATCH_SIZE)]
    
    print(f"[DEBUG] Starting Parallel Indexing for {len(documents)} chunks across {len(embeddings_list)} keys...")
    t_start = time.time()
    
    # We use a simple counter to distribute batches to keys
    batch_results = [None] * len(batches)
    
    def process_batch(batch_idx: int):
        batch = batches[batch_idx]
        # Assign a key based on batch index (rotation)
        key_idx = batch_idx % len(embeddings_list)
        
        retries = 3
        while retries > 0:
            try:
                current_embedding = embeddings_list[key_idx]
                return FAISS.from_documents(batch, current_embedding)
            except Exception as e:
                error_str = str(e).upper()
                is_quota = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "QUOTA" in error_str
                
                if is_quota:
                    # Respect 60s cooldown or rotate keys
                    print(f"[DEBUG] Key {key_idx+1} hit rate limit. Rotating...")
                    key_idx = (key_idx + 1) % len(embeddings_list)
                    time.sleep(2)
                else:
                    print(f"[DEBUG] Batch {batch_idx} failed: {e}")
                    retries -= 1
                    time.sleep(1)
                
                retries -= 1
        return None

    # Process all batches in parallel using a thread pool
    # We limit workers based on number of keys to hit all of them at once
    max_workers = max(len(embeddings_list), 4)
    merge_lock = threading.Lock()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(process_batch, idx): idx for idx in range(len(batches))}
        
        completed_count = 0
        for future in as_completed(future_to_idx):
            res = future.result()
            if res:
                with merge_lock:
                    if _store is None:
                        _store = res
                    else:
                        _store.merge_from(res)
                
                completed_count += 1
                if completed_count % 5 == 0 or completed_count == len(batches):
                    print(f"[DEBUG] Parallel Progress: {completed_count}/{len(batches)} batches indexed.")

    # Save to disk for persistence across restarts
    if _store:
        print(f"[DEBUG] Saving index to disk: {PERSIST_DIRECTORY}")
        _store.save_local(PERSIST_DIRECTORY)

    print(f"[DEBUG] Parallel Indexing complete! Total time: {time.time() - t_start:.2f}s.")

    unique_files = {doc.metadata.get("file_path", "") for doc in documents}
    _stats = {
        "files_indexed": len(unique_files),
        "chunks_indexed": len(documents),
    }


def search(query: str, embeddings: GoogleGenerativeAIEmbeddings, k: int = 5) -> list[Document]:
    """
    Embed *query* and return the top-k most similar Documents.
    Raises RuntimeError if no repository has been indexed yet.
    """
    if _store is None:
        raise RuntimeError(
            "No repository has been indexed yet. "
            "Please call POST /rag/index first."
        )
    results = _store.similarity_search(query, k=k)
    return results


def get_stats() -> dict:
    """Return indexing statistics for the currently loaded repository."""
    return _stats.copy()


def is_ready() -> bool:
    """Return True if a repository is currently indexed."""
    return _store is not None
