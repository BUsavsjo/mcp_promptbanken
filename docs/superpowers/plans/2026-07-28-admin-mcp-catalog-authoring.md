# Admin-MCP Catalog Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an AI client author, edit, and publish prompts/packages in the open Promptbanken catalog (`catalog_prompts`/`catalog_prompt_variants`/`catalog_packages`) through a new, strictly separate `/admin` MCP route on the hosted `mcp_promptbanken` server.

**Architecture:** The server holds Peter's platform_owner Supabase **refresh token** as a secret and exchanges it for short-lived access tokens, so the existing `auth.uid()`-gated catalog RPCs (already live, already used by `admin.js`) work completely unmodified. A dedicated bearer secret (`PROMPTBANKEN_ADMIN_KEY`) gates the new `/admin` route, fail-closed. Admin tools are dispatched through a hand-rolled JSON-RPC function that never touches the shared `@mcp.tool()`/FastMCP registry backing `/sse` — so they are structurally, not just by-allowlist, absent from every other surface.

**Tech Stack:** Python 3 (FastMCP/Starlette, `httpx`), PL/pgSQL (Supabase/Postgres), PowerShell contract-test runner.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md` (this repo). Every task below implements one section of it.
- Target tables: `catalog_prompts`/`catalog_prompt_variants`/`catalog_packages` family only. Never touch `pro_prompt_templates` (separate system, out of scope).
- `/admin` must refuse to serve any request if `PROMPTBANKEN_ADMIN_KEY` is unset (fail-closed) — unlike the existing optional `PROMPTBANKEN_MCP_API_KEY` pattern.
- All 8 new tools are named `admin_*` and must never appear in `tools/list` on `/mcp`, `/mcp/key`, or `/sse`.
- New Postgres functions follow the repo's existing pattern exactly: `app_private.<name>` holds the real logic + `security definer` + `set search_path = ''`; a thin `public.<name>` SQL wrapper (`set search_path = public, app_private, pg_temp`) is what gets granted to `authenticated`. See `supabase/migrations/20260721110000_catalog_prompt_rpcs.sql` in the `promptbanken` repo for the exact convention.
- Swedish error messages in all new SQL functions (matches every existing function in this codebase).
- Tests use `unittest`/`unittest.mock.patch`, matching `mcp-server/tests/test_vault.py` — no new test framework.

---

### Task 1: Supabase migration — metadata columns, parametric RPC params, publish gate, admin audit table

**Repo:** `promptbanken` (`C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\promptbanken`)

**Files:**
- Create: `supabase/migrations/20260728120000_admin_catalog_authoring.sql`

**Interfaces:**
- Produces (consumed by Task 3's `admin_catalog.py`): RPCs `upsert_catalog_prompt_variant` (extended signature), `upsert_catalog_package_variant` (extended signature), `publish_catalog_prompt` (tightened gate, same signature), `list_draft_catalog_prompts()`, `get_catalog_prompt_by_id(p_prompt_id uuid)`, `log_admin_write_attempt(p_tool text, p_target_id uuid, p_outcome text, p_detail jsonb default null)`.

- [ ] **Step 1: Write the migration file**

```sql
-- Admin-MCP katalogförfattande: metadata-kolumner, parametriska RPC-parametrar,
-- skärpt publiceringsspärr, samt en admin-audit-tabell.
-- Se docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md
-- i mcp_promptbanken-repot.

-- 1. Metadata-kolumner på catalog_prompt_variants (nullable -- krav vid
--    publicering hanteras i publish_catalog_prompt nedan, inte via NOT NULL,
--    så befintliga admin.js-anrop som inte sätter dem fortsätter fungera).
alter table public.catalog_prompt_variants
    add column if not exists risk_level text,
    add column if not exists area text,
    add column if not exists tags text[],
    add column if not exists output_format text;

-- 2. upsert_catalog_prompt_variant: lägg till parametrisk rendering +
--    metadata-parametrar. Signaturen ändras (nya obligatoriska positioner
--    för PostgREST-anrop med defaults) -- drop+recreate, samma mönster som
--    20260726184226_improve_catalog_prompt_quality.sql använde för
--    get_published_prompt.
drop function if exists public.upsert_catalog_prompt_variant(uuid, text, text, text, text, text, text, text, text, jsonb);
drop function if exists app_private.upsert_catalog_prompt_variant(uuid, text, text, text, text, text, text, text, text, jsonb);

create or replace function app_private.upsert_catalog_prompt_variant(
    p_prompt_id uuid,
    p_context_key text,
    p_title text,
    p_summary text,
    p_prompt_text text,
    p_example_input text default null,
    p_audience_label text default null,
    p_tone_hint text default null,
    p_context_notes text default null,
    p_suggested_variables jsonb default '{}'::jsonb,
    p_risk_level text default null,
    p_area text default null,
    p_tags text[] default null,
    p_output_format text default null,
    p_parameter_schema jsonb default null,
    p_default_bindings jsonb default '{}'::jsonb,
    p_binding_overrides jsonb default '[]'::jsonb
)
returns public.catalog_prompt_variants
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_variant public.catalog_prompt_variants;
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;

    if p_parameter_schema is not null and jsonb_typeof(p_parameter_schema) <> 'object' then
        raise exception 'parameter_schema måste vara ett jsonb-objekt.';
    end if;
    if jsonb_typeof(coalesce(p_default_bindings, '{}'::jsonb)) <> 'object' then
        raise exception 'default_bindings måste vara ett jsonb-objekt.';
    end if;
    if jsonb_typeof(coalesce(p_binding_overrides, '[]'::jsonb)) <> 'array' then
        raise exception 'binding_overrides måste vara en jsonb-array.';
    end if;

    insert into public.catalog_prompt_variants (
        prompt_id, context_key, title, summary, prompt_text, example_input,
        audience_label, tone_hint, context_notes, suggested_variables,
        risk_level, area, tags, output_format,
        parameter_schema, default_bindings, binding_overrides
    ) values (
        p_prompt_id, p_context_key, p_title, p_summary, p_prompt_text, p_example_input,
        p_audience_label, p_tone_hint, p_context_notes, coalesce(p_suggested_variables, '{}'::jsonb),
        p_risk_level, p_area, p_tags, p_output_format,
        p_parameter_schema, coalesce(p_default_bindings, '{}'::jsonb), coalesce(p_binding_overrides, '[]'::jsonb)
    )
    on conflict (prompt_id, context_key) do update
    set title = excluded.title,
        summary = excluded.summary,
        prompt_text = excluded.prompt_text,
        example_input = excluded.example_input,
        audience_label = excluded.audience_label,
        tone_hint = excluded.tone_hint,
        context_notes = excluded.context_notes,
        suggested_variables = excluded.suggested_variables,
        risk_level = excluded.risk_level,
        area = excluded.area,
        tags = excluded.tags,
        output_format = excluded.output_format,
        parameter_schema = excluded.parameter_schema,
        default_bindings = excluded.default_bindings,
        binding_overrides = excluded.binding_overrides
    returning * into v_variant;

    update public.catalog_prompts
       set updated_by = auth.uid()
     where id = p_prompt_id;

    return v_variant;
