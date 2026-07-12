# save_workspace_prompt (MCP write) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Pro-gated write tool `save_workspace_prompt` to the hosted `mcp_promptbanken` server (this repo, Docker on `mcp.promptbanken.se`), letting any MCP client (Claude, ChatGPT, Copilot) save a generalised, GDPR-checked prompt into the caller's personal Pro workspace.

**Architecture:** A new SECURITY DEFINER Supabase RPC (`app_private.save_prompt_for_key`, in the separate `promptbanken` repo's database) reuses the existing `enforce_content_access_model()` trigger unchanged by setting a transaction-local `request.jwt.claim.sub` before INSERT — no duplicated validation logic. The hosted server calls this RPC over `httpx` (same pattern as its existing read-side `pro_templates.py`), exposes it as an MCP tool + a first POST REST endpoint, and ports the previously-local-only `check_input_risk` tool so the full "generalise → check → approve → save" flow is possible against the public address.

**Tech Stack:** Supabase Postgres (plpgsql, SECURITY DEFINER), Python 3.12 (FastMCP, Starlette, httpx), Docker/docker-compose, Caddy reverse proxy. No automated tests in either repo — verification is manual (`ast.parse`, `python -c` scripts, `curl`).

**Spec:** `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md`

## Global Constraints

- **Two repos.** Database/migration work happens in `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken\supabase\migrations\`. MCP server/tool work happens in `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\`. Commit separately in each repo — they have independent git histories.
- **Pro-only.** `plan <> 'pro'` must be rejected by the RPC with a clear error, logged as `not_pro`. Free keys never write.
- **`visibility` is hardcoded to `'private'`** in the RPC — the client can never request `'workspace'`/`'public'` visibility through this tool.
- **`search_path` must be pinned** (`set search_path = public, app_private, pg_temp`) on the new RPC — this was the first hardening requirement the user called out, non-negotiable.
- **No automated test suite in either repo.** "Run the test" below always means: run a manual `python -c` script, a `curl` command, or a SQL query in the Supabase SQL Editor, and compare against the stated expected output.
- **Docs in Swedish** in both repos' README/CLAUDE.md, matching existing convention. Code comments only when WHY is non-obvious.
- **Never commit `.env` or raw keys.** Test Pro keys must be revoked after verification (existing convention, see `LOG.md` in this repo).
- **`hosted_guard.py`'s allowlist must stay in sync** with `_tool_definitions()`/the JSON-RPC dispatch in `mcp_server.py` — every new tool needs both a `tools/call` dispatch branch AND an `allowed_methods`/`allowed_tool_args` entry, or the guard will flag/block it depending on `PROMPTBANKEN_MCP_HOSTED_GUARD`.

---

### Task 1: Supabase migration — schema, log table, `save_prompt_for_key` RPC

**Files:**
- Create: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken\supabase\migrations\20260712100000_save_prompt_for_key.sql`
- Create: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken\supabase\tests\save_prompt_for_key.sql`

**Interfaces:**
- Consumes: existing tables `public.api_keys` (`key_hash`, `revoked_at`, `scopes`, `workspace_id`), `public.workspaces` (`id`, `plan`, `type`, `owner_user_id`, `max_prompts`, `mcp_enabled`, `status`), `public.content_items` (existing columns, see `20260612120000_initial_schema.sql:122-144`), existing trigger `app_private.enforce_content_access_model()` (unmodified), existing helper `app_private.slugify_candidate(p_name text, p_fallback_prefix text)` (defined in `20260703120000_create_pro_order.sql`).
- Produces: `app_private.save_prompt_for_key(p_key_hash text, p_title text, p_content text, p_category text, p_source text default 'manual', p_risk_check_passed boolean default false, p_idempotency_key uuid default null) returns public.content_items`, granted to `anon`. New columns `content_items.source text`, `content_items.idempotency_key uuid`. New table `app_private.mcp_write_attempts`. Consumed by Task 3 (`pro_templates.py`).

- [ ] **Step 1: Write the migration file**

```sql
-- C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken\supabase\migrations\20260712100000_save_prompt_for_key.sql
-- MCP write: "Spara detta som mall". Ny skrivväg för Pro-nycklar, gated och
-- loggad. Se docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md
-- i mcp_promptbanken-repot för fullständig design.

-- 1. Nya kolumner på content_items.
alter table public.content_items
    add column if not exists source text not null default 'manual'
        check (source in ('manual', 'chat_extraction'));

alter table public.content_items
    add column if not exists idempotency_key uuid;

create unique index if not exists content_items_idempotency_key_per_workspace
    on public.content_items (workspace_id, idempotency_key)
    where idempotency_key is not null;

-- 2. Loggtabell: dubblar som underlag för rate limiting och observability.
create table if not exists app_private.mcp_write_attempts (
    id bigint generated always as identity primary key,
    key_hash text not null,
    workspace_id uuid,
    outcome text not null,
    risk_check_passed boolean,
    created_at timestamptz not null default now()
);

create index if not exists mcp_write_attempts_key_hash_created_at
    on app_private.mcp_write_attempts (key_hash, created_at desc);

revoke all on table app_private.mcp_write_attempts from public;

-- 3. save_prompt_for_key: SECURITY DEFINER, nyckelhash-baserad (samma
--    förtroendemodell som get_pro_templates_for_mcp_key/get_workspace_prompts_for_key).
--    Passerar den befintliga enforce_content_access_model-triggern OFÖRÄNDRAD genom
--    att sätta auth.uid() via en transaktionslokal session-inställning.
create or replace function app_private.save_prompt_for_key(
    p_key_hash            text,
    p_title                text,
    p_content               text,
    p_category              text,
    p_source                 text default 'manual',
    p_risk_check_passed      boolean default false,
    p_idempotency_key         uuid default null
) returns public.content_items
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
declare
    v_key           public.api_keys%rowtype;
    v_workspace     public.workspaces%rowtype;
    v_recent_count  integer;
    v_existing      public.content_items%rowtype;
    v_candidate_slug text;
    v_suffix        integer := 0;
    v_row           public.content_items%rowtype;
begin
    -- 1. Nyckel giltig?
    select k.* into v_key
      from public.api_keys k
     where k.key_hash = p_key_hash
       and k.revoked_at is null
       and k.scopes @> array['mcp']::text[]
     limit 1;

    if not found then
        insert into app_private.mcp_write_attempts (key_hash, outcome, risk_check_passed)
        values (p_key_hash, 'invalid_key', p_risk_check_passed);
        raise exception 'Ogiltig eller aterkallad MCP-nyckel.';
    end if;

    select w.* into v_workspace
      from public.workspaces w
     where w.id = v_key.workspace_id
       and w.mcp_enabled = true
       and w.status = 'active';

    if not found then
        insert into app_private.mcp_write_attempts (key_hash, outcome, risk_check_passed)
        values (p_key_hash, 'invalid_key', p_risk_check_passed);
        raise exception 'Arbetsytan ar inte aktiv eller saknar MCP-atkomst.';
    end if;

    -- 2. Plan = pro?
    if v_workspace.type <> 'personal' or v_workspace.plan <> 'pro' then
        insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
        values (p_key_hash, v_workspace.id, 'not_pro', p_risk_check_passed);
        raise exception 'save_workspace_prompt kraver en Pro-nyckel pa en personlig arbetsyta.';
    end if;

    -- 3. Rate limit: max 10 forsok/60s for samma nyckel.
    select count(*) into v_recent_count
      from app_private.mcp_write_attempts
     where key_hash = p_key_hash
       and created_at > now() - interval '60 seconds';

    if v_recent_count >= 10 then
        insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
        values (p_key_hash, v_workspace.id, 'rate_limited', p_risk_check_passed);
        raise exception 'For manga skrivforsok senaste minuten. Forsok igen om en liten stund.';
    end if;

    -- 4. Innehallsvalidering.
    if trim(coalesce(p_title, '')) = '' or length(p_title) > 200
       or trim(coalesce(p_content, '')) = '' or length(p_content) > 20000
       or trim(coalesce(p_category, '')) = '' then
        insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
        values (p_key_hash, v_workspace.id, 'invalid_input', p_risk_check_passed);
        raise exception 'Ogiltig indata: title (1-200 tecken), content (1-20000 tecken) och category kravs.';
    end if;

    -- 5. Idempotens: samma nyckel i samma workspace -> returnera befintlig rad.
    if p_idempotency_key is not null then
        select * into v_existing
          from public.content_items
         where workspace_id = v_workspace.id
           and idempotency_key = p_idempotency_key;

        if found then
            insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
            values (p_key_hash, v_workspace.id, 'idempotent_hit', p_risk_check_passed);
            return v_existing;
        end if;
    end if;

    -- 6. Risk-check-flagga.
    if not p_risk_check_passed then
        insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
        values (p_key_hash, v_workspace.id, 'risk_check_not_passed', p_risk_check_passed);
        raise exception 'risk_check_passed maste vara true. Kor check_input_risk och lat anvandaren godkanna forst.';
    end if;

    -- 7. Slug + INSERT. Triggern enforce_content_access_model korer harifran
    --    (auth.uid() loses fran raden vi satter nedan) och kan fortfarande
    --    avvisa pa max_prompts-gransen -> loggas som limit_reached i exception-fallet.
    v_candidate_slug := app_private.slugify_candidate(p_title, 'mall');
    while exists (
        select 1 from public.content_items
         where workspace_id = v_workspace.id and slug = v_candidate_slug
    ) loop
        v_suffix := v_suffix + 1;
        v_candidate_slug := substr(app_private.slugify_candidate(p_title, 'mall'), 1, 110)
            || '-' || v_suffix::text;
    end loop;

    perform set_config('request.jwt.claim.sub', v_workspace.owner_user_id::text, true);

    begin
        insert into public.content_items (
            workspace_id, owner_user_id, type, title, slug, content,
            status, visibility, category, created_by, source, idempotency_key
        ) values (
            v_workspace.id, v_workspace.owner_user_id, 'prompt', p_title, v_candidate_slug, p_content,
            'draft', 'private', p_category, v_workspace.owner_user_id, p_source, p_idempotency_key
        )
        returning * into v_row;
    exception when others then
        insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
        values (p_key_hash, v_workspace.id, 'limit_reached', p_risk_check_passed);
        raise;
    end;

    -- 8. Lyckad skrivning.
    insert into app_private.mcp_write_attempts (key_hash, workspace_id, outcome, risk_check_passed)
    values (p_key_hash, v_workspace.id, 'success', p_risk_check_passed);

    return v_row;
end;
$$;

revoke all on function app_private.save_prompt_for_key(text, text, text, text, text, boolean, uuid) from public;
grant execute on function app_private.save_prompt_for_key(text, text, text, text, text, boolean, uuid) to anon;
```

- [ ] **Step 2: Write the verification script**

```sql
-- C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken\supabase\tests\save_prompt_for_key.sql
-- Kor mot staging. Ersatt <PRO_KEY_HASH> med sha256 av en riktig Pro-testnyckel,
-- <FREE_KEY_HASH> med sha256 av en Free-nyckel.

-- 1. Ogiltig nyckel -> exception 'Ogiltig eller aterkallad MCP-nyckel.'
select app_private.save_prompt_for_key(
    'not-a-real-hash', 'Test', 'Innehall', 'kommunikation', 'manual', true, null
);

-- 2. Free-nyckel -> exception 'save_workspace_prompt kraver en Pro-nyckel...'
select app_private.save_prompt_for_key(
    '<FREE_KEY_HASH>', 'Test', 'Innehall', 'kommunikation', 'manual', true, null
);

-- 3. Pro-nyckel, risk_check_passed=false -> exception 'risk_check_passed maste vara true...'
select app_private.save_prompt_for_key(
    '<PRO_KEY_HASH>', 'Test', 'Innehall', 'kommunikation', 'manual', false, null
);

-- 4. Pro-nyckel, tom title -> exception 'Ogiltig indata...'
select app_private.save_prompt_for_key(
    '<PRO_KEY_HASH>', '', 'Innehall', 'kommunikation', 'manual', true, null
);

-- 5. Pro-nyckel, giltigt anrop -> lyckas, returnerar en content_items-rad
--    med visibility='private', status='draft', source='manual'.
select * from app_private.save_prompt_for_key(
    '<PRO_KEY_HASH>', 'Mitt testmall', 'Testinnehall for verifiering.', 'kommunikation', 'manual', true, gen_random_uuid()
);

-- 6. Loggen ska nu innehalla rader for forsok 1-5.
select outcome, count(*) from app_private.mcp_write_attempts group by outcome order by outcome;
-- Expected: invalid_key=1, not_pro=1, risk_check_not_passed=1, invalid_input=1, success=1
```

- [ ] **Step 3: Apply and verify against staging**

Run the migration file in the Supabase SQL Editor against **staging** (never production directly). Then run `save_prompt_for_key.sql` with real staging Pro/Free key hashes substituted. Expected: exceptions 1-4 raise the exact messages shown in the comments; query 5 returns one row with `visibility = 'private'`, `status = 'draft'`, `source = 'manual'`; query 6 shows one row per outcome as listed.

- [ ] **Step 4: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken"
git add supabase/migrations/20260712100000_save_prompt_for_key.sql supabase/tests/save_prompt_for_key.sql
git commit -m "feat(db): add save_prompt_for_key RPC for MCP write (Pro-gated)"
```

---

### Task 2: Port `check_input_risk` into the hosted server

**Files:**
- Create: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\risk_checker.py`
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\mcp_server.py`

**Interfaces:**
- Produces: `RiskChecker` class with `.check(text: str) -> RiskCheck`, `RiskCheck.to_dict() -> dict[str, object]`. New MCP tool `check_input_risk(text: str) -> dict[str, object]`. Consumed by Task 5 (`hosted_guard.py` allowlist) and by clients as the mandatory pre-write step described in `save_workspace_prompt`'s tool description (Task 4).

- [ ] **Step 1: Copy `risk_checker.py` verbatim**

```python
# C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\risk_checker.py
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskCheck:
    allowed: bool
    warnings: list[str]
    recommended_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "warnings": self.warnings,
            "recommended_action": self.recommended_action,
        }


class RiskChecker:
    PATTERNS = {
        "personnummer": re.compile(r"\b(?:\d{6}|\d{8})[-+]?\d{4}\b"),
        "e-postadress": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
        "telefonnummer": re.compile(r"\b(?:\+46|0)\s?(?:\d[\s-]?){7,12}\b"),
        "arendenummer": re.compile(r"\b(?:dnr|diarie|arende|ärende)[\s:.-]*[A-Za-z0-9/-]{3,}\b", re.IGNORECASE),
    }

    def check(self, text: str) -> RiskCheck:
        warnings = [
            f"Texten verkar innehalla {label}."
            for label, pattern in self.PATTERNS.items()
            if pattern.search(text)
        ]
        return RiskCheck(
            allowed=True,
            warnings=warnings,
            recommended_action=(
                "Anonymisera eller generalisera markerade uppgifter innan prompten anvands."
                if warnings
                else "Ingen tydlig personuppgiftsrisk hittades med enkel regelkontroll."
            ),
        )
```

- [ ] **Step 2: Verify it's an exact copy**

Run:
```bash
diff "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\promptbanken\mcp-server\server\risk_checker.py" "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\risk_checker.py"
```
Expected: no output (files identical).

- [ ] **Step 3: Import and instantiate in `mcp_server.py`**

In `mcp_server.py`, find (around line 25):

```python
from .risk_checker import RiskChecker
```

This import does not exist yet in this file — add it next to the other relative imports at the top:

```python
from .hosted_guard import HostedMetadataGuard
from .pro_templates import list_pro_templates as _fetch_pro_templates
from .pro_templates import list_private_prompts as _fetch_private_prompts
from .pro_templates import list_shared_prompts as _fetch_shared_prompts
from .pro_templates import list_shared_workspaces as _fetch_shared_workspaces
from .risk_checker import RiskChecker
from .skill_repository import InvalidSkillIdError, SkillRepository
from .skill_router import SkillRouter
from .supabase_repository import SupabaseRepository
```

Then, right after the existing module-level instantiation block:

```python
repo_root = Path(__file__).resolve().parents[1]
repository = SkillRepository(repo_root=repo_root)
router = SkillRouter(repository=repository)
risk_checker = RiskChecker()
```

(`router = SkillRouter(repository=repository)` already exists — just add the `risk_checker = RiskChecker()` line directly below it.)

- [ ] **Step 4: Add the `@mcp.tool()`**

Add this after the existing `list_skills` tool definition (around line 152, before `_pro_templates_payload`):

```python
@mcp.tool()
def check_input_risk(text: str) -> dict[str, object]:
    """Check text for common personal-data patterns (personnummer, e-post,
    telefonnummer, arendenummer) before saving it as a template. Never blocks,
    only warns -- the calling model/user decides whether to edit or proceed."""
    logger.info("tool_call name=check_input_risk")
    return risk_checker.check(text).to_dict()
```

- [ ] **Step 5: Register in `_tool_definitions()`**

In `_tool_definitions()` (starts around line 734), add this entry to the returned list, right after the `"list_skills"` entry:

```python
{
    "name": "check_input_risk",
    "description": (
        "Check text for common personal-data patterns (personnummer, e-post, "
        "telefonnummer, arendenummer) before saving it as a template. Never blocks, "
        "only warns."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
},
```

- [ ] **Step 6: Register in `_handle_mcp_message`'s `tools/call` dispatch**

In `_handle_mcp_message` (around line 858), add this branch right after the `if tool_name == "list_skills":` block:

```python
if tool_name == "check_input_risk":
    text = arguments.get("text")
    if not isinstance(text, str):
        return _json_rpc_error(request_id, -32602, "Invalid check_input_risk arguments")
    return _json_rpc_result(request_id, _mcp_content_result(risk_checker.check(text).to_dict()))
```

- [ ] **Step 7: Syntax-check the files**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "import ast; ast.parse(open('server/risk_checker.py', encoding='utf-8').read()); print('OK')"
python -c "import ast; ast.parse(open('server/mcp_server.py', encoding='utf-8').read()); print('OK')"
```
Expected: `OK` twice.

- [ ] **Step 8: Manual behavior check**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "
import sys; sys.path.insert(0, '.')
from server.risk_checker import RiskChecker
result = RiskChecker().check('Kontakta mig pa 070-1234567 eller test@example.com')
print(result.to_dict())
"
```
Expected: `allowed=True`, `warnings` contains entries for `telefonnummer` and `e-postadress`, `recommended_action` starts with `Anonymisera eller generalisera`.

- [ ] **Step 9: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git add mcp-server/server/risk_checker.py mcp-server/server/mcp_server.py
git commit -m "feat(mcp): port check_input_risk from local server (needed for save_workspace_prompt flow)"
```

(Note: `hosted_guard.py` allowlist for `check_input_risk` is added together with `save_workspace_prompt`'s allowlist entries in Task 5, to keep guard changes in one reviewable commit.)

---

### Task 3: `pro_templates.py` — write client function

**Files:**
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\pro_templates.py`

**Interfaces:**
- Consumes: `app_private.save_prompt_for_key` (Task 1), module-level `_SUPABASE_URL`, `_ANON_KEY`, `_hash_key`, `is_configured` (all already exist in this file).
- Produces: `save_prompt(mcp_key: str, title: str, content: str, category: str, source: str = "manual", risk_check_passed: bool = False, idempotency_key: str | None = None) -> dict[str, Any]`. Raises `RuntimeError` on missing config, `httpx.HTTPStatusError` on RPC rejection. Consumed by Task 4 (`mcp_server.py`).

- [ ] **Step 1: Add the function**

Append to the end of `pro_templates.py` (after the existing `list_shared_workspaces` function):

```python
def save_prompt(
    mcp_key: str,
    title: str,
    content: str,
    category: str,
    source: str = "manual",
    risk_check_passed: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Skriver en ny prompt i nyckelns personliga Pro-arbetsyta via
    save_prompt_for_key (samma anon-beviljade förtroendemodell som
    get_pro_templates_for_mcp_key/get_workspace_prompts_for_key, se
    promptbanken/supabase/migrations/20260712100000_save_prompt_for_key.sql).

    Till skillnad från de övriga funktionerna i denna fil (som fångar alla
    fel och returnerar en tom lista) låter denna undantag propagera -- en
    tyst tom retur vid ett write-fel skulle dölja för klientmodellen att
    skrivningen faktiskt misslyckades.
    """
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY ar inte konfigurerat.")

    url = f"{_SUPABASE_URL}/rest/v1/rpc/save_prompt_for_key"
    payload = {
        "p_key_hash": _hash_key(mcp_key),
        "p_title": title,
        "p_content": content,
        "p_category": category,
        "p_source": source,
        "p_risk_check_passed": risk_check_passed,
        "p_idempotency_key": idempotency_key,
    }
    response = httpx.post(
        url,
        headers={
            "apikey": _ANON_KEY,
            "Authorization": f"Bearer {_ANON_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=5,
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 2: Syntax-check the file**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "import ast; ast.parse(open('server/pro_templates.py', encoding='utf-8').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Manual behavior check (no live Supabase needed)**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "
import sys; sys.path.insert(0, '.')
from server.pro_templates import save_prompt
try:
    save_prompt('', 'Test', 'Innehall', 'kommunikation')
except RuntimeError as exc:
    print('OK:', exc)
"
```
Expected: `OK: MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY ar inte konfigurerat.` (since `SUPABASE_URL`/`SUPABASE_ANON_KEY` are unset in this shell and `mcp_key` is empty).

- [ ] **Step 4: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git add mcp-server/server/pro_templates.py
git commit -m "feat(mcp): add save_prompt write client (calls save_prompt_for_key RPC)"
```

---

### Task 4: `mcp_server.py` — tool, dispatch, REST endpoint, route, openapi

**Files:**
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\mcp_server.py`

**Interfaces:**
- Consumes: `save_prompt` (Task 3), `_mcp_key_from_request` (existing, line 127), `_json_rpc_result`/`_json_rpc_error`/`_mcp_content_result` (existing), `_error` (existing, used elsewhere e.g. line 592), `logger` (existing).
- Produces: `_save_workspace_prompt_payload(mcp_key, title, content, category, source, risk_check_passed, idempotency_key) -> dict[str, Any]`, MCP tool `save_workspace_prompt`, REST `POST /api/v1/my-prompts`. Consumed by Task 5 (`hosted_guard.py`), Task 6 (smoke test), Task 8 (production verification).

- [ ] **Step 1: Add the import**

Near the top, next to the other `pro_templates` imports (around line 21-24):

```python
from .pro_templates import list_pro_templates as _fetch_pro_templates
from .pro_templates import list_private_prompts as _fetch_private_prompts
from .pro_templates import list_shared_prompts as _fetch_shared_prompts
from .pro_templates import list_shared_workspaces as _fetch_shared_workspaces
from .pro_templates import save_prompt as _save_prompt
```

Also add `import httpx` next to the existing `import anyio` / `import uvicorn` imports at the very top of the file (needed for the `httpx.HTTPStatusError` catch in Step 2):

```python
import anyio
import httpx
import uvicorn
```

- [ ] **Step 2: Add the payload helper**

Add this function right after `_pro_templates_payload` (around line 160), before the `list_skills` tool:

```python
def _save_workspace_prompt_payload(
    mcp_key: str,
    title: str,
    content: str,
    category: str,
    source: str,
    risk_check_passed: bool,
    idempotency_key: str | None,
) -> dict[str, Any]:
    if not mcp_key:
        return {"status": "error", "message": "MCP-nyckel kravs (X-MCP-Key eller Authorization)."}
    try:
        row = _save_prompt(mcp_key, title, content, category, source, risk_check_passed, idempotency_key)
        return {"status": "success", "prompt": row}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.info("tool_call name=save_workspace_prompt status=error detail=%s", detail)
        return {"status": "error", "message": detail}
    except RuntimeError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.error("save_workspace_prompt_failed error=%s", exc)
        return {"status": "error", "message": "Kunde inte spara prompten."}
```

- [ ] **Step 3: Add the `@mcp.tool()`**

Add this after the `list_shared_workspace_prompts` tool (end of the existing tool block, around line 122-123, before `if __name__ == "__main__":`):

```python
@mcp.tool()
def save_workspace_prompt(
    title: str,
    content: str,
    category: str,
    source: str = "manual",
    risk_check_passed: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Save a generalised, already GDPR-checked template into the caller's
    personal Pro workspace. IMPORTANT for the calling model: generalise the
    content (remove names/personal numbers/org-specific details) and run
    check_input_risk on the generated template BEFORE calling this tool. Show
    the proposal to the user and wait for explicit approval before calling.
    Set risk_check_passed=true only after the approved check -- calls with
    risk_check_passed=false are rejected. Generate your own idempotency_key
    (UUID) per approval so a retry after a timeout never creates a duplicate.
    Suggested categories (optional, not enforced): kommunikation,
    forandringsledning, processer, beslutsberedning, visuellt, ledarskap,
    arbetsbank. Requires a Pro key (X-MCP-Key/Authorization); free keys are
    rejected."""
    logger.info("tool_call name=save_workspace_prompt")
    return _save_workspace_prompt_payload(
        "", title, content, category, source, risk_check_passed, idempotency_key
    )
```

- [ ] **Step 4: Register in `_tool_definitions()`**

Add this entry at the end of the list returned by `_tool_definitions()` (after the `"list_shared_workspace_prompts"` entry, around line 813):

```python
{
    "name": "save_workspace_prompt",
    "description": (
        "Save a generalised, already GDPR-checked template into the caller's "
        "personal Pro workspace. Requires a Pro key. See the tool description "
        "for the required approval + risk-check flow."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "category": {"type": "string"},
            "source": {"type": "string", "default": "manual"},
            "risk_check_passed": {"type": "boolean", "default": False},
            "idempotency_key": {"type": "string"},
        },
        "required": ["title", "content", "category"],
        "additionalProperties": False,
    },
},
```

- [ ] **Step 5: Register in `_handle_mcp_message`'s `tools/call` dispatch**

Add this branch right after the `list_shared_workspace_prompts` branch (around line 900, before `return _json_rpc_error(request_id, -32601, "Tool not found")`):

```python
if tool_name == "save_workspace_prompt":
    title = arguments.get("title")
    content = arguments.get("content")
    category = arguments.get("category")
    source = arguments.get("source", "manual")
    risk_check_passed = arguments.get("risk_check_passed", False)
    idempotency_key = arguments.get("idempotency_key")
    if not all(isinstance(v, str) and v for v in (title, content, category)):
        return _json_rpc_error(request_id, -32602, "Invalid save_workspace_prompt arguments")
    if not isinstance(risk_check_passed, bool):
        return _json_rpc_error(request_id, -32602, "risk_check_passed must be a boolean")
    return _json_rpc_result(
        request_id,
        _mcp_content_result(
            _save_workspace_prompt_payload(
                mcp_key, title, content, category, source, risk_check_passed, idempotency_key
            )
        ),
    )
```

- [ ] **Step 6: Add the REST endpoint**

Add this function right after `_api_shared_workspace_prompts` (around line 651-652):

```python
async def _api_save_workspace_prompt(request: Request) -> JSONResponse:
    mcp_key = _mcp_key_from_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_error("INVALID_JSON", "Request body must be JSON"), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_error("INVALID_BODY", "Request body must be a JSON object"), status_code=400)
    title, content, category = body.get("title"), body.get("content"), body.get("category")
    if not all(isinstance(v, str) and v for v in (title, content, category)):
        return JSONResponse(
            _error("INVALID_ARGUMENTS", "title, content and category are required strings"), status_code=400
        )
    payload = _save_workspace_prompt_payload(
        mcp_key,
        title,
        content,
        category,
        body.get("source", "manual"),
        bool(body.get("risk_check_passed", False)),
        body.get("idempotency_key"),
    )
    status_code = 200 if payload.get("status") == "success" else 400
    logger.info("http_request path=/api/v1/my-prompts method=POST status=%s", status_code)
    return JSONResponse(payload, status_code=status_code)
```

- [ ] **Step 7: Register the route**

In the `Starlette(routes=[...])` list (around line 1057), the existing GET route for `/api/v1/my-prompts` has no explicit `methods=` — add one for clarity, and add the new POST route directly below it:

```python
Route("/api/v1/my-prompts", endpoint=_api_my_prompts, methods=["GET"]),
Route("/api/v1/my-prompts", endpoint=_api_save_workspace_prompt, methods=["POST"]),
```

(Replace the existing single-line `Route("/api/v1/my-prompts", endpoint=_api_my_prompts),` with these two lines. Starlette matches on path AND method, so this is not a collision.)

- [ ] **Step 8: Add the OpenAPI schema entry**

In `_openapi_schema()` (around line 654), add a `"post"` key to the existing `/api/v1/my-prompts` path entry. Find:

```python
            "/api/v1/my-prompts": {
                "get": {
                    "summary": "List only the caller's own saved prompts (requires a valid MCP key)",
                    "responses": {"200": {"description": "OK"}},
                }
            },
```

Replace with:

```python
            "/api/v1/my-prompts": {
                "get": {
                    "summary": "List only the caller's own saved prompts (requires a valid MCP key)",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "Save a new prompt into the caller's personal Pro workspace (requires a Pro MCP key)",
                    "responses": {"200": {"description": "Saved"}, "400": {"description": "Rejected"}},
                },
            },
```

- [ ] **Step 9: Syntax-check the file**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "import ast; ast.parse(open('server/mcp_server.py', encoding='utf-8').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 10: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git add mcp-server/server/mcp_server.py
git commit -m "feat(mcp): add save_workspace_prompt tool, POST /api/v1/my-prompts"
```

---

### Task 5: `hosted_guard.py` — allowlist for `save_workspace_prompt` and `check_input_risk`

**Files:**
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\server\hosted_guard.py`

**Interfaces:**
- Consumes: nothing new (works purely on tool name/argument dicts already passed to it by `mcp_server.py`).
- Produces: updated `HostedMetadataGuard.allowed_methods`, `.allowed_tool_args`, and a new branch in `.inspect_tool_args`. Used by `HostedMetadataGuardMiddleware` (already wraps the app, see `mcp_server.py:1066`).

- [ ] **Step 1: Add both tool names to `allowed_methods`**

In `__init__`, find:

```python
            "list_pro_templates",
            "list_my_prompts",
            "list_my_private_prompts",
            "list_my_shared_workspaces",
            "list_shared_workspace_prompts",
        }
```

Replace with:

```python
            "list_pro_templates",
            "list_my_prompts",
            "list_my_private_prompts",
            "list_my_shared_workspaces",
            "list_shared_workspace_prompts",
            "check_input_risk",
            "save_workspace_prompt",
        }
```

- [ ] **Step 2: Add both tools to `allowed_tool_args`**

Find:

```python
            "list_shared_workspace_prompts": {"workspace_id"},
            "get_skill": {"skill_id", "include_prompt"},
        }
```

Replace with:

```python
            "list_shared_workspace_prompts": {"workspace_id"},
            "get_skill": {"skill_id", "include_prompt"},
            "check_input_risk": {"text"},
            "save_workspace_prompt": {
                "title", "content", "category", "source", "risk_check_passed", "idempotency_key"
            },
        }
```

- [ ] **Step 3: Add argument validation branches in `inspect_tool_args`**

Find the existing `elif` chain:

```python
        elif tool_name == "list_shared_workspace_prompts":
            workspace_id = arguments.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id:
                return {"reason": "invalid_workspace_id", "method": method, "tool": tool_name, "id": request_id}
        elif arguments:
            return {"reason": "unexpected_arguments", "method": method, "tool": tool_name, "id": request_id}
        return None
```

Replace with:

```python
        elif tool_name == "list_shared_workspace_prompts":
            workspace_id = arguments.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id:
                return {"reason": "invalid_workspace_id", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "check_input_risk":
            text = arguments.get("text")
            if not isinstance(text, str):
                return {"reason": "invalid_text", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "save_workspace_prompt":
            title = arguments.get("title")
            content = arguments.get("content")
            category = arguments.get("category")
            if not all(isinstance(v, str) and v for v in (title, content, category)):
                return {"reason": "invalid_save_arguments", "method": method, "tool": tool_name, "id": request_id}
            risk_check_passed = arguments.get("risk_check_passed")
            if risk_check_passed is not None and not isinstance(risk_check_passed, bool):
                return {"reason": "invalid_risk_check_passed", "method": method, "tool": tool_name, "id": request_id}
        elif arguments:
            return {"reason": "unexpected_arguments", "method": method, "tool": tool_name, "id": request_id}
        return None
```

- [ ] **Step 4: Syntax-check the file**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "import ast; ast.parse(open('server/hosted_guard.py', encoding='utf-8').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Manual behavior check**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
python -c "
import sys; sys.path.insert(0, '.')
from server.hosted_guard import HostedMetadataGuard
from server.skill_repository import SkillRepository
from pathlib import Path
repo = SkillRepository(repo_root=Path('.').resolve())
guard = HostedMetadataGuard(repo)

# Valid call -> None (no warning)
print(guard.inspect_tool_args('save_workspace_prompt', {'title': 'T', 'content': 'C', 'category': 'kommunikation'}, 'save_workspace_prompt', 1))

# Missing category -> warning
print(guard.inspect_tool_args('save_workspace_prompt', {'title': 'T', 'content': 'C'}, 'save_workspace_prompt', 2))

# Unexpected extra argument -> warning
print(guard.inspect_tool_args('save_workspace_prompt', {'title': 'T', 'content': 'C', 'category': 'K', 'visibility': 'public'}, 'save_workspace_prompt', 3))

# check_input_risk valid -> None
print(guard.inspect_tool_args('check_input_risk', {'text': 'hej'}, 'check_input_risk', 4))
"
```
Expected: `None`, then a dict with `'reason': 'invalid_save_arguments'`, then a dict with `'reason': 'unexpected_arguments'`, then `None`.

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git add mcp-server/server/hosted_guard.py
git commit -m "feat(guard): allowlist save_workspace_prompt and check_input_risk"
```

---

### Task 6: Local smoke test — stdio server + `tools/list`

**Files:** none created/modified (verification-only task).

**Interfaces:**
- Consumes: everything from Tasks 2-5 (fully wired MCP server).
- Produces: confidence that the server starts and lists the two new tools before touching staging/production.

- [ ] **Step 1: Run the setup script if `.venv` doesn't exist**

Run:
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
npm run setup:python
```
Expected: completes without error (skips if `.venv` already has the right packages).

- [ ] **Step 2: Start the server locally in hosted mode**

Run (background, needs to be stopped after the check):
```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
npm run serve
```
Expected: log line `http_server_start host=0.0.0.0 port=8000 mode=hosted hosted_guard=warn` (or `block`, depending on `PROMPTBANKEN_MCP_HOSTED_GUARD`), no tracebacks on startup (confirms `risk_checker.py`/`pro_templates.py`/`mcp_server.py`/`hosted_guard.py` all import cleanly together).

- [ ] **Step 3: Check `/healthz` and `tools/list`**

In a second terminal:
```bash
curl -s http://127.0.0.1:8000/healthz
curl -s -X POST http://127.0.0.1:8000/mcp -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}"
```
Expected: `/healthz` returns `"status":"ok"` with `"catalog":"open","plan":"public"` (no key sent). The `tools/list` response's `result.tools` array contains entries named `save_workspace_prompt` and `check_input_risk` alongside the existing tools.

- [ ] **Step 4: Stop the local server**

Stop the process started in Step 2 (Ctrl+C in that terminal, or close the background shell).

- [ ] **Step 5: No commit** — this task is verification-only, nothing to commit.

---

### Task 7: Apply migration to staging Supabase and re-verify

**Files:** none (operational task).

**Interfaces:**
- Consumes: `20260712100000_save_prompt_for_key.sql` + `save_prompt_for_key.sql` test script (Task 1).
- Produces: a confirmed-working RPC on staging, ready for the hosted server to call against in Task 8's production step.

- [ ] **Step 1: Apply the migration to staging**

Open the Supabase SQL Editor for the **staging** project, paste and run `20260712100000_save_prompt_for_key.sql` in full.
Expected: no errors; `select * from app_private.mcp_write_attempts limit 1;` returns zero rows (table exists, empty).

- [ ] **Step 2: Get or create a staging Pro test key**

If a live Pro test key from prior sessions still exists, reuse it (check `LOG.md` in this repo for the note that the last one was revoked — if so, create a fresh one via the `promptbanken` staging admin UI: log in, upgrade to Pro on a test account, generate an MCP key under "Integrationer").

- [ ] **Step 3: Run the verification script from Task 1 with the real key hash**

Compute the hash and run the queries from `save_prompt_for_key.sql` (Task 1, Step 2) against staging, substituting `<PRO_KEY_HASH>` with `sha256(<raw key>)` (Python one-liner: `python -c "import hashlib; print(hashlib.sha256(b'<raw key>').hexdigest())"`).
Expected: same results as documented in Task 1 Step 3.

- [ ] **Step 4: Revoke the test key**

Revoke the staging test key immediately after verification (same convention as prior sessions — never leave a live-looking key lying around, even on staging).

- [ ] **Step 5: No commit** — this task is operational-only.

---

### Task 8: Build, deploy, and verify in production

**Files:** none (operational task).

**Interfaces:**
- Consumes: the full feature from Tasks 1-5, staging-verified in Task 7.
- Produces: `save_workspace_prompt` live and working on `https://mcp.promptbanken.se`.

- [ ] **Step 1: Apply the migration to production Supabase**

Only after Task 7 is fully green. Run `20260712100000_save_prompt_for_key.sql` against the **production** Supabase project via the SQL Editor.
Expected: no errors.

- [ ] **Step 2: Push commits and pull on the VPS**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git push origin main
```
Then on the VPS (`/home/wenstrompeter/mcp_promptbanken`):
```bash
git pull origin main
```

- [ ] **Step 3: Rebuild and restart the container**

On the VPS (see `TODO.md`/`CLAUDE.md` for the known `docker-compose` 1.29.2 `'ContainerConfig'` recreate bug — if it recurs, `docker rm -f` the stale container before retrying):
```bash
docker-compose up -d --build
docker-compose ps
docker-compose logs -f --tail=50 promptbanken-mcp
```
Expected: `docker-compose ps` shows the service `Up`; logs show `http_server_start ... mode=hosted` with no tracebacks.

- [ ] **Step 4: Create (or reuse) a production Pro test key**

Same as Task 7 Step 2, but against the production `promptbanken` site. Note the raw key value only long enough to hash it and run the next step — never store it anywhere persistent.

- [ ] **Step 5: Verify no-key and invalid-key rejection in production**

```bash
curl -s -X POST https://mcp.promptbanken.se/mcp -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"save_workspace_prompt\",\"arguments\":{\"title\":\"T\",\"content\":\"C\",\"category\":\"kommunikation\",\"risk_check_passed\":true}}}"
```
Expected (no `X-MCP-Key` header sent): JSON-RPC result whose `content[0].text` decodes to `{"status": "error", "message": "MCP-nyckel kravs (X-MCP-Key eller Authorization)."}`.

- [ ] **Step 6: Verify the full flow with the real Pro key**

```bash
curl -s -X POST https://mcp.promptbanken.se/api/v1/my-prompts -H "X-MCP-Key: <riktig Pro-nyckel>" -H "Content-Type: application/json" -d "{\"title\":\"Produktionstest\",\"content\":\"Testinnehall for produktionsverifiering.\",\"category\":\"kommunikation\",\"risk_check_passed\":true,\"idempotency_key\":\"11111111-1111-1111-1111-111111111111\"}"
```
Expected: HTTP 200, JSON body `{"status": "success", "prompt": {...}}` with `visibility: "private"`, `status: "draft"`, `source: "manual"`.

- [ ] **Step 7: Verify idempotency in production**

Re-run the exact same `curl` command from Step 6 (same `idempotency_key`).
Expected: HTTP 200, same `id` in the returned `prompt` object as Step 6 — no duplicate row created.

- [ ] **Step 8: Verify the row is visible in the web admin UI**

Log into `admin.html` on the production `promptbanken` site with the account that owns the test Pro key. Check "Mina prompts".
Expected: the row titled "Produktionstest" appears there, identical in behavior to a web-created prompt (editable, deletable).

- [ ] **Step 9: Clean up test data and revoke the key**

Delete the "Produktionstest" row via `admin.html`, then revoke the production test key.

- [ ] **Step 10: No commit** — this task is operational-only (already committed in Tasks 1-5).

---

### Task 9: Documentation — README, CLAUDE.md, DECISIONS.md, TODO.md, LOG.md

**Files:**
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server\README.md`
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\CLAUDE.md`
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\PROJECT.md`
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\DECISIONS.md`
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\TODO.md`
- Modify: `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\LOG.md`

**Interfaces:** none — pure documentation, last task.

- [ ] **Step 1: `README.md` — document the new endpoint and tool**

In the `## HTTP-endpoints` section (around line 105-114), find the `GET /api/v1/routing-instructions` line and add directly after it:

```
POST /api/v1/my-prompts             # Pro-gated write: save a new prompt (see save_workspace_prompt tool)
```

In the `## Tools` section (around line 194), add two entries following the existing style: `check_input_risk(text)` — never blocks, only warns; `save_workspace_prompt(title, content, category, source, risk_check_passed, idempotency_key)` — Pro-gated write, requires `risk_check_passed=true`.

- [ ] **Step 2: `CLAUDE.md` — document the write path**

In the "### Kontextstyrda Pro-verktyg" section, add a new subsection directly after it:

```markdown
### Write: `save_workspace_prompt` (2026-07-12)

Första write-verktyget i den hostade servern — se "Beslut: medveten omprövning
av read-only-gränsen" i `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md`.
Pro-gated (avvisar Free-nycklar), skriver alltid `visibility='private'`,
`status='draft'` i användarens personliga arbetsyta. Kräver `risk_check_passed=true`
(satt av klientmodellen efter ett `check_input_risk`-anrop och användarens
uttryckliga godkännande — servern kan inte tekniskt verifiera detta, se specen).
RPC:n (`app_private.save_prompt_for_key`, i `promptbanken`-repot) loggar varje
försök i `app_private.mcp_write_attempts` (rate limit + observability, ingen
prompttext lagras i loggen). Ny REST-endpoint: `POST /api/v1/my-prompts`.
```

Also update the `## Endpoints` list to mark the new method:

```
GET/POST /api/v1/my-prompts                                # GET: lista; POST: spara ny (Pro-gated)
```

- [ ] **Step 3: `PROJECT.md` — update the scope statement**

Find:

```
## Avgränsning
Projektet ska inte köra någon AI-modell, spara användarinput eller fungera som ett stort projektnav.
```

Replace with:

```
## Avgränsning
Projektet ska inte köra någon AI-modell eller fungera som ett stort projektnav. Servern var till 2026-07-12 helt read-only; den har sedan dess ett enda, smalt write-undantag (`save_workspace_prompt`, Pro-gated, se DECISIONS.md) för att spara en redan klientgenererad och GDPR-granskad mall — den tar fortfarande aldrig emot eller sparar rå användarchatt.
```

- [ ] **Step 4: `DECISIONS.md` — record the decision**

Add a new entry at the top of the file (most recent first, matching existing convention), dated 2026-07-12:

```markdown
## 2026-07-12 - Smalt, Pro-gated write-undantag från read-only-gränsen

### Beslut
Servern fick sitt första write-verktyg, `save_workspace_prompt`, trots den
tidigare uttalade "servern är read-only"-gränsen i `PROJECT.md`/`CLAUDE.md`.

### Skäl
Användaren vill kunna säga "spara det här som en mall" i valfri MCP-klient
(Claude, ChatGPT, Copilot) mot den publikt nåbara adressen, inte bara från en
lokalt körande stdio-process. Verktyget är avsiktligt smalt: bara en enda
skrivväg, bara Pro-nycklar, `visibility` hårdkodad till privat, och innehållet
är avsett att redan vara klientgeneraliserat (namn/personnummer borttaget)
innan det når servern — se `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md`.

### Konsekvens
Servern är inte längre strikt metadata-only. Framtida write-tools måste
motivera samma smala, loggade, Pro-gated mönster explicit — detta beslut är
inte en generell öppning för godtycklig skrivning.
```

- [ ] **Step 5: `TODO.md` — mark done**

Add to the `## Klart` section:

```markdown
- [x] `save_workspace_prompt` (MCP write, Pro-gated) — ny RPC `app_private.save_prompt_for_key` i `promptbanken`-repot, ny REST-endpoint `POST /api/v1/my-prompts`, portade `check_input_risk` hit från lokala servern. Se `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md` och `DECISIONS.md`. 2026-07-12.
```

- [ ] **Step 6: `LOG.md` — add today's entry**

Add a new dated section at the top of the file:

```markdown
## 2026-07-12

### Gjort
- Designade och byggde `save_workspace_prompt`: första write-verktyget i den hostade servern, Pro-gated, se `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md` och plan `docs/superpowers/plans/2026-07-12-save-workspace-prompt-write.md`.
- Ny RPC `app_private.save_prompt_for_key` i `promptbanken`-repot: pinnad `search_path`, rate limit + observability via `app_private.mcp_write_attempts`, idempotens via `idempotency_key`, innehållsvalidering, återanvänder `enforce_content_access_model`-triggern oförändrad via en transaktionslokal `auth.uid()`-koppling.
- Porterade `check_input_risk` från lokala `promptbanken/mcp-server/` hit — behövdes för att "generalisera → check → godkänn → spara"-flödet ska fungera mot den publika adressen.
- Ny REST-endpoint `POST /api/v1/my-prompts`, första POST-endpointen i detta repo.
- Uppdaterade `hosted_guard.py`s allowlist för de två nya verktygen.
- Verifierat end-to-end mot både staging och produktion med en dedikerad Pro-testnyckel (revoked efter test).

### Nästa steg
- Ingen kvarstående punkt för detta arbetspass. Framtida: delning till `shared_workspace_addons` via write, semantisk dubblettdetektering, `search_path`-uppstädning på de äldre läs-RPC:erna — se speccens "Uttryckligen utanför scope v1".
```

- [ ] **Step 7: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git add mcp-server/README.md CLAUDE.md PROJECT.md DECISIONS.md TODO.md LOG.md
git commit -m "docs: document save_workspace_prompt write path and decision"
```

---

## Self-Review

**Spec coverage:**
- RPC-design (search_path, förtroendeväxling, slug, valideringsordning) → Task 1 ✓
- Säkerhet (search_path, rate limiting, innehållsvalidering) → Task 1 ✓
- Idempotens → Task 1 (RPC), Task 4 (tool param) ✓
- Risk-check-parameter → Task 1 (RPC gate), Task 2 (ported tool), Task 4 (tool description + dispatch) ✓
- Loggning/observability → Task 1 (`mcp_write_attempts`) ✓
- Reversibilitet/rollback → dokumenterad i specen, ingen kodtask (medvetet manuellt, se spec) — inte en task, korrekt eftersom det bara är en beredskaps-SQL-snutt, inget att bygga i förväg.
- Kategorisering (förslagslista) → Task 4 (tool description) ✓
- Kodändringar: migration → Task 1; check_input_risk-portning → Task 2; pro_templates.py → Task 3; mcp_server.py (tool/dispatch/REST/route/openapi) → Task 4; hosted_guard.py → Task 5 ✓
- Testplan (punkt 1-15 i specen) → Task 1 (1-2 delvis), Task 6 (lokal smoke), Task 7 (staging), Task 8 (produktion) ✓
- "Beslut: medveten omprövning" → Task 9 (DECISIONS.md) ✓

**Placeholder scan:** alla kodsteg innehåller fullständig, körbar kod (ingen `...`/TBD). Task 9's dokumentationstillägg är kompletta textstycken, inte platshållare.

**Type consistency:** `save_prompt_for_key(p_key_hash, p_title, p_content, p_category, p_source, p_risk_check_passed, p_idempotency_key)` (Task 1, SQL) matchar parameterordningen i `save_prompt(mcp_key, title, content, category, source, risk_check_passed, idempotency_key)` (Task 3, Python) matchar `_save_workspace_prompt_payload(mcp_key, title, content, category, source, risk_check_passed, idempotency_key)` (Task 4) matchar `save_workspace_prompt(title, content, category, source, risk_check_passed, idempotency_key)`-verktygets signatur (Task 4) och REST-bodyns fältnamn (Task 4, Step 6). `hosted_guard.py`s `allowed_tool_args["save_workspace_prompt"]` (Task 5) innehåller exakt samma argumentnamn.

## Beroendeordning

Task 1 (DB) och Task 2 (risk_checker-portning) är oberoende av varandra, kan göras parallellt. Task 3 kräver Task 1 (RPC måste finnas för att testas mot staging, men kan skrivas/syntax-checkas innan). Task 4 kräver Task 2 + Task 3. Task 5 kräver Task 4 (och Task 2 för `check_input_risk`-delen). Task 6 kräver Task 2-5. Task 7 kräver Task 1 + Task 6 (bör vara lokalt grönt innan staging). Task 8 kräver Task 7 grönt. Task 9 kan göras när som helst efter Task 8, men bör vara sist så dokumentationen beskriver verifierad, inte planerad, funktionalitet.
