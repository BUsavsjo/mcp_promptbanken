# health_check catalog/plan/message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `health_check` (REST `GET /healthz` and the MCP `health_check` tool/JSON-RPC method) report `catalog`/`plan`/`message` fields that reflect the access level of whatever `X-MCP-Key`/`Authorization` key was sent with the request.

**Architecture:** Extend `SupabaseRepository` to retain the `plan` field already returned by the `verify_mcp_key` RPC (currently discarded). Add a new `_health_check_payload(mcp_key)` helper in `mcp_server.py` that maps four states (no key / invalid key / free / pro) to `catalog`/`plan`/`message`, and wire it into the two request paths that have header access (REST `_healthz`, JSON-RPC `tools/call` dispatch for `health_check`). The plain `@mcp.tool() health_check()` (stdio, no header context) is left unchanged.

**Tech Stack:** Python 3.12, no test framework in this repo (verified manually — see `CLAUDE.md`: "Inga automatiserade tester finns i repot ännu"). Verification here uses the same manual pattern already used in this repo: import the module in a throwaway `python -c` script and assert on the returned dict, then a live `curl` check after deploy.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-03-health-check-catalog-status-design.md`
- `plan` values are exactly `public` / `free` / `pro` — no `team` value in this version (explicitly excluded in the spec).
- `catalog` values are exactly `open` / `workspace` / `pro`.
- The `invalid_key` message text MUST be the same string object/value already used for `workspace_message` in `_WORKSPACE_STATUS_MESSAGES["invalid_key"]` — no duplicate string literal.
- `catalog`/`plan`/`message` are **always** present in the `health_check` response (unlike `workspace_status`/`workspace_message` on `/api/v1/skills`, which are omitted when no key is sent).
- No extra Supabase network call when `mcp_key` is empty (keep `/healthz` fast for infra health checks that never send a key).
- Documentation in Swedish, matching the rest of the repo's `README.md`/`CLAUDE.md`.

---

### Task 1: Expose `plan` from `SupabaseRepository`

**Files:**
- Modify: `mcp-server/server/supabase_repository.py:141-160` (the `SupabaseRepository.__init__` and `_resolve_workspace` methods)

**Interfaces:**
- Consumes: existing `_verify_mcp_key(raw_key: str) -> dict[str, str] | None` (already returns `{"workspace_id": ..., "plan": ..., "workspace_type": ...}`, defined earlier in the same file).
- Produces: `SupabaseRepository.plan` property, type `str | None`. Returns `None` if the key never resolved (no key, invalid key, or network failure); returns the raw `plan` string (`"free"`, `"pro"`, or whatever Supabase returns) if resolved.

- [ ] **Step 1: Read current state to confirm line numbers**

Run: `grep -n "_resolve_workspace\|def __init__\|self._resolved\|self._workspace_id" mcp-server/server/supabase_repository.py`

Expected: shows `__init__` around line 141 and `_resolve_workspace` around line 146, matching the snippet below (line numbers may drift slightly — use the printed output, not the hardcoded numbers, to locate the exact block).

- [ ] **Step 2: Update `__init__` to add plan/workspace_type storage**

Replace:

```python
    def __init__(self, mcp_api_key: str) -> None:
        self._mcp_api_key = mcp_api_key
        self._workspace_id: str | None = None
        self._resolved: bool | None = None
```

With:

```python
    def __init__(self, mcp_api_key: str) -> None:
        self._mcp_api_key = mcp_api_key
        self._workspace_id: str | None = None
        self._resolved: bool | None = None
        self._plan: str | None = None
        self._workspace_type: str | None = None
```

- [ ] **Step 3: Update `_resolve_workspace` to store plan/workspace_type**

Replace:

```python
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
```

With:

```python
    def _resolve_workspace(self) -> bool:
        if self._resolved is not None:
            return self._resolved
        result = _verify_mcp_key(self._mcp_api_key)
        if result is None:
            self._resolved = False
            return False
        self._workspace_id = result["workspace_id"]
        self._plan = result.get("plan")
        self._workspace_type = result.get("workspace_type")
        self._resolved = True
        return True
```

- [ ] **Step 4: Add the `plan` property**

Directly below `key_is_valid()` (which already exists in this file, added in a previous session), add:

```python
    @property
    def plan(self) -> str | None:
        """Rå plan-etikett ('free'/'pro') från verify_mcp_key, eller None om nyckeln inte är giltig."""
        self._resolve_workspace()
        return self._plan
