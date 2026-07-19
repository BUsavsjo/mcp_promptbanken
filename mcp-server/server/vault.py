"""Valvet: sex nyckelhash-baserade RPC:er för personliga insättningar
(prompt/assistant). Samma anon-beviljade förtroendemodell som
pro_templates.py -- nyckelns sha256-hash är i sig beviset på behörighet.

Se promptbanken/supabase/migrations/20260716101500_valvet_read_rpcs.sql,
20260716102000_valvet_save_rpc.sql, 20260716102500_valvet_update_archive_rpc.sql.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("promptbanken_mcp.vault")

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def is_configured() -> bool:
    return bool(_SUPABASE_URL and _ANON_KEY)


def _headers() -> dict[str, str]:
    return {
        "apikey": _ANON_KEY,
        "Authorization": f"Bearer {_ANON_KEY}",
        "Content-Type": "application/json",
    }


def _call_rpc(function_name: str, payload: dict[str, Any]) -> Any:
    url = f"{_SUPABASE_URL}/rest/v1/rpc/{function_name}"
    response = httpx.post(url, headers=_headers(), json=payload, timeout=5)
    response.raise_for_status()
    return response.json()


def list_items(
    mcp_key: str,
    type_: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List the caller's own Valvet items (module='valvet')."""
    if not mcp_key or not is_configured():
        return []
    try:
        return _call_rpc(
            "list_my_items_for_key",
            {
                "p_key_hash": _hash_key(mcp_key),
                "p_type": type_,
                "p_category": category,
                "p_status": status,
            },
        )
    except Exception as exc:
        logger.error("list_my_items_failed error=%s", exc)
        return []


def search_items(
    mcp_key: str,
    query: str,
    type_: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Search the caller's own Valvet items (title/content/category)."""
    if not mcp_key or not is_configured():
        return []
    try:
        return _call_rpc(
            "search_my_items_for_key",
            {
                "p_key_hash": _hash_key(mcp_key),
                "p_query": query,
                "p_type": type_,
                "p_category": category,
            },
        )
    except Exception as exc:
        logger.error("search_my_items_failed error=%s", exc)
        return []


def get_item(mcp_key: str, item_id: str) -> dict[str, Any] | None:
    """Fetch ONE item in full, or None if it doesn't exist / isn't owned by this key."""
    if not mcp_key or not is_configured():
        return None
    try:
        rows = _call_rpc(
            "get_my_item_for_key", {"p_key_hash": _hash_key(mcp_key), "p_id": item_id}
        )
        return rows[0] if rows else None
    except Exception as exc:
        logger.error("get_my_item_failed error=%s", exc)
        return None


def save_item(
    mcp_key: str,
    idempotency_key: str,
    type_: str,
    title: str,
    content: str,
    category: str | None = None,
) -> dict[str, Any]:
    """Create a new item. Lets exceptions propagate -- a silent empty return
    on a write failure would hide from the client model that the write
    actually failed (same reasoning as pro_templates.save_prompt)."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")
    return _call_rpc(
        "save_my_item_for_key",
        {
            "p_key_hash": _hash_key(mcp_key),
            "p_idempotency_key": idempotency_key,
            "p_type": type_,
            "p_title": title,
            "p_content": content,
            "p_category": category,
        },
    )


def update_item(
    mcp_key: str,
    item_id: str,
    expected_updated_at: str,
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Update an existing item (Pro-only; optimistic locking via expected_updated_at)."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")
    return _call_rpc(
        "update_my_item_for_key",
        {
            "p_key_hash": _hash_key(mcp_key),
            "p_id": item_id,
            "p_expected_updated_at": expected_updated_at,
            "p_title": title,
            "p_content": content,
            "p_category": category,
        },
    )


def archive_item(mcp_key: str, item_id: str, confirm: bool, restore: bool = False) -> dict[str, Any]:
    """Archive or restore an item (Pro-only; confirm must be true)."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")
    return _call_rpc(
        "archive_my_item_for_key",
        {
            "p_key_hash": _hash_key(mcp_key),
            "p_id": item_id,
            "p_confirm": confirm,
            "p_restore": restore,
        },
    )


def log_write_attempt(mcp_key: str, tool: str, outcome: str) -> None:
    """Log a rejected write attempt as its OWN, independent PostgREST
    transaction (same pattern/reason as pro_templates.log_write_attempt --
    a raised exception rolls back the whole calling transaction, so logging
    from inside it would never persist for the rejected-attempt case).

    Calls the SAME log_write_attempt RPC that save_workspace_prompt already
    uses (pro_templates.log_write_attempt), just with an explicit p_tool so
    Valvet's write attempts don't get counted as save_workspace_prompt
    attempts. p_risk_check_passed is omitted (defaults to null server-side)
    -- Valvet items have no risk-check concept."""
    if not mcp_key or not is_configured():
        return
    try:
        url = f"{_SUPABASE_URL}/rest/v1/rpc/log_write_attempt"
        payload = {"p_key_hash": _hash_key(mcp_key), "p_outcome": outcome, "p_tool": tool}
        response = httpx.post(url, headers=_headers(), json=payload, timeout=5)
        response.raise_for_status()
    except Exception as exc:
        logger.error("vault_log_write_attempt_failed tool=%s outcome=%s error=%s", tool, outcome, exc)


def list_active_packages(mcp_key: str) -> list[str]:
    """List the areas (package identifiers) the caller's workspace has activated."""
    if not mcp_key or not is_configured():
        return []
    try:
        rows = _call_rpc("list_active_packages_for_key", {"p_key_hash": _hash_key(mcp_key)})
        return [row["area"] for row in rows]
    except Exception as exc:
        logger.error("list_active_packages_failed error=%s", exc)
        return []


def activate_package(mcp_key: str, area: str) -> None:
    """Activate a prompt package (idempotent). Lets exceptions propagate --
    same reasoning as save_item: a silent failure would hide from the
    client model that the activation didn't happen."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")
    _call_rpc("activate_package_for_key", {"p_key_hash": _hash_key(mcp_key), "p_area": area})


def deactivate_package(mcp_key: str, area: str) -> None:
    """Deactivate a prompt package (idempotent)."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")
    _call_rpc("deactivate_package_for_key", {"p_key_hash": _hash_key(mcp_key), "p_area": area})


def copy_template(mcp_key: str, template_id: str, confirm: bool) -> dict[str, Any]:
    """Copy one prompt package template into the caller's Valvet. Requires
    confirm=true -- it creates real content and counts against the shared
    monthly copy quota."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")
    return _call_rpc(
        "copy_template_to_valvet_for_key",
        {"p_key_hash": _hash_key(mcp_key), "p_template_id": template_id, "p_confirm": confirm},
    )
