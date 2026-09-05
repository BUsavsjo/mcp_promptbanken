"""RLS-bundna Creator-läsningar för Promptbanken Connect."""

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

import httpx


class HttpClient(Protocol):
    def post(
        self,
        path: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, object],
    ) -> Any:
        """Utför ett POST-anrop mot Supabase REST API."""


class SupabaseConnectRepository:
    """Läser Creator-data med anroparens OAuth-token; ingen service-nyckel används."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        http_client: HttpClient | None = None,
    ) -> None:
        self._http_client = http_client or httpx.Client(base_url=supabase_url.rstrip("/"), timeout=10.0)
        self._publishable_key = publishable_key

    def list_library(
        self, *, access_token: str, kind: str = "all", limit: int = 50
    ) -> list[Mapping[str, object]]:
        if kind not in {"all", "prompt", "package"} or not 1 <= limit <= 100:
            raise ValueError("Ogiltiga biblioteksargument.")

        entries: list[Mapping[str, object]] = []
        if kind in {"all", "prompt"}:
            for function_name in ("list_my_creator_prompts", "list_my_library_prompts"):
                entries.extend(self._library_entry(row, "prompt") for row in self._rpc(access_token, function_name))
        if kind in {"all", "package"}:
            entries.extend(
                self._library_entry(row, "package")
                for row in self._rpc(access_token, "list_my_creator_package_drafts")
            )

        return sorted(entries, key=lambda item: str(item.get("updated_at", "")), reverse=True)[:limit]

    def get_library_prompt(
        self, *, access_token: str, prompt_id: str
    ) -> Mapping[str, object] | None:
        if not self._is_uuid(prompt_id):
            return None

        rows = self._rpc(
            access_token,
            "get_my_connect_library_prompt",
            {"p_content_item_id": prompt_id},
        )
        if not rows:
            return None

        prompt = self._prompt_payload(rows[0])
        if not prompt["is_library_reference"]:
            return prompt

        live_rows = self._rpc(
            access_token,
            "get_referenced_library_prompt",
            {"p_content_item_id": prompt_id, "p_context_keys": ["generell"]},
        )
        if not live_rows:
            return None
        live = live_rows[0]
        prompt.update(
            {
                "title": live.get("title"),
                "summary": live.get("summary"),
                "content": live.get("prompt_text"),
                "area": live.get("area"),
                "risk_level": live.get("risk_level"),
                "security_examples": live.get("security_examples"),
            }
        )
        return prompt

    def list_packages(self, *, access_token: str, limit: int = 50) -> list[Mapping[str, object]]:
        if not 1 <= limit <= 100:
            raise ValueError("Ogiltigt gränsvärde.")
        packages = [self._package_summary(row) for row in self._rpc(access_token, "list_my_creator_package_drafts")]
        return packages[:limit]

    def get_package(self, *, access_token: str, package_id: str) -> Mapping[str, object] | None:
        if not self._is_uuid(package_id):
            return None
        package_rows = self._rpc(access_token, "list_my_creator_package_drafts")
        package = next((row for row in package_rows if str(row.get("id")) == package_id), None)
        if package is None:
            return None

        result = self._package_summary(package)
        if bool(package.get("is_library_reference", False)):
            live_rows = self._rpc(
                access_token,
                "get_referenced_library_package",
                {"p_draft_id": package_id, "p_context_keys": ["generell"]},
            )
            if not live_rows:
                return None
            first = live_rows[0]
            result.update(
                {
                    "title": first.get("title"),
                    "summary": first.get("summary"),
                    "package_type": first.get("package_type"),
                    "intro_text": first.get("intro_text"),
                    "items": [
                        {
                            "position": row.get("item_sort_order"),
                            "title": row.get("item_title"),
                            "summary": row.get("item_summary"),
                            "content": row.get("item_prompt_text"),
                        }
                        for row in sorted(live_rows, key=lambda row: int(row.get("item_sort_order", 0)))
                    ],
                }
            )
            return result

        item_rows = self._rpc(access_token, "list_creator_package_draft_items", {"p_draft_id": package_id})
        items: list[Mapping[str, object]] = []
        for item in sorted(item_rows, key=lambda row: int(row.get("position", 0))):
            prompt = self.get_library_prompt(access_token=access_token, prompt_id=str(item.get("content_item_id", "")))
            if prompt is None:
                return None
            items.append({"position": item.get("position"), **prompt})
        result["items"] = items
        return result

    def list_shares(
        self, *, access_token: str, include_inactive: bool = False
    ) -> list[Mapping[str, object]]:
        shares = self._rpc(access_token, "list_my_creator_shares")
        if include_inactive:
            return shares
        return [share for share in shares if bool(share.get("is_active", False))]

    def _rpc(
        self,
        access_token: str,
        function_name: str,
        payload: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        response = self._http_client.post(
            f"/rest/v1/rpc/{function_name}",
            headers={
                "apikey": self._publishable_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=dict(payload or {}),
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, list):
            raise ValueError("Supabase returnerade ett oväntat svar.")
        return [row for row in result if isinstance(row, Mapping)]

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            UUID(value)
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _library_entry(row: Mapping[str, object], kind: str) -> Mapping[str, object]:
        return {
            "id": str(row["id"]),
            "kind": kind,
            "title": row.get("title"),
            "summary": row.get("summary"),
            "status": row.get("status"),
            "updated_at": row.get("updated_at"),
            "is_library_reference": bool(row.get("is_library_reference", False)),
        }

    @staticmethod
    def _prompt_payload(row: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "id": str(row["id"]),
            "title": row.get("title"),
            "summary": row.get("summary"),
            "content": row.get("content"),
            "status": row.get("status"),
            "module": row.get("module"),
            "is_library_reference": bool(row.get("is_library_reference", False)),
            "source_prompt_id": row.get("source_prompt_id"),
        }
        if row.get("category") is not None:
            payload["category"] = row.get("category")
        return payload

    @staticmethod
    def _package_summary(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "id": str(row["id"]),
            "title": row.get("title"),
            "summary": row.get("summary"),
            "status": row.get("status"),
            "package_type": row.get("package_type"),
            "is_library_reference": bool(row.get("is_library_reference", False)),
        }