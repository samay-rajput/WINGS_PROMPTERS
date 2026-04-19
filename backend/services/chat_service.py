"""
chat_service.py
---------------
Implements the mode-aware RAG chat pipeline:

  user query + mode -> retrieve chunks -> build mode prompt -> Gemini LLM -> structured answer

Modes
-----
  B1 - Critical File Identification
  B2 - Execution Flow Explanation
  B3 - Intelligent Repository Summary
"""

from __future__ import annotations

import logging
import os
import time

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from . import rag_service, vector_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM setup (Gemini)
# ---------------------------------------------------------------------------

LLM_MODEL = os.getenv("GEMINI_MODEL_RAG", "gemini-2.5-flash")
MAX_RETRY_ROUNDS = max(1, int(os.getenv("GEMINI_CHAT_RETRY_ROUNDS", "3")))


def _candidate_api_keys() -> list[tuple[str, str]]:
    """Return unique configured Gemini RAG keys in priority order."""
    candidates: list[tuple[str, str]] = []
    seen_values: set[str] = set()

    for env_name in (
        "GEMINI_API_RAG",
        "GEMINI_API_RAG_SECONDARY",
        "GEMINI_API_KEY_RAG",
        "GEMINI_API_KEY_RAG_SECONDARY",
    ):
        value = (os.getenv(env_name) or "").strip()
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        candidates.append((env_name, value))

    return candidates


def _looks_like_auth_or_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "invalid api key" in msg
        or "api key not valid" in msg
        or "invalid_argument" in msg
        or "permission_denied" in msg
        or "resource_exhausted" in msg
        or "rate limit" in msg
        or "quota" in msg
        or "429" in msg
        or "401" in msg
    )


def _invoke_with_key_fallback(messages: list[SystemMessage | HumanMessage]):
    candidates = _candidate_api_keys()
    if not candidates:
        raise EnvironmentError(
            "No Gemini RAG API key configured. "
            "Set GEMINI_API_RAG (and optionally GEMINI_API_RAG_SECONDARY) in backend/.env."
        )

    attempted_keys: set[str] = set()
    last_error: Exception | None = None

    for round_idx in range(1, MAX_RETRY_ROUNDS + 1):
        saw_transient = False

        for idx, (env_name, api_key) in enumerate(candidates, start=1):
            attempted_keys.add(env_name)
            try:
                llm = ChatGoogleGenerativeAI(
                    model=LLM_MODEL,
                    google_api_key=api_key,
                    temperature=0,
                    max_retries=0,
                )
                response = llm.invoke(messages)
                if idx > 1:
                    logger.warning(
                        "[RAG CHAT] Fallback Gemini key succeeded using %s.",
                        env_name,
                    )
                return response
            except Exception as exc:
                last_error = exc
                msg = str(exc).lower()

                if _looks_like_auth_or_quota_error(exc):
                    logger.warning("[RAG CHAT] Gemini key rejected/limited for %s: %s", env_name, exc)
                    continue

                if "503" in msg or "unavailable" in msg or "timed out" in msg or "deadline" in msg:
                    saw_transient = True
                    logger.warning(
                        "[RAG CHAT] Transient Gemini failure on %s (round %d/%d): %s",
                        env_name,
                        round_idx,
                        MAX_RETRY_ROUNDS,
                        exc,
                    )
                    continue

                raise

        if saw_transient and round_idx < MAX_RETRY_ROUNDS:
            time.sleep(min(2 ** (round_idx - 1), 4))
            continue
        break

    attempted = ", ".join(sorted(attempted_keys))
    detail = f" Last error: {last_error}" if last_error else ""
    raise EnvironmentError(
        "All configured Gemini RAG keys failed for chat. "
        f"Attempted: {attempted}.{detail}"
    )


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

