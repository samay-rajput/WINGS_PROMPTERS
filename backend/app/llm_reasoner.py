"""
llm_reasoner.py
───────────────
Semantic reasoning engine for Codebase Intelligence Agent.
Handles prompting while relying on `llm_provider` for robust pipeline
execution via sequential provider limits/fallbacks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm_provider import generate_with_fallback

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction from LLM output (handles markdown fences)."""
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

    logger.error("Failed to extract JSON from LLM response: %s...", text[:200])
    return {"raw_response": text}


# ── Public reasoning functions ────────────────────────────────────────────

async def explain_folder_structure(signal_json: dict[str, Any]) -> dict[str, Any]:
    system_prompt = (
        "You are a senior software architect.\n"
        "Based on the folder names and sample files provided, explain the likely "
        "responsibility of each directory.\n"
        "Also infer the architectural style if possible "
        "(MVC, layered, modular, component-based, microservices, etc.).\n"
        "Return STRICT JSON with this schema:\n"
        "{\n"
        '  "architecture_style": "<inferred style>",\n'
        '  "folders": {\n'
        '    "<folder_name>": "<purpose description>",\n'
        "    ...\n"
        "  }\n"
        "}\n"
        "Do NOT include markdown fences or extra commentary."
    )

    user_prompt = (
        "Here is the folder structure signal for a software repository:\n\n"
        f"{json.dumps(signal_json, indent=2)}\n\n"
        "Provide your analysis."
    )

    try:
        response_text = await generate_with_fallback(system_prompt, user_prompt)
        return _extract_json(response_text)
    except Exception as e:
        logger.error("All providers failed during folder structure explanation: %s", e)
        return {"architecture_style": "unknown (LLM failure)", "folders": {}}


async def explain_execution_flow(
    entry_file: str,
    entry_content: str,
    extra_context: str = "",
) -> list[str]:
    system_prompt = (
        "You are a senior software architect.\n"
        "This file represents the startup entry point of a software system.\n"
        "Explain step-by-step runtime execution during application initialization.\n"
        "Adapt your explanation based on the detected ecosystem "
        "(Node server, Flask/Django app, Spring Boot app, React bootstrap, etc.).\n"
        "Return STRICT JSON: an ordered list of strings, each describing one step.\n"
        'Example: ["Step 1: ...", "Step 2: ...", ...]\n'
        "Do NOT include markdown fences or extra commentary."
    )

    user_prompt = f"Entry file: {entry_file}\n\n```\n{entry_content}\n```"
    if extra_context:
        user_prompt += f"\n\nAdditional related file context:\n```\n{extra_context}\n```"

    try:
        response_text = await generate_with_fallback(system_prompt, user_prompt)
        result = _extract_json(response_text)
        
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("steps", "execution_flow", "flow"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [str(v) for v in result.values()]
        return [str(result)]
        
    except Exception as e:
        logger.error("All providers failed during execution flow narration: %s", e)
        return ["Analysis failed: No responsive LLM providers currently available."]
