# Valvet — MCP-verktyg (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lägg till sex nya MCP-verktyg (`list_my_items`, `search_my_items`, `get_my_item`, `save_my_item`, `update_my_item`, `archive_my_item`) i den hostade servern, bredvid befintliga verktyg — inget befintligt verktyg byts ut eller ändrar beteende.

**Architecture:** Ny fil `mcp-server/server/vault.py` (samma stil som `pro_templates.py`: `httpx`-anrop mot nyckelhash-baserade `public.*_for_key`-RPC:er i `promptbanken`-repot, ingen `mcp_server`-roll behövs). `mcp_server.py` får sex nya `@mcp.tool()`-funktioner, sex nya rader i `_tool_definitions()`, sex nya grenar i `_handle_mcp_message`-dispatchen, och sex nya REST-routes. `hosted_guard.py`s allowlist utökas i takt med detta (obligatoriskt — servern är metadata/skriv-gated by design, se `PROJECT.md`).

**Tech Stack:** Python 3, FastMCP, Starlette, httpx. Inga automatiserade tester i repot — verifiering sker manuellt via `npm run serve` (hosted-läge) + `curl` mot `/mcp` och REST-endpoints.

**Beroende:** Kräver att **Plan A** (`promptbanken`-repot, `docs/superpowers/specs/2026-07-16-valvet-design.md` → `docs/superpowers/plans/2026-07-16-valvet-schema-and-rpcs.md`) är applicerad och verifierad mot **staging** innan Task 4 (end-to-end-verifiering) kan köras — utan de sex `public.*_for_key`-RPC:erna svarar `vault.py` bara med tomma listor/fel.

## Global Constraints

- Servern är metadata/skriv-gated by design (se `PROJECT.md`/`CLAUDE.md`): varje nytt verktyg **måste** läggas till i `hosted_guard.py`s `allowed_methods`/`allowed_tool_args` — annars blockeras det tyst av `HostedMetadataGuardMiddleware` i produktion trots att det finns i `_tool_definitions()`.
- Dokumentation på svenska (kod-kommentarer bara där WHY är icke-uppenbart), engelska docstrings/beskrivningar i `@mcp.tool()`-funktionerna (matchar befintlig stil — jämför `list_my_prompts`/`list_pro_templates` ovan, som har engelska docstrings trots svenska kommentarer i övrigt).
- Inga nya Python-beroenden (allt görs med `httpx`, redan ett beroende).
- Skriv-verktygen (`save_my_item`/`update_my_item`/`archive_my_item`) ska **aldrig** tyst svälja ett write-fel som ett tomt/success-liknande svar — samma princip som `save_workspace_prompt` redan följer (`vault.py`s write-funktioner låter `httpx.HTTPStatusError` propagera, läs-funktionerna fångar allt och returnerar tomt).
- `X-MCP-Key`/`Authorization`-header-hantering återanvänds oförändrad (`_mcp_key_from_request`) — inga nya auth-mekanismer.

---

## Filstruktur

- `mcp-server/server/vault.py` — ny fil, sex RPC-anropande funktioner + en logg-funktion.
- `mcp-server/server/mcp_server.py` — modifieras: import, sex payload-funktioner, sex `@mcp.tool()`, sex `_tool_definitions()`-poster, sex dispatch-grenar, sex REST-routes.
- `mcp-server/server/hosted_guard.py` — modifieras: sex nya poster i `allowed_methods` och `allowed_tool_args`.

---

### Task 1: `vault.py`

**Files:**
- Create: `mcp-server/server/vault.py`

**Interfaces:**
- Produces: `list_items(mcp_key, type_=None, category=None, status=None) -> list[dict]`, `search_items(mcp_key, query, type_=None, category=None) -> list[dict]`, `get_item(mcp_key, item_id) -> dict | None`, `save_item(mcp_key, idempotency_key, type_, title, content, category=None) -> dict` (raises on failure), `update_item(mcp_key, item_id, expected_updated_at, title=None, content=None, category=None) -> dict` (raises on failure), `archive_item(mcp_key, item_id, confirm, restore=False) -> dict` (raises on failure), `log_write_attempt(mcp_key, tool, outcome) -> None`.

- [ ] **Step 1: Skriv filen**

```python
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
    from inside it would never persist for the rejected-attempt case)."""
    if not mcp_key or not is_configured():
        return
    try:
        _call_rpc(
            "log_vault_write_attempt",
            {"p_key_hash": _hash_key(mcp_key), "p_tool": tool, "p_outcome": outcome},
        )
    except Exception as exc:
        logger.error("log_vault_write_attempt_failed tool=%s outcome=%s error=%s", tool, outcome, exc)
```

- [ ] **Step 2: Syntax-sanity**

```powershell
python -c "import ast; ast.parse(open('mcp-server/server/vault.py', encoding='utf-8').read())"
```
Förväntat: inget fel/output.

- [ ] **Step 3: Commit**

```bash
git add mcp-server/server/vault.py
git commit -m "feat: add vault.py with the six Valvet RPC-calling functions"
```

---

### Task 2: Läs-verktyg i `mcp_server.py`

**Files:**
- Modify: `mcp-server/server/mcp_server.py`

**Interfaces:**
- Consumes: `vault.list_items`, `vault.search_items`, `vault.get_item` (Task 1).
- Produces: `@mcp.tool()`-funktionerna `list_my_items`, `search_my_items`, `get_my_item`; JSON-RPC-dispatch-stöd för samma; REST `GET /api/v1/vault/items`, `GET /api/v1/vault/items/search`, `GET /api/v1/vault/items/{item_id}`.

- [ ] **Step 1: Lägg till importen**

I importblocket (efter rad 27, `from .pro_templates import log_write_attempt as _log_write_attempt`):

```python
from .vault import list_items as _vault_list_items
from .vault import search_items as _vault_search_items
from .vault import get_item as _vault_get_item
from .vault import save_item as _vault_save_item
from .vault import update_item as _vault_update_item
from .vault import archive_item as _vault_archive_item
from .vault import log_write_attempt as _vault_log_write_attempt
```

(Alla sju importeras nu — Task 3 använder de tre write-relaterade.)

- [ ] **Step 2: Lägg till payload-funktionerna**

Direkt efter `_shared_workspace_prompts_payload`-funktionen (strax före raden `@mcp.tool()\ndef list_my_private_prompts...` — se rad ~356 i nuvarande fil):

```python
_VAULT_NO_KEY_MESSAGE = (
    "Ingen MCP-nyckel skickades. Autentisera med din personliga X-MCP-Key för att se dina Valvet-insättningar."
)


def _list_my_items_payload(
    mcp_key: str = "", type_: str | None = None, category: str | None = None, status: str | None = None
) -> dict[str, Any]:
    if not mcp_key:
        return {"workspace_status": "no_key", "workspace_message": _VAULT_NO_KEY_MESSAGE, "items": []}
    return {"items": _vault_list_items(mcp_key, type_, category, status)}


def _search_my_items_payload(
    mcp_key: str = "", query: str = "", type_: str | None = None, category: str | None = None
) -> dict[str, Any]:
    if not mcp_key:
        return {"workspace_status": "no_key", "workspace_message": _VAULT_NO_KEY_MESSAGE, "items": []}
    return {"items": _vault_search_items(mcp_key, query, type_, category)}


def _get_my_item_payload(mcp_key: str = "", item_id: str = "") -> dict[str, Any]:
    if not mcp_key:
        return {"workspace_status": "no_key", "workspace_message": _VAULT_NO_KEY_MESSAGE, "item": None}
    item = _vault_get_item(mcp_key, item_id)
    if item is None:
        return {"status": "error", "message": "Insättningen hittades inte.", "item": None}
    return {"item": item}
```

- [ ] **Step 3: Lägg till `@mcp.tool()`-wrapperna**

Direkt efter `list_shared_workspace_prompts` (rad ~378, före `def _error(...)`):

```python
@mcp.tool()
def list_my_items(type: str | None = None, category: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List the caller's own Valvet items (personal prompt/assistant vault).
    Excludes archived items unless status='archived' is passed explicitly."""
    logger.info("tool_call name=list_my_items")
    return _list_my_items_payload(type_=type, category=category, status=status)


@mcp.tool()
def search_my_items(query: str, type: str | None = None, category: str | None = None) -> dict[str, Any]:
    """Search the caller's own Valvet items by title/content/category. Never
    returns archived items."""
    logger.info("tool_call name=search_my_items")
    return _search_my_items_payload(query=query, type_=type, category=category)


@mcp.tool()
def get_my_item(id: str) -> dict[str, Any]:
    """Fetch one Valvet item in full, including its updated_at timestamp
    (needed as expected_updated_at for a later update_my_item call)."""
    logger.info("tool_call name=get_my_item")
    return _get_my_item_payload(item_id=id)
```

- [ ] **Step 4: Lägg till i `_tool_definitions()`**

Direkt efter `list_shared_workspace_prompts`-posten (före `save_workspace_prompt`-posten, rad ~913):

