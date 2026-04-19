"""
rag_service.py
--------------
Orchestrates the full indexing pipeline:

  GitHub URL → github_service → ingestion_service → embedding_service → vector_store

Also exposes the `retrieve` helper used by chat_service.
"""

from . import github_service, ingestion_service, embedding_service, vector_store
from langchain_core.documents import Document


def index_repository(github_url: str) -> dict:
    """
    Full indexing pipeline for a GitHub repository.

    Steps
    -----
    1. Fetch all relevant source files from GitHub.
    2. Split files into overlapping, self-describing chunks.
    3. Build (or rebuild) the FAISS vector store using the local embedding model.

    Returns
    -------
    dict with keys: files_fetched, files_indexed, chunks_indexed
    """
    # 1. Fetch files
    print(f"[RAG] Fetching repository: {github_url}")
    files, meta = github_service.fetch_repository_files(github_url)
    print(f"[RAG] Fetched {len(files)} files.")

    if not files:
        raise ValueError(
            f"No indexable source files found in repository: {github_url}"
        )

    # 2. Chunk into LangChain Documents
    print("[RAG] Chunking files into documents...")
    documents = ingestion_service.create_documents(files)
    print(f"[RAG] Created {len(documents)} chunks.")

    if not documents:
        raise ValueError("Chunking produced zero documents. Check file contents.")

    # 3. Build vector store (local model — no API calls, no rate limits)
    embeddings = embedding_service.get_embeddings()
    vector_store.build(documents, embeddings)

    # 4. Return stats
    stats = ingestion_service.get_ingestion_stats(files, documents)
    stats["branch"] = meta.get("branch", "unknown")
    stats["owner"] = meta.get("owner", "")
    stats["repo"] = meta.get("repo", "")
    return stats


def retrieve(query: str, k: int = 20) -> list[Document]:
    """
    Embed *query* and return the top-k most relevant code chunks.
    Delegates to vector_store which raises RuntimeError if not indexed.
    """
    embeddings = embedding_service.get_embeddings()
    return vector_store.search(query, embeddings, k=k)
