-- MCP API-nycklar kopplade till workspaces.
-- Den faktiska nyckeln visas bara vid skapande; här lagras bara sha256-hashen.

create table if not exists mcp_keys (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id) on delete cascade,
  key_hash      text not null unique,          -- sha256(raw_key) i hex
  name          text not null default '',
  scopes        text[] not null default '{mcp}',
  revoked_at    timestamptz,
  created_at    timestamptz not null default now()
);

-- Bara workspace-ägaren ser sina egna nycklar.
alter table mcp_keys enable row level security;

create policy "workspace_owner_select" on mcp_keys
  for select using (
    workspace_id in (
      select id from workspaces where owner_id = auth.uid()
    )
  );

create policy "workspace_owner_insert" on mcp_keys
  for insert with check (
    workspace_id in (
      select id from workspaces where owner_id = auth.uid()
    )
  );

create policy "workspace_owner_update" on mcp_keys
  for update using (
    workspace_id in (
      select id from workspaces where owner_id = auth.uid()
    )
  );

create policy "workspace_owner_delete" on mcp_keys
  for delete using (
    workspace_id in (
      select id from workspaces where owner_id = auth.uid()
    )
  );

-- Begränsa ett personligt (free) workspace till max 1 aktiv nyckel.
create or replace function check_mcp_key_limit()
returns trigger language plpgsql as $$
declare
  plan_name text;
  active_count int;
begin
  select plan into plan_name from workspaces where id = new.workspace_id;
  if plan_name = 'free' then
    select count(*) into active_count
    from mcp_keys
    where workspace_id = new.workspace_id
      and revoked_at is null;
    if active_count >= 1 then
      raise exception 'Free-plan workspaces may only have one active MCP key';
    end if;
  end if;
  return new;
end;
$$;

create trigger enforce_mcp_key_limit
  before insert on mcp_keys
  for each row execute function check_mcp_key_limit();
