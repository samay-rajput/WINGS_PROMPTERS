"""
main.py — Application entry point
──────────────────────────────────
Creates the FastAPI app, mounts the router, and configures logging.
Run with:  uvicorn app.main:app --reload
"""

from __future__ import annotations

# ── MUST be before all other imports — prevent TF from loading native DLLs ──
# TF's C++ extensions conflict with FAISS on Windows/Anaconda.
# These env vars tell HuggingFace/sentence-transformers to use PyTorch only.
import os
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# ─────────────────────────────────────────────────────────────────────────────

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from api.rag_routes import router as rag_router

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Codebase Intelligence Agent",
    version="1.0.0",
    description=(
        "Analyses any public GitHub repository and returns structured "
        "architectural intelligence — folder explanations, entry-point "
        "detection with execution flow, and a file-level dependency graph."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # allow all origins during dev (frontend can run on any port)
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(rag_router, prefix="/rag", tags=["RAG"])


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
