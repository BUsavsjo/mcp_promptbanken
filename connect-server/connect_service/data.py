"""RLS-bundna Creator-läsningar för Promptbanken Connect."""

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

import httpx


class ConnectWriteError(Exception):
    """Ett säkert, användbart fel från Connects skriv-RPC:er.

    kind skiljer orsakerna åt så att klienten kan förklara rätt sak för användaren:
    quota (planens gräns), permission (inloggning/behörighet), validation (fel i
    uppgifterna) eller technical (tillfälligt fel hos Promptbanken).
    """

    def __init__(self, message: str, kind: str = "technical") -> None:
        super().__init__(message)
        self.kind = kind


WRITE_ERROR_TEXT = {
    "quota": "Du har nått gränsen för privata prompts i Free-läget. Arkivera en prompt eller uppgradera kontot.",
    "permission": "Promptbanken kunde inte bekräfta din inloggning eller behörighet. Logga in på nytt i anslutningen och försök igen.",
    "technical": "Promptbanken svarade inte som väntat. Inget har ändrats. Försök igen om en stund.",
    "validation": "Ändringen kunde inte genomföras. Kontrollera uppgifterna och försök igen.",
}


_SEARCH_SYNONYMS = {
    "hr": ("personal", "medarbetare", "rekrytering", "arbetsmiljö", "förändringsledning"),
}


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
                entries.extend(
                    self._library_entry(row, "prompt")
                    for row in self._rpc(access_token, function_name)
                    if row.get("status") != "archived"
                )
        if kind in {"all", "package"}:
            entries.extend(
                self._library_entry(row, "package")
                for row in self._rpc(access_token, "list_my_creator_package_drafts")
                if row.get("status") != "archived"
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
        packages = [
            self._package_summary(row)
            for row in self._rpc(access_token, "list_my_creator_package_drafts")
            if row.get("status") != "archived"
        ]
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

    def create_my_prompt(
        self,
        *,
        access_token: str,
        title: str,
        content: str,
        summary: str | None,
        category: str | None,
        request_id: str,
    ) -> Mapping[str, object]:
        return self._rpc_object(
            access_token,
            "connect_create_my_prompt",
            {
                "p_title": title,
                "p_content": content,
                "p_summary": summary,
                "p_category": category,
                "p_confirmed": True,
                "p_request_id": request_id,
            },
        )

    def search_open_catalog(
        self,
        *,
        access_token: str,
        query: str,
        kind: str,
        category: str | None,
        limit: int,
        cursor: int,
    ) -> Mapping[str, object]:
        items: list[dict[str, object]] = []
        normalized_query = query.strip().casefold()
        normalized_category = category.strip().casefold() if isinstance(category, str) and category.strip() else None
        scores: dict[str, int] = {}
        if kind in {"all", "prompt"}:
            for row in self._rpc(access_token, "list_published_prompts", {"p_context_keys": ["generell"]}):
                item = {"id": str(row["id"]), "kind": "prompt", "title": row.get("title"), "summary": row.get("summary"), "category": row.get("area")}
                score = self._catalog_score(item, normalized_query, normalized_category)
                if score:
                    scores[item["id"]] = score
                    items.append(item)
        if kind in {"all", "package"}:
            for row in self._rpc(access_token, "list_published_packages", {"p_context_keys": ["generell"]}):
                item = {"id": str(row["id"]), "kind": "package", "title": row.get("title"), "summary": row.get("summary"), "category": row.get("area"), "package_type": row.get("package_type")}
                score = self._catalog_score(item, normalized_query, normalized_category)
                if score:
                    scores[item["id"]] = score
                    items.append(item)
        # Flest matchande ord först, sedan alfabetiskt, så att flerordsfrågor ger träffar.
        items.sort(key=lambda item: (-scores[item["id"]], str(item.get("title") or "").casefold(), str(item["id"])))
        page = items[cursor : cursor + limit]
        next_cursor = str(cursor + limit) if cursor + limit < len(items) else None
        return {"items": page, "next_cursor": next_cursor}

    def list_connect_documents(self, *, access_token: str, categories: set[str]) -> list[Mapping[str, object]]:
        """Egna Creator-prompter i Connects personliga kategorier, med innehåll."""
        return [
            {"id": str(row["id"]), "category": row.get("category"), "content": row.get("content"), "updated_at": row.get("updated_at")}
            for row in self._rpc(access_token, "list_my_creator_prompts")
            if row.get("category") in categories and row.get("status") != "archived"
        ]

    def get_open_item(self, *, access_token: str, kind: str, ref: str) -> Mapping[str, object] | None:
        """Läser publicerat Open-innehåll med text, motsvarande Opens get_template och list_package_prompts."""
        if kind == "prompt":
            for row in self._rpc(access_token, "list_published_prompts", {"p_context_keys": ["generell"]}):
                if ref in {str(row.get("id")), str(row.get("slug"))}:
                    return {
                        "kind": "prompt",
                        "id": str(row["id"]),
                        "slug": row.get("slug"),
                        "title": row.get("title"),
                        "summary": row.get("summary"),
                        "prompt_text": row.get("prompt_text"),
                        "example_input": row.get("example_input"),
                        "risk_level": row.get("risk_level"),
                        "output_format": row.get("output_format"),
                    }
            return None
        if kind == "package":
            slug = ref
            if self._is_uuid(ref):
                match = next(
                    (row for row in self._rpc(access_token, "list_published_packages", {"p_context_keys": ["generell"]}) if str(row.get("id")) == ref),
                    None,
                )
                if match is None:
                    return None
                slug = str(match.get("slug"))
            rows = self._rpc(access_token, "list_published_package_prompts", {"p_package_slug": slug, "p_context_keys": ["generell"]})
            if not rows:
                return None
            return {
                "kind": "package",
                "slug": slug,
                "steps": [
                    {
                        "position": row.get("sort_order"),
                        "prompt_id": str(row.get("prompt_id")),
                        "title": row.get("step_title") or row.get("title"),
                        "intro": row.get("step_intro"),
                        "required": row.get("is_required"),
                        "prompt_text": row.get("prompt_text"),
                    }
                    for row in sorted(rows, key=lambda row: int(row.get("sort_order") or 0))
                ],
            }
        raise ValueError("Okänd typ.")

    def update_my_prompt(self, *, access_token: str, prompt_id: str, title: str, content: str, summary: str | None, category: str | None, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_update_my_prompt", {"p_content_item_id": prompt_id, "p_title": title, "p_content": content, "p_summary": summary, "p_category": category, "p_request_id": request_id})

    def archive_my_prompt(self, *, access_token: str, prompt_id: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_archive_my_prompt", {"p_content_item_id": prompt_id, "p_request_id": request_id})

    def save_my_package(self, *, access_token: str, package_id: str | None, title: str, summary: str | None, package_type: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_save_my_package", {"p_draft_id": package_id, "p_title": title, "p_summary": summary, "p_package_type": package_type, "p_request_id": request_id})

    def set_package_prompts(self, *, access_token: str, package_id: str, prompt_ids: list[str], request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_set_package_prompts", {"p_draft_id": package_id, "p_prompt_ids": prompt_ids, "p_request_id": request_id})

    def archive_my_package(self, *, access_token: str, package_id: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_archive_my_package", {"p_draft_id": package_id, "p_request_id": request_id})

    def add_open_prompt_to_library(self, *, access_token: str, prompt_id: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_add_catalog_prompt_to_library", {"p_prompt_id": prompt_id, "p_request_id": request_id})

    def add_open_package_to_library(self, *, access_token: str, package_id: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_add_catalog_package_to_library", {"p_package_id": package_id, "p_request_id": request_id})

    def create_my_share(self, *, access_token: str, subject_type: str, subject_id: str, pin_version: bool, expires_at: str | None, label: str | None, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_create_my_share", {"p_subject_type": subject_type, "p_subject_id": subject_id, "p_pin_version": pin_version, "p_expires_at": expires_at, "p_label": label, "p_request_id": request_id})

    def revoke_my_share(self, *, access_token: str, share_id: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_revoke_my_share", {"p_share_id": share_id, "p_request_id": request_id})

    def extend_my_share(self, *, access_token: str, share_id: str, expires_at: str, request_id: str) -> Mapping[str, object]:
        return self._connect_write(access_token, "connect_extend_my_share", {"p_share_id": share_id, "p_expires_at": expires_at, "p_request_id": request_id})

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

    def _rpc_object(
        self,
        access_token: str,
        function_name: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        try:
            response = self._http_client.post(
                f"/rest/v1/rpc/{function_name}",
                headers={
                    "apikey": self._publishable_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=dict(payload),
            )
        except httpx.TransportError as error:
            raise ConnectWriteError(WRITE_ERROR_TEXT["technical"], kind="technical") from error
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            message, kind = self._write_error(error)
            raise ConnectWriteError(message, kind=kind) from error
        result = response.json()
        if not isinstance(result, Mapping):
            raise ConnectWriteError(WRITE_ERROR_TEXT["technical"], kind="technical")
        return result

    def _connect_write(self, access_token: str, function_name: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._rpc_object(access_token, function_name, {**payload, "p_confirmed": True})

    @staticmethod
    def _write_error_message(error: httpx.HTTPStatusError) -> str:
        return SupabaseConnectRepository._write_error(error)[0]

    @staticmethod
    def _write_error(error: httpx.HTTPStatusError) -> tuple[str, str]:
        """Översätter fel till (meddelande, kind) utan att läcka databasdetaljer."""
        try:
            payload = error.response.json()
        except (ValueError, AttributeError):
            payload = {}
        message = payload.get("message") if isinstance(payload, Mapping) else None
        code = payload.get("code") if isinstance(payload, Mapping) else None
        status = getattr(error.response, "status_code", 0)
        if isinstance(message, str) and "nått gränsen" in message:
            return WRITE_ERROR_TEXT["quota"], "quota"
        if status in {401, 403} or code in {"42501", "PGRST301", "PGRST302"}:
            return WRITE_ERROR_TEXT["permission"], "permission"
        if isinstance(message, str) and message.startswith("Open-referenser är skrivskyddade."):
            return message, "validation"
        # Egna RAISE EXCEPTION i Promptbankens funktioner (P0001) är skrivna för
        # användare och avslöjar inga tabellnamn; allt annat hålls generellt.
        if code == "P0001" and isinstance(message, str) and 0 < len(message) <= 300:
            return message, "validation"
        if status >= 500 or status == 0:
            return WRITE_ERROR_TEXT["technical"], "technical"
        return WRITE_ERROR_TEXT["validation"], "validation"

    @staticmethod
    def _matches_catalog_item(item: Mapping[str, object], query: str, category: str | None) -> bool:
        return SupabaseConnectRepository._catalog_score(item, query, category) > 0

    @staticmethod
    def _catalog_score(item: Mapping[str, object], query: str, category: str | None) -> int:
        """Antal ord i frågan som träffar titel, sammanfattning eller kategori (0 = ingen träff)."""
        if category is not None and str(item.get("category") or "").casefold() != category:
            return 0
        if not query:
            return 1
        haystack = " ".join(str(item.get(key) or "") for key in ("title", "summary", "category")).casefold()
        if query in haystack:
            return len(query.split()) + 1
        score = 0
        for word in query.split():
            terms = _SEARCH_SYNONYMS.get(word, (word,))
            if any(term in haystack for term in terms):
                score += 1
        return score

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
