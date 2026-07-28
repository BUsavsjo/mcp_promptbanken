# Catalog version history (undo for admin-MCP edits/deletes)

**Status:** approved, not yet implemented
**Date:** 2026-07-29
**Repos affected:** `promptbanken` (Supabase migration), `mcp_promptbanken` (admin-MCP tools)

## Problem

The admin-MCP catalog authoring system (shipped 2026-07-28, extended
2026-07-29 with `admin_unpublish_prompt`/`admin_delete_draft_prompt`/
`admin_unpublish_package`/`admin_delete_draft_package`) has two ways to
lose content with no way back:

1. `admin_upsert_prompt_variant` silently overwrites a variant's content
   on every call — no history, no diff, no way to see what it looked like
   before an AI client's edit.
2. `admin_delete_draft_prompt`/`admin_delete_draft_package` permanently
   delete a row. Restricted to `status = 'draft'` and (for prompts) not
   referenced by a package, but within that scope, irreversible.

An AI client driving the admin-MCP (Claude Desktop, Claude Code, or any
other MCP client with the admin bearer key) can make a mistake — wrong
edit, wrong delete — and today the only recovery path is "there isn't
one." Peter wants an easy way to back out of either mistake without
needing direct Supabase access each time.

## Approach

A single generic history table plus a generic trigger function, attached
to all four catalog tables. This guarantees every UPDATE/DELETE is
captured regardless of which RPC (existing or future) performs it — the
guarantee lives in the database, not in per-function discipline.

Considered and rejected: snapshotting inside each write RPC individually.
Simpler to read per-function, but a new write path added later that
forgets to snapshot would silently break the guarantee. The trigger
approach can't be bypassed by an oversight in application code.

## Schema

```sql
create table app_private.catalog_history (
    id bigserial primary key,
    table_name text not null,      -- 'catalog_prompts' | 'catalog_prompt_variants'
                                    -- | 'catalog_packages' | 'catalog_package_items'
    row_id uuid not null,          -- the primary key of the affected row
    operation text not null,       -- 'update' | 'delete'
    row_data jsonb not null,       -- to_jsonb(OLD)
    changed_at timestamptz not null default now(),
    changed_by uuid                -- auth.uid() at the time of the change
);

create index catalog_history_table_row_idx
    on app_private.catalog_history (table_name, row_id, changed_at desc);
```

Not exposed to `anon`/`authenticated` directly — only reachable through
the four RPCs below, same pattern as `app_private.admin_write_attempts`.

### Trigger function

```sql
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
```

Mounted `before update or delete` on `catalog_prompts`,
`catalog_prompt_variants`, `catalog_packages`, `catalog_package_items`.
Cascade deletes (e.g. deleting a `catalog_prompts` row cascades to its
`catalog_prompt_variants` rows via the existing FK) fire real per-row
DELETE statements internally in Postgres, so the trigger captures those
too — no separate handling needed for cascades.

`row_id` assumes every one of the four tables has a single-column `id`
primary key. Confirmed true for all four in the current schema
(`catalog_package_items` has its own `id`, not a composite key on
`package_id`/`prompt_id`).

## Restore RPCs

Four new functions, same `app_private`/`public` two-layer pattern and
`app_private.current_user_is_platform_owner()` gate as every other admin
write RPC (`publish_catalog_prompt`, `delete_draft_catalog_prompt`, etc).

### `admin_list_prompt_history(p_prompt_id uuid)`

Returns every history row where either:
- `table_name = 'catalog_prompts' and row_id = p_prompt_id`, or
- `table_name = 'catalog_prompt_variants' and row_data->>'prompt_id' = p_prompt_id::text`

Ordered `changed_at desc`. Each row includes `id` (the history entry's
own id, needed for restore), `table_name`, `operation`, `changed_at`,
and enough of `row_data` (title, context_key, summary) for an admin to
recognize which version they want without reading the full jsonb blob.

### `admin_restore_prompt_version(p_history_id bigint, p_confirm boolean)`

1. Requires `p_confirm = true` (matches `delete_draft_catalog_prompt`'s
   gate) and platform_owner.
