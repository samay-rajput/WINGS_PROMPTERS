"""
Pydantic models for request / response validation.
Keeps the API contract explicit and self-documenting.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl
from typing import Any


# ── Request ─────────────────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    github_url: str = Field(
        ...,
        description="Full HTTPS URL to a public GitHub repository",
        examples=["https://github.com/expressjs/express"],
    )


# ── Response sub-models ────────────────────────────────────────────────────
class EntryAnalysis(BaseModel):
    entry_file: str
    runtime_entry_file: str | None = None
    execution_flow: list[str]


class GraphNode(BaseModel):
    id: str
    label: str
    layer: str = "unknown"


class GraphEdge(BaseModel):
    source: str
    target: str


# ── Top-level response ─────────────────────────────────────────────────────
class AnalyzeResponse(BaseModel):
    m1_folder_explanation: dict[str, Any]
    m2_entry_analysis: EntryAnalysis
    m3_dependency_graph: list[GraphEdge]
    m3_architecture_summary: str


# ── Chat Support ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    repo_url: str


class ChatResponse(BaseModel):
    reply: str

