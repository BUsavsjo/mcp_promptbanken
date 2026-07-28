# Catalog Version History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin-MCP an undo path — every UPDATE/DELETE on the four `catalog_*` tables is captured automatically, and two new admin-MCP tool pairs let a platform-owner list and restore a prior version of a prompt or package.

**Architecture:** A generic `app_private.catalog_history` table plus one trigger function (`app_private.record_catalog_history()`) mounted `before update or delete` on `catalog_prompts`, `catalog_prompt_variants`, `catalog_packages`, `catalog_package_items`. Four new platform-owner-gated RPCs (list/restore × prompt/package) read that table and upsert a chosen snapshot back into the live table. Four new admin-MCP tools wire those RPCs into `mcp_promptbanken`.

**Tech Stack:** PostgreSQL/PL-pgSQL (Supabase migration, `promptbanken` repo), Python 3.12 (`mcp_promptbanken` repo, `mcp-server/server/admin_catalog.py` + `mcp_server.py`), `unittest` for tests.

## Global Constraints

- Every new RPC must gate on `app_private.current_user_is_platform_owner()`, raising `'Endast plattformsägare kan redigera katalogen.'` on failure — exact wording matches all existing admin RPCs (spec: "Restore RPCs").
- `admin_restore_prompt_version`/`admin_restore_package_version` require `p_confirm = true`, mirroring `delete_draft_catalog_prompt`'s gate (spec: "Restore RPCs" step 1).
- `catalog_history` is never granted directly to `anon`/`authenticated` — only the four wrapper RPCs are (spec: "Schema").
- A single restore call restores exactly one history row; no auto-restore-everything (spec: "Scope decision: one row at a time").
- Admin tool count goes from 12 to 16 (spec: "MCP tool wiring").

---

### Task 1: `catalog_history` table and trigger function

**Files:**
- Create: `supabase/migrations/20260729130000_catalog_history_table_and_trigger.sql`

**Interfaces:**
- Produces: table `app_private.catalog_history(id, table_name, row_id, operation, row_data, changed_at, changed_by)`; function `app_private.record_catalog_history() returns trigger`; triggers named `catalog_prompts_history`, `catalog_prompt_variants_history`, `catalog_packages_history`, `catalog_package_items_history`.

- [ ] **Step 1: Write the migration file**

```sql
-- app_private.catalog_history: generic before-update/delete snapshot table,
-- captured by a single trigger function mounted on all four catalog_* tables.
-- See docs/superpowers/specs/2026-07-29-catalog-version-history-design.md.

create table app_private.catalog_history (
    id bigserial primary key,
    table_name text not null,
    row_id uuid not null,
    operation text not null,
    row_data jsonb not null,
    changed_at timestamptz not null default now(),
    changed_by uuid
);

create index catalog_history_table_row_idx
    on app_private.catalog_history (table_name, row_id, changed_at desc);

create function app_private.record_catalog_history()
returns trigger
language plpgsql
security definer
set search_path to ''
as $$
begin
    insert into app_private.catalog_history (table_name, row_id, operation, row_data, changed_by)
    values (tg_table_name, old.id, lower(tg_op), to_jsonb(old), auth.uid());
    return old;
end;
$$;

create trigger catalog_prompts_history
    before update or delete on public.catalog_prompts
    for each row execute function app_private.record_catalog_history();

create trigger catalog_prompt_variants_history
    before update or delete on public.catalog_prompt_variants
    for each row execute function app_private.record_catalog_history();

create trigger catalog_packages_history
    before update or delete on public.catalog_packages
    for each row execute function app_private.record_catalog_history();

create trigger catalog_package_items_history
    before update or delete on public.catalog_package_items
    for each row execute function app_private.record_catalog_history();
```

- [ ] **Step 2: Apply the migration to production via the Supabase MCP tool**

Use `mcp__supabase__apply_migration` with `name: "catalog_history_table_and_trigger"` and the exact SQL from Step 1 as `query`. This project has no local Supabase stack — migrations are applied directly, matching how every prior migration this session was applied.

- [ ] **Step 3: Verify the trigger fires on UPDATE**

Run via `mcp__supabase__execute_sql`:

```sql
update catalog_prompt_variants
   set summary = summary
 where id = (select id from catalog_prompt_variants limit 1)
returning id;
```

Then:

```sql
select table_name, operation, row_data->>'summary' as summary, changed_at
  from app_private.catalog_history
 order by changed_at desc
 limit 1;
```

Expected: one row, `table_name = 'catalog_prompt_variants'`, `operation = 'update'`.

- [ ] **Step 4: Verify cascade delete is captured**