```python
        {
            "name": "list_my_items",
            "description": (
                "List the caller's own Valvet items (personal prompt/assistant vault). "
                "Excludes archived items unless status='archived' is passed explicitly."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["prompt", "assistant"]},
                    "category": {"type": "string"},
                    "status": {"type": "string", "enum": ["draft", "review", "published", "archived"]},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "search_my_items",
            "description": "Search the caller's own Valvet items by title/content/category.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "type": {"type": "string", "enum": ["prompt", "assistant"]},
                    "category": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_my_item",
            "description": "Fetch one Valvet item in full, including updated_at (needed for update_my_item).",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string", "format": "uuid"}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
```

- [ ] **Step 5: Lägg till dispatch-grenarna**

I `_handle_mcp_message`, direkt efter grenen `if tool_name == "list_shared_workspace_prompts": ...` (före `if tool_name == "save_workspace_prompt":`, rad ~1027):

```python
        if tool_name == "list_my_items":
            return _json_rpc_result(request_id, _mcp_content_result(
                _list_my_items_payload(mcp_key, arguments.get("type"), arguments.get("category"), arguments.get("status"))
            ))
        if tool_name == "search_my_items":
            query = arguments.get("query")
            if not isinstance(query, str) or not query:
                return _json_rpc_error(request_id, -32602, "Invalid search_my_items arguments")
            return _json_rpc_result(request_id, _mcp_content_result(
                _search_my_items_payload(mcp_key, query, arguments.get("type"), arguments.get("category"))
            ))
        if tool_name == "get_my_item":
            item_id = arguments.get("id")
            if not isinstance(item_id, str) or not item_id:
                return _json_rpc_error(request_id, -32602, "Invalid get_my_item arguments")
            return _json_rpc_result(request_id, _mcp_content_result(_get_my_item_payload(mcp_key, item_id)))
```

- [ ] **Step 6: Lägg till REST-routes**

Handler-funktioner direkt efter `_api_shared_workspace_prompts` (rad ~706, före `_api_save_workspace_prompt`):

```python
async def _api_vault_list_items(request: Request) -> JSONResponse:
    mcp_key = _mcp_key_from_request(request)
    q = request.query_params
    logger.info("http_request path=/api/v1/vault/items status=200")
    return JSONResponse(_list_my_items_payload(mcp_key, q.get("type"), q.get("category"), q.get("status")))


async def _api_vault_search_items(request: Request) -> JSONResponse:
    mcp_key = _mcp_key_from_request(request)
    q = request.query_params
    query = q.get("query", "")
    logger.info("http_request path=/api/v1/vault/items/search status=200")
    return JSONResponse(_search_my_items_payload(mcp_key, query, q.get("type"), q.get("category")))


async def _api_vault_get_item(request: Request) -> JSONResponse:
    item_id = request.path_params["item_id"]
    mcp_key = _mcp_key_from_request(request)
    logger.info("http_request path=/api/v1/vault/items/%s status=200", item_id)
    return JSONResponse(_get_my_item_payload(mcp_key, item_id))
```

Route-registreringar i `Route(...)`-listan (rad ~1204, direkt efter `Route("/api/v1/shared-workspaces/{workspace_id}/prompts", ...)`):

```python
            Route("/api/v1/vault/items", endpoint=_api_vault_list_items, methods=["GET"]),
            Route("/api/v1/vault/items/search", endpoint=_api_vault_search_items, methods=["GET"]),
            Route("/api/v1/vault/items/{item_id}", endpoint=_api_vault_get_item, methods=["GET"]),
```

**Viktigt om routningsordning:** `/api/v1/vault/items/search` måste registreras **före** `/api/v1/vault/items/{item_id}` i listan (Starlette matchar routes i registreringsordning) — annars fångar `{item_id}`-mönstret upp `search` som ett id. Ordningen ovan (`items`, `items/search`, `items/{item_id}`) är redan korrekt.

- [ ] **Step 7: Uppdatera `hosted_guard.py`**

I `allowed_methods` (efter `"save_workspace_prompt",`):

```python
            "list_my_items",
            "search_my_items",
            "get_my_item",
```

I `allowed_tool_args` (efter `"save_workspace_prompt": {...}`):

```python
            "list_my_items": {"type", "category", "status"},
            "search_my_items": {"query", "type", "category"},
            "get_my_item": {"id"},
```

I `inspect_tool_args`, ny `elif`-gren efter `elif tool_name == "save_workspace_prompt": ...` men FÖRE `elif arguments:` (den generella catch-all):

```python
        elif tool_name == "search_my_items":
            query = arguments.get("query")
            if not isinstance(query, str) or not query:
                return {"reason": "invalid_query", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "get_my_item":
            item_id = arguments.get("id")
            if not isinstance(item_id, str) or not item_id:
                return {"reason": "invalid_item_id", "method": method, "tool": tool_name, "id": request_id}
```