```

- [ ] **Step 5: Syntax-check the file**

Run: `python -c "import ast; ast.parse(open('mcp-server/server/supabase_repository.py', encoding='utf-8').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Manual behavior check (no live Supabase needed)**

Run:

```bash
cd mcp-server
PROMPTBANKEN_MCP_MODE=hosted .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from server.supabase_repository import SupabaseRepository
repo = SupabaseRepository('this-key-does-not-exist')
print('plan for invalid key:', repo.plan)
print('key_is_valid:', repo.key_is_valid())
"
```

Expected: `plan for invalid key: None` (since `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_MCP_ROLE_JWT` are unset in this shell, `_verify_mcp_key` logs `supabase_not_configured` and returns `None`, so `_resolved` becomes `False` and `_plan` stays `None`). `key_is_valid: False`.

- [ ] **Step 7: Commit**

```bash
git add mcp-server/server/supabase_repository.py
git commit -m "Exponera plan-fält från verify_mcp_key i SupabaseRepository"
```

---

### Task 2: `_health_check_payload` helper and wiring in `mcp_server.py`

**Files:**
- Modify: `mcp-server/server/mcp_server.py` (near the existing `_healthz` function and `health_check()` tool, and the `_handle_mcp_message` dispatch)

**Interfaces:**
- Consumes: `SupabaseRepository.plan` (Task 1), `SupabaseRepository.key_is_valid()` (existing), `_supabase_repo_for_key(mcp_key: str) -> SupabaseRepository | None` (existing, defined near the top of `mcp_server.py`), `_WORKSPACE_STATUS_MESSAGES` dict (existing, defined near `_add_workspace_status`).
- Produces: `_health_check_payload(mcp_key: str = "") -> dict[str, Any]`, used by both the REST endpoint and the JSON-RPC dispatch.

- [ ] **Step 1: Locate the existing `health_check` tool and `_healthz` REST handler**

Run: `grep -n "def health_check\|async def _healthz\|tool_name == \"health_check\"" mcp-server/server/mcp_server.py`

Expected output shows three matches: the `@mcp.tool() def health_check()` definition, the `async def _healthz(_: Request)` definition, and the `if tool_name == "health_check":` branch inside `_handle_mcp_message`.

- [ ] **Step 2: Add the message lookup table and `_health_check_payload` helper**

Find the existing `@mcp.tool() def health_check()` block:

```python
@mcp.tool()
def health_check() -> dict[str, Any]:
    """Return lightweight service status without loading prompt text."""
    logger.info("tool_call name=health_check")
    return {
        "status": "ok",
        "service": "promptbanken-mcp",
        "version": SERVICE_VERSION,
        "mode": SERVER_MODE,
        "skills_count": len(repository.list_skills()),
    }
```

Replace it with:

```python
_HEALTH_CHECK_STATES = {
    "no_key": {
        "plan": "public",
        "catalog": "open",
        "message": (
            "Detta är den öppna katalogen. Autentisera med API/MCP-nyckel för "
            "användar- eller Pro-mallar på kommun.promptbanken.se."
        ),
    },
    "invalid_key": {
        "plan": "public",
        "catalog": "open",
        "message": _WORKSPACE_STATUS_MESSAGES["invalid_key"],
    },
    "free": {
        "plan": "free",
        "catalog": "workspace",
        "message": (
            "Inloggad med en free-nyckel. Publika mallar och dina egna sparade "
            "prompts är tillgängliga. Uppgradera till Pro för premium-mallar."
        ),
    },
    "pro": {
        "plan": "pro",
        "catalog": "pro",
        "message": (
            "Inloggad med en Pro-nyckel. Publika mallar, dina sparade prompts "
            "och premium-mallarna är tillgängliga."
        ),
    },
}


def _health_check_state(mcp_key: str) -> str:
    if not mcp_key:
        return "no_key"
    repo = _supabase_repo_for_key(mcp_key)
    if repo is None or not repo.key_is_valid():
        return "invalid_key"
    return "pro" if repo.plan == "pro" else "free"


def _health_check_payload(mcp_key: str = "") -> dict[str, Any]:
    state = _HEALTH_CHECK_STATES[_health_check_state(mcp_key)]
    return {
        "status": "ok",
        "service": "promptbanken-mcp",
        "version": SERVICE_VERSION,
        "mode": SERVER_MODE,
        "skills_count": len(repository.list_skills()),
        "catalog": state["catalog"],
        "plan": state["plan"],
        "message": state["message"],
    }


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Return lightweight service status without loading prompt text."""
    logger.info("tool_call name=health_check")
    return _health_check_payload()
```

