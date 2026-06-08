"""
rag_routes.py
-------------
FastAPI router exposing the two RAG endpoints:

  POST /rag/index  — ingest a GitHub repository
  POST /rag/chat   — query the indexed repository
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from services import rag_service, chat_service, vector_store

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class IndexRequest(BaseModel):
    github_url: str

    @field_validator("github_url")
    @classmethod
    def must_be_github(cls, v: str) -> str:
        v = v.strip()
        if "github.com" not in v:
            raise ValueError("URL must be a valid github.com repository URL.")
        return v


class IndexResponse(BaseModel):
    status: str
    owner: str
    repo: str
    branch: str
    files_fetched: int
    files_indexed: int
    chunks_indexed: int


class ChatRequest(BaseModel):
    question: str
    mode: str

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        v = v.upper()
        if v not in {"B1", "B2", "B3"}:
            raise ValueError("mode must be one of: B1, B2, B3")
        return v

    @field_validator("question")
    @classmethod
    def non_empty_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty.")
        return v


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    mode: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/index", response_model=IndexResponse, summary="Index a GitHub repository")
def index_repository(body: IndexRequest):
    """
    Fetch a GitHub repository, process its source files, and build an
    in-memory FAISS vector store.  Any previously indexed repository is
    replaced.
    """
    try:
        stats = rag_service.index_repository(body.github_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}")

    return IndexResponse(status="success", **stats)


@router.post("/chat", response_model=ChatResponse, summary="Chat with the indexed repository")
def chat_with_repository(body: ChatRequest):
    """
    Answer a question about the currently indexed repository using RAG.

    **Modes**
    - `B1` — Critical file identification (auth, DB, controllers)
    - `B2` — Execution flow explanation (request-to-response trace)
    - `B3` — Intelligent repository summary (tech stack, architecture)
    """
    if not vector_store.is_ready():
        raise HTTPException(
            status_code=400,
            detail=(
                "No repository is indexed yet. "
                "Please call POST /rag/index with a GitHub URL first."
            ),
        )

    try:
        result = chat_service.chat(question=body.question, mode=body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        mode=body.mode,
    )


@router.get("/status", summary="Check if a repository is indexed")
async def index_status():
    """Returns indexing stats for the currently loaded repository, or a not-ready signal."""
    if not vector_store.is_ready():
        return {"indexed": False, "message": "No repository indexed yet."}
    stats = vector_store.get_stats()
    return {"indexed": True, **stats}