(`list_my_items` behöver ingen egen valideringsgren — alla dess argument är valfria strängar, redan täckt av den generella `unexpected_args`-kontrollen högre upp i funktionen.)

- [ ] **Step 8: Manuell verifiering (utan riktig nyckel ännu, bara att servern startar och listar verktyget)**

```powershell
npm run serve
```
I ett annat fönster:
```powershell
curl -s -X POST http://localhost:8000/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | Select-String "list_my_items|search_my_items|get_my_item"
```
Förväntat: alla tre namn syns i svaret.

- [ ] **Step 9: Commit**

```bash
git add mcp-server/server/mcp_server.py mcp-server/server/hosted_guard.py
git commit -m "feat: wire list_my_items, search_my_items, get_my_item into the hosted MCP server"
```

---

### Task 3: Skriv-verktyg i `mcp_server.py`

**Files:**
- Modify: `mcp-server/server/mcp_server.py`
- Modify: `mcp-server/server/hosted_guard.py`

**Interfaces:**
- Consumes: `vault.save_item`, `vault.update_item`, `vault.archive_item`, `vault.log_write_attempt` (Task 1).
- Produces: `@mcp.tool()` `save_my_item`, `update_my_item`, `archive_my_item`; REST `POST /api/v1/vault/items` (save), `PATCH /api/v1/vault/items/{item_id}` (update), `POST /api/v1/vault/items/{item_id}/archive` (archive/restore).

- [ ] **Step 1: Fel-klassificering**

Direkt efter `_classify_write_error` (rad ~189, före `_save_workspace_prompt_payload`):

```python
_VAULT_WRITE_OUTCOME_PATTERNS = [
    ("Ogiltig nyckel", "invalid_key"),
    ("Uppgradera till Pro", "not_pro"),
    ("För många försök", "rate_limited"),
    ("Ogiltig typ", "invalid_input"),
    ("Titel", "invalid_input"),
    ("Innehåll", "invalid_input"),
    ("Månadskvoten", "quota_reached"),
    ("hittades inte", "not_found"),
    ("ändrats sedan du hämtade", "conflict"),
    ("confirm måste vara true", "invalid_input"),
]


def _classify_vault_write_error(detail: str) -> str:
    for needle, outcome in _VAULT_WRITE_OUTCOME_PATTERNS:
        if needle in detail:
            return outcome
    return "limit_reached"
```

- [ ] **Step 2: Payload-funktionerna**

Direkt efter `_classify_vault_write_error`:

```python
def _save_my_item_payload(
    mcp_key: str, idempotency_key: str, type_: str, title: str, content: str, category: str | None
) -> dict[str, Any]:
    if not mcp_key:
        return {"status": "error", "message": "MCP-nyckel krävs (X-MCP-Key eller Authorization)."}
    try:
        item = _vault_save_item(mcp_key, idempotency_key, type_, title, content, category)
        return {"status": "success", "item": item}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.info("tool_call name=save_my_item status=error detail=%s", detail)
        outcome = _classify_vault_write_error(detail)
        _vault_log_write_attempt(mcp_key, "save_my_item", outcome)
        try:
            clean_message = exc.response.json().get("message", detail)
        except Exception:
            clean_message = detail
        return {"status": "error", "message": clean_message}
    except RuntimeError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.error("save_my_item_failed error=%s", exc)
        return {"status": "error", "message": "Kunde inte spara insättningen."}


def _update_my_item_payload(
    mcp_key: str,
    item_id: str,
    expected_updated_at: str,
    title: str | None,
    content: str | None,
    category: str | None,
) -> dict[str, Any]:
    if not mcp_key:
        return {"status": "error", "message": "MCP-nyckel krävs (X-MCP-Key eller Authorization)."}
    try:
        item = _vault_update_item(mcp_key, item_id, expected_updated_at, title, content, category)
        return {"status": "success", "item": item}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.info("tool_call name=update_my_item status=error detail=%s", detail)
        outcome = _classify_vault_write_error(detail)
        _vault_log_write_attempt(mcp_key, "update_my_item", outcome)
        try:
            clean_message = exc.response.json().get("message", detail)
        except Exception:
            clean_message = detail
        return {"status": "error", "message": clean_message}
    except RuntimeError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.error("update_my_item_failed error=%s", exc)
        return {"status": "error", "message": "Kunde inte uppdatera insättningen."}


def _archive_my_item_payload(mcp_key: str, item_id: str, confirm: bool, restore: bool) -> dict[str, Any]:
    if not mcp_key:
        return {"status": "error", "message": "MCP-nyckel krävs (X-MCP-Key eller Authorization)."}
    try:
        item = _vault_archive_item(mcp_key, item_id, confirm, restore)
        return {"status": "success", "item": item}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.info("tool_call name=archive_my_item status=error detail=%s", detail)
        outcome = _classify_vault_write_error(detail)
        _vault_log_write_attempt(mcp_key, "archive_my_item_restore" if restore else "archive_my_item", outcome)
        try:
            clean_message = exc.response.json().get("message", detail)
        except Exception:
            clean_message = detail
        return {"status": "error", "message": clean_message}
    except RuntimeError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.error("archive_my_item_failed error=%s", exc)
        return {"status": "error", "message": "Kunde inte arkivera/återställa insättningen."}
```

