"""
analysis_orchestrator.py
────────────────────────
Top-level orchestration layer.  Wires together every service into the
complete analysis pipeline:

  GitHub URL
    → metadata + tree fetch
    → file filtering & scoring
    → M1 folder signal extraction + LLM explanation
    → M2 entry-point detection + execution-flow reasoning
    → M3 dependency graph construction (pure Python)
    → unified JSON response
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any

from app.config import MAX_FILE_SIZE_BYTES
from app.github_service import (
    fetch_file_content,
    fetch_repo_metadata,
    fetch_repo_tree,
    parse_github_url,
)
from app.file_filter_service import filter_and_rank
from app.entry_detector import detect_entry_point
from app.dependency_builder import build_dependency_graph
from app.llm_reasoner import explain_execution_flow, explain_folder_structure
from app.models import AnalyzeResponse, EntryAnalysis

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _build_folder_signal(tree_paths: list[str]) -> dict[str, Any]:
    """Build the compact folder-intelligence signal sent to Gemini (M1).

    Output shape:
      {
        "folders": { "src": ["controllers", "services"], ... },
        "samples": { "controllers": ["authController.js"], ... }
      }
    """
    folders: dict[str, set[str]] = defaultdict(set)
    samples: dict[str, list[str]] = defaultdict(list)

    for p in tree_paths:
        parts = p.replace("\\", "/").split("/")
        if len(parts) >= 2:
            top_dir = parts[0]
            sub_dir = parts[1]
            folders[top_dir].add(sub_dir)
            # Keep ≤3 sample files per sub-dir
            if len(parts) >= 3 and len(samples[sub_dir]) < 3:
                samples[sub_dir].append(parts[-1])
        elif len(parts) == 1:
            folders["<root>"].add(parts[0])

    return {
        "folders": {k: sorted(v) for k, v in folders.items()},
        "samples": dict(samples),
    }


async def _batch_fetch_contents(
    owner: str,
    repo: str,
    paths: list[str],
    concurrency: int = 10,
) -> dict[str, str]:
    """Fetch file contents in parallel with bounded concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, str] = {}

    async def _fetch(p: str) -> None:
        async with semaphore:
            content = await fetch_file_content(owner, repo, p)
            if content and len(content) <= MAX_FILE_SIZE_BYTES:
                results[p] = content

    await asyncio.gather(*[_fetch(p) for p in paths])
    return results


# ── Main pipeline ───────────────────────────────────────────────────────────

async def run_analysis(github_url: str) -> AnalyzeResponse:
    """Execute the full analysis pipeline and return a validated response."""

    # 1. Parse URL  →  owner / repo
    owner, repo = parse_github_url(github_url)
    logger.info("═══ Starting analysis: %s/%s ═══", owner, repo)

    # 2. Metadata  →  default branch
    meta = await fetch_repo_metadata(owner, repo)
    branch = meta.get("default_branch", "main")
    logger.info("Default branch: %s", branch)

    # 3. Full tree
    tree = await fetch_repo_tree(owner, repo, branch)
    all_paths = [item["path"] for item in tree if item.get("type") == "blob"]
    logger.info("Total blobs in tree: %d", len(all_paths))

    # 4. Filter & rank
    ranked_paths = filter_and_rank(tree)

    # 5. Build folder signal (uses ALL paths for full picture)
    folder_signal = _build_folder_signal(all_paths)

    # 6. Detect entry point (uses ALL paths so config files are visible)
    entry_file = await detect_entry_point(owner, repo, all_paths)

    runtime_entry_file = None
    if any(entry_file.endswith(x) for x in ["vite.config.js", "next.config.js", "webpack.config.js", "docusaurus.config.js"]):
        for p in ["src/main.js", "src/index.js", "main.py"]:
            if any(path.endswith(p) for path in all_paths):
                runtime_entry_file = next(path for path in all_paths if path.endswith(p))
                break

    flow_entry_file = runtime_entry_file or entry_file

    # 7. Fetch file contents in parallel (no LLM, just GitHub API)
    file_contents, entry_content_raw = await asyncio.gather(
        _batch_fetch_contents(owner, repo, ranked_paths, concurrency=10),
        fetch_file_content(owner, repo, flow_entry_file),
    )

    entry_content = entry_content_raw or ""

    # 8. M1 — folder explanation (LLM call #1)
    m1_result = await explain_folder_structure(folder_signal)

    # 9. M2 — execution flow reasoning (LLM call #2, sequential to avoid 429)
    extra_ctx = ""
    if entry_content:
        import re as _re
        first_import = _re.search(
            r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|from\s+([A-Za-z0-9_\.]+)\s+import)""",
            entry_content,
        )
        if first_import:
            raw = (first_import.group(1) or first_import.group(2) or first_import.group(3) or "").strip()
            candidates: list[str] = []

            if raw:
                if raw.startswith("."):
                    base_dir = os.path.dirname(flow_entry_file).replace("\\", "/")
                    rel = os.path.normpath(os.path.join(base_dir, raw)).replace("\\", "/")
                    candidates.extend([
                        rel,
                        rel + ".js",
                        rel + ".ts",
                        rel + ".jsx",
                        rel + ".tsx",
                        rel + ".py",
                        rel + "/index.js",
                        rel + "/index.ts",
                        rel + "/index.jsx",
                        rel + "/index.tsx",
                    ])
                else:
                    candidates.append(raw)
                    if "." in raw:
                        candidates.append(raw.replace(".", "/") + ".py")

            seen: set[str] = set()
            for candidate in candidates:
                normalized = candidate.strip("./")
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)

                if normalized in file_contents and file_contents[normalized]:
                    extra_ctx = file_contents[normalized][:3000]
                    break

                exact_path = next(
                    (p for p in all_paths if p == normalized or p.endswith("/" + normalized)),
                    None,
                )
                if not exact_path:
                    continue

                cached = file_contents.get(exact_path)
                if cached:
                    extra_ctx = cached[:3000]
                    break

                fetched = await fetch_file_content(owner, repo, exact_path)
                if fetched:
                    extra_ctx = fetched[:3000]
                    break

    execution_flow = await explain_execution_flow(flow_entry_file, entry_content, extra_ctx)

    # 10. M3 — dependency graph (pure Python, no LLM)
    nodes, edges, summary = build_dependency_graph(file_contents, all_paths)

    # 11. Assemble response
    logger.info("═══ Analysis complete: %s/%s ═══", owner, repo)
    return AnalyzeResponse(
        m1_folder_explanation=m1_result,
        m2_entry_analysis=EntryAnalysis(
            entry_file=entry_file,
            runtime_entry_file=runtime_entry_file,
            execution_flow=execution_flow,
        ),
        m3_dependency_graph=edges,
        m3_architecture_summary=summary,
    )
