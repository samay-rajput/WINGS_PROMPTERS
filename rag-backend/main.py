"""
Chat with Repository — RAG Backend
Entry point: starts the FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Fix for Windows FAISS OpenMP deadlock
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Load environment variables from .env before anything else
load_dotenv()

from api.rag_routes import router as rag_router

app = FastAPI(
    title="Chat with Repository — RAG API",
    description=(
        "Ingest any GitHub repository and chat with its codebase "
        "using Gemini + FAISS-powered RAG."
    ),
    version="1.0.0",
)

# Allow all origins for hackathon demo; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the RAG router
app.include_router(rag_router, prefix="/rag", tags=["RAG"])


from fastapi.responses import RedirectResponse

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to the Swagger UI automatically."""
    return RedirectResponse(url="/docs")