- [ ] **Step 3: `@mcp.tool()`-wrapperna**

Direkt efter `save_workspace_prompt` (i botten av filen, efter rad ~1264):

```python
@mcp.tool()
def save_my_item(
    idempotency_key: str,
    type: str,
    title: str,
    content: str,
    category: str | None = None,
) -> dict[str, Any]:
    """Save a new item to the caller's Valvet (personal prompt/assistant
    vault). Requires an idempotency_key (client-generated UUID) so a retried
    call never creates a duplicate. Free keys are limited to 5 saves per
    calendar month; Pro keys have no monthly cap."""
    logger.info("tool_call name=save_my_item")
    return _save_my_item_payload("", idempotency_key, type, title, content, category)


@mcp.tool()
def update_my_item(
    id: str,
    expected_updated_at: str,
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Update an existing Valvet item. Pro-only. expected_updated_at must be
    the updated_at value from a prior get_my_item/list_my_items call
    (optimistic locking) -- on mismatch, re-fetch and retry."""
    logger.info("tool_call name=update_my_item")
    return _update_my_item_payload("", id, expected_updated_at, title, content, category)


@mcp.tool()
def archive_my_item(id: str, confirm: bool, restore: bool = False) -> dict[str, Any]:
    """Archive (or, with restore=true, un-archive) a Valvet item. Pro-only.
    confirm must be explicitly true -- the call is rejected otherwise, to
    guard against an ambiguous or injected instruction archiving the wrong
    item. Archiving an already-archived item (or restoring an already-active
    one) is a safe no-op."""
    logger.info("tool_call name=archive_my_item")
    return _archive_my_item_payload("", id, confirm, restore)
```

- [ ] **Step 4: `_tool_definitions()`**

Efter `save_workspace_prompt`-posten (sista i listan, rad ~934):

```python
        {
            "name": "save_my_item",
            "description": (
                "Save a new item to the caller's Valvet (personal prompt/assistant vault). "
                "Requires idempotency_key. Free keys: max 5 saves/calendar month."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "idempotency_key": {"type": "string", "format": "uuid"},
                    "type": {"type": "string", "enum": ["prompt", "assistant"]},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["idempotency_key", "type", "title", "content"],
                "additionalProperties": False,
            },
        },
        {
            "name": "update_my_item",
            "description": (
                "Update an existing Valvet item. Pro-only. expected_updated_at (from a prior "
                "get_my_item call) is required for optimistic locking."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "expected_updated_at": {"type": "string", "format": "date-time"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["id", "expected_updated_at"],
                "additionalProperties": False,
            },
        },
        {
            "name": "archive_my_item",
            "description": (
                "Archive or restore a Valvet item. Pro-only. confirm must be true, "
                "otherwise the call is rejected."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "confirm": {"type": "boolean"},
                    "restore": {"type": "boolean", "default": False},
                },
                "required": ["id", "confirm"],
                "additionalProperties": False,
            },
        },
```

- [ ] **Step 5: Dispatch-grenarna**

Efter `save_workspace_prompt`-grenen (rad ~1045, före `return _json_rpc_error(request_id, -32601, "Tool not found")`):

```python
        if tool_name == "save_my_item":
            idempotency_key = arguments.get("idempotency_key")
            item_type = arguments.get("type")
            title = arguments.get("title")
            content = arguments.get("content")
            if not all(isinstance(v, str) and v for v in (idempotency_key, item_type, title, content)):
                return _json_rpc_error(request_id, -32602, "Invalid save_my_item arguments")
            return _json_rpc_result(
                request_id,
                _mcp_content_result(
                    _save_my_item_payload(mcp_key, idempotency_key, item_type, title, content, arguments.get("category"))
                ),
            )
        if tool_name == "update_my_item":
            item_id = arguments.get("id")
            expected_updated_at = arguments.get("expected_updated_at")
            if not all(isinstance(v, str) and v for v in (item_id, expected_updated_at)):
                return _json_rpc_error(request_id, -32602, "Invalid update_my_item arguments")
            return _json_rpc_result(
                request_id,
                _mcp_content_result(
                    _update_my_item_payload(
                        mcp_key, item_id, expected_updated_at,
                        arguments.get("title"), arguments.get("content"), arguments.get("category"),
                    )
                ),
            )
        if tool_name == "archive_my_item":
            item_id = arguments.get("id")
            confirm = arguments.get("confirm")
            restore = arguments.get("restore", False)
            if not isinstance(item_id, str) or not item_id or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid archive_my_item arguments")
            if not isinstance(restore, bool):
                return _json_rpc_error(request_id, -32602, "restore must be a boolean")
            return _json_rpc_result(
                request_id, _mcp_content_result(_archive_my_item_payload(mcp_key, item_id, confirm, restore))
            )
```