BASE_RULES = """
You are an expert, highly intelligent senior AI engineer analyzing a GitHub repository.
You will be provided with the text of filtered files relevant to the query to help answer the user's question, no matter if it is simple or complex.

Follow these guidelines:
1. Use the provided code context as your primary source of truth. Always cite the specific `FILE_PATH` when referencing code.
2. If the context does not explicitly contain the full exact answer, do NOT reject the question. Use your general programming knowledge to deduce, infer, or explain how it likely works based on the framework and available snippets.
3. Be as helpful as possible. For complex questions, provide the best architectural or conceptual answer you can derive from the snippets. For simple questions, just answer it directly.
4. Do not completely invent unknown file contents, but you may explain standard framework conventions and how this repository likely follows them.
5. Be concise, precise, and highly technical.
""".strip()


MODE_INSTRUCTIONS = {
    "B1": """
MODE: Critical File Identification

Your task is to identify the most important files in the repository related to:
- Authentication and authorization
- Database configuration and connection
- Controllers, routers, or API handlers

For each critical file:
- State the FILE_PATH clearly.
- Explain specifically what role it plays.
- Quote or reference key code snippets that justify its importance.
""".strip(),

    "B2": """
MODE: Execution Flow Explanation

Your task is to trace the complete runtime execution flow of this application.
Follow this chain precisely:

  HTTP Request -> Router/Route definition -> Controller/Handler -> Service/Business logic -> Database/External call -> Response

For each step:
- Identify the relevant FILE_PATH.
- Describe what happens at that step.
- Show how control is passed to the next step.
Use bullet points or numbered steps for clarity.
""".strip(),

    "B3": """
MODE: Intelligent Repository Summary

Your task is to provide a high-level architectural overview derived purely from the code. Cover:
1. **Tech Stack** - Languages, frameworks, libraries actually used.
2. **Architecture Type** - MVC, microservices, serverless, monolith, etc.
3. **Key Design Patterns** - Dependency injection, repository pattern, middleware, etc.
4. **Entry Points** - Main files / bootstrapping files.
5. **Notable Components** - Any standout modules, services, or abstractions.

Cite FILE_PATHs as evidence for each claim.
""".strip(),
}


def _build_system_prompt(mode: str) -> str:
    mode_instruction = MODE_INSTRUCTIONS.get(mode.upper())
    if not mode_instruction:
        raise ValueError(f"Unknown mode: {mode!r}. Must be one of B1, B2, B3.")
    return f"{BASE_RULES}\n\n{mode_instruction}"


def _build_human_message(question: str, docs: list[Document]) -> str:
    context_blocks = "\n\n---\n\n".join(doc.page_content for doc in docs)
    return (
        f"RETRIEVED CODE CONTEXT:\n\n{context_blocks}\n\n"
        f"---\n\nQUESTION: {question}"
    )


def _extract_sources(docs: list[Document]) -> list[str]:
    """Deduplicate and sort file paths from retrieved documents."""
    paths = {doc.metadata.get("file_path", "unknown") for doc in docs}
    return sorted(paths)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat(question: str, mode: str) -> dict:
    """
    Main chat entry point.

    Parameters
    ----------
    question : str  - The user's question about the repository.
    mode     : str  - One of "B1", "B2", "B3".

    Returns
    -------
    dict with keys: answer (str), sources (list[str])
    """
    mode = mode.upper()

    if not vector_store.is_ready():
        raise RuntimeError(
            "No repository has been indexed yet. "
            "Please call POST /rag/index with a GitHub URL first."
        )

    docs: list[Document] = rag_service.retrieve(question, k=20)

    if not docs:
        return {
            "answer": "I do not have enough context to answer this question.",
            "sources": [],
        }

    system_prompt = _build_system_prompt(mode)
    human_message = _build_human_message(question, docs)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message),
    ]

    response = _invoke_with_key_fallback(messages)
    answer_text = response.content if hasattr(response, "content") else str(response)
    sources = _extract_sources(docs)

    return {
        "answer": answer_text,
        "sources": sources,
    }
