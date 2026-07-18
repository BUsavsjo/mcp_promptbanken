# Valvet status-clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Valvet MCP tool surface (`list_my_items`, `save_my_item`) explain that `status='draft'` means the item is already fully saved and private, and stop advertising `review`/`published` as usable `list_my_items` filter values when no client can ever set them.

**Architecture:** Pure text/schema edit in `mcp-server/server/mcp_server.py` — no new fields, no behavior change, no database/RPC change. Two independent copies of each tool's metadata exist in this file (a `@mcp.tool()`-decorated function with a docstring, read by local stdio clients; a manual JSON-RPC dict in `_tool_definitions()`, read by hosted HTTP clients) and both get the same clarifying sentence. The hosted `list_my_items` JSON schema's `status` enum is narrowed from four values to two (`draft`, `archived`), with a property-level note explaining the other two are reserved.

**Tech Stack:** Python 3.12, no test framework in this repo (`CLAUDE.md`: "Inga automatiserade tester finns i repot ännu"). Verification uses the same manual pattern as prior work in this repo: `ast.parse` for a syntax check, then `python -c` importing the module directly and asserting on the returned dicts.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-18-valvet-status-clarity-design.md`
- Scope is the MCP surface only (`mcp_promptbanken` repo). Do not touch `promptbanken/admin.html`, `valvet_promptbanken`, or the database enum.
- All added text in `mcp_server.py` is English, matching this file's existing convention. README.md/CLAUDE.md additions are Swedish, matching those files' existing convention.
- No response field changes — `save_my_item`/`list_my_items`/`get_my_item` continue to return `status` exactly as before; only descriptions and the `status` filter's enum change.
- `list_my_items`'s `status` filter enum becomes exactly `["draft", "archived"]` — do not remove `review`/`published` from the database enum (owned by the `promptbanken` repo, out of scope here).

---

### Task 1: Clarify draft + narrow the status enum in `mcp_server.py`

**Files:**
- Modify: `mcp-server/server/mcp_server.py:526-531` (`list_my_items` local docstring)
- Modify: `mcp-server/server/mcp_server.py:1785-1798` (`save_my_item` local docstring)
- Modify: `mcp-server/server/mcp_server.py:1251-1266` (`list_my_items` hosted JSON-RPC definition, inside `_tool_definitions()`)
- Modify: `mcp-server/server/mcp_server.py:1312-1330` (`save_my_item` hosted JSON-RPC definition, inside `_tool_definitions()`)

**Interfaces:**
- Consumes: nothing new — same existing functions (`_list_my_items_payload`, `_save_my_item_payload`, `_tool_definitions`), same signatures, unchanged.
- Produces: nothing new for other tasks — `_tool_definitions()` still returns `list[dict[str, Any]]`, same shape, only text/enum values inside it change. Task 2 (docs) references the exact enum/description values fixed here, so this task must land first.

- [ ] **Step 1: Read current state to confirm line numbers**

Run: `grep -n "def list_my_items\|def save_my_item\|\"name\": \"list_my_items\"\|\"name\": \"save_my_item\"" mcp-server/server/mcp_server.py`

Expected: four matches — the two `@mcp.tool()` function defs and the two `"name": "..."` dict entries — at or near lines 527, 1786, 1252, 1313 (line numbers may have drifted slightly; use the printed output to locate the exact blocks below, not the hardcoded numbers).

- [ ] **Step 2: Update the local `list_my_items` docstring**

Find:

```python
@mcp.tool()
def list_my_items(type: str | None = None, category: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List the caller's own Valvet items (personal prompt/assistant vault).
    Excludes archived items unless status='archived' is passed explicitly."""
    logger.info("tool_call name=list_my_items")
    return _list_my_items_payload(type_=type, category=category, status=status)
```

Replace with:

```python
@mcp.tool()
def list_my_items(type: str | None = None, category: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List the caller's own Valvet items (personal prompt/assistant vault).
    All items are private to the owning key regardless of status. Excludes
    archived items unless status='archived' is passed explicitly."""
    logger.info("tool_call name=list_my_items")
    return _list_my_items_payload(type_=type, category=category, status=status)
```

- [ ] **Step 3: Update the local `save_my_item` docstring**

Find:

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
```

Replace with:

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
    calendar month; Pro keys have no monthly cap. The item is fully saved
    and private to the caller immediately -- status='draft' only describes
    editing state, not save state or visibility."""
    logger.info("tool_call name=save_my_item")
    return _save_my_item_payload("", idempotency_key, type, title, content, category)
```

- [ ] **Step 4: Update the hosted `list_my_items` JSON-RPC definition**

Find (inside `_tool_definitions()`):

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
```

Replace with:

```python
        {
            "name": "list_my_items",
            "description": (
                "List the caller's own Valvet items (personal prompt/assistant vault). "
                "All items are private to the owning key regardless of status. "
                "Excludes archived items unless status='archived' is passed explicitly."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["prompt", "assistant"]},
                    "category": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["draft", "archived"],
                        "description": (
                            "review and published exist in the database enum but are "
                            "reserved for a future review/publishing workflow -- no "
                            "Valvet client (web or MCP) can set them yet."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
```

- [ ] **Step 5: Update the hosted `save_my_item` JSON-RPC definition**

Find (inside `_tool_definitions()`):

```python
        {
            "name": "save_my_item",
            "description": (
                "Save a new item to the caller's Valvet (personal prompt/assistant vault). "
                "Requires idempotency_key. Free keys: max 5 saves/calendar month."
            ),
            "inputSchema": {
```

Replace with:

```python
        {
            "name": "save_my_item",
            "description": (
                "Save a new item to the caller's Valvet (personal prompt/assistant vault). "
                "Requires idempotency_key. Free keys: max 5 saves/calendar month. "
                "The item is fully saved and private to the caller immediately -- "
                "status='draft' only describes editing state, not save state or visibility."
            ),
            "inputSchema": {
```

(Only the `description` value changes — leave the rest of this dict, starting at `"inputSchema": {`, untouched.)

- [ ] **Step 6: Syntax-check the file**

Run: `python -c "import ast; ast.parse(open('mcp-server/server/mcp_server.py', encoding='utf-8').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 7: Verify the hosted tool definitions**

Run:

```bash
cd mcp-server
PROMPTBANKEN_MCP_MODE=hosted .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from server import mcp_server
defs = {d['name']: d for d in mcp_server._tool_definitions()}
li = defs['list_my_items']
sv = defs['save_my_item']
status_schema = li['inputSchema']['properties']['status']
assert status_schema['enum'] == ['draft', 'archived'], status_schema['enum']
assert 'reserved' in status_schema['description']
assert 'private to the owning key' in li['description']
assert 'fully saved and private' in sv['description']
print('OK')
"
```

Expected: `OK`

- [ ] **Step 8: Verify the local docstrings**

Run:

```bash
cd mcp-server
PROMPTBANKEN_MCP_MODE=local .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from server import mcp_server
assert 'private to the owning key' in mcp_server.list_my_items.__doc__
assert 'fully saved and private' in mcp_server.save_my_item.__doc__
print('OK')
"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add mcp-server/server/mcp_server.py
git commit -m "Forklara draft och smalna av status-enum i Valvets MCP-verktyg"
```

---

### Task 2: Documentation — README.md, CLAUDE.md, TODO.md

**Files:**
- Modify: `README.md:111-121` (Valvet section, add a new "Status" subsection)
- Modify: `CLAUDE.md:146-167` (Write: Valvet section, add one sentence)
- Modify: `TODO.md` (the `## Klart` section, add one bullet)

**Interfaces:**
- Consumes: the exact enum values and description wording fixed in Task 1 (`draft`/`archived` active, `review`/`published` reserved) — this task must describe them accurately, so it runs after Task 1.
- Produces: nothing consumed by other tasks — this is documentation only.

- [ ] **Step 1: Add a "Status" subsection to README.md's Valvet section**

Find (the last bullet of the Valvet tool list, followed by the next section header):

```markdown
- `archive_my_item`/REST `POST /api/v1/vault/items/{id}/archive` — arkiverar eller (med `restore:true`) återställer en insättning. Pro-only. Kräver `confirm:true`.

### Supabase-migration
```

Replace with:

```markdown
- `archive_my_item`/REST `POST /api/v1/vault/items/{id}/archive` — arkiverar eller (med `restore:true`) återställer en insättning. Pro-only. Kräver `confirm:true`.

**Status:** en Valvet-post har alltid en av `draft`/`review`/`published`/`archived` i databasens enum, men bara `draft` (standard vid skapande) och `archived` går att nå via Valvets verktyg i Fas 1 — `list_my_items`s `status`-filter accepterar bara dessa två. Posten är fullt sparad och privat till nyckelns ägare direkt vid `save_my_item`; `draft` beskriver bara redigeringsläge, inte om posten finns eller vem som ser den (Valvet-poster har ingen egen synlighetskolumn — de är alltid privata). `review`/`published` är reserverade för ett framtida gransknings-/publiceringsflöde; ingen klient (webb eller MCP) kan sätta dem idag.

### Supabase-migration
```

- [ ] **Step 2: Add one sentence to CLAUDE.md's Write: Valvet section**

Find:

```markdown
tyst men loggade ett falskt `vault_write_attempt_failed`-fel trots att
loggraden faktiskt skrevs.
```

If that exact text isn't found (the real string is `vault_log_write_attempt_failed`, verify with the grep in the next line before editing), instead find:

```markdown
tyst men loggade ett falskt `vault_log_write_attempt_failed`-fel trots att
loggraden faktiskt skrevs.
```

Replace with:

```markdown
tyst men loggade ett falskt `vault_log_write_attempt_failed`-fel trots att
loggraden faktiskt skrevs. **Status:** bara `draft`/`archived` är nåbara via
Valvets verktyg (`update_my_item` har inget `status`-argument, webbappen
sätter aldrig `review`/`published`) — se README.md och
`docs/superpowers/specs/2026-07-18-valvet-status-clarity-design.md`. Lägg
aldrig till `review`/`published` som giltiga i `list_my_items`s
`status`-enum utan att först bygga ett sätt att faktiskt sätta dem.
```

- [ ] **Step 3: Add a bullet to TODO.md's Klart section**

Find the `## Klart` section header and add a new first bullet directly below it:

```markdown
- [x] Förtydligade `draft`-status i Valvets MCP-verktyg (`list_my_items`/`save_my_item`-beskrivningar + docstrings förklarar att posten redan är sparad och privat oavsett status) och smalnade av `list_my_items`s `status`-filter till `draft`/`archived` (`review`/`published` var döda/oåtkomliga värden — `update_my_item` har inget `status`-argument). Se `docs/superpowers/specs/2026-07-18-valvet-status-clarity-design.md`.
```

- [ ] **Step 4: Review the diff before committing**

Run: `git diff README.md CLAUDE.md TODO.md`

Expected: only the three additions from Steps 1-3 above — confirm no other text in these files changed, and that the terminology (`draft`/`archived` active, `review`/`published` reserved) matches Task 1's actual enum/description wording exactly.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md TODO.md
git commit -m "Dokumentera Valvets status-konvention (draft/archived aktiva, review/published reserverade)"
```

---

### Task 3: Deploy and live verification

**Files:** none (operational task, no code changes)

**Interfaces:**
- Consumes: the deployed VPS environment (`docker-compose`, Caddy) — no new environment variables required.
- Produces: nothing — this is the final verification step confirming Tasks 1-2 work in production, matching the spec's testplan item 1.

- [ ] **Step 1: Push commits from Tasks 1-2**

```bash
git push origin main
```

- [ ] **Step 2: Deploy on the VPS**

Run on the VPS (see `TODO.md`/`CLAUDE.md` for the known `docker-compose` 1.29.2 `'ContainerConfig'` recreate bug — if it recurs, remove the stale hash-prefixed container with `docker rm -f <name>` before retrying `up -d --build`):

```bash
cd /home/wenstrompeter/mcp_promptbanken
git pull origin main
docker-compose up -d --build
docker-compose ps
```

- [ ] **Step 3: Verify the hosted `tools/list` response over `/mcp`**

```bash
curl -s -X POST https://mcp.promptbanken.se/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Expected: the `list_my_items` entry's `inputSchema.properties.status.enum` is `["draft","archived"]` (grep the raw output for `"review"` — it should no longer appear anywhere in the `list_my_items` or `save_my_item` entries), and both entries' `description` fields contain the new clarifying sentences ("private to the owning key" / "fully saved and private").

- [ ] **Step 4 (optional, only with a real test key): Confirm `save_my_item`'s response shape is unchanged**

This performs a real write against production (creates one Valvet item and
counts against that key's monthly quota if it's a Free key) — only run it
if the user provides a live test MCP key, same pattern as prior sessions
in this repo. Skip this step entirely otherwise; Task 1's Step 7 already
confirms the schema/description text without touching production data.

```bash
curl -s -X POST https://mcp.promptbanken.se/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-MCP-Key: <riktig testnyckel>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"save_my_item","arguments":{"idempotency_key":"<ett-nytt-uuid>","type":"prompt","title":"Statustest","content":"Verifierar att status fortfarande ar draft efter denna andring."}}}'
```

Expected: response contains `"status":"draft"`, unchanged from before this
plan — this task only touched descriptions/enum, never the response shape.

- [ ] **Step 5: Mark this task done, no further doc changes expected**

If Step 3's output matches expectations exactly, this step is a no-op. If production behaves differently than the local verification in Task 1 (e.g. a stale container serving old code), fix the underlying deploy issue, redeploy, and re-run Step 3 before considering this task complete — do not edit README/CLAUDE.md wording to match an unexpected production result without first confirming it isn't a stale-deploy artifact.
