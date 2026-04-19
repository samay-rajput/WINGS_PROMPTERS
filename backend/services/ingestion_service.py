"""
ingestion_service.py
---------------------
Converts raw file content into overlapping text chunks ready for embedding.

Chunking strategy:
  - Chunk size : 800 tokens  (approximated via character count; tiktoken fallback)
  - Overlap    : 100 tokens
  - Each chunk is prefixed with file path so the LLM always has provenance.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE = 3200      # ~800 tokens × 4 chars/token (conservative estimate)
CHUNK_OVERLAP = 400    # ~100 tokens × 4 chars/token
MAX_TOTAL_CHUNKS = 10_000   # hard cap — prevents OOM on giant repos (Kubernetes, Linux)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_splitter() -> RecursiveCharacterTextSplitter:
    """Create a reusable text splitter configured for source code."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
        length_function=len,
    )


def create_documents(files: list[dict]) -> list[Document]:
    """
    Given a list of {"path": str, "content": str} dicts, split each file
    into overlapping chunks and return a list of LangChain Document objects.

    Each Document:
      - page_content : "FILE_PATH: <path>\\nCODE:\\n<chunk text>"
      - metadata     : {"file_path": str, "chunk_index": int}

    Total chunks are capped at MAX_TOTAL_CHUNKS to prevent OOM on giant repos.
    """
    splitter = build_splitter()
    documents: list[Document] = []

    for file in files:
        if len(documents) >= MAX_TOTAL_CHUNKS:
            break

        path: str = file["path"]
        content: str = file["content"]

        if not content.strip():
            continue

        # Split the raw content into chunks
        chunks = splitter.split_text(content)

        for idx, chunk in enumerate(chunks):
            if len(documents) >= MAX_TOTAL_CHUNKS:
                break
            # Prepend file provenance so every chunk is self-contained
            page_content = f"FILE_PATH: {path}\nCODE:\n{chunk}"
            doc = Document(
                page_content=page_content,
                metadata={"file_path": path, "chunk_index": idx},
            )
            documents.append(doc)

    if len(documents) >= MAX_TOTAL_CHUNKS:
        import logging
        logging.getLogger(__name__).warning(
            "Chunk cap (%d) reached — large repo was truncated for RAG indexing.",
            MAX_TOTAL_CHUNKS,
        )

    return documents


def get_ingestion_stats(files: list[dict], documents: list[Document]) -> dict:
    """Return a summary dict for the /rag/index response."""
    unique_files = {doc.metadata["file_path"] for doc in documents}
    return {
        "files_fetched": len(files),
        "files_indexed": len(unique_files),
        "chunks_indexed": len(documents),
    }
