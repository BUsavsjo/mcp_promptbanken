from __future__ import annotations

import os
import re
from typing import Any

import httpx


SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("PROMPTBANKEN_SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("PROMPTBANKEN_SUPABASE_ANON_KEY")
)

_ALLOWED_CONTEXT_KEYS = frozenset({"generell", "kommun", "skola", "företag", "förening", "privat"})
_ALLOWED_TOOL_METADATA = frozenset(
    {"get_prompt", "list_packages", "get_package", "list_package_prompts"}
)
_ALLOWED_PACKAGE_TYPES = frozenset({"collection", "workflow"})
_SAFE_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _safe_slug(value: str | None) -> str | None:
    if isinstance(value, str) and len(value) <= 120 and _SAFE_SLUG.fullmatch(value):
        return value
    return None


def _safe_context_keys(context_keys: list[str] | None) -> list[str] | None:
    if not isinstance(context_keys, list):
        return None
    return [
        key for key in context_keys if isinstance(key, str) and key in _ALLOWED_CONTEXT_KEYS
    ][:10]


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    safe: dict[str, Any] = {}
    tool = metadata.get("tool")
    if isinstance(tool, str) and tool in _ALLOWED_TOOL_METADATA:
        safe["tool"] = tool

    package_type = metadata.get("package_type")
    if isinstance(package_type, str) and package_type in _ALLOWED_PACKAGE_TYPES:
        safe["package_type"] = package_type
    return safe


def track_usage_event(
    *,
    event_type: str,
    outcome: str = "success",
    prompt_slug: str | None = None,
    package_slug: str | None = None,
    context_keys: list[str] | None = None,
    result_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Send best-effort anonymous analytics for the open MCP endpoint.

    Never send keys, user input, rendered prompt text, user-agent, or IP.
    Analytics failure must not fail an MCP tool call.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    payload = {
        "p_source": "open_mcp",
        "p_event_type": event_type,
        "p_outcome": outcome,
        "p_prompt_slug": _safe_slug(prompt_slug),
        "p_package_slug": _safe_slug(package_slug),
        "p_context_keys": _safe_context_keys(context_keys),
        "p_area": None,
        "p_risk_level": None,
        "p_result_count": result_count if type(result_count) is int and result_count >= 0 else None,
        "p_catalog_version": None,
        "p_metadata": _safe_metadata(metadata),
    }

    try:
        with httpx.Client(timeout=2.0) as client:
            client.post(
                f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/track_library_usage_event",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except Exception:
        return