- [ ] **Step 3: Update the REST `_healthz` handler to read the key**

Find:

```python
async def _healthz(_: Request) -> JSONResponse:
    logger.info("http_request path=/healthz status=200")
    return JSONResponse(
        {
            "status": "ok",
            "service": "promptbanken-mcp",
            "version": SERVICE_VERSION,
            "mode": SERVER_MODE,
            "skills_count": len(repository.list_skills()),
        }
    )
```

Replace with:

```python
async def _healthz(request: Request) -> JSONResponse:
    logger.info("http_request path=/healthz status=200")
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_health_check_payload(mcp_key))
```

- [ ] **Step 4: Update the JSON-RPC dispatch branch**

Find, inside `_handle_mcp_message`:

```python
        if tool_name == "health_check":
            return _json_rpc_result(request_id, _mcp_content_result(health_check()))
```

Replace with:

```python
        if tool_name == "health_check":
            return _json_rpc_result(request_id, _mcp_content_result(_health_check_payload(mcp_key)))
```

- [ ] **Step 5: Syntax-check the file**

Run: `python -c "import ast; ast.parse(open('mcp-server/server/mcp_server.py', encoding='utf-8').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Manual behavior check — no key**

Run:

```bash
cd mcp-server
PROMPTBANKEN_MCP_MODE=hosted .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from server import mcp_server
import json
print(json.dumps(mcp_server._health_check_payload(''), ensure_ascii=False))
"
```

Expected: JSON containing `"catalog": "open"`, `"plan": "public"`, and a `"message"` starting with `"Detta är den öppna katalogen."`.

- [ ] **Step 7: Manual behavior check — invalid key**

Run:

```bash
cd mcp-server
PROMPTBANKEN_MCP_MODE=hosted .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from server import mcp_server
import json
print(json.dumps(mcp_server._health_check_payload('not-a-real-key'), ensure_ascii=False))
"
```

Expected: `"catalog": "open"`, `"plan": "public"`, `"message"` identical to the string in `mcp_server._WORKSPACE_STATUS_MESSAGES["invalid_key"]` — verify with a second print statement in the same script: `print(mcp_server._WORKSPACE_STATUS_MESSAGES["invalid_key"] == mcp_server._health_check_payload('not-a-real-key')['message'])` should print `True`.

- [ ] **Step 8: Verify `no_key` vs `invalid_key` both map to the same catalog/plan but different message text**

Run:

```bash
cd mcp-server
PROMPTBANKEN_MCP_MODE=hosted .venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from server import mcp_server
a = mcp_server._health_check_payload('')
b = mcp_server._health_check_payload('not-a-real-key')
assert a['catalog'] == b['catalog'] == 'open'
assert a['plan'] == b['plan'] == 'public'
assert a['message'] != b['message']
print('OK')
"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add mcp-server/server/mcp_server.py
git commit -m "Lagg till catalog/plan/message i health_check baserat pa X-MCP-Key"
```

---

### Task 3: Documentation

**Files:**
- Modify: `README.md` (the "Workspace-skills från Supabase" section, near where `workspace_status`/`workspace_message` are documented, and near the `/healthz` example response)
- Modify: `CLAUDE.md` (the "Nyckelhantering per anrop" section)
- Modify: `TODO.md` (mark the item done, matching the style of the existing "Klart" section)

**Interfaces:**
- Consumes: nothing from Task 1/2 code — pure documentation, but must accurately describe the four states and field names implemented there (`catalog`, `plan`, `message`, values `public`/`free`/`pro` and `open`/`workspace`/`pro`).
- Produces: nothing consumed by other tasks — this is the last task.

- [ ] **Step 1: Update the `/healthz` example response in README.md**

Find:

```json
{
  "status": "ok",
  "service": "promptbanken-mcp",
  "version": "1.1.0",
  "mode": "hosted",
  "skills_count": 21
}
```

Replace with:

```json
{
  "status": "ok",
  "service": "promptbanken-mcp",
  "version": "1.1.0",
  "mode": "hosted",
  "skills_count": 21,
  "catalog": "open",
  "plan": "public",
  "message": "Detta är den öppna katalogen. Autentisera med API/MCP-nyckel för användar- eller Pro-mallar på kommun.promptbanken.se."
}
```

- [ ] **Step 2: Add a documentation paragraph in README.md near the existing `workspace_status` text**

Locate the paragraph that starts with `- \`list_skills_simple\` och REST-endpointen \`GET /api/v1/skills\` inkluderar då fälten` (added in a previous session) and add directly after it:

