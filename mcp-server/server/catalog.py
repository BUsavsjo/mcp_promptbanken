from __future__ import annotations

import json
import os
from typing import Any

import httpx


class CatalogNotConfigured(Exception):
    """Raised when SUPABASE_URL/SUPABASE_ANON_KEY are missing."""


def _supabase_config() -> tuple[str, str]:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")

    if not supabase_url or not supabase_anon_key:
        raise CatalogNotConfigured(
            "SUPABASE_URL och SUPABASE_ANON_KEY måste vara satta som miljövariabler "
            "för att läsa den publicerade katalogen."
        )

    return supabase_url, supabase_anon_key


def _call_rpc(function_name: str, payload: dict[str, Any]) -> Any:
    supabase_url, supabase_anon_key = _supabase_config()
    response = httpx.post(
        f"{supabase_url}/rest/v1/rpc/{function_name}",
        headers={
            "Content-Type": "application/json",
            "apikey": supabase_anon_key,
            "Authorization": f"Bearer {supabase_anon_key}",
        },
        json=payload,
        timeout=15,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise RuntimeError(f"Kunde inte anropa {function_name} ({exc.response.status_code}): {detail}") from exc
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ogiltigt JSON-svar från {function_name}.") from exc


def list_published_prompts(context_keys: list[str] | None = None) -> list[dict[str, Any]]:
    return _call_rpc(
        "list_published_prompts",
        {"p_context_keys": context_keys or ["generell"]},
    )


def get_published_prompt(
    slug: str, context_keys: list[str] | None = None
) -> list[dict[str, Any]]:
    return _call_rpc(
        "get_published_prompt",
        {"p_slug": slug, "p_context_keys": context_keys or ["generell"]},
    )


def list_published_packages(
    context_keys: list[str] | None = None, package_type: str | None = None
) -> list[dict[str, Any]]:
    return _call_rpc(
        "list_published_packages",
        {
            "p_context_keys": context_keys or ["generell"],
            "p_package_type": package_type,
        },
    )


def get_published_package(
    slug: str, context_keys: list[str] | None = None
) -> list[dict[str, Any]]:
    return _call_rpc(
        "get_published_package",
        {"p_slug": slug, "p_context_keys": context_keys or ["generell"]},
    )


def list_published_package_prompts(
    package_slug: str, context_keys: list[str] | None = None
) -> list[dict[str, Any]]:
    return _call_rpc(
        "list_published_package_prompts",
        {
            "p_package_slug": package_slug,
            "p_context_keys": context_keys or ["generell"],
        },
    )