2. Looks up the `catalog_history` row by id. Raises if not found, or if
   `table_name` isn't `catalog_prompts`/`catalog_prompt_variants`
   (guards against a caller passing a package-history id here).
3. If the row is a `catalog_prompt_variants` snapshot, first check the
   parent `catalog_prompts` row still exists — if not, raise "restore
   the prompt itself first" rather than letting the FK insert fail with
   an opaque error.
4. Upsert `row_data` back into the live table via
   `jsonb_populate_record` + `insert ... on conflict (id) do update`.
   Works whether the row still exists (edit case) or was deleted
   (delete case) — same statement shape either way.
5. Return the restored row.

`jsonb_populate_record` degrades gracefully across schema drift: a
column added since the snapshot was taken gets its default/null: a
column since removed in `row_data` is silently ignored by the insert
(explicit column list, not `select *` from the jsonb).

### `admin_list_package_history(p_package_id uuid)` / `admin_restore_package_version(p_history_id bigint, p_confirm boolean)`

Same shape, covering `catalog_packages` and `catalog_package_items`
(matched via `row_data->>'package_id'`).

### Scope decision: one row at a time

A single `restore` call restores exactly one history row, not "every
row that was part of this prompt when it was deleted." If a prompt with
three context variants was deleted, `admin_list_prompt_history` shows
all four resulting history entries (the prompt row + three variant
rows) and the admin restores the prompt row first, then each variant
separately. No auto-restore-everything flow. This keeps the RPCs simple
or 1:1 with a single table row, and the scenario is inherently rare
(delete is already restricted to draft-status, unpublished content —
most "oops" cases are caught by unpublish, not delete).

## MCP tool wiring (mcp_promptbanken repo)

`mcp-server/server/admin_catalog.py`: four new thin wrapper functions
(`list_prompt_history`, `restore_prompt_version`, `list_package_history`,
`restore_package_version`), following the existing `_write`/`_call_rpc`
pattern — `restore_*` goes through `_write` (rate-limited, audited),
`list_*` is a plain read like `list_draft_prompts`/`get_prompt`.

`mcp-server/server/mcp_server.py`: four new entries in
`_admin_tool_definitions()` and four new `tool_name ==` branches in
`_handle_admin_message`, following the exact shape of the existing
`admin_get_prompt`/`admin_publish_prompt` pairs. Admin tool count goes
from 12 to 16.

## Testing

**SQL (manual verification via Supabase MCP, no automated SQL test
harness exists in this repo today):**
- Trigger fires on UPDATE and DELETE for all four tables, including a
  cascade delete (delete a `catalog_prompts` row with variants, confirm
  variant history rows also appear).
- Restore reconstructs a deleted `catalog_prompts` row and its variants
  correctly (values match pre-delete state).
- Restore reconstructs an overwritten variant back to its pre-edit
  content.
- Non-platform-owner call to any of the four new RPCs raises the
  standard authorization error.
- `p_confirm = false`/omitted on either restore RPC raises without
  restoring anything.
- Restoring a variant whose parent prompt is still deleted raises the
  "restore the prompt first" error, doesn't attempt the insert.

**Python (`mcp-server/tests/test_admin_route.py`):**
- Update the "exactly N admin tools" assertion to 16 and the new names.
- One dispatch test per new tool, mirroring the existing
  `test_admin_create_prompt_dispatches_to_admin_catalog`/
  `test_admin_publish_prompt_requires_confirm_argument` shape — confirm
  argument validation for the two restore tools, correct RPC name/args
  passed through for all four.

**Contract test:** add the four new names to the `admin` profile tool
list in `mcp-server/mcp-contract.json` (same file touched in the
2026-07-29 unpublish/delete change).

## Out of scope

- No UI for browsing history — read-only via the new list tools only.
  If this needs a visual diff/timeline later, that's a separate,
  smaller follow-up once the underlying data exists.
- No automatic multi-row restore (see Scope decision above).
- No retention/pruning — history is kept indefinitely. Prompt content
  is small (text + metadata), volume is low; revisit only if this
  becomes a real storage concern.
- No versioning for `content_items` (the separate Supabase-workspace
  Valvet table) — this spec covers only the `catalog_*` tables the
  admin-MCP writes to.
