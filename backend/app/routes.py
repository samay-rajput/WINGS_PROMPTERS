"""
routes.py
─────────
FastAPI router for the /analyze endpoint.
Keeps HTTP concerns separate from business logic.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import AnalyzeRequest, AnalyzeResponse, ChatRequest, ChatResponse
from app.analysis_orchestrator import run_analysis
from app.llm_provider import generate_with_fallback
from app.github_service import (
    fetch_repo_metadata,
    fetch_repo_tree,
    parse_github_url,
)
from app.file_filter_service import filter_and_rank

logger = logging.getLogger(__name__)

router = APIRouter()

_ERROR_PAYLOAD = {"error": "Analysis failed"}
_MAX_GRAPH_EDGES = 5000
_OWNER_REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$")
_FRAMEWORK_CONFIG_SUFFIXES = (
    "vite.config.js",
    "next.config.js",
    "webpack.config.js",
    "docusaurus.config.js",
)
_RUNTIME_ENTRY_CANDIDATES = ("src/main.js", "src/index.js", "main.py")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "dict"):
        dumped = value.dict()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _normalize_graph_edges(payload: dict[str, Any]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, str]] = []

    def _append(source: Any, target: Any) -> None:
        if len(edges) >= _MAX_GRAPH_EDGES:
            return
        src = str(source).strip() if source is not None else ""
        tgt = str(target).strip() if target is not None else ""
        if not src or not tgt:
            return
        key = (src, tgt)
        if key in seen:
            return
        seen.add(key)
        edges.append({"source": src, "target": tgt})

    def _consume_edge_like(edge_like: Any) -> None:
        if len(edges) >= _MAX_GRAPH_EDGES:
            return
        if isinstance(edge_like, dict):
            _append(
                edge_like.get("source", edge_like.get("from")),
                edge_like.get("target", edge_like.get("to")),
            )
            return
        if isinstance(edge_like, (list, tuple)) and len(edge_like) >= 2:
            _append(edge_like[0], edge_like[1])

    edge_candidates = payload.get("m3_edges")
    if not edge_candidates:
        graph = payload.get("m3_dependency_graph")
        if isinstance(graph, list):
            edge_candidates = graph
        elif isinstance(graph, dict):
            nested_edges = graph.get("edges")
            if isinstance(nested_edges, list):
                edge_candidates = nested_edges
            else:
                for source, targets in graph.items():
                    if source in {"nodes", "edges"}:
                        continue
                    if isinstance(targets, (str, bytes)):
                        _append(source, targets)
                        continue
                    if not isinstance(targets, (list, tuple, set)):
                        continue
                    for target in targets:
                        _append(source, target)
                    if len(edges) >= _MAX_GRAPH_EDGES:
                        break
        else:
            edge_candidates = []

    if isinstance(edge_candidates, list):
        for candidate in edge_candidates:
            _consume_edge_like(candidate)
            if len(edges) >= _MAX_GRAPH_EDGES:
                break

    if len(edges) >= _MAX_GRAPH_EDGES:
        logger.warning("[API] dependency graph edges capped at %d", _MAX_GRAPH_EDGES)

    return edges


def _collect_known_paths(payload: dict[str, Any], normalized_edges: list[dict[str, str]]) -> set[str]:
    paths: set[str] = set()

    def _add(value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            paths.add(text)

    for edge in normalized_edges:
        _add(edge.get("source"))
        _add(edge.get("target"))

    nodes = payload.get("m3_nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                _add(node.get("id"))
                _add(node.get("path"))
                _add(node.get("label"))
            else:
                _add(node)

    graph = payload.get("m3_dependency_graph")
    if isinstance(graph, dict):
        for source, targets in graph.items():
            if source in {"nodes", "edges"}:
                continue
            _add(source)
            if isinstance(targets, (list, tuple, set)):
                for target in targets:
                    _add(target)
            elif isinstance(targets, (str, bytes)):
                _add(targets)

    return paths


def _normalize_entry_analysis(
    payload: dict[str, Any],
    normalized_edges: list[dict[str, str]],
) -> dict[str, Any]:
    raw_entry = _as_dict(payload.get("m2_entry_analysis"))
    entry_file = str(raw_entry.get("entry_file", "ENTRY_NOT_FOUND")).strip() or "ENTRY_NOT_FOUND"

    flow_raw = raw_entry.get("execution_flow", [])
    if isinstance(flow_raw, list):
        execution_flow = [str(step).strip() for step in flow_raw if str(step).strip()]
    elif flow_raw:
        execution_flow = [str(flow_raw).strip()]
    else:
        execution_flow = []

    runtime_entry_file_raw = raw_entry.get("runtime_entry_file")
    runtime_entry_file = (
        str(runtime_entry_file_raw).strip()
        if runtime_entry_file_raw not in (None, "")
        else None
    )

    if (
        runtime_entry_file is None
        and any(entry_file.endswith(suffix) for suffix in _FRAMEWORK_CONFIG_SUFFIXES)
    ):
        known_paths = _collect_known_paths(payload, normalized_edges)
        for candidate in _RUNTIME_ENTRY_CANDIDATES:
            if candidate in known_paths or any(p.endswith(f"/{candidate}") for p in known_paths):
                runtime_entry_file = candidate
                break

    result: dict[str, Any] = {
        "entry_file": entry_file,
        "execution_flow": execution_flow,
    }
    if runtime_entry_file:
        result["runtime_entry_file"] = runtime_entry_file
    return result


def _normalize_analysis_payload(raw_result: Any) -> dict[str, Any]:
    payload = _as_dict(raw_result)
    normalized_edges = _normalize_graph_edges(payload)

    m1_raw = _as_dict(payload.get("m1_folder_explanation"))
    summary = payload.get("m3_architecture_summary", payload.get("m3_summary", ""))

    return {
        "m1_folder_explanation": m1_raw,
        "m2_entry_analysis": _normalize_entry_analysis(payload, normalized_edges),
        "m3_dependency_graph": normalized_edges,
        "m3_architecture_summary": str(summary) if summary is not None else "",
    }


def _parse_repo_reference(repo_ref: str) -> tuple[str, str]:
    cleaned = (repo_ref or "").strip().rstrip("/")
    if "github.com/" in cleaned:
        return parse_github_url(cleaned)

    match = _OWNER_REPO_RE.fullmatch(cleaned)
    if not match:
        raise ValueError(f"Cannot parse owner/repo from input: {repo_ref}")

    owner = match.group("owner")
    repo = match.group("repo").removesuffix(".git")
    return owner, repo


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    response_model_exclude_none=True,
    summary="Analyse a public GitHub repository",
    description=(
        "Accepts a public GitHub repository URL and returns structured "
        "architectural intelligence: folder explanations (M1), entry-point "
        "analysis with execution flow (M2), and a file-level dependency graph (M3)."
    ),
)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    logger.info("[API] /analyze request received")

    try:
        logger.info("[API] repository analysis started")
        raw_result = await run_analysis(request.github_url)
        normalized_payload = _normalize_analysis_payload(raw_result)
        logger.info("[API] dependency graph normalized")
        logger.info("[API] response sent")
        return AnalyzeResponse(**normalized_payload)
    except Exception as exc:
        logger.exception("Analysis failed: %s", exc)
        return JSONResponse(status_code=500, content=_ERROR_PAYLOAD)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    logger.info("[API] /chat request received")
    try:
        owner, repo = _parse_repo_reference(request.repo_url)

        # Load lightweight repository context
        meta = await fetch_repo_metadata(owner, repo)
        branch = meta.get("default_branch", "main")
        tree = await fetch_repo_tree(owner, repo, branch)
        blob_paths = [item["path"] for item in tree if item.get("type") == "blob"]
        ranked_paths = filter_and_rank(tree)
        context_paths = ranked_paths[:40] if ranked_paths else blob_paths[:40]
        context_preview = "\n".join(context_paths) if context_paths else "(no repository files found)"

        system_prompt = (
            "You are a helpful software architecture assistant.\n"
            f"Repository: {owner}/{repo} (branch: {branch}).\n"
            f"Total files discovered: {len(blob_paths)}.\n"
            "Answer the user's questions concerning the repository structure.\n"
            "Use the lightweight, filtered file list below as context:\n"
            f"```\n{context_preview}\n```"
        )

        reply = await generate_with_fallback(system_prompt, request.message)
        logger.info("[API] response sent")
        return ChatResponse(reply=reply)
    except Exception as exc:
        logger.error("Chat failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content=_ERROR_PAYLOAD)
