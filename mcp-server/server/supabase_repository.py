"""Hämtar användarspecifika prompts från Supabase och returnerar dem som Skill-objekt."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import unicodedata
from typing import Any

import httpx

from .skill_repository import Skill

logger = logging.getLogger("promptbanken_mcp.supabase")

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
_MCP_ROLE_JWT = os.getenv("SUPABASE_MCP_ROLE_JWT", "")


def _supabase_headers() -> dict[str, str]:
    # apikey måste vara en av Supabase-gatewayens (Kong) kända projektnycklar
    # (anon/service_role) för att passera — den känner inte till anpassade
    # roller. Authorization är det PostgREST läser role-claim från och byter
    # Postgres-roll (mcp_server) utifrån, så den begränsade rollen räcker där.
    return {
        "apikey": _ANON_KEY,
        "Authorization": f"Bearer {_MCP_ROLE_JWT}",
        "Content-Type": "application/json",
        "Content-Profile": "app_private",
    }


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _verify_mcp_key(raw_key: str) -> dict[str, str] | None:
    """Verifierar MCP-nyckeln via RPC och returnerar {workspace_id, plan, workspace_type} om giltig."""
    if not _SUPABASE_URL or not _ANON_KEY or not _MCP_ROLE_JWT:
        logger.warning("supabase_not_configured SUPABASE_URL/SUPABASE_ANON_KEY/SUPABASE_MCP_ROLE_JWT missing")
        return None

    key_hash = _hash_key(raw_key)
    url = f"{_SUPABASE_URL}/rest/v1/rpc/verify_mcp_key"
    try:
        response = httpx.post(
            url,
            headers=_supabase_headers(),
            json={"p_key_hash": key_hash},
            timeout=5,
        )
        response.raise_for_status()
        rows = response.json()
    except Exception as exc:
        logger.error("supabase_key_verify_failed error=%s", exc)
        return None

    if not rows:
        return None
    row = rows[0]
    workspace_id = row.get("workspace_id")
    if not workspace_id:
        return None
    return {
        "workspace_id": workspace_id,
        "plan": row.get("plan", ""),
        "workspace_type": row.get("workspace_type", ""),
    }


def _get_workspace_prompts(workspace_id: str) -> list[dict[str, Any]]:
    """Hämtar aktiva prompts för ett workspace via RPC."""
    url = f"{_SUPABASE_URL}/rest/v1/rpc/get_workspace_prompts"
    try:
        response = httpx.post(
            url,
            headers=_supabase_headers(),
            json={"p_workspace_id": workspace_id},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("supabase_get_workspace_prompts_failed error=%s", exc)
        return []


def _slugify(text: str) -> str:
    """Normaliserar svenska tecken (å/ä→a, ö→o) och gör texten till ett skill-id-säkert segment."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug or "prompt"


def _skill_id_for_item(item: dict[str, Any]) -> str:
    """Bygger ett läsbart, stabilt skill-id från titel + kort uuid-suffix (för unikhet)."""
    raw_id = str(item.get("id", ""))
    suffix = raw_id.replace("-", "")[:4] or "0000"
    slug = _slugify(item.get("title") or "prompt")[:30]
    return f"workspace_{slug}_{suffix}"[:50]


def _items_to_skills(items: list[dict[str, Any]]) -> list[Skill]:
    skills: list[Skill] = []
    for item in items:
        raw_id = str(item.get("id", ""))
        if not raw_id:
            continue
        skills.append(
            Skill(
                id=_skill_id_for_item(item),
                name=item.get("title", ""),
                display_name=item.get("title", ""),
                description=item.get("summary", ""),
                category=item.get("category") or "Arbetsyta",
                file="",
                intents=[],
                roles=[],
                audiences=[a.strip() for a in (item.get("audience") or "").split(",") if a.strip()],
                risk_level="medium",
                risk_message=Skill._default_risk_message("medium"),
                requires_anonymization=True,
                anonymization_level="required",
                example_phrases=[],
                output_type="text",
                language="sv-SE",
                version="1.0.0",
                source="workspace",
                source_id=raw_id,
            )
        )
    return skills


class SupabaseRepository:
    """Hämtar workspace-prompts via app_private RPC-funktioner och returnerar dem som Skills."""

    def __init__(self, mcp_api_key: str) -> None:
        self._mcp_api_key = mcp_api_key
        self._workspace_id: str | None = None
        self._resolved: bool | None = None

    def _resolve_workspace(self) -> bool:
        if self._resolved is not None:
            return self._resolved
        result = _verify_mcp_key(self._mcp_api_key)
        if result is None:
            self._resolved = False
            return False
        self._workspace_id = result["workspace_id"]
        self._resolved = True
        return True

    def key_is_valid(self) -> bool:
        """Om nyckeln matchar en aktiv, orevocerad mcp-nyckel med ett aktiverat workspace.

        RPC:n verify_mcp_key ger samma tomma resultat oavsett om nyckeln saknas,
        är återkallad eller om workspacet är inaktiverat, så det går inte att
        skilja ut exakt orsak härifrån (se TODO.md).
        """
        return self._resolve_workspace()

    def list_skills(self) -> list[Skill]:
        if not self._resolve_workspace():
            return []
        items = _get_workspace_prompts(self._workspace_id)
        logger.info("supabase_list_skills workspace_id=%s count=%s", self._workspace_id, len(items))
        return _items_to_skills(items)

    def get_prompt(self, skill_id: str) -> str | None:
        """Returnerar prompttexten (body) för en workspace-skill, eller None."""
        if not self._resolve_workspace():
            return None
        items = _get_workspace_prompts(self._workspace_id)
        for item in items:
            if _skill_id_for_item(item) == skill_id:
                return item.get("content", "")
        return None

    @property
    def is_configured(self) -> bool:
        return bool(self._mcp_api_key and _SUPABASE_URL and _ANON_KEY and _MCP_ROLE_JWT)
