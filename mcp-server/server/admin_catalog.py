"""Admin catalog authoring: calls the platform_owner-gated catalog RPCs
(create_catalog_prompt, upsert_catalog_prompt_variant, publish_catalog_prompt,
package equivalents, plus the new draft-read RPCs) using a real Supabase
access token from admin_auth. See
docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Any

import httpx

from . import admin_auth

logger = logging.getLogger("promptbanken_mcp.admin_catalog")

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

_RATE_LIMIT_MAX_CALLS = 30
_RATE_LIMIT_WINDOW_SECONDS = 60
_recent_calls: deque[float] = deque()


class AdminRateLimitExceeded(Exception):
    pass


def _check_rate_limit() -> None:
    now = time.monotonic()
    while _recent_calls and now - _recent_calls[0] > _RATE_LIMIT_WINDOW_SECONDS:
        _recent_calls.popleft()
    if len(_recent_calls) >= _RATE_LIMIT_MAX_CALLS:
        raise AdminRateLimitExceeded(
            f"Fler än {_RATE_LIMIT_MAX_CALLS} admin-skrivningar på {_RATE_LIMIT_WINDOW_SECONDS}s -- vänta och försök igen."
        )
    _recent_calls.append(now)


def _call_rpc(function_name: str, payload: dict[str, Any]) -> Any:
    access_token = admin_auth.get_access_token()
    response = httpx.post(
        f"{_SUPABASE_URL}/rest/v1/rpc/{function_name}",
        headers={
            "apikey": _ANON_KEY,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    if response.status_code == 204:
        return None
    return response.json()


def _log_attempt(tool: str, target_id: str | None, outcome: str, detail: dict[str, Any] | None = None) -> None:
    try:
        _call_rpc(
            "log_admin_write_attempt",
            {"p_tool": tool, "p_target_id": target_id, "p_outcome": outcome, "p_detail": detail},
        )
    except Exception as exc:
        logger.error("admin_write_attempt_log_failed tool=%s error=%s", tool, exc)


def _write(tool: str, function_name: str, payload: dict[str, Any], target_id: str | None = None) -> Any:
    """Shared write path: rate-limit, call the RPC, log the outcome either
    way, then let a failure propagate -- a silent failure would hide from
    the calling AI client that the write didn't happen (same reasoning as
    pro_templates.save_prompt)."""
    _check_rate_limit()
    try:
        result = _call_rpc(function_name, payload)
    except Exception as exc:
        _log_attempt(tool, target_id, "rejected", {"error": str(exc)})
        raise
    _log_attempt(tool, target_id, "success")
    return result


def create_prompt(slug: str, title: str, summary: str, prompt_text: str) -> dict[str, Any]:
    return _write(
        "admin_create_prompt",
        "create_catalog_prompt",
        {"p_slug": slug, "p_title": title, "p_summary": summary, "p_prompt_text": prompt_text},
    )


def upsert_prompt_variant(
    prompt_id: str,
    context_key: str,
    title: str,
    summary: str,
    prompt_text: str,
    risk_level: str | None = None,
    area: str | None = None,
    tags: list[str] | None = None,
    output_format: str | None = None,
    parameter_schema: dict[str, Any] | None = None,
    default_bindings: dict[str, Any] | None = None,
    binding_overrides: list[Any] | None = None,
) -> dict[str, Any]:
    return _write(
        "admin_upsert_prompt_variant",
        "upsert_catalog_prompt_variant",
        {
            "p_prompt_id": prompt_id,
            "p_context_key": context_key,
            "p_title": title,
            "p_summary": summary,
            "p_prompt_text": prompt_text,
            "p_risk_level": risk_level,
            "p_area": area,
            "p_tags": tags,
            "p_output_format": output_format,
            "p_parameter_schema": parameter_schema,
            "p_default_bindings": default_bindings if default_bindings is not None else {},
            "p_binding_overrides": binding_overrides if binding_overrides is not None else [],
        },
        target_id=prompt_id,
    )


def publish_prompt(prompt_id: str, confirm: bool) -> dict[str, Any]:
    if confirm is not True:
        raise ValueError("confirm måste vara true för att publicera en prompt.")
    return _write(
        "admin_publish_prompt", "publish_catalog_prompt", {"p_prompt_id": prompt_id}, target_id=prompt_id
    )


def list_draft_prompts() -> list[dict[str, Any]]:
    return _call_rpc("list_draft_catalog_prompts", {}) or []


def get_prompt(prompt_id: str) -> list[dict[str, Any]]:
    return _call_rpc("get_catalog_prompt_by_id", {"p_prompt_id": prompt_id}) or []


def create_package(
    slug: str, package_type: str, title: str, summary: str, intro_text: str | None = None
) -> dict[str, Any]:
    return _write(
        "admin_create_package",
        "create_catalog_package",
        {
            "p_slug": slug,
            "p_package_type": package_type,
            "p_title": title,
            "p_summary": summary,
            "p_intro_text": intro_text,
        },
    )


def add_prompt_to_package(package_id: str, prompt_id: str, sort_order: int) -> dict[str, Any]:
    return _write(
        "admin_add_prompt_to_package",
        "add_prompt_to_catalog_package",
        {"p_package_id": package_id, "p_prompt_id": prompt_id, "p_sort_order": sort_order},
        target_id=package_id,
    )


def publish_package(package_id: str, confirm: bool) -> dict[str, Any]:
    if confirm is not True:
        raise ValueError("confirm måste vara true för att publicera ett paket.")
    return _write(
        "admin_publish_package", "publish_catalog_package", {"p_package_id": package_id}, target_id=package_id
    )