- [ ] **Step 6: REST-routes**

Handlers efter `_api_save_workspace_prompt` (rad ~733):

```python
async def _api_vault_save_item(request: Request) -> JSONResponse:
    mcp_key = _mcp_key_from_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_error("INVALID_JSON", "Request body must be JSON"), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_error("INVALID_BODY", "Request body must be a JSON object"), status_code=400)
    idempotency_key = body.get("idempotency_key")
    item_type = body.get("type")
    title = body.get("title")
    content = body.get("content")
    if not all(isinstance(v, str) and v for v in (idempotency_key, item_type, title, content)):
        return JSONResponse(
            _error("INVALID_ARGUMENTS", "idempotency_key, type, title and content are required strings"),
            status_code=400,
        )
    payload = _save_my_item_payload(mcp_key, idempotency_key, item_type, title, content, body.get("category"))
    status_code = 200 if payload.get("status") == "success" else 400
    logger.info("http_request path=/api/v1/vault/items method=POST status=%s", status_code)
    return JSONResponse(payload, status_code=status_code)


async def _api_vault_update_item(request: Request) -> JSONResponse:
    item_id = request.path_params["item_id"]
    mcp_key = _mcp_key_from_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_error("INVALID_JSON", "Request body must be JSON"), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_error("INVALID_BODY", "Request body must be a JSON object"), status_code=400)
    expected_updated_at = body.get("expected_updated_at")
    if not isinstance(expected_updated_at, str) or not expected_updated_at:
        return JSONResponse(
            _error("INVALID_ARGUMENTS", "expected_updated_at is required"), status_code=400
        )
    payload = _update_my_item_payload(
        mcp_key, item_id, expected_updated_at, body.get("title"), body.get("content"), body.get("category")
    )
    status_code = 200 if payload.get("status") == "success" else 400
    logger.info("http_request path=/api/v1/vault/items/%s method=PATCH status=%s", item_id, status_code)
    return JSONResponse(payload, status_code=status_code)


async def _api_vault_archive_item(request: Request) -> JSONResponse:
    item_id = request.path_params["item_id"]
    mcp_key = _mcp_key_from_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    confirm = body.get("confirm")
    restore = bool(body.get("restore", False))
    if not isinstance(confirm, bool):
        return JSONResponse(_error("INVALID_ARGUMENTS", "confirm (boolean) is required"), status_code=400)
    payload = _archive_my_item_payload(mcp_key, item_id, confirm, restore)
    status_code = 200 if payload.get("status") == "success" else 400
    logger.info("http_request path=/api/v1/vault/items/%s/archive method=POST status=%s", item_id, status_code)
    return JSONResponse(payload, status_code=status_code)
```

Route-registreringar, direkt efter `Route("/api/v1/vault/items/{item_id}", ...)` från Task 2:

```python
            Route("/api/v1/vault/items", endpoint=_api_vault_save_item, methods=["POST"]),
            Route("/api/v1/vault/items/{item_id}", endpoint=_api_vault_update_item, methods=["PATCH"]),
            Route("/api/v1/vault/items/{item_id}/archive", endpoint=_api_vault_archive_item, methods=["POST"]),
```

- [ ] **Step 7: Uppdatera `hosted_guard.py`**

I `allowed_methods` (efter de tre läs-verktygen från Task 2):

```python
            "save_my_item",
            "update_my_item",
            "archive_my_item",
```

I `allowed_tool_args`:

```python
            "save_my_item": {"idempotency_key", "type", "title", "content", "category"},
            "update_my_item": {"id", "expected_updated_at", "title", "content", "category"},
            "archive_my_item": {"id", "confirm", "restore"},
```

I `inspect_tool_args`, nya grenar (samma plats som Task 2 Step 7, före den generella `elif arguments:`):

