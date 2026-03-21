"""
chat_service.py
----------------
Implements the mode-aware RAG chat pipeline:

  user query + mode → retrieve chunks → build mode prompt → Gemini LLM → structured answer

Modes
-----
  B1 — Critical File Identification
  B2 — Execution Flow Explanation
  B3 — Intelligent Repository Summary
"""

import os
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from . import rag_service, vector_store

# ---------------------------------------------------------------------------
# LLM setup (Groq - Llama3)
# ---------------------------------------------------------------------------

# Optimized for code analysis and complex reasoning
LLM_MODEL = "llama-3.3-70b-versatile"


def _get_llm() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY_RAG") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY_RAG is not set. "
            "Please check your .env file."
        )
    return ChatGroq(
        model_name=LLM_MODEL,
        groq_api_key=api_key,
        temperature=0,  # Strict grounding for code analysis
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

  HTTP Request → Router/Route definition → Controller/Handler → Service/Business logic → Database/External call → Response

For each step:
- Identify the relevant FILE_PATH.
- Describe what happens at that step.
- Show how control is passed to the next step.
Use bullet points or numbered steps for clarity.
""".strip(),

    "B3": """
MODE: Intelligent Repository Summary

Your task is to provide a high-level architectural overview derived purely from the code. Cover:
1. **Tech Stack** — Languages, frameworks, libraries actually used.
2. **Architecture Type** — MVC, microservices, serverless, monolith, etc.
3. **Key Design Patterns** — Dependency injection, repository pattern, middleware, etc.
4. **Entry Points** — Main files / bootstrapping files.
5. **Notable Components** — Any standout modules, services, or abstractions.

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
    question : str  — The user's question about the repository.
    mode     : str  — One of "B1", "B2", "B3".

    Returns
    -------
    dict with keys: answer (str), sources (list[str])
    """
    mode = mode.upper()

    # Guard: repository must be indexed first
    if not vector_store.is_ready():
        raise RuntimeError(
            "No repository has been indexed yet. "
            "Please call POST /rag/index with a GitHub URL first."
        )

    # 1. Retrieve top-50 relevant chunks (massive context for Gemini flash)
    docs: list[Document] = rag_service.retrieve(question, k=50)

    if not docs:
        return {
            "answer": "I do not have enough context to answer this question.",
            "sources": [],
        }

    # 2. Build prompts
    system_prompt = _build_system_prompt(mode)
    human_message = _build_human_message(question, docs)

    # 3. Call Gemini LLM
    llm = _get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message),
    ]
    response = llm.invoke(messages)
    answer_text = response.content if hasattr(response, "content") else str(response)

    # 4. Collect source file references
    sources = _extract_sources(docs)

    return {
        "answer": answer_text,
        "sources": sources,
    }
