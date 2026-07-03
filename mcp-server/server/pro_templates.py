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