```python
        elif tool_name == "save_my_item":
            idempotency_key = arguments.get("idempotency_key")
            item_type = arguments.get("type")
            title = arguments.get("title")
            content = arguments.get("content")
            if not all(isinstance(v, str) and v for v in (idempotency_key, item_type, title, content)):
                return {"reason": "invalid_save_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "update_my_item":
            item_id = arguments.get("id")
            expected_updated_at = arguments.get("expected_updated_at")
            if not all(isinstance(v, str) and v for v in (item_id, expected_updated_at)):
                return {"reason": "invalid_update_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "archive_my_item":
            item_id = arguments.get("id")
            confirm = arguments.get("confirm")
            if not isinstance(item_id, str) or not item_id or not isinstance(confirm, bool):
                return {"reason": "invalid_archive_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
```

- [ ] **Step 8: Syntax-sanity + starta servern**

```powershell
python -c "import ast; ast.parse(open('mcp-server/server/mcp_server.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('mcp-server/server/hosted_guard.py', encoding='utf-8').read())"
npm run serve
```
Förväntat: servern startar utan traceback.

- [ ] **Step 9: Commit**

```bash
git add mcp-server/server/mcp_server.py mcp-server/server/hosted_guard.py
git commit -m "feat: wire save_my_item, update_my_item, archive_my_item into the hosted MCP server"
```

---

### Task 4: End-to-end-verifiering mot staging

**Förutsättning:** Plan A applicerad och verifierad mot staging Supabase-projektet, och `.env`/miljövariabler pekar dit (`SUPABASE_URL`, `SUPABASE_ANON_KEY`). En riktig Free- och en riktig Pro-testnyckels **rå** värden (inte hash) behövs.

- [ ] **Step 1: Starta servern mot staging**

```powershell
$env:SUPABASE_URL = "<staging-url>"
$env:SUPABASE_ANON_KEY = "<staging-anon-key>"
npm run serve
```

- [ ] **Step 2: Kör igenom hela flödet med curl**

```powershell
$freeKey = "<fri-nyckel>"
$proKey = "<pro-nyckel>"

# Tomt valv
curl -s http://localhost:8000/api/v1/vault/items -H "X-MCP-Key: $freeKey"

# Spara (Free, med idempotency)
curl -s -X POST http://localhost:8000/api/v1/vault/items -H "X-MCP-Key: $freeKey" -H "Content-Type: application/json" `
  -d '{"idempotency_key":"11111111-1111-1111-1111-111111111111","type":"prompt","title":"Test","content":"Innehåll","category":"A"}'

# Samma idempotency-nyckel igen -> samma id, inget nytt skapat
curl -s -X POST http://localhost:8000/api/v1/vault/items -H "X-MCP-Key: $freeKey" -H "Content-Type: application/json" `
  -d '{"idempotency_key":"11111111-1111-1111-1111-111111111111","type":"prompt","title":"Test","content":"Innehåll","category":"A"}'

# Lista, sök, hämta
curl -s http://localhost:8000/api/v1/vault/items -H "X-MCP-Key: $freeKey"
curl -s "http://localhost:8000/api/v1/vault/items/search?query=Test" -H "X-MCP-Key: $freeKey"

# Free kan INTE uppdatera/arkivera
curl -s -X PATCH http://localhost:8000/api/v1/vault/items/<id> -H "X-MCP-Key: $freeKey" -H "Content-Type: application/json" `
  -d '{"expected_updated_at":"2026-01-01T00:00:00Z","title":"X"}'
# Förväntat: status=error, "Uppgradera till Pro..."

# Pro: fullständig CRUD
curl -s -X POST http://localhost:8000/api/v1/vault/items -H "X-MCP-Key: $proKey" -H "Content-Type: application/json" `
  -d '{"idempotency_key":"22222222-2222-2222-2222-222222222222","type":"assistant","title":"Pro-test","content":"Du är..."}'
curl -s -X PATCH http://localhost:8000/api/v1/vault/items/<pro-id> -H "X-MCP-Key: $proKey" -H "Content-Type: application/json" `
  -d '{"expected_updated_at":"<updated_at från ovan>","title":"Pro-test (redigerad)"}'
curl -s -X POST http://localhost:8000/api/v1/vault/items/<pro-id>/archive -H "X-MCP-Key: $proKey" -H "Content-Type: application/json" `
  -d '{"confirm":true}'
