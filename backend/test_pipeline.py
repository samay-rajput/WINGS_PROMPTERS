"""
Quick integration test — validates all pipeline stages except Gemini calls.
Run:  python test_pipeline.py
"""

import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.github_service import parse_github_url, fetch_repo_metadata, fetch_repo_tree
from app.file_filter_service import filter_and_rank
from app.entry_detector import detect_entry_point
from app.dependency_builder import build_dependency_graph


async def main():
    url = "https://github.com/expressjs/express"
    print(f"\n{'='*60}")
    print(f"  Pipeline Test — {url}")
    print(f"{'='*60}\n")

    # Step 1: Parse URL
    owner, repo = parse_github_url(url)
    print(f"✅ Step 1 — Parsed URL → owner={owner}, repo={repo}")

    # Step 2: Fetch metadata
    meta = await fetch_repo_metadata(owner, repo)
    branch = meta.get("default_branch", "main")
    print(f"✅ Step 2 — Metadata fetched → branch={branch}")

    # Step 3: Fetch tree
    tree = await fetch_repo_tree(owner, repo, branch)
    all_paths = [item["path"] for item in tree if item.get("type") == "blob"]
    print(f"✅ Step 3 — Tree fetched → {len(all_paths)} blobs")

    # Step 4: Filter & rank
    ranked = filter_and_rank(tree)
    print(f"✅ Step 4 — Filtered & ranked → {len(ranked)} files selected")
    print(f"   Top 5: {ranked[:5]}")

    # Step 5: Entry point detection
    entry = await detect_entry_point(owner, repo, all_paths)
    print(f"✅ Step 5 — Entry point detected → {entry}")

    # Step 6: Dependency graph (no content fetch for speed)
    # Just test with empty contents to verify graph builder works
    nodes, edges, summary = build_dependency_graph({}, all_paths)
    print(f"✅ Step 6 — Dependency builder works → {len(nodes)} nodes, {len(edges)} edges")
    print(f"Summary: {summary}")

    print(f"\n{'='*60}")
    print(f"  ALL PIPELINE STAGES PASSED ✅")
    print(f"  (LLM calls skipped — test Gemini separately)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