Create a disposable throwaway prompt and delete it to confirm the variant's history row appears too (cascade fires real per-row deletes internally):

```sql
insert into catalog_prompts (slug, status) values ('history-test-throwaway', 'draft') returning id;
-- note the returned id as :test_prompt_id
insert into catalog_prompt_variants (prompt_id, context_key, title, summary, prompt_text)
values (:test_prompt_id, 'generell', 'Throwaway', 'Throwaway', 'Throwaway text') returning id;
delete from catalog_prompts where id = :test_prompt_id;

select table_name, operation, row_id from app_private.catalog_history
 where row_id = :test_prompt_id
    or row_data->>'prompt_id' = :test_prompt_id::text
 order by changed_at desc;
```

Expected: two rows — one `table_name = 'catalog_prompts'`, one `table_name = 'catalog_prompt_variants'`, both `operation = 'delete'`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260729130000_catalog_history_table_and_trigger.sql
git commit -m "feat(supabase): generic catalog_history table + trigger for admin-MCP undo"
```

---

### Task 2: Restore RPCs for prompts

**Files:**
- Create: `supabase/migrations/20260729131500_catalog_history_restore_rpcs.sql` (this task writes the prompt half; Task 3 appends the package half to the same file)

**Interfaces:**
- Consumes: `app_private.catalog_history` (Task 1), `app_private.current_user_is_platform_owner()` (existing, from `20260721150000_catalog_write_rpc_authorization.sql`).
- Produces: `public.admin_list_prompt_history(p_prompt_id uuid) returns setof jsonb`, `public.admin_restore_prompt_version(p_history_id bigint, p_confirm boolean) returns jsonb`.

- [ ] **Step 1: Write the list/restore functions for prompts**

```sql
create function app_private.list_prompt_history(p_prompt_id uuid)
returns table(
    history_id bigint,
    table_name text,
    operation text,
    changed_at timestamptz,
    summary jsonb
)
language plpgsql
security definer
set search_path to ''
as $$
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;

    return query
    select h.id, h.table_name, h.operation, h.changed_at,
           jsonb_build_object(
               'title', h.row_data->>'title',
               'context_key', h.row_data->>'context_key'
           )
      from app_private.catalog_history h
     where (h.table_name = 'catalog_prompts' and h.row_id = p_prompt_id)
        or (h.table_name = 'catalog_prompt_variants' and h.row_data->>'prompt_id' = p_prompt_id::text)
     order by h.changed_at desc;
end;
$$;

create function public.admin_list_prompt_history(p_prompt_id uuid)
returns setof app_private.list_prompt_history
language sql
security definer
set search_path to 'public', 'app_private', 'pg_temp'
as $$
    select * from app_private.list_prompt_history(p_prompt_id);
$$;

grant execute on function public.admin_list_prompt_history(uuid) to anon, authenticated, service_role;