```markdown
- `GET /healthz` (och MCP-verktyget/JSON-RPC-metoden `health_check`) returnerar alltid `catalog`/`plan`/`message` baserat på samma nyckel: `plan` är `public`/`free`/`pro`, `catalog` är `open`/`workspace`/`pro`. Utan nyckel eller med en ogiltig/återkallad nyckel visas `public`/`open`. Till skillnad från `workspace_status` på `/api/v1/skills` utelämnas dessa fält aldrig — `health_check` ska alltid ge en fullständig bild av katalogläget.
```

- [ ] **Step 3: Update CLAUDE.md**

Locate the line in the "Nyckelhantering per anrop" section:

```markdown
`_mcp_key_from_request()` (`mcp_server.py`) läser `X-MCP-Key` först; saknas den provas `Authorization: Bearer <token>` som fallback (för klienter som ChatGPT som bara kan skicka en generisk Bearer-token). Matchar token den globala `PROMPTBANKEN_MCP_API_KEY` tolkas den INTE som workspace-nyckel — den skickas aldrig vidare som hash till Supabase.
```

Add directly after it:

```markdown
`health_check` (REST `/healthz` och MCP-verktyget) läser samma nyckel och svarar alltid med `catalog`/`plan`/`message` (`public`/`free`/`pro`, se README). Ingen extra Supabase-anrop görs om ingen nyckel skickas — `/healthz` utan nyckel (t.ex. Dockers healthcheck) är lika snabb som innan.
```

- [ ] **Step 4: Update TODO.md**

Find the `## Klart` section header and add a new first bullet directly below it:

```markdown
- [x] Lade till `catalog`/`plan`/`message`-fält i `health_check` (REST `/healthz` och MCP-verktyget) — visar `public`/`free`/`pro` baserat på `X-MCP-Key`/`Authorization`-nyckelns plan, alltid närvarande (inte utelämnat som `workspace_status`). Se `docs/superpowers/specs/2026-07-03-health-check-catalog-status-design.md` för designen.
```

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md TODO.md
git commit -m "Dokumentera catalog/plan/message-falt i health_check"
```

---

### Task 4: Deploy and live verification

**Files:** none (operational task, no code changes)

**Interfaces:**
- Consumes: the deployed VPS environment (`docker-compose`, Caddy) — no new environment variables required, reuses existing `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_MCP_ROLE_JWT`.
- Produces: nothing — this is the final verification step confirming Tasks 1-3 work in production.

- [ ] **Step 1: Push commits from Tasks 1-3**

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

- [ ] **Step 3: Verify no-key state**

```bash
curl -s http://127.0.0.1:8000/healthz
```

Expected: JSON with `"catalog":"open"`, `"plan":"public"`.

- [ ] **Step 4: Verify invalid-key state**

```bash
curl -s https://mcp.promptbanken.se/healthz -H "X-MCP-Key: definitely-not-a-real-key"
```

Expected: `"catalog":"open"`, `"plan":"public"`, message text matching the `invalid_key` string.

- [ ] **Step 5: Verify free/pro state with a real key (ask the user for a live test key, as done for the Pro-templates feature in this same session)**

```bash
curl -s https://mcp.promptbanken.se/healthz -H "X-MCP-Key: <riktig nyckel>"
```

Expected: `"catalog":"free"` or `"catalog":"pro"` matching the workspace's actual plan, and `"plan"` matching.

- [ ] **Step 6: Mark the TODO.md item's deploy status and commit if any wording changed**

If the manual verification above required no doc changes, this step is a no-op. If it did (e.g. correcting a state that behaved differently in production than expected), update `TODO.md`/README accordingly and commit with message `"Justera health_check-dokumentation efter produktionsverifiering"`.