end;
$$;

create or replace function public.upsert_catalog_prompt_variant(
    p_prompt_id uuid,
    p_context_key text,
    p_title text,
    p_summary text,
    p_prompt_text text,
    p_example_input text default null,
    p_audience_label text default null,
    p_tone_hint text default null,
    p_context_notes text default null,
    p_suggested_variables jsonb default '{}'::jsonb,
    p_risk_level text default null,
    p_area text default null,
    p_tags text[] default null,
    p_output_format text default null,
    p_parameter_schema jsonb default null,
    p_default_bindings jsonb default '{}'::jsonb,
    p_binding_overrides jsonb default '[]'::jsonb
) returns public.catalog_prompt_variants
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
    select * from app_private.upsert_catalog_prompt_variant(
        p_prompt_id, p_context_key, p_title, p_summary, p_prompt_text,
        p_example_input, p_audience_label, p_tone_hint, p_context_notes, p_suggested_variables,
        p_risk_level, p_area, p_tags, p_output_format,
        p_parameter_schema, p_default_bindings, p_binding_overrides
    );
$$;

revoke all on function public.upsert_catalog_prompt_variant(
    uuid, text, text, text, text, text, text, text, text, jsonb,
    text, text, text[], text, jsonb, jsonb, jsonb
) from public;
grant execute on function public.upsert_catalog_prompt_variant(
    uuid, text, text, text, text, text, text, text, text, jsonb,
    text, text, text[], text, jsonb, jsonb, jsonb
) to authenticated;

-- 3. upsert_catalog_package_variant: samma parametriska tillägg (packages
--    fick parameter_schema/default_bindings/binding_overrides-kolumner i
--    20260725133000_catalog_parameter_schemas.sql men ingen RPC skriver dem).
drop function if exists public.upsert_catalog_package_variant(uuid, text, text, text, text, text);
drop function if exists app_private.upsert_catalog_package_variant(uuid, text, text, text, text, text);

create or replace function app_private.upsert_catalog_package_variant(
    p_package_id uuid,
    p_context_key text,
    p_title text,
    p_summary text,
    p_intro_text text default null,
    p_audience_label text default null,
    p_parameter_schema jsonb default null,
    p_default_bindings jsonb default '{}'::jsonb,
    p_binding_overrides jsonb default '[]'::jsonb
)
returns public.catalog_package_variants
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_variant public.catalog_package_variants;
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;

    if p_parameter_schema is not null and jsonb_typeof(p_parameter_schema) <> 'object' then
        raise exception 'parameter_schema måste vara ett jsonb-objekt.';
    end if;
    if jsonb_typeof(coalesce(p_default_bindings, '{}'::jsonb)) <> 'object' then
        raise exception 'default_bindings måste vara ett jsonb-objekt.';
    end if;
    if jsonb_typeof(coalesce(p_binding_overrides, '[]'::jsonb)) <> 'array' then
        raise exception 'binding_overrides måste vara en jsonb-array.';
    end if;

    insert into public.catalog_package_variants (
        package_id, context_key, title, summary, intro_text, audience_label,
        parameter_schema, default_bindings, binding_overrides
    ) values (
        p_package_id, p_context_key, p_title, p_summary, p_intro_text, p_audience_label,
        p_parameter_schema, coalesce(p_default_bindings, '{}'::jsonb), coalesce(p_binding_overrides, '[]'::jsonb)
    )
    on conflict (package_id, context_key) do update
    set title = excluded.title,
        summary = excluded.summary,
        intro_text = excluded.intro_text,
        audience_label = excluded.audience_label,
        parameter_schema = excluded.parameter_schema,
        default_bindings = excluded.default_bindings,
        binding_overrides = excluded.binding_overrides
    returning * into v_variant;

    update public.catalog_packages
       set updated_by = auth.uid()
     where id = p_package_id;

    return v_variant;
end;
$$;

create or replace function public.upsert_catalog_package_variant(
    p_package_id uuid,
    p_context_key text,
    p_title text,
    p_summary text,
    p_intro_text text default null,
    p_audience_label text default null,
    p_parameter_schema jsonb default null,
    p_default_bindings jsonb default '{}'::jsonb,
    p_binding_overrides jsonb default '[]'::jsonb
) returns public.catalog_package_variants
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
    select * from app_private.upsert_catalog_package_variant(
        p_package_id, p_context_key, p_title, p_summary, p_intro_text, p_audience_label,
        p_parameter_schema, p_default_bindings, p_binding_overrides
    );
$$;

revoke all on function public.upsert_catalog_package_variant(
    uuid, text, text, text, text, text, jsonb, jsonb, jsonb
) from public;
grant execute on function public.upsert_catalog_package_variant(
    uuid, text, text, text, text, text, jsonb, jsonb, jsonb
) to authenticated;

-- 4. Skärpt publiceringsspärr: kräv risk_level/area/tags/output_format på
--    generell-varianten, utöver den redan befintliga kravet att den finns.
create or replace function app_private.publish_catalog_prompt(p_prompt_id uuid)
returns public.catalog_prompts
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_prompt public.catalog_prompts;
    v_generell public.catalog_prompt_variants;
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;

    select * into v_generell
      from public.catalog_prompt_variants
     where prompt_id = p_prompt_id
       and context_key = 'generell';

    if not found then
        raise exception 'Prompten måste ha en generell variant innan publicering.';
    end if;

    if v_generell.risk_level is null or v_generell.area is null
       or v_generell.tags is null or v_generell.output_format is null then
        raise exception 'risk_level, area, tags och output_format måste vara satta innan publicering.';
    end if;

    update public.catalog_prompts
       set status = 'published',
           updated_by = auth.uid()
     where id = p_prompt_id
     returning * into v_prompt;

    return v_prompt;