create function app_private.restore_prompt_version(p_history_id bigint, p_confirm boolean)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
    v_history app_private.catalog_history;
    v_parent_exists boolean;
    v_restored jsonb;
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;
    if p_confirm is not true then
        raise exception 'confirm måste vara true för att återställa en version.';
    end if;

    select * into v_history from app_private.catalog_history where id = p_history_id;
    if not found then
        raise exception 'Ingen historikpost hittades med id %', p_history_id;
    end if;
    if v_history.table_name not in ('catalog_prompts', 'catalog_prompt_variants') then
        raise exception 'Historikpost % tillhör inte en prompt (table_name=%).', p_history_id, v_history.table_name;
    end if;

    if v_history.table_name = 'catalog_prompt_variants' then
        select exists(
            select 1 from public.catalog_prompts
             where id = (v_history.row_data->>'prompt_id')::uuid
        ) into v_parent_exists;
        if not v_parent_exists then
            raise exception 'Prompten som varianten hör till finns inte längre -- återställ prompten (catalog_prompts-historikposten) först.';
        end if;

        insert into public.catalog_prompt_variants (
            id, prompt_id, context_key, title, summary, prompt_text, example_input,
            audience_label, tone_hint, context_notes, suggested_variables,
            parameter_schema, default_bindings, binding_overrides,
            risk_level, area, tags, output_format
        )
        select
            (v_history.row_data->>'id')::uuid,
            (v_history.row_data->>'prompt_id')::uuid,
            v_history.row_data->>'context_key',
            v_history.row_data->>'title',
            v_history.row_data->>'summary',
            v_history.row_data->>'prompt_text',
            v_history.row_data->>'example_input',
            v_history.row_data->>'audience_label',
            v_history.row_data->>'tone_hint',
            v_history.row_data->>'context_notes',
            v_history.row_data->'suggested_variables',
            v_history.row_data->'parameter_schema',
            coalesce(v_history.row_data->'default_bindings', '{}'::jsonb),
            coalesce(v_history.row_data->'binding_overrides', '[]'::jsonb),
            v_history.row_data->>'risk_level',
            v_history.row_data->>'area',
            case when v_history.row_data ? 'tags'
                 then array(select jsonb_array_elements_text(v_history.row_data->'tags'))
                 else null end,
            v_history.row_data->>'output_format'
        on conflict (id) do update set
            context_key = excluded.context_key,
            title = excluded.title,
            summary = excluded.summary,
            prompt_text = excluded.prompt_text,
            example_input = excluded.example_input,
            audience_label = excluded.audience_label,
            tone_hint = excluded.tone_hint,
            context_notes = excluded.context_notes,
            suggested_variables = excluded.suggested_variables,
            parameter_schema = excluded.parameter_schema,
            default_bindings = excluded.default_bindings,
            binding_overrides = excluded.binding_overrides,
            risk_level = excluded.risk_level,
            area = excluded.area,
            tags = excluded.tags,
            output_format = excluded.output_format
        returning to_jsonb(catalog_prompt_variants.*) into v_restored;
    else
        insert into public.catalog_prompts (id, slug, status, icon_key, image_key, color_theme, updated_by)
        select
            (v_history.row_data->>'id')::uuid,
            v_history.row_data->>'slug',
            v_history.row_data->>'status',
            v_history.row_data->>'icon_key',
            v_history.row_data->>'image_key',
            v_history.row_data->>'color_theme',
            auth.uid()
        on conflict (id) do update set
            slug = excluded.slug,
            status = excluded.status,
            icon_key = excluded.icon_key,
            image_key = excluded.image_key,
            color_theme = excluded.color_theme,
            updated_by = excluded.updated_by
        returning to_jsonb(catalog_prompts.*) into v_restored;
    end if;

    return v_restored;
end;
$$;

create function public.admin_restore_prompt_version(p_history_id bigint, p_confirm boolean)
returns jsonb
language sql
security definer
set search_path to 'public', 'app_private', 'pg_temp'
as $$
    select app_private.restore_prompt_version(p_history_id, p_confirm);
$$;

grant execute on function public.admin_restore_prompt_version(bigint, boolean) to anon, authenticated, service_role;
```

Note: `catalog_prompts.slug` has a unique constraint — if the slug was reused by a different prompt after the original was deleted, the restore's `on conflict (id) do update` still succeeds (conflict target is `id`, not `slug`), but a *separate* unique-violation on `slug` is possible and will surface as a Postgres error naturally; no special handling needed beyond letting it propagate, same as every other write RPC in this codebase.

- [ ] **Step 2: Apply the migration**

Use `mcp__supabase__apply_migration` with `name: "catalog_history_restore_rpcs"` — but hold off on actually applying until Task 3 has appended the package half below, so this is one migration transaction covering both. Skip applying in this task; Task 3's Step 2 applies the combined file.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260729131500_catalog_history_restore_rpcs.sql
git commit -m "feat(supabase): admin_list_prompt_history / admin_restore_prompt_version RPCs"
```

---

### Task 3: Restore RPCs for packages

**Files:**
- Modify: `supabase/migrations/20260729131500_catalog_history_restore_rpcs.sql` (append to the file from Task 2)

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `public.admin_list_package_history(p_package_id uuid) returns setof jsonb`, `public.admin_restore_package_version(p_history_id bigint, p_confirm boolean) returns jsonb`.

- [ ] **Step 1: Append the list/restore functions for packages to the same migration file**

