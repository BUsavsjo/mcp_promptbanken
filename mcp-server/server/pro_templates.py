"""Hämtar Promptbanken Pro-mallar via nyckelbaserad RPC (get_pro_templates_for_mcp_key)."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("promptbanken_mcp.pro_templates")

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def is_configured() -> bool:
    return bool(_SUPABASE_URL and _ANON_KEY)


def list_pro_templates(mcp_key: str) -> list[dict[str, Any]]:
    """Hämtar premium-mallar (teaser eller fullständiga, beroende på nyckelns plan).

    RPC:n `get_pro_templates_for_mcp_key` är beviljad direkt till `anon` — att
    känna till nyckelns sha256-hash är i sig beviset på behörighet, precis som
    verify_mcp_key/get_workspace_prompts. Ingen mcp_server-roll/JWT behövs här,
    bara SUPABASE_URL/SUPABASE_ANON_KEY (samma som redan används för workspace-
    skills i supabase_repository.py).
    """
    if not mcp_key or not is_configured():
        return []

    url = f"{_SUPABASE_URL}/rest/v1/rpc/get_pro_templates_for_mcp_key"
    try:
        response = httpx.post(
            url,
            headers={
                "apikey": _ANON_KEY,
                "Authorization": f"Bearer {_ANON_KEY}",
                "Content-Type": "application/json",
            },
            json={"p_key_hash": _hash_key(mcp_key)},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("pro_templates_fetch_failed error=%s", exc)
        return []


def _call_context_rpc(function_name: str, mcp_key: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Anropar en av de nyckelhash-baserade kontext-RPC:erna (samma anon-beviljade
    förtroendemodell som get_pro_templates_for_mcp_key ovan, se
    promptbanken/supabase/migrations/20260706103000_context_mcp_scope.sql)."""
    if not mcp_key or not is_configured():
        return []

    payload: dict[str, Any] = {"p_key_hash": _hash_key(mcp_key)}
    if extra:
        payload.update(extra)

    url = f"{_SUPABASE_URL}/rest/v1/rpc/{function_name}"
    try:
        response = httpx.post(
            url,
            headers={
                "apikey": _ANON_KEY,
                "Authorization": f"Bearer {_ANON_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("%s_fetch_failed error=%s", function_name, exc)
        return []


def list_private_prompts(mcp_key: str) -> list[dict[str, Any]]:
    """Nyckelns egna privata Pro-prompts (personlig yta). Returnerar aldrig
    andra medlemmars privata prompts eller organisationsprompts. Kontextstyrt:
    default-scope = privat (se migration 20260706103000_context_mcp_scope.sql
    i promptbanken-repot)."""
    return _call_context_rpc(
        "get_workspace_prompts_for_key", mcp_key, {"p_scope": "private", "p_workspace_id": None}
    )


def list_shared_prompts(mcp_key: str, workspace_id: str) -> list[dict[str, Any]]:
    """Delade prompts från EN delad arbetsyta där nyckelns ägare är medlem.
    Kräver explicit workspace_id (från list_shared_workspaces) — nyckeln kan
    aldrig läsa en delad yta den inte tillhör."""
    return _call_context_rpc(
        "get_workspace_prompts_for_key", mcp_key, {"p_scope": None, "p_workspace_id": workspace_id}
    )


def list_shared_workspaces(mcp_key: str) -> list[dict[str, Any]]:
    """Discovery: vilka delade arbetsytor nyckelns ägare kan välja mellan."""
    return _call_context_rpc("list_shared_workspaces_for_key", mcp_key)
