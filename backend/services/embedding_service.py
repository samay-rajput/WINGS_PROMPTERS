"""
embedding_service.py
---------------------
Provides the local sentence-transformer embedding model for the RAG pipeline.

Model: all-MiniLM-L6-v2
  - Size  : ~80 MB (downloaded once to ~/.cache/huggingface/)
  - Speed : ~1000 sentences/sec on CPU
  - Dims  : 384
  - Zero API calls, zero rate limits, runs fully offline after first download.

We force PyTorch-only mode (TRANSFORMERS_NO_TF=1) so HuggingFace never tries
to load TensorFlow/Keras, which avoids the tf-keras compatibility error on
machines that have TensorFlow installed.
"""

import os

# Force PyTorch backend — must be set BEFORE any HuggingFace imports
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # suppresses tokenizers fork warning

from langchain_huggingface import HuggingFaceEmbeddings

# Model is loaded once at module import and reused for all requests.
_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
_embeddings_instance: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Return the shared HuggingFaceEmbeddings instance (lazy singleton).
    First call loads the model from disk/cache (~80 MB, one-time download).
    """
    global _embeddings_instance
    if _embeddings_instance is None:
        print(f"[RAG] Loading local embedding model: {_EMBEDDING_MODEL_NAME} (PyTorch backend)...")
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name=_EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("[RAG] Embedding model ready ✓")
    return _embeddings_instance


def get_all_embeddings() -> list[HuggingFaceEmbeddings]:
    """Legacy alias — returns a single-element list for backward compatibility."""
    return [get_embeddings()]