```sql
create function app_private.list_package_history(p_package_id uuid)
returns table(
    history_id bigint,
    table_name text,
    operation text,
    changed_at timestamptz,
    summary jsonb
)
language plpgsql
security definer
set search_path to ''
as $$
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;

    return query
    select h.id, h.table_name, h.operation, h.changed_at,
           jsonb_build_object(
               'title', h.row_data->>'title',
               'context_key', h.row_data->>'context_key'
           )
      from app_private.catalog_history h
     where (h.table_name = 'catalog_packages' and h.row_id = p_package_id)
        or (h.table_name = 'catalog_package_items' and h.row_data->>'package_id' = p_package_id::text)
     order by h.changed_at desc;
end;
$$;

create function public.admin_list_package_history(p_package_id uuid)
returns setof app_private.list_package_history
language sql
security definer
set search_path to 'public', 'app_private', 'pg_temp'
as $$
    select * from app_private.list_package_history(p_package_id);
$$;

grant execute on function public.admin_list_package_history(uuid) to anon, authenticated, service_role;


create function app_private.restore_package_version(p_history_id bigint, p_confirm boolean)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
    v_history app_private.catalog_history;
    v_parent_exists boolean;
    v_restored jsonb;
begin
    if not app_private.current_user_is_platform_owner() then
        raise exception 'Endast plattformsägare kan redigera katalogen.';
    end if;
    if p_confirm is not true then
        raise exception 'confirm måste vara true för att återställa en version.';
    end if;

    select * into v_history from app_private.catalog_history where id = p_history_id;
    if not found then
        raise exception 'Ingen historikpost hittades med id %', p_history_id;
    end if;
    if v_history.table_name not in ('catalog_packages', 'catalog_package_items') then
        raise exception 'Historikpost % tillhör inte ett paket (table_name=%).', p_history_id, v_history.table_name;
    end if;

    if v_history.table_name = 'catalog_package_items' then
        select exists(
            select 1 from public.catalog_packages
             where id = (v_history.row_data->>'package_id')::uuid
        ) into v_parent_exists;
        if not v_parent_exists then
            raise exception 'Paketet som raden hör till finns inte längre -- återställ paketet (catalog_packages-historikposten) först.';
        end if;

        insert into public.catalog_package_items (id, package_id, prompt_id, sort_order, step_title, step_intro, is_required)
        select
            (v_history.row_data->>'id')::uuid,
            (v_history.row_data->>'package_id')::uuid,
            (v_history.row_data->>'prompt_id')::uuid,
            (v_history.row_data->>'sort_order')::int,
            v_history.row_data->>'step_title',
            v_history.row_data->>'step_intro',
            (v_history.row_data->>'is_required')::boolean
        on conflict (id) do update set
            sort_order = excluded.sort_order,
            step_title = excluded.step_title,
            step_intro = excluded.step_intro,
            is_required = excluded.is_required
        returning to_jsonb(catalog_package_items.*) into v_restored;
    else
        insert into public.catalog_packages (id, slug, package_type, status, updated_by)
        select
            (v_history.row_data->>'id')::uuid,
            v_history.row_data->>'slug',
            v_history.row_data->>'package_type',
            v_history.row_data->>'status',
            auth.uid()
        on conflict (id) do update set
            slug = excluded.slug,
            package_type = excluded.package_type,
            status = excluded.status,
            updated_by = excluded.updated_by
        returning to_jsonb(catalog_packages.*) into v_restored;
    end if;

    return v_restored;
end;
$$;

create function public.admin_restore_package_version(p_history_id bigint, p_confirm boolean)
returns jsonb
language sql
security definer
set search_path to 'public', 'app_private', 'pg_temp'
as $$
    select app_private.restore_package_version(p_history_id, p_confirm);
$$;

grant execute on function public.admin_restore_package_version(bigint, boolean) to anon, authenticated, service_role;
```

Before finalizing, run `mcp__supabase__execute_sql` with:
```sql
select column_name from information_schema.columns where table_name = 'catalog_packages' order by ordinal_position;
select column_name from information_schema.columns where table_name = 'catalog_package_items' order by ordinal_position;
```
and cross-check every column name used in the two `insert ... select` statements above against the real schema — the prompt-side columns in Task 2 were taken from a live `information_schema.columns` query earlier this session, but the exact package/package_items column list was not re-verified while writing this plan. Adjust the column lists to match before applying if they differ.

- [ ] **Step 2: Apply the combined migration (prompt + package RPCs) to production**

Use `mcp__supabase__apply_migration` with `name: "catalog_history_restore_rpcs"` and the full file contents (Task 2's Step 1 SQL followed by this task's Step 1 SQL) as `query`.

- [ ] **Step 3: Verify restore of an edited variant**

```sql
-- capture current content, make a throwaway edit, confirm history + restore round-trips
select id, summary from catalog_prompt_variants where id = (select id from catalog_prompt_variants limit 1);
-- note :variant_id and :original_summary

update catalog_prompt_variants set summary = 'TEMP TEST EDIT' where id = :variant_id;

select admin_list_prompt_history((select prompt_id from catalog_prompt_variants where id = :variant_id));
-- note the history_id of the row with operation='update' and the newest changed_at

select admin_restore_prompt_version(:history_id, true);

select summary from catalog_prompt_variants where id = :variant_id;
-- expected: back to :original_summary
```

- [ ] **Step 4: Verify restore of a deleted throwaway prompt**

Reuse the throwaway prompt pattern from Task 1 Step 4 (or create a fresh one), delete it, then:

```sql
select admin_list_prompt_history(:test_prompt_id);
-- note history_id for table_name='catalog_prompts', operation='delete'
select admin_restore_prompt_version(:that_history_id, true);
select * from catalog_prompts where id = :test_prompt_id;
-- expected: row exists again
```

Clean up afterward: `delete from catalog_prompts where id = :test_prompt_id;` (bypasses the restore round-trip entirely, this is just discarding the throwaway test fixture).

- [ ] **Step 5: Verify the confirm gate and the not-platform-owner gate**

```sql
select admin_restore_prompt_version(:history_id, false);
-- expected: error "confirm måste vara true..."
select admin_restore_prompt_version(999999999, true);
-- expected: error "Ingen historikpost hittades..."
```

(The not-platform-owner path is already covered structurally — every RPC in this codebase uses the same `current_user_is_platform_owner()` check, and Peter's the only platform owner, so there's no second account to test against directly; rely on code review of the guard clause instead of a live negative test here.)

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/20260729131500_catalog_history_restore_rpcs.sql
git commit -m "feat(supabase): admin_list_package_history / admin_restore_package_version RPCs"
```

---

### Task 4: Python wrapper functions in `admin_catalog.py`

**Files:**
- Modify: `mcp-server/server/admin_catalog.py:158-161` (insert new functions between `delete_draft_prompt` and `list_draft_prompts`, and again after `delete_draft_package` at the end of the file)

**Interfaces:**
- Consumes: `_write(tool, function_name, payload, target_id=None)` (existing, `admin_catalog.py:80`), `_call_rpc(function_name, payload)` (existing, `admin_catalog.py:47`).
- Produces: `list_prompt_history(prompt_id: str) -> list[dict[str, Any]]`, `restore_prompt_version(history_id: int, confirm: bool) -> dict[str, Any]`, `list_package_history(package_id: str) -> list[dict[str, Any]]`, `restore_package_version(history_id: int, confirm: bool) -> dict[str, Any]`.

- [ ] **Step 1: Add the prompt-history functions**

Insert directly before `def list_draft_prompts() -> list[dict[str, Any]]:` at line 160:

```python
def list_prompt_history(prompt_id: str) -> list[dict[str, Any]]:
    return _call_rpc("admin_list_prompt_history", {"p_prompt_id": prompt_id}) or []


def restore_prompt_version(history_id: int, confirm: bool) -> dict[str, Any]:
    if confirm is not True:
        raise ValueError("confirm måste vara true för att återställa en version.")
    return _write(
        "admin_restore_prompt_version",
        "admin_restore_prompt_version",
        {"p_history_id": history_id, "p_confirm": confirm},
        target_id=str(history_id),
    )
```

- [ ] **Step 2: Add the package-history functions at the end of the file**

Append after `delete_draft_package` (end of file, currently line 216):

```python


def list_package_history(package_id: str) -> list[dict[str, Any]]:
    return _call_rpc("admin_list_package_history", {"p_package_id": package_id}) or []


def restore_package_version(history_id: int, confirm: bool) -> dict[str, Any]:
    if confirm is not True:
        raise ValueError("confirm måste vara true för att återställa en version.")
    return _write(
        "admin_restore_package_version",
        "admin_restore_package_version",
        {"p_history_id": history_id, "p_confirm": confirm},
        target_id=str(history_id),
    )
```

- [ ] **Step 3: Sanity-check the file parses**

Run: `"./mcp-server/.venv/Scripts/python.exe" -c "import ast; ast.parse(open('mcp-server/server/admin_catalog.py').read())"` (from the `mcp_promptbanken` repo root)
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add mcp-server/server/admin_catalog.py
git commit -m "feat(admin): add history list/restore wrapper functions to admin_catalog.py"
```

---

### Task 5: Tool definitions in `mcp_server.py`

**Files:**
- Modify: `mcp-server/server/mcp_server.py:2717-2718` (insert new tool definitions before the closing `]` of `_admin_tool_definitions()`)

**Interfaces:**
- Consumes: none (pure data).
- Produces: four new entries in the list returned by `_admin_tool_definitions()`.

- [ ] **Step 1: Insert the four tool definitions**

Find this exact block (the end of `_admin_tool_definitions()`):

```python
        {
            "name": "admin_delete_draft_package",
            "description": "Permanently delete a draft package. Requires confirm=true. Rejected if the package is published (unpublish first). Member prompts are not deleted, only the package and its item links.",
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string"}, "confirm": {"type": "boolean"}},
                "required": ["package_id", "confirm"],
                "additionalProperties": False,
            },
        },
    ]
```