```

Förväntat: exakt de resultat/felmeddelanden som beskrivs i kommentarerna.

- [ ] **Step 3: Verifiera via `/mcp` (tools/list och tools/call)**

```powershell
curl -s -X POST http://localhost:8000/mcp -H "Content-Type: application/json" -H "X-MCP-Key: $proKey" `
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_my_items","arguments":{}}}'
```
Förväntat: samma resultat som REST-varianten, inpackat i MCP:s `content`-format.

- [ ] **Step 4: Verifiera att `hosted_guard` faktiskt blockerar oväntade argument**

```powershell
curl -s -X POST http://localhost:8000/mcp -H "Content-Type: application/json" -H "X-MCP-Key: $proKey" `
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"archive_my_item","arguments":{"id":"x","confirm":true,"extra_field":"nope"}}}'
```
Förväntat: guard-varning i serverloggen (`hosted_payload_warning` eller motsvarande, se `mcp_server.py`s middleware-logik för `HostedMetadataGuardMiddleware`) — verifiera manuellt i terminalen där `npm run serve` kör.

---

### Task 5: Dokumentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `TODO.md`, `LOG.md`, `DECISIONS.md`

**Note:** repot har redan osparade lokala ändringar i `LOG.md`/`TODO.md`/en plan-fil sedan tidigare (se `git status` innan du börjar) — lägg dina tillägg till, skriv INTE över det som redan står där.

- [ ] **Step 1: `README.md`** — lägg till efter raden om `list_shared_workspace_prompts` (rad ~107):

```markdown
- `list_my_items`/REST `GET /api/v1/vault/items` — nyckelns egna Valvet-insättningar (personligt prompt/assistant-valv, `module='valvet'`). Utesluter arkiverade om inte `status=archived` skickas explicit.
- `search_my_items`/REST `GET /api/v1/vault/items/search?query=...` — söker titel/innehåll/kategori bland nyckelns Valvet-insättningar.
- `get_my_item`/REST `GET /api/v1/vault/items/{id}` — hämtar en insättning i sin helhet, inklusive `updated_at` (krävs för `update_my_item`).
- `save_my_item`/REST `POST /api/v1/vault/items` — skapar en ny insättning. Kräver `idempotency_key`. Free-nycklar: max 5 sparningar/kalendermånad. Pro: ingen månadskvot.
- `update_my_item`/REST `PATCH /api/v1/vault/items/{id}` — uppdaterar en insättning. Pro-only. Kräver `expected_updated_at` (optimistic locking — avvisas med tydligt fel om posten ändrats sedan den hämtades).
- `archive_my_item`/REST `POST /api/v1/vault/items/{id}/archive` — arkiverar eller (med `restore:true`) återställer en insättning. Pro-only. Kräver `confirm:true`.
```

- [ ] **Step 2: `CLAUDE.md`** — lägg till en ny sektion efter "### Write: `save_workspace_prompt` (2026-07-12)":

```markdown
### Write: Valvet — full CRUD (2026-07-16)

Sex nya verktyg för Valvet (`mcp-server/server/vault.py`): `list_my_items`,
`search_my_items`, `get_my_item` (alla plan-oberoende, read-only) och
`save_my_item`/`update_my_item`/`archive_my_item` (write). Till skillnad
från `save_workspace_prompt` (som skriver till kommunens `content_items`,
`module='kommun'` implicit) skriver dessa alltid `module='valvet'` — ett helt
separat tak och synlighetsregelverk i `promptbanken`-repot, se
`docs/superpowers/specs/2026-07-16-valvet-design.md` där. `save_my_item` är
tillgängligt för Free (5/kalendermånad) och Pro (obegränsat); `update_my_item`/
`archive_my_item` är Pro-only. Samma två-fas-loggning som `save_workspace_prompt`
(lyckade skrivningar loggas inifrån RPC:n, avvisade loggas separat av Python
efter ett fångat fel) mot samma `app_private.mcp_write_attempts`-tabell,
nu med en `tool`-kolumn så flera write-verktyg kan dela loggen utan att
blanda ihop sina kvoter/rate limits.
```

- [ ] **Step 3: `TODO.md`** — lägg till under "## Klart" (utan att röra befintliga rader):

```markdown
- [x] Valvet MCP-verktyg (`list_my_items`, `search_my_items`, `get_my_item`, `save_my_item`, `update_my_item`, `archive_my_item`) — se `docs/superpowers/plans/2026-07-16-valvet-mcp-tools.md`. Kräver Plan A (`promptbanken`-repot) applicerad mot produktions-Supabase innan detta är live i produktion, inte bara staging.
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md TODO.md LOG.md DECISIONS.md
git commit -m "docs: document the six new Valvet MCP tools"
```

---

## Klart-kriterier för Plan B

- Alla sex verktyg syns i `tools/list` och svarar korrekt i `tools/call` mot staging.
- `hosted_guard.py` blockerar oväntade argument (Task 4, Step 4).
- Free/Pro-gating, idempotens, optimistic locking och `confirm`-kravet alla manuellt verifierade end-to-end (Task 4).
- Dokumentation uppdaterad (Task 5).
- Klart för produktionsdeploy (kräver separat, uttryckligt beslut — se `AGENTS.md`/`CLAUDE.md` om deploy-flödet, inte del av denna plan).