end;
$$;

-- Signaturen är oförändrad (uuid) -- ingen ny grant behövs, public.publish_catalog_prompt
-- pekar redan mot app_private.publish_catalog_prompt.

-- 5. Nya read-RPC:er för admin-granskning (drafts syns idag ingenstans --
--    RLS på catalog_prompts har ingen policy, se 20260721160000_catalog_core_rls.sql,
--    så det finns ingen annan väg att läsa en draft än en ny security-definer-RPC).
create or replace function app_private.list_draft_catalog_prompts()
returns table (
    id uuid,
    slug text,
    status text,
    title text,
    summary text,
    risk_level text,
    area text,
    tags text[],
    output_format text,
    created_at timestamptz,
    updated_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan lista katalog-drafts.';
    end if;

    return query
    select cp.id, cp.slug, cp.status, v.title, v.summary,
           v.risk_level, v.area, v.tags, v.output_format,
           cp.created_at, cp.updated_at
      from public.catalog_prompts cp
      left join public.catalog_prompt_variants v
        on v.prompt_id = cp.id and v.context_key = 'generell'
     where cp.status = 'draft'
     order by cp.created_at desc;
end;
$$;

create or replace function public.list_draft_catalog_prompts()
returns table (
    id uuid, slug text, status text, title text, summary text,
    risk_level text, area text, tags text[], output_format text,
    created_at timestamptz, updated_at timestamptz
)
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
    select * from app_private.list_draft_catalog_prompts();
$$;

revoke all on function public.list_draft_catalog_prompts() from public;
grant execute on function public.list_draft_catalog_prompts() to authenticated;

create or replace function app_private.get_catalog_prompt_by_id(p_prompt_id uuid)
returns table (
    id uuid,
    slug text,
    status text,
    context_key text,
    title text,
    summary text,
    prompt_text text,
    risk_level text,
    area text,
    tags text[],
    output_format text,
    parameter_schema jsonb,
    default_bindings jsonb,
    binding_overrides jsonb
)
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan läsa en katalogprompt.';
    end if;

    return query
    select cp.id, cp.slug, cp.status, v.context_key, v.title, v.summary, v.prompt_text,
           v.risk_level, v.area, v.tags, v.output_format,
           v.parameter_schema, v.default_bindings, v.binding_overrides
      from public.catalog_prompts cp
      join public.catalog_prompt_variants v on v.prompt_id = cp.id
     where cp.id = p_prompt_id
     order by case when v.context_key = 'generell' then 0 else 1 end;
end;
$$;

create or replace function public.get_catalog_prompt_by_id(p_prompt_id uuid)
returns table (
    id uuid, slug text, status text, context_key text, title text, summary text, prompt_text text,
    risk_level text, area text, tags text[], output_format text,
    parameter_schema jsonb, default_bindings jsonb, binding_overrides jsonb
)
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
    select * from app_private.get_catalog_prompt_by_id(p_prompt_id);
$$;

revoke all on function public.get_catalog_prompt_by_id(uuid) from public;
grant execute on function public.get_catalog_prompt_by_id(uuid) to authenticated;

-- 6. Admin-audit: loggar VARJE admin-skrivning (inte bara avvisade, till
--    skillnad från mcp_write_attempts), egen tabell eftersom ett
--    komprometterat PROMPTBANKEN_ADMIN_KEY är en helt annan risknivå än en
--    enskild användarnyckel.
create table if not exists app_private.admin_write_attempts (
    id uuid primary key default gen_random_uuid(),
    tool text not null,
    target_id uuid,
    outcome text not null,
    detail jsonb,
    created_at timestamptz not null default now()
);

create or replace function app_private.log_admin_write_attempt(
    p_tool text,
    p_target_id uuid,
    p_outcome text,
    p_detail jsonb default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan logga admin-skrivningar.';
    end if;

    insert into app_private.admin_write_attempts (tool, target_id, outcome, detail)
    values (p_tool, p_target_id, p_outcome, p_detail);
end;
$$;

create or replace function public.log_admin_write_attempt(
    p_tool text,
    p_target_id uuid,
    p_outcome text,
    p_detail jsonb default null
)
returns void
language sql
security definer
set search_path = public, app_private, pg_temp
as $$
    select app_private.log_admin_write_attempt(p_tool, p_target_id, p_outcome, p_detail);
$$;

revoke all on function public.log_admin_write_attempt(text, uuid, text, jsonb) from public;
grant execute on function public.log_admin_write_attempt(text, uuid, text, jsonb) to authenticated;
```

- [ ] **Step 2: Apply the migration to the linked Supabase project**

```powershell
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\promptbanken"
supabase db push
```

Confirm the output lists `20260728120000_admin_catalog_authoring.sql` as applied, no errors.

- [ ] **Step 3: Verify in SQL editor / `execute_sql`**

```sql
select proname from pg_proc
 where pronamespace = 'app_private'::regnamespace
   and proname in (
     'upsert_catalog_prompt_variant', 'upsert_catalog_package_variant',
     'publish_catalog_prompt', 'list_draft_catalog_prompts',
     'get_catalog_prompt_by_id', 'log_admin_write_attempt'
   );
-- expect 6 rows

select column_name from information_schema.columns
 where table_schema = 'public' and table_name = 'catalog_prompt_variants'
   and column_name in ('risk_level', 'area', 'tags', 'output_format');
-- expect 4 rows
```

- [ ] **Step 4: Manual publish-gate smoke test (staging)**

Via SQL editor, logged in as the platform_owner test user (or `set local role` trick used elsewhere in this repo's tests):

```sql
select public.create_catalog_prompt('admin-plan-smoke-test', 'Smoke test', 'summary', 'prompt text');
-- note the returned id as :id
select public.upsert_catalog_prompt_variant(:id, 'generell', 'Smoke test', 'summary', 'prompt text');
select public.publish_catalog_prompt(:id);
-- expect: exception "risk_level, area, tags och output_format måste vara satta innan publicering."
select public.upsert_catalog_prompt_variant(
    :id, 'generell', 'Smoke test', 'summary', 'prompt text',
    null, null, null, null, '{}'::jsonb,
    'low', 'test', array['smoke'], 'text'
);
select public.publish_catalog_prompt(:id);
-- expect: success, status = 'published'
delete from public.catalog_prompts where id = :id; -- cleanup, cascades to variants
```

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\promptbanken"
git add supabase/migrations/20260728120000_admin_catalog_authoring.sql
git commit -m "feat(supabase): admin catalog authoring RPCs, metadata columns, publish gate, audit table"
```

---

### Task 2: Auth bridge — `admin_auth.py` + one-time bootstrap script

**Repo:** `mcp_promptbanken` (`C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken`)

**Files:**
- Create: `mcp-server/server/admin_auth.py`
- Create: `mcp-server/scripts/get-admin-refresh-token.py`
- Modify: `.gitignore` (add the token state file)
- Test: `mcp-server/tests/test_admin_auth.py`

**Interfaces:**
- Produces (consumed by Task 3): `admin_auth.is_configured() -> bool`, `admin_auth.get_access_token() -> str`, `admin_auth.AdminAuthNotConfigured` exception.
- Consumes: env vars `SUPABASE_URL`, `SUPABASE_ANON_KEY` (already used elsewhere), new `SUPABASE_ADMIN_REFRESH_TOKEN`.

- [ ] **Step 1: Write the failing test**

```python
# mcp-server/tests/test_admin_auth.py
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import admin_auth


class _TokenResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        admin_auth._cached_access_token = None
        admin_auth._cached_expires_at = 0.0
        admin_auth._cached_refresh_token = None

    @patch("server.admin_auth._ANON_KEY", "test-anon-key")
    @patch("server.admin_auth._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_auth._REFRESH_TOKEN", "seed-refresh-token")
    @patch("server.admin_auth._persist_refresh_token")
    @patch("server.admin_auth.httpx.post")
    def test_get_access_token_exchanges_and_caches(self, post, persist):
        post.return_value = _TokenResponse(
            {"access_token": "at-1", "expires_in": 3600, "refresh_token": "rt-2"}
        )

        token = admin_auth.get_access_token()

        self.assertEqual(token, "at-1")
        self.assertEqual(post.call_count, 1)
        persist.assert_called_once_with("rt-2")

        # Second call within the cache window must NOT re-exchange.
        token_again = admin_auth.get_access_token()
        self.assertEqual(token_again, "at-1")
        self.assertEqual(post.call_count, 1)

    @patch("server.admin_auth._ANON_KEY", "test-anon-key")
    @patch("server.admin_auth._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_auth._REFRESH_TOKEN", "seed-refresh-token")
    @patch("server.admin_auth._persist_refresh_token")
    @patch("server.admin_auth.httpx.post")
    def test_get_access_token_refreshes_after_expiry_buffer(self, post, persist):
        post.side_effect = [
            _TokenResponse({"access_token": "at-1", "expires_in": 61, "refresh_token": "rt-2"}),
            _TokenResponse({"access_token": "at-2", "expires_in": 3600, "refresh_token": "rt-3"}),
        ]

        first = admin_auth.get_access_token()
        # Simulate time passing past the 60s expiry buffer without sleeping.
        admin_auth._cached_expires_at = time.monotonic() - 1
        second = admin_auth.get_access_token()

        self.assertEqual(first, "at-1")
        self.assertEqual(second, "at-2")
        self.assertEqual(post.call_count, 2)

    @patch("server.admin_auth._ANON_KEY", "")
    @patch("server.admin_auth._SUPABASE_URL", "")
    @patch("server.admin_auth._REFRESH_TOKEN", "")
    def test_get_access_token_raises_when_not_configured(self):
        with self.assertRaises(admin_auth.AdminAuthNotConfigured):
            admin_auth.get_access_token()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
.venv\Scripts\python.exe -m unittest tests.test_admin_auth -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'server.admin_auth'`.

- [ ] **Step 3: Write `admin_auth.py`**

```python
# mcp-server/server/admin_auth.py
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
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_admin_auth -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Write the one-time bootstrap script**

```python
# mcp-server/scripts/get-admin-refresh-token.py
#!/usr/bin/env python3
"""One-time bootstrap: exchange the platform owner's Supabase email+password
for a refresh_token to store as SUPABASE_ADMIN_REFRESH_TOKEN on the VPS. Run
this locally once; never commit or log the printed output. See
docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md."""
from __future__ import annotations

import getpass
import os
import sys

import httpx


def main() -> int:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    email = input("Platform owner email: ").strip()
    password = getpass.getpass("Password: ")

    response = httpx.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    print("\nSUPABASE_ADMIN_REFRESH_TOKEN=" + payload["refresh_token"])
    print("\nStore this as a secret on the VPS (.env, never git). It is only ever shown here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Add the token state file to `.gitignore`**

Append to `.gitignore` (repo root):

```
mcp-server/.admin_refresh_token_state.json
```

- [ ] **Step 7: Commit**

```bash
git add mcp-server/server/admin_auth.py mcp-server/scripts/get-admin-refresh-token.py mcp-server/tests/test_admin_auth.py .gitignore
git commit -m "feat(mcp): add admin auth bridge (Supabase refresh-token exchange)"
```

---

### Task 3: `admin_catalog.py` — RPC calls, rate limit, audit logging

**Repo:** `mcp_promptbanken`

**Files:**
- Create: `mcp-server/server/admin_catalog.py`
- Test: `mcp-server/tests/test_admin_catalog.py`

**Interfaces:**
- Consumes: `admin_auth.get_access_token()` (Task 2).
- Produces (consumed by Task 4): `create_prompt`, `upsert_prompt_variant`, `publish_prompt`, `list_draft_prompts`, `get_prompt`, `create_package`, `add_prompt_to_package`, `publish_package`, exception `AdminRateLimitExceeded`.

- [ ] **Step 1: Write the failing test**

```python
# mcp-server/tests/test_admin_catalog.py
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import admin_catalog


class _JsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class AdminCatalogTests(unittest.TestCase):
    def setUp(self):
        admin_catalog._recent_calls.clear()

    @patch("server.admin_catalog._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_catalog._ANON_KEY", "test-anon-key")
    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_create_prompt_calls_rpc_and_logs_success(self, post, get_token):
        post.side_effect = [
            _JsonResponse({"id": "prompt-1", "slug": "test-slug"}),
            _JsonResponse(None, status_code=204),
        ]

        result = admin_catalog.create_prompt("test-slug", "Title", "Summary", "Prompt text")

        self.assertEqual(result["id"], "prompt-1")
        self.assertEqual(post.call_count, 2)
        first_call_url = post.call_args_list[0].args[0]
        second_call_url = post.call_args_list[1].args[0]
        self.assertIn("/rpc/create_catalog_prompt", first_call_url)
        self.assertIn("/rpc/log_admin_write_attempt", second_call_url)
        second_call_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(second_call_payload["p_outcome"], "success")

    @patch("server.admin_catalog._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_catalog._ANON_KEY", "test-anon-key")
    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_create_prompt_logs_rejection_and_reraises(self, post, get_token):
        failure = RuntimeError("RPC rejected")
        post.side_effect = [failure, _JsonResponse(None, status_code=204)]

        with self.assertRaises(RuntimeError):
            admin_catalog.create_prompt("test-slug", "Title", "Summary", "Prompt text")

        self.assertEqual(post.call_count, 2)
        second_call_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(second_call_payload["p_outcome"], "rejected")

    def test_publish_prompt_requires_explicit_confirm(self):
        with self.assertRaises(ValueError):
            admin_catalog.publish_prompt("prompt-1", confirm=False)

    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_rate_limit_blocks_after_max_calls(self, post, get_token):
        post.return_value = _JsonResponse(None, status_code=204)
        for _ in range(admin_catalog._RATE_LIMIT_MAX_CALLS):
            admin_catalog._check_rate_limit()

        with self.assertRaises(admin_catalog.AdminRateLimitExceeded):
            admin_catalog._check_rate_limit()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_admin_catalog -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'server.admin_catalog'`.

- [ ] **Step 3: Write `admin_catalog.py`**

```python
# mcp-server/server/admin_catalog.py
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
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_admin_catalog -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp-server/server/admin_catalog.py mcp-server/tests/test_admin_catalog.py
git commit -m "feat(mcp): add admin_catalog RPC layer with rate limit and audit logging"
```

---

### Task 4: `/admin` Starlette route + hand-rolled dispatch in `mcp_server.py`

**Repo:** `mcp_promptbanken`

**Files:**
- Modify: `mcp-server/server/mcp_server.py` (add imports, dispatch function, route handler, middleware, route registration)
- Test: `mcp-server/tests/test_admin_route.py`

**Interfaces:**
- Consumes: `admin_catalog.*` (Task 3), `admin_auth.AdminAuthNotConfigured` (Task 2).
- Produces: `_handle_admin_message(message: dict) -> dict | None`, `_admin_streamable_http(request) -> Response`, `Route("/admin", ...)` in the route list, `AdminBearerAuthMiddleware`.

- [ ] **Step 1: Write the failing test**

```python
# mcp-server/tests/test_admin_route.py
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import _handle_admin_message, _admin_tool_definitions


class AdminRouteTests(unittest.TestCase):
    def test_admin_tool_definitions_are_exactly_the_eight_admin_tools(self):
        names = {tool["name"] for tool in _admin_tool_definitions()}
        self.assertEqual(
            names,
            {
                "admin_create_prompt",
                "admin_upsert_prompt_variant",
                "admin_list_draft_prompts",
                "admin_get_prompt",
                "admin_publish_prompt",
                "admin_create_package",
                "admin_add_prompt_to_package",
                "admin_publish_package",
            },
        )

    def test_tools_list_returns_admin_tools(self):
        response = _handle_admin_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("admin_create_prompt", names)

    def test_unknown_tool_returns_json_rpc_error(self):
        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_templates", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], -32601)

    @patch("server.mcp_server.admin_catalog.create_prompt")
    def test_admin_create_prompt_dispatches_to_admin_catalog(self, create_prompt):
        create_prompt.return_value = {"id": "prompt-1"}

        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "admin_create_prompt",
                    "arguments": {
                        "slug": "test-slug",
                        "title": "Title",
                        "summary": "Summary",
                        "prompt_text": "Prompt text",
                    },
                },
            }
        )

        create_prompt.assert_called_once_with("test-slug", "Title", "Summary", "Prompt text")
        self.assertNotIn("error", response)

    def test_admin_publish_prompt_requires_confirm_argument(self):
        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "admin_publish_prompt", "arguments": {"prompt_id": "prompt-1"}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_admin_route -v
```

Expected: FAIL with `ImportError: cannot import name '_handle_admin_message'`.

- [ ] **Step 3: Add the import at the top of `mcp_server.py`**

Add near the other `from . import ...` lines (after line 23's `from . import catalog as _catalog`):

```python
from . import admin_auth
from . import admin_catalog
```

- [ ] **Step 4: Add the admin tool definitions and dispatch function**

Add this block just before `async def _mcp_http_response` (currently at line 2570), so it sits next to the existing dispatch it deliberately does NOT share code with:

```python
def _admin_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "admin_create_prompt",
            "description": "Create a new draft catalog prompt (status='draft') with its 'generell' variant in one call. Returns the new prompt's id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "prompt_text": {"type": "string"},
                },
                "required": ["slug", "title", "summary", "prompt_text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_upsert_prompt_variant",
            "description": "Add or edit one context variant (generell/skola/kommun/foretag/forening/privat) of an existing prompt. Editing an already-published prompt goes through this same tool.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "string"},
                    "context_key": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "prompt_text": {"type": "string"},
                    "risk_level": {"type": "string"},
                    "area": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "output_format": {"type": "string"},
                    "parameter_schema": {"type": "object"},
                    "default_bindings": {"type": "object"},
                    "binding_overrides": {"type": "array"},
                },
                "required": ["prompt_id", "context_key", "title", "summary", "prompt_text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_list_draft_prompts",
            "description": "List all draft (unpublished) catalog prompts for review.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "admin_get_prompt",
            "description": "Fetch one catalog prompt (any status) with all its context variants, by id.",
            "inputSchema": {
                "type": "object",
                "properties": {"prompt_id": {"type": "string"}},
                "required": ["prompt_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_publish_prompt",
            "description": "Publish a draft prompt. Requires confirm=true. Rejected unless the generell variant exists and risk_level/area/tags/output_format are all set.",
            "inputSchema": {
                "type": "object",
                "properties": {"prompt_id": {"type": "string"}, "confirm": {"type": "boolean"}},
                "required": ["prompt_id", "confirm"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_create_package",
            "description": "Create a new draft catalog package.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "package_type": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "intro_text": {"type": "string"},
                },
                "required": ["slug", "package_type", "title", "summary"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_add_prompt_to_package",
            "description": "Add an existing prompt to a draft package at a given sort position.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "package_id": {"type": "string"},
                    "prompt_id": {"type": "string"},
                    "sort_order": {"type": "integer"},
                },
                "required": ["package_id", "prompt_id", "sort_order"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_publish_package",
            "description": "Publish a draft package. Requires confirm=true. Rejected unless the generell variant exists, it has at least one prompt, and every prompt in it is already published.",
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string"}, "confirm": {"type": "boolean"}},
                "required": ["package_id", "confirm"],
                "additionalProperties": False,
            },
        },
    ]


def _handle_admin_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch for the /admin route ONLY. Deliberately does not share any
    code path with _handle_mcp_message (public/key_authenticated) or the
    @mcp.tool()/FastMCP registry backing /sse -- see the 2026-07-27
    render-contract spec for why a shared path is exactly the mistake being
    avoided here."""
    request_id = message.get("id")
    method = message.get("method")
    if method is None:
        return None
    if method == "initialize":
        return _json_rpc_result(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "promptbanken-admin", "version": SERVICE_VERSION},
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return _json_rpc_result(request_id, {})
    if method == "tools/list":
        return _json_rpc_result(request_id, {"tools": _admin_tool_definitions()})
    if method != "tools/call":
        return _json_rpc_error(request_id, -32601, "Method not found")

    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    tool_name = params.get("name")
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}

    try:
        if tool_name == "admin_create_prompt":
            for key in ("slug", "title", "summary", "prompt_text"):
                if not isinstance(arguments.get(key), str) or not arguments.get(key):
                    return _json_rpc_error(request_id, -32602, f"Invalid or missing '{key}'")
            result = admin_catalog.create_prompt(
                arguments["slug"], arguments["title"], arguments["summary"], arguments["prompt_text"]
            )
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_upsert_prompt_variant":
            for key in ("prompt_id", "context_key", "title", "summary", "prompt_text"):
                if not isinstance(arguments.get(key), str) or not arguments.get(key):
                    return _json_rpc_error(request_id, -32602, f"Invalid or missing '{key}'")
            result = admin_catalog.upsert_prompt_variant(
                arguments["prompt_id"],
                arguments["context_key"],
                arguments["title"],
                arguments["summary"],
                arguments["prompt_text"],
                risk_level=arguments.get("risk_level"),
                area=arguments.get("area"),
                tags=arguments.get("tags"),
                output_format=arguments.get("output_format"),
                parameter_schema=arguments.get("parameter_schema"),
                default_bindings=arguments.get("default_bindings"),
                binding_overrides=arguments.get("binding_overrides"),
            )
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_list_draft_prompts":
            return _json_rpc_result(request_id, _mcp_content_result(admin_catalog.list_draft_prompts()))

        if tool_name == "admin_get_prompt":
            prompt_id = arguments.get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id:
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'prompt_id'")
            return _json_rpc_result(request_id, _mcp_content_result(admin_catalog.get_prompt(prompt_id)))

        if tool_name == "admin_publish_prompt":
            prompt_id = arguments.get("prompt_id")
            confirm = arguments.get("confirm")
            if not isinstance(prompt_id, str) or not prompt_id or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'prompt_id'/'confirm'")
            result = admin_catalog.publish_prompt(prompt_id, confirm)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_create_package":
            for key in ("slug", "package_type", "title", "summary"):
                if not isinstance(arguments.get(key), str) or not arguments.get(key):
                    return _json_rpc_error(request_id, -32602, f"Invalid or missing '{key}'")
            result = admin_catalog.create_package(
                arguments["slug"],
                arguments["package_type"],
                arguments["title"],
                arguments["summary"],
                arguments.get("intro_text"),
            )
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_add_prompt_to_package":
            package_id = arguments.get("package_id")
            prompt_id = arguments.get("prompt_id")
            sort_order = arguments.get("sort_order")
            if (
                not isinstance(package_id, str) or not package_id
                or not isinstance(prompt_id, str) or not prompt_id
                or not isinstance(sort_order, int)
            ):
                return _json_rpc_error(request_id, -32602, "Invalid or missing package_id/prompt_id/sort_order")
            result = admin_catalog.add_prompt_to_package(package_id, prompt_id, sort_order)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_publish_package":
            package_id = arguments.get("package_id")
            confirm = arguments.get("confirm")
            if not isinstance(package_id, str) or not package_id or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'package_id'/'confirm'")
            result = admin_catalog.publish_package(package_id, confirm)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        return _json_rpc_error(request_id, -32601, "Tool not found")
    except ValueError as exc:
        return _json_rpc_error(request_id, -32602, str(exc))
    except admin_auth.AdminAuthNotConfigured as exc:
        return _json_rpc_error(request_id, -32000, str(exc))
    except admin_catalog.AdminRateLimitExceeded as exc:
        return _json_rpc_error(request_id, -32000, str(exc))
    except Exception as exc:
        logger.error("admin_tool_call_failed tool=%s error=%s", tool_name, exc)
        return _json_rpc_error(request_id, -32000, str(exc))


async def _admin_streamable_http(request: Request) -> Response:
    if request.method == "GET":
        return Response(status_code=405, headers={"Allow": "POST"})
    if request.method == "DELETE":
        return Response(status_code=405, headers={"Allow": "POST"})
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_json_rpc_error(None, -32700, "Parse error"), status_code=400)

    is_batch = isinstance(payload, list)
    messages = payload if is_batch else [payload]
    if not all(isinstance(message, dict) for message in messages):
        return JSONResponse(_json_rpc_error(None, -32600, "Invalid Request"), status_code=400)

    responses = [
        response for message in messages if (response := _handle_admin_message(message)) is not None
    ]
    logger.info("admin_request status=%s batch=%s", 200 if responses else 202, is_batch)
    if not responses:
        return Response(status_code=202)
    return JSONResponse(responses if is_batch else responses[0])
```

- [ ] **Step 5: Add the fail-closed admin auth middleware**

Add just after `class BearerAuthMiddleware` (currently ending at line 2654):

```python
def _admin_api_key() -> str:
    return os.getenv("PROMPTBANKEN_ADMIN_KEY", "")


class AdminBearerAuthMiddleware:
    """Fail-closed gate for /admin only. Unlike BearerAuthMiddleware (which
    is optional and guards the WHOLE server), this one is mandatory: if
    PROMPTBANKEN_ADMIN_KEY is unset, every request to /admin is rejected --
    the server never falls back to an open admin surface. This is the only
    thing standing between an arbitrary caller and platform-wide catalog
    writes, since the route always authorizes internally as platform_owner
    regardless of who's calling (see admin_auth)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/admin":
            await self.app(scope, receive, send)
            return

        token = _admin_api_key()
        headers = dict(scope.get("headers") or [])
        authorization = headers.get(b"authorization", b"").decode("utf-8")
        if not token or not hmac.compare_digest(authorization, f"Bearer {token}"):
            logger.warning("admin_auth_denied configured=%s", bool(token))
            response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
```

- [ ] **Step 6: Register the route and wrap it with the new middleware**

In the `routes=[...]` list (currently ending `Mount("/messages/", app=sse.handle_post_message),` around line 2774), add:

```python
            Route("/admin", endpoint=_admin_streamable_http, methods=["GET", "POST", "DELETE"]),
```

Change the app-wrapping line (currently `app = OriginValidationMiddleware(BearerAuthMiddleware(HostedMetadataGuardMiddleware(app)))`) to:

```python
    app = OriginValidationMiddleware(
        AdminBearerAuthMiddleware(BearerAuthMiddleware(HostedMetadataGuardMiddleware(app)))
    )
```

`HostedMetadataGuardMiddleware` already only inspects `{"/messages/", "/mcp", "/mcp/key"}` (line 2664) so `/admin` passes through it untouched -- correct, since that guard exists specifically for the read-only-in-hosted-mode surface, not for a legitimately-writing admin surface.

- [ ] **Step 7: Run test to verify it passes**

```powershell
.venv\Scripts\python.exe -m unittest tests.test_admin_route -v
```

Expected: PASS (5 tests).

- [ ] **Step 8: Run the full existing test suite to check for regressions**

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 9: Commit**

```bash
git add mcp-server/server/mcp_server.py mcp-server/tests/test_admin_route.py
git commit -m "feat(mcp): add fail-closed /admin route with isolated tool dispatch"
```

---

### Task 5: Contract-test admin profile

**Repo:** two locations — the global skill (`C:\Users\petwen\.claude\skills\promptbanken-mcp-contract-test`) and this repo's contract (`mcp_promptbanken/mcp-server/mcp-contract.json`).

**Files:**
- Modify: `C:\Users\petwen\.claude\skills\promptbanken-mcp-contract-test\scripts\test-mcp-contract.ps1`
- Modify: `mcp-server/mcp-contract.json`
- Modify: `C:\Users\petwen\.claude\skills\promptbanken-mcp-contract-test\SKILL.md`

**Interfaces:**
- Consumes: the running `/admin` route from Task 4 (tested against a local `npm run serve` instance; production run is manual, per the skill's existing "run public locally, run all after deploy" workflow).

- [ ] **Step 1: Add `admin_bearer` auth support to the contract-test script**

In `test-mcp-contract.ps1`, extend `Get-ProfileHeaders` (currently only handles `"none"`/`"workspace_key"`) to also handle a new auth type:

```powershell
function Get-ProfileHeaders {
    param([pscustomobject]$ProfileConfig)

    $headers = @{}
    $auth = $ProfileConfig.auth
    if ($null -eq $auth -or $auth.type -eq "none") {
        return $headers
    }
    if ($auth.type -eq "admin_bearer") {
        $adminKey = Get-EnvironmentValue $auth.keyEnv
        if ([string]::IsNullOrWhiteSpace($adminKey)) {
            return $null
        }
        $headers["Authorization"] = "Bearer $adminKey"
        return $headers
    }
    if ($auth.type -ne "workspace_key") {
        throw "Unsupported auth type '$($auth.type)'."
    }

    $workspaceKey = Get-EnvironmentValue $auth.keyEnv
    if ([string]::IsNullOrWhiteSpace($workspaceKey)) {
        return $null
    }

    $headers["X-MCP-Key"] = $workspaceKey
    $globalBearer = Get-EnvironmentValue $auth.globalBearerEnv
    if (-not [string]::IsNullOrWhiteSpace($globalBearer)) {
        $headers["Authorization"] = "Bearer $globalBearer"
    }
    return $headers
}
```

- [ ] **Step 2: Add a check that admin tools are unreachable without the key, and a 401-without-key check**

After the existing `foreach ($profileName in $Profile)` loop's blocked-calls section (around line 314-326), no change needed there -- the existing `blockedCalls` mechanism already handles "call a tool not in this profile's group and expect an error code". Add a new dedicated check block right before the `Test-Cors` call (around line 342), gated on a new optional profile field `expectUnauthorizedWithoutAuth`:

```powershell
        if ($profileConfig.expectUnauthorizedWithoutAuth -eq $true) {
            try {
                Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" `
                    -Body (@{ jsonrpc = "2.0"; id = "1"; method = "tools/list"; params = @{} } | ConvertTo-Json) `
                    -ErrorAction Stop | Out-Null
                Add-Check $checks $profileName "unauthorized-without-key" $false "expected 401, request succeeded"
            }
            catch {
                $statusCode = $_.Exception.Response.StatusCode.value__
                Add-Check $checks $profileName "unauthorized-without-key" ($statusCode -eq 401) "expected=401; actual=$statusCode"
            }
        }
```

- [ ] **Step 3: Add the `admin` profile to `mcp-contract.json`**

```json
    "admin": {
      "endpoint": "/admin",
      "groups": [
        "admin"
      ],
      "auth": {
        "type": "admin_bearer",
        "keyEnv": "PROMPTBANKEN_ADMIN_TEST_KEY"
      },
      "skipIfMissingAuth": true,
      "expectUnauthorizedWithoutAuth": true
    }
```

And add the tool group (alongside `public`/`vault`/`legacyAuthenticated`):

```json
    "admin": {
      "tools": [
        "admin_create_prompt",
        "admin_upsert_prompt_variant",
        "admin_list_draft_prompts",
        "admin_get_prompt",
        "admin_publish_prompt",
        "admin_create_package",
        "admin_add_prompt_to_package",
        "admin_publish_package"
      ]
    }
```

Also add a `blockedCalls` entry to the existing `public`, `free`, `pro`, and `sse` profiles asserting the admin tools are unreachable there, e.g. on `public`:

```json
      "blockedCalls": [
        {
          "tool": "list_my_items",
          "arguments": {},
          "expectErrorCode": -32601
        },
        {
          "tool": "admin_create_prompt",
          "arguments": { "slug": "x", "title": "x", "summary": "x", "prompt_text": "x" },
          "expectErrorCode": -32601
        }
      ],
```

(Same addition, with `expectIsError`/`expectTextContains` instead of `expectErrorCode`, on the `sse` profile's `blockedCalls`.)

- [ ] **Step 4: Document the new profile in `SKILL.md`**

Add a line to the "Run" section's "All profiles" example:

```
$env:PROMPTBANKEN_ADMIN_TEST_KEY = "<admin-route-bearer-key>"  # PROMPTBANKEN_ADMIN_KEY on the server
```

And a row to the top overview: "admin profile checks `/admin` is 401 without the key, and that none of the 8 `admin_*` tools ever appear on public/free/pro/sse."

- [ ] **Step 5: Run the public + admin profiles locally**

```powershell
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken\mcp-server"
.venv\Scripts\python.exe scripts\serve-http.js  # or however npm run serve is started locally
```

In a second terminal:

```powershell
$env:PROMPTBANKEN_ADMIN_TEST_KEY = "<local-test-value-matching-PROMPTBANKEN_ADMIN_KEY>"
& "$env:USERPROFILE\.claude\skills\promptbanken-mcp-contract-test\scripts\test-mcp-contract.ps1" `
  -Contract ".\mcp-contract.json" -BaseUrl "http://localhost:8000" -Profile public,admin
```

Expected: exit code `0`, `admin` profile shows `unauthorized-without-key` PASS plus `tools:list-exact` PASS for the 8 admin tools (this run intentionally has no valid admin key configured server-side yet, so `tools/list` with the key still returns the 8 tools per the dispatch, but any real write call would fail at the `admin_auth`/RPC layer until `SUPABASE_ADMIN_REFRESH_TOKEN` is set -- that's expected locally and fine for this check).

- [ ] **Step 6: Commit both locations separately**

```bash
cd "C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\mcp_promptbanken\mcp_promptbanken"
git add mcp-server/mcp-contract.json
git commit -m "test(mcp): add admin contract profile"
```

```powershell
cd "C:\Users\petwen\.claude\skills\promptbanken-mcp-contract-test"
git add scripts/test-mcp-contract.ps1 SKILL.md
git commit -m "feat: support admin_bearer auth and expectUnauthorizedWithoutAuth checks" 2>$null
```

(If this skill directory isn't a git repo, skip the second commit -- just confirm the files are saved.)

---

### Task 6: Repo docs

**Repo:** `mcp_promptbanken`

**Files:**
- Modify: `TODO.md`, `LOG.md`, `DECISIONS.md`, `CLAUDE.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Add a `TODO.md` entry under "Klart"**

```markdown
- [x] **Admin-MCP (2026-07-28):** ny `/admin`-route, fail-closed bakom `PROMPTBANKEN_ADMIN_KEY`, 8 `admin_*`-verktyg för katalogförfattande (create/upsert/publish prompt+package, list/get drafts), Supabase refresh-token-brygga (`admin_auth.py`), egen audit-tabell (`app_private.admin_write_attempts`). Se `docs/superpowers/specs/2026-07-28-admin-mcp-catalog-authoring-design.md` och `docs/superpowers/plans/2026-07-28-admin-mcp-catalog-authoring.md`.
```

- [ ] **Step 2: Add a `DECISIONS.md` entry**

```markdown
## Admin-MCP: JWT-brygga istället för ny nyckeltyp (2026-07-28)

Katalogens write-RPC:er (`create_catalog_prompt` m.fl., 2026-07-21) är redan
`auth.uid()`-gated för `platform_owner`. Istället för att bygga en parallell
MCP-nyckelmodell för admin, håller `/admin`-routen Peters riktiga Supabase
refresh_token som hemlighet och växlar in access-tokens per anrop --
RLS/RPC:er förblir helt oförändrade. Se spec/plan-filerna för fullständig
motivering.
```

- [ ] **Step 3: Add a `LOG.md` entry summarizing the session**

```markdown
## 2026-07-28 - Admin-MCP katalogförfattande (spec + plan)

Brainstormade och specade en ny `/admin`-MCP-route för AI-klient-driven
katalogförfattande. Nyckelfynd: två separata malldatabaser existerar
(`pro_prompt_templates` vs `catalog_prompts`-familjen) -- admin-MCP:t riktar
sig mot den senare, den MCP:n faktiskt serverar. Auth löstes via en riktig
Supabase-JWT-brygga (refresh token), inte en ny nyckeltyp. Se spec/plan.
```

- [ ] **Step 4: Update `CLAUDE.md`'s repo-layout section**

Add `admin_auth.py`, `admin_catalog.py` to the `mcp-server/server/` file list, and a one-line mention of `/admin` alongside the existing `/mcp`/`/sse`/`/api/v1/*` endpoint list.

- [ ] **Step 5: Commit**

```bash
git add TODO.md DECISIONS.md LOG.md CLAUDE.md
git commit -m "docs: log admin MCP catalog authoring work"
```

---

## Self-Review

**Spec coverage:** metadata columns (Task 1) / parametric RPC params (Task 1) / publish gate (Task 1) / audit table (Task 1) / JWT auth bridge (Task 2) / fail-closed `/admin` route (Task 4) / 8 `admin_*` tools (Task 4) / structural isolation from `/sse` (Task 4, by design — no `@mcp.tool()` used) / rate limit (Task 3) / contract-test admin profile (Task 5) / repo docs (Task 6) — all covered.

**Placeholder scan:** no TBD/TODO markers; every step has literal code or an exact command.

**Type consistency:** `admin_catalog.create_prompt(slug, title, summary, prompt_text)` signature matches both the test in Task 3 and the dispatch call in Task 4. `admin_auth.get_access_token()`/`is_configured()`/`AdminAuthNotConfigured` match between Tasks 2, 3, and 4. `_admin_tool_definitions()`/`_handle_admin_message()` names match between Task 4's implementation and its own test.