Replace with:

```python
        {
            "name": "admin_delete_draft_package",
            "description": "Permanently delete a draft package. Requires confirm=true. Rejected if the package is published (unpublish first). Member prompts are not deleted, only the package and its item links.",
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string"}, "confirm": {"type": "boolean"}},
                "required": ["package_id", "confirm"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_list_prompt_history",
            "description": "List every recorded edit/delete for a prompt (its own row plus every context variant), newest first. Each entry's history_id is what admin_restore_prompt_version takes.",
            "inputSchema": {
                "type": "object",
                "properties": {"prompt_id": {"type": "string"}},
                "required": ["prompt_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_restore_prompt_version",
            "description": "Restore one history entry (from admin_list_prompt_history) back into the live prompt or variant row. Requires confirm=true. If restoring a variant whose parent prompt was deleted, restore the prompt's own history entry first.",
            "inputSchema": {
                "type": "object",
                "properties": {"history_id": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["history_id", "confirm"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_list_package_history",
            "description": "List every recorded edit/delete for a package (its own row plus every package-item link), newest first. Each entry's history_id is what admin_restore_package_version takes.",
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string"}},
                "required": ["package_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "admin_restore_package_version",
            "description": "Restore one history entry (from admin_list_package_history) back into the live package or package-item row. Requires confirm=true. If restoring an item whose parent package was deleted, restore the package's own history entry first.",
            "inputSchema": {
                "type": "object",
                "properties": {"history_id": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["history_id", "confirm"],
                "additionalProperties": False,
            },
        },
    ]
```

- [ ] **Step 2: Commit**

```bash
git add mcp-server/server/mcp_server.py
git commit -m "feat(admin): register 4 catalog-history tool definitions"
```

---

### Task 6: Dispatch handlers in `mcp_server.py`

**Files:**
- Modify: `mcp-server/server/mcp_server.py:2856-2864` (insert new `tool_name ==` branches before the final `return _json_rpc_error(request_id, -32601, "Tool not found")` inside `_handle_admin_message`)

**Interfaces:**
- Consumes: `admin_catalog.list_prompt_history`, `admin_catalog.restore_prompt_version`, `admin_catalog.list_package_history`, `admin_catalog.restore_package_version` (Task 4); `_json_rpc_error`, `_json_rpc_result`, `_mcp_content_result` (existing helpers already used by every other branch in this function).
- Produces: working `tools/call` dispatch for the four new tool names.

- [ ] **Step 1: Insert the four dispatch branches**

Find this exact block:

```python
        if tool_name == "admin_delete_draft_package":
            package_id = arguments.get("package_id")
            confirm = arguments.get("confirm")
            if not isinstance(package_id, str) or not package_id or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'package_id'/'confirm'")
            admin_catalog.delete_draft_package(package_id, confirm)
            return _json_rpc_result(request_id, _mcp_content_result({"status": "deleted", "package_id": package_id}))

        return _json_rpc_error(request_id, -32601, "Tool not found")
```

Replace with:

```python
        if tool_name == "admin_delete_draft_package":
            package_id = arguments.get("package_id")
            confirm = arguments.get("confirm")
            if not isinstance(package_id, str) or not package_id or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'package_id'/'confirm'")
            admin_catalog.delete_draft_package(package_id, confirm)
            return _json_rpc_result(request_id, _mcp_content_result({"status": "deleted", "package_id": package_id}))

        if tool_name == "admin_list_prompt_history":
            prompt_id = arguments.get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id:
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'prompt_id'")
            result = admin_catalog.list_prompt_history(prompt_id)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_restore_prompt_version":
            history_id = arguments.get("history_id")
            confirm = arguments.get("confirm")
            if not isinstance(history_id, int) or isinstance(history_id, bool) or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'history_id'/'confirm'")
            result = admin_catalog.restore_prompt_version(history_id, confirm)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_list_package_history":
            package_id = arguments.get("package_id")
            if not isinstance(package_id, str) or not package_id:
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'package_id'")
            result = admin_catalog.list_package_history(package_id)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        if tool_name == "admin_restore_package_version":
            history_id = arguments.get("history_id")
            confirm = arguments.get("confirm")
            if not isinstance(history_id, int) or isinstance(history_id, bool) or not isinstance(confirm, bool):
                return _json_rpc_error(request_id, -32602, "Invalid or missing 'history_id'/'confirm'")
            result = admin_catalog.restore_package_version(history_id, confirm)
            return _json_rpc_result(request_id, _mcp_content_result(result))

        return _json_rpc_error(request_id, -32601, "Tool not found")
```

