"""RLS-bundna läsningar för Promptbanken Connect."""

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

import httpx


class HttpClient(Protocol):
    def get(
        self,
        path: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str],
    ) -> Any:
        """Utför ett GET-anrop mot Supabase REST API."""


class SupabaseConnectRepository:
    """Läser via anroparens OAuth-token; service-nycklar används aldrig här."""

    _LIST_FIELDS = "id,title,summary,updated_at,status,visibility,workspace_id,type,module"
    _ITEM_FIELDS = "id,title,summary,content,updated_at,status,visibility,workspace_id,type,module"

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        http_client: HttpClient | None = None,
    ) -> None:
        self._http_client = http_client or httpx.Client(base_url=supabase_url.rstrip("/"), timeout=10.0)
        self._publishable_key = publishable_key

    def list_library(self, *, access_token: str, user_id: str) -> list[Mapping[str, object]]:
        return self._list(
            access_token,
            {
                "select": self._LIST_FIELDS,
                "module": "eq.valvet",
                "owner_user_id": f"eq.{user_id}",
                "visibility": "eq.private",
                "status": "neq.archived",
                "order": "updated_at.desc",
            },
        )

    def list_shared_items(self, *, access_token: str) -> list[Mapping[str, object]]:
        return self._list(
            access_token,
            {
                "select": self._LIST_FIELDS,
                "visibility": "eq.workspace",
                "module": "neq.valvet",
                "status": "neq.archived",
                "order": "updated_at.desc",
            },
        )

    def get_item(self, *, access_token: str, item_id: str) -> Mapping[str, object] | None:
        try:
            UUID(item_id)
        except ValueError:
            return None

        rows = self._list(
            access_token,
            {"select": self._ITEM_FIELDS, "id": f"eq.{item_id}", "limit": "1"},
        )
        return rows[0] if rows else None

    def _list(self, access_token: str, params: Mapping[str, str]) -> list[Mapping[str, object]]:
        response = self._http_client.get(
            "/rest/v1/content_items",
            headers={
                "apikey": self._publishable_key,
                "Authorization": f"Bearer {access_token}",
            },
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Supabase returnerade ett oväntat svar.")
        return [row for row in payload if isinstance(row, Mapping)]
