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
    3. Build (or rebuild) the FAISS vector store.

    Returns
    -------
    dict with keys: files_fetched, files_indexed, chunks_indexed
    """
    # 1. Fetch files
    print(f"[DEBUG] Fetching repository files from: {github_url}")
    files, meta = github_service.fetch_repository_files(github_url)
    print(f"[DEBUG] Successfully fetched {len(files)} files.")
    
    if not files:
        raise ValueError(
            f"No indexable source files found in repository: {github_url}"
        )

    # 2. Chunk into LangChain Documents
    print("[DEBUG] Chunking files into documents...")
    documents = ingestion_service.create_documents(files)
    print(f"[DEBUG] Created {len(documents)} chunks.")
    
    if not documents:
        raise ValueError("Chunking produced zero documents. Check file contents.")

    # 3. Build vector store
    print("[DEBUG] Loading/Retrieving local embedding model...")
    embeddings_list = embedding_service.get_all_embeddings()
    print("[DEBUG] Building FAISS vector store (embedding chunks)...")
    vector_store.build(documents, embeddings_list)
    print("[DEBUG] FAISS index built successfully.")

    # 4. Return stats
    stats = ingestion_service.get_ingestion_stats(files, documents)
    stats["branch"] = meta.get("branch", "unknown")
    stats["owner"] = meta.get("owner", "")
    stats["repo"] = meta.get("repo", "")
    return stats


def retrieve(query: str, k: int = 5) -> list[Document]:
    """
    Embed *query* and return the top-k most relevant code chunks.
    Delegates to vector_store which raises RuntimeError if not indexed.
    """
    embeddings_list = embedding_service.get_all_embeddings()
    return vector_store.search(query, embeddings_list[0], k=k)