(`isinstance(history_id, int) and not isinstance(history_id, bool)` guards against Python's `bool` being a subclass of `int` — same guard shape already used for `sort_order` in the existing `admin_add_prompt_to_package` branch.)

- [ ] **Step 2: Commit**

```bash
git add mcp-server/server/mcp_server.py
git commit -m "feat(admin): dispatch the 4 catalog-history tools"
```

---

### Task 7: Tests

**Files:**
- Modify: `mcp-server/tests/test_admin_route.py`
- Modify: `mcp-server/mcp-contract.json`

**Interfaces:**
- Consumes: `_admin_tool_definitions`, `_handle_admin_message` (existing test imports), `server.mcp_server.admin_catalog.*` (patched via `unittest.mock.patch`, same pattern as `test_admin_create_prompt_dispatches_to_admin_catalog`).

- [ ] **Step 1: Update the tool-count assertion**

In `test_admin_tool_definitions_are_exactly_the_twelve_admin_tools`, rename it and add the four new names:

```python
    def test_admin_tool_definitions_are_exactly_the_sixteen_admin_tools(self):
        names = {tool["name"] for tool in _admin_tool_definitions()}
        self.assertEqual(
            names,
            {
                "admin_create_prompt",
                "admin_upsert_prompt_variant",
                "admin_list_draft_prompts",
                "admin_get_prompt",
                "admin_publish_prompt",
                "admin_unpublish_prompt",
                "admin_delete_draft_prompt",
                "admin_list_prompt_history",
                "admin_restore_prompt_version",
                "admin_create_package",
                "admin_add_prompt_to_package",
                "admin_publish_package",
                "admin_unpublish_package",
                "admin_delete_draft_package",
                "admin_list_package_history",
                "admin_restore_package_version",
            },
        )
```

- [ ] **Step 2: Run to confirm it fails first (proves the old assertion was in force)**

Run: `cd "mcp_promptbanken" && "./mcp-server/.venv/Scripts/python.exe" -m unittest mcp-server.tests.test_admin_route.AdminRouteTests.test_admin_tool_definitions_are_exactly_the_sixteen_admin_tools -v`
Expected: FAIL (actual set only has 12 names, since Task 5 hasn't run yet if executing tasks out of order — if Task 5/6 already landed, this step instead confirms PASS immediately, which is fine; the point is the assertion is exercised).

- [ ] **Step 3: Add dispatch tests for the four new tools**

Insert after `test_admin_publish_prompt_requires_confirm_argument`:

```python
    @patch("server.mcp_server.admin_catalog.list_prompt_history")
    def test_admin_list_prompt_history_dispatches_to_admin_catalog(self, list_prompt_history):
        list_prompt_history.return_value = [{"history_id": 1, "table_name": "catalog_prompts"}]

        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "admin_list_prompt_history", "arguments": {"prompt_id": "prompt-1"}},
            }
        )

        list_prompt_history.assert_called_once_with("prompt-1")
        self.assertNotIn("error", response)

    def test_admin_restore_prompt_version_requires_confirm_argument(self):
        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "admin_restore_prompt_version", "arguments": {"history_id": 1}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)

    @patch("server.mcp_server.admin_catalog.restore_prompt_version")
    def test_admin_restore_prompt_version_dispatches_to_admin_catalog(self, restore_prompt_version):
        restore_prompt_version.return_value = {"id": "prompt-1"}

        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "admin_restore_prompt_version",
                    "arguments": {"history_id": 1, "confirm": True},
                },
            }
        )

        restore_prompt_version.assert_called_once_with(1, True)
        self.assertNotIn("error", response)

    @patch("server.mcp_server.admin_catalog.list_package_history")
    def test_admin_list_package_history_dispatches_to_admin_catalog(self, list_package_history):
        list_package_history.return_value = [{"history_id": 2, "table_name": "catalog_packages"}]

        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "admin_list_package_history", "arguments": {"package_id": "package-1"}},
            }
        )

        list_package_history.assert_called_once_with("package-1")
        self.assertNotIn("error", response)

    def test_admin_restore_package_version_requires_confirm_argument(self):
        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "admin_restore_package_version", "arguments": {"history_id": 2}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)

    @patch("server.mcp_server.admin_catalog.restore_package_version")
    def test_admin_restore_package_version_dispatches_to_admin_catalog(self, restore_package_version):
        restore_package_version.return_value = {"id": "package-1"}

        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "admin_restore_package_version",
                    "arguments": {"history_id": 2, "confirm": True},
                },
            }
        )

        restore_package_version.assert_called_once_with(2, True)
        self.assertNotIn("error", response)
```

- [ ] **Step 4: Run the full admin test file**

Run: `cd "mcp_promptbanken" && "./mcp-server/.venv/Scripts/python.exe" -m unittest mcp-server.tests.test_admin_route -v`
Expected: all tests pass (12 existing/renamed + 6 new = the full `AdminRouteTests` class, plus the unchanged `AdminBearerAuthMiddlewareTests`).

- [ ] **Step 5: Update `mcp-contract.json`**

In `mcp-server/mcp-contract.json`, find the `"admin"` profile's `"tools"` array (currently ending `"admin_unpublish_package", "admin_delete_draft_package"`) and add the four new names:

```json
        "admin_list_prompt_history",
        "admin_restore_prompt_version",
        "admin_list_package_history",
        "admin_restore_package_version"
```

(inserted as the last four entries in that array, adjusting the preceding line's trailing comma).

- [ ] **Step 6: Run the full test suite**

Run: `cd "mcp_promptbanken" && "./mcp-server/.venv/Scripts/python.exe" -m unittest discover -s mcp-server/tests -p "test_*.py"`
Expected: `OK`, all tests pass (65 total: the 59 from before this plan plus the 6 new dispatch tests).

- [ ] **Step 7: Commit**

```bash
git add mcp-server/tests/test_admin_route.py mcp-server/mcp-contract.json
git commit -m "test(admin): cover the 4 catalog-history tools, update contract to 16 admin tools"
```

---

### Task 8: Deploy and verify live

**Files:** none (operational task)

**Interfaces:** none.

- [ ] **Step 1: Push both repos**

```bash
cd "promptbanken" && git push origin main
cd "mcp_promptbanken" && git push origin main
```

- [ ] **Step 2: Deploy `mcp_promptbanken` to the VPS**

Use the `vps-deploy` skill: check disk space, `git pull` on `~/mcp_promptbanken`, `docker-compose up -d --build` (expect and handle the known `ContainerConfig` recreate bug the same way as every prior deploy this session — `docker rm -f` the renamed stopped container, then `docker-compose up -d` without `--build`).

- [ ] **Step 3: Verify tool count live**

```bash
curl -s -X POST localhost:8000/admin -H "Authorization: Bearer $PROMPTBANKEN_ADMIN_KEY" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -c "import json,sys; d=json.load(sys.stdin); names=[t['name'] for t in d['result']['tools']]; print(len(names), 'tools')"
```
Expected: `16 tools`.

- [ ] **Step 4: Verify a real restore round-trip against production data**

Pick a real (non-throwaway) prompt, make a trivial edit via `admin_upsert_prompt_variant` (e.g. append a space to the summary and immediately revert it manually if the round-trip fails), call `admin_list_prompt_history`, call `admin_restore_prompt_version` with the entry from before the edit, confirm the content matches the pre-edit state. Use a prompt Peter is not actively editing to avoid clobbering concurrent work — ask him to name one, or use a low-traffic draft prompt if one exists (`admin_list_draft_prompts`).

- [ ] **Step 5: Update the mcp_promptbanken TODO.md**

Add a `Klart` entry dated 2026-07-29 (or the actual deploy date) noting catalog version history shipped, admin tools 12 → 16, referencing this plan and the spec.

```bash
git add TODO.md
git commit -m "docs: mark catalog version history shipped in TODO.md"
git push origin main
```

---

## Self-Review Notes

- **Spec coverage:** every section of the design doc (schema, trigger, four RPCs, scope decision, MCP wiring, testing, out-of-scope) maps to a task above. Out-of-scope items (no UI, no auto multi-restore, no retention/pruning, no `content_items` versioning) are deliberately not tasked.
- **Column-list caveat (Task 3):** the `catalog_packages`/`catalog_package_items` insert column lists were built from the migrations read earlier this session (`20260721100000_catalog_core.sql`-era schema plus the `updated_by` column added alongside `publish_catalog_package`), not from a fresh `information_schema.columns` query at plan-writing time — Task 3 Step 1 includes an explicit instruction to re-verify against the live schema before applying, specifically because this is the one place in the plan where the exact column set wasn't independently confirmed like the prompt-side tables were.
- **Type consistency:** `list_prompt_history`/`restore_prompt_version`/`list_package_history`/`restore_package_version` names match exactly across the SQL RPC names (Task 2/3), the Python wrapper functions (Task 4), and the dispatch calls (Task 6). `history_id` is `int`/`bigint` consistently (JSON-RPC `integer` schema type in Task 5, Python `int` in Task 4/6, Postgres `bigint` in Task 2/3).
