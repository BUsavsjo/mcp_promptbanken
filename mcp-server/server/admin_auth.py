"""Auth bridge for the /admin route: exchanges a long-lived Supabase refresh
token (SUPABASE_ADMIN_REFRESH_TOKEN) for short-lived access tokens, so the
existing platform_owner-gated catalog RPCs (auth.uid()-based RLS, see
supabase/migrations/20260721150000_catalog_write_rpc_authorization.sql in the
promptbanken repo) work completely unmodified. See
docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("promptbanken_mcp.admin_auth")

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
_REFRESH_TOKEN = os.getenv("SUPABASE_ADMIN_REFRESH_TOKEN", "")

_EXPIRY_BUFFER_SECONDS = 60

_STATE_PATH = Path(
    os.getenv(
        "ADMIN_REFRESH_TOKEN_STATE_PATH",
        str(Path(__file__).resolve().parents[1] / ".admin_refresh_token_state.json"),
    )
)

_cached_access_token: str | None = None
_cached_expires_at: float = 0.0
_cached_refresh_token: str | None = None


class AdminAuthNotConfigured(Exception):
    """Raised when SUPABASE_ADMIN_REFRESH_TOKEN/SUPABASE_URL/SUPABASE_ANON_KEY are missing."""


def is_configured() -> bool:
    return bool(_SUPABASE_URL and _ANON_KEY and _REFRESH_TOKEN)


def _load_refresh_token() -> str:
    """Prefer the last rotated refresh token persisted on disk over the
    original env var -- Supabase Auth rotates refresh tokens on every
    exchange, so the env var value stops working after the first refresh."""
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text())["refresh_token"]
        except (OSError, ValueError, KeyError) as exc:
            logger.error("admin_refresh_token_state_read_failed error=%s", exc)
    return _REFRESH_TOKEN


def _persist_refresh_token(refresh_token: str) -> None:
    try:
        _STATE_PATH.write_text(json.dumps({"refresh_token": refresh_token}))
    except OSError as exc:
        logger.error("admin_refresh_token_persist_failed error=%s", exc)


def _exchange_refresh_token(refresh_token: str) -> dict[str, Any]:
    response = httpx.post(
        f"{_SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        headers={"apikey": _ANON_KEY, "Content-Type": "application/json"},
        json={"refresh_token": refresh_token},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_access_token() -> str:
    """Returns a valid access token, refreshing it if the cached one is
    missing or within _EXPIRY_BUFFER_SECONDS of expiring. Raises
    AdminAuthNotConfigured if the admin credential isn't set up, and lets
    httpx errors from a failed refresh propagate -- the /admin route must
    see a real error, not a silent stale/empty token."""
    global _cached_access_token, _cached_expires_at, _cached_refresh_token

    if not is_configured():
        raise AdminAuthNotConfigured(
            "SUPABASE_ADMIN_REFRESH_TOKEN/SUPABASE_URL/SUPABASE_ANON_KEY måste vara satta."
        )

    if _cached_refresh_token is None:
        _cached_refresh_token = _load_refresh_token()

    now = time.monotonic()
    if _cached_access_token and now < _cached_expires_at - _EXPIRY_BUFFER_SECONDS:
        return _cached_access_token

    payload = _exchange_refresh_token(_cached_refresh_token)
    _cached_access_token = payload["access_token"]
    _cached_expires_at = now + int(payload["expires_in"])
    new_refresh_token = payload.get("refresh_token")
    if new_refresh_token:
        _cached_refresh_token = new_refresh_token
        _persist_refresh_token(new_refresh_token)
    return _cached_access_token
