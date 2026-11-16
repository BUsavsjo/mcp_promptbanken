# Admin-MCP OAuth Database Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lägg till en klientmedveten, databastvingad behörighetsgräns och spårbar audit för Admin-MCP utan att ändra den generella plattformsägarrollen.

**Architecture:** En privat allowlist kopplar godkända Supabase OAuth-`client_id` till Admin-MCP. En ny central katalogadminfunktion kräver både `platform_owner` och godkänd klient när JWT:n innehåller `client_id`; katalogens befintliga security-definer-RPC:er använder denna funktion, medan vanliga webbsessioner utan `client_id` fortsätter fungera under cutover.

**Tech Stack:** Supabase Postgres, PL/pgSQL, PostgREST RPC, Supabase CLI, SQL-verifieringsscenarier

**Spec:** `../specs/2026-09-11-admin-mcp-oauth-service-design.md`

## Global Constraints

- Arbeta i ett isolerat worktree för `promptbanken`; läs dess `AGENTS.md` och `supabase/README.md` före ändringar.
- Skapa migrationen med `supabase migration new admin_mcp_oauth_authorization`; hitta aldrig på tidsstämpeln manuellt.
- Ändra inte `app_private.current_user_is_platform_owner()`.
- Verklig e-postadress eller verkligt OAuth-`client_id` får inte hårdkodas i migration, testfixture eller Git.
- `app_private.admin_mcp_oauth_clients` ska ligga utanför exponerade scheman och sakna grants till `anon`, `authenticated` och `PUBLIC`.
- Alla nya security-definer-funktioner ska ha tomt `search_path`, explicit authkontroll och återkallad standard-`EXECUTE`.
- Katalogtabellernas befintliga RLS och återkallade direkträttigheter ska bevaras.
- Webbsession och den gamla adminsessionen utan `client_id` ska fungera under cutover; OAuth-token med okänd eller avstängd klient ska nekas.
- Ingen migration körs i produktion innan den har verifierats i staging och Supabase advisors har granskats.

---

## File Structure

- Create via Supabase CLI: migrationen vars namn slutar med `_admin_mcp_oauth_authorization.sql` — privat klientlista, central behörighetsfunktion, kontext-RPC och auditkolumner.
- Create: `supabase/tests/verify_admin_mcp_oauth_authorization.sql` — körbara positiva och negativa authscenarier i en återställd transaktion.
- Modify: `supabase/README.md` — driftmodell, klientgodkännande och verifieringskommando.
- Modify: `TODO.md`, `LOG.md`, `DECISIONS.md` — arbetsminne enligt repo-instruktionerna.

### Task 1: Lås säkerhetsscenarierna före migrationen

**Files:**
- Create: `supabase/tests/verify_admin_mcp_oauth_authorization.sql`

**Interfaces:**
- Consumes: befintliga `public.profiles`, `app_private.current_user_is_platform_owner()` och katalog-RPC:er.
- Produces: ett SQL-scenario som kräver `public.get_admin_mcp_context()` och `app_private.current_session_may_administer_catalog()`.

- [ ] **Step 1: Skapa ett test som använder befintlig RLS-fixture**

Lägg testet i en transaktion och använd de fasta, anonymiserade användarna från `supabase/tests/rls_staging_check.sql`. Testet ska sätta hela claimobjektet, inte bara `request.jwt.claim.sub`:

```sql
begin;

insert into auth.users (
  id, aud, role, email, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at
)
values
  (
    '00000000-0000-0000-0000-000000000001',
    'authenticated', 'authenticated', 'platform.owner@example.test', now(),
    '{}'::jsonb, '{}'::jsonb, now(), now()
  ),
  (
    '00000000-0000-0000-0000-000000000002',
    'authenticated', 'authenticated', 'workspace.admin@example.test', now(),
    '{}'::jsonb, '{}'::jsonb, now(), now()
  );

insert into public.workspaces (id, name, slug, owner_user_id)
values (
  '10000000-0000-0000-0000-000000000001',
  'Admin MCP Test Workspace',
  'admin-mcp-test',
  '00000000-0000-0000-0000-000000000002'
);

insert into public.profiles (user_id, workspace_id, role)
values
  (
    '00000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    'platform_owner'
  ),
  (
    '00000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000001',
    'workspace_admin'
  );

insert into app_private.admin_mcp_oauth_clients (client_id, label, enabled)
values
  ('00000000-0000-0000-0000-00000000a001', 'Admin MCP test', true),
  ('00000000-0000-0000-0000-00000000a002', 'Avstängd Admin MCP test', false);

create or replace function pg_temp.assert_admin_allowed(
  p_expected boolean,
  p_label text
)
returns void
language plpgsql
as $$
declare
  v_actual boolean;
begin
  select coalesce((public.get_admin_mcp_context() ->> 'allowed')::boolean, false)
    into v_actual;
  if v_actual is distinct from p_expected then
    raise exception '%: expected %, got %', p_label, p_expected, v_actual;
  end if;
end
$$;

set local role authenticated;

select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a001',
    'email', 'platform.owner@example.test'
  )::text,
  true
);

do $$
declare
  v_context jsonb;
begin
  select public.get_admin_mcp_context() into v_context;
  if coalesce((v_context ->> 'allowed')::boolean, false) is not true then
    raise exception 'approved platform_owner client should be allowed: %', v_context;
  end if;
  if v_context ->> 'user_id' <> '00000000-0000-0000-0000-000000000001' then
    raise exception 'context returned wrong user';
  end if;
end
$$;
```

Fortsätt i samma fil med de fyra exakta fallen:

```sql
select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a099'
  )::text,
  true
);
select pg_temp.assert_admin_allowed(false, 'unknown OAuth client');

select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a002'
  )::text,
  true
);
select pg_temp.assert_admin_allowed(false, 'disabled OAuth client');

select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000002',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000002',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a001'
  )::text,
  true
);
select pg_temp.assert_admin_allowed(false, 'non-platform owner');

select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated'
  )::text,
  true
);
select pg_temp.assert_admin_allowed(true, 'legacy web session during cutover');
```

Avsluta med `rollback;` så testet aldrig lämnar klientrader eller auditdata.

- [ ] **Step 2: Lägg till en statisk täckningskontroll för katalogfunktionerna**

Definiera exakt denna lista i testfilen och kräv att varje effektiv funktion använder den nya hjälpfunktionen:

```sql
do $$
declare
  v_required text[] := array[
    'create_catalog_prompt',
    'upsert_catalog_prompt_variant',
    'publish_catalog_prompt',
    'create_catalog_package',
    'upsert_catalog_package_variant',
    'upsert_catalog_package_metadata',
    'add_prompt_to_catalog_package',
    'update_catalog_package_item',
    'remove_prompt_from_catalog_package',
    'publish_catalog_package',
    'create_prompt_draft_from_chat',
    'create_package_draft_from_chat',
    'list_draft_catalog_prompts',
    'get_catalog_prompt_by_id',
    'log_admin_write_attempt',
    'unpublish_catalog_prompt',
    'delete_draft_catalog_prompt',
    'unpublish_catalog_package',
    'delete_draft_catalog_package',
    'list_prompt_history',
    'list_package_history',
    'restore_prompt_version',
    'restore_package_version'
  ];
  v_found integer;
  v_all_guarded boolean;
begin
  select count(distinct p.proname),
         bool_and(
           position(
             'current_session_may_administer_catalog()'
             in pg_get_functiondef(p.oid)
           ) > 0
         )
    into v_found, v_all_guarded
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'app_private'
     and p.proname = any(v_required);

  if v_found <> cardinality(v_required) then
    raise exception 'catalog admin function coverage incomplete: %/%',
      v_found, cardinality(v_required);
  end if;
  if v_all_guarded is not true then
    raise exception 'one or more catalog admin overloads use the old guard';
  end if;
end
$$;
```

- [ ] **Step 3: Kör testet och bekräfta rött läge**

Kör först `supabase --version` och `supabase db --help`. Starta den lokala Supabase-miljön enligt repots dokumentation och kör:

```powershell
psql $env:SUPABASE_LOCAL_DB_URL -v ON_ERROR_STOP=1 -f .\supabase\tests\verify_admin_mcp_oauth_authorization.sql
```

Förväntat: testet stoppar vid att `app_private.admin_mcp_oauth_clients` eller `public.get_admin_mcp_context()` saknas. Ett saknat test-DB-URL är inte godkänt rött läge; konfigurera den lokala testmiljön först.

- [ ] **Step 4: Commit**

```powershell
git add supabase/tests/verify_admin_mcp_oauth_authorization.sql
git commit -m "test: define Admin MCP OAuth database boundary"
```

### Task 2: Skapa allowlist, authkontext och auditidentitet

**Files:**
- Create via CLI: `supabase/migrations/*_admin_mcp_oauth_authorization.sql`
- Test: `supabase/tests/verify_admin_mcp_oauth_authorization.sql`

**Interfaces:**
- Consumes: `auth.uid()`, `auth.jwt()`, `app_private.current_user_is_platform_owner()`.
- Produces: `app_private.current_session_may_administer_catalog() returns boolean` och `public.get_admin_mcp_context() returns jsonb`.

- [ ] **Step 1: Skapa migrationens verkliga sökväg med CLI**

```powershell
npx supabase --version
npx supabase migration new admin_mcp_oauth_authorization
$migrationPath = Get-ChildItem .\supabase\migrations\*_admin_mcp_oauth_authorization.sql |
  Sort-Object LastWriteTime |
  Select-Object -Last 1 -ExpandProperty FullName
$migrationPath
```

Förväntat: exakt en ny fil skapad av CLI och dess fullständiga sökväg skrivs ut.

- [ ] **Step 2: Lägg in den privata tabellen och grundskyddet**

Skriv följande i den CLI-skapade filen:

```sql
create table app_private.admin_mcp_oauth_clients (
    client_id text primary key,
    label text not null check (length(trim(label)) between 1 and 120),
    enabled boolean not null default true,
    approved_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now()
);

alter table app_private.admin_mcp_oauth_clients enable row level security;
revoke all on table app_private.admin_mcp_oauth_clients from public, anon, authenticated;
```

Lägg inte in någon verklig klientrad i migrationen.

- [ ] **Step 3: Lägg in den centrala behörighetsfunktionen**

```sql
create or replace function app_private.current_session_may_administer_catalog()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select
        app_private.current_user_is_platform_owner()
        and (
            nullif(auth.jwt() ->> 'client_id', '') is null
            or exists (
                select 1
                  from app_private.admin_mcp_oauth_clients c
                 where c.client_id = auth.jwt() ->> 'client_id'
                   and c.enabled is true
            )
        );
$$;

revoke all on function app_private.current_session_may_administer_catalog() from public;
```

Ge inte `authenticated` direkt `EXECUTE`; publika RPC:er anropar funktionen som security definer.

- [ ] **Step 4: Lägg in den read-only kontext-RPC som tjänsten använder för 403**

```sql
create or replace function public.get_admin_mcp_context()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'user_id', auth.uid(),
        'email', nullif(auth.jwt() ->> 'email', ''),
        'role', case
            when app_private.current_user_is_platform_owner() then 'platform_owner'
            else 'not_platform_owner'
        end,
        'client_id', nullif(auth.jwt() ->> 'client_id', ''),
        'client_approved', case
            when nullif(auth.jwt() ->> 'client_id', '') is null then false
            else exists (
                select 1
                  from app_private.admin_mcp_oauth_clients c
                 where c.client_id = auth.jwt() ->> 'client_id'
                   and c.enabled is true
            )
        end,
        'allowed', app_private.current_session_may_administer_catalog()
    );
$$;

revoke all on function public.get_admin_mcp_context() from public, anon;
grant execute on function public.get_admin_mcp_context() to authenticated;
```

- [ ] **Step 5: Utöka auditkolumnerna och bind dem till request-kontexten**

```sql
alter table app_private.admin_write_attempts
    add column actor_user_id uuid references auth.users(id) on delete set null,
    add column oauth_client_id text;
```

Återskapa den effektiva `app_private.log_admin_write_attempt(text, uuid, text, jsonb)` från den senaste migrationen, men ersätt authgrinden och inserten med:

```sql
if not app_private.current_session_may_administer_catalog() then
    raise exception 'Endast godkända katalogadministratörer kan logga admin-skrivningar.';
end if;

if auth.uid() is null then
    raise exception 'Admin-audit kräver en autentiserad användare.';
end if;

insert into app_private.admin_write_attempts (
    tool, target_id, outcome, detail, actor_user_id, oauth_client_id
)
values (
    p_tool,
    p_target_id,
    p_outcome,
    p_detail,
    auth.uid(),
    nullif(auth.jwt() ->> 'client_id', '')
);
```

Behåll den publika wrapperns signatur oförändrad.

- [ ] **Step 6: Kör testet igen och kontrollera delresultatet**

```powershell
psql $env:SUPABASE_LOCAL_DB_URL -v ON_ERROR_STOP=1 -f $migrationPath
psql $env:SUPABASE_LOCAL_DB_URL -v ON_ERROR_STOP=1 -f .\supabase\tests\verify_admin_mcp_oauth_authorization.sql
```

Förväntat: kontextscenarierna passerar; den statiska funktionskontrollen är fortfarande röd tills Task 3.

- [ ] **Step 7: Commit**

```powershell
git add $migrationPath supabase/tests/verify_admin_mcp_oauth_authorization.sql
git commit -m "feat: add Admin MCP OAuth client authorization"
```

### Task 3: Flytta samtliga katalogadmin-RPC:er till den nya grinden

**Files:**
- Modify: den CLI-skapade `*_admin_mcp_oauth_authorization.sql`
- Test: `supabase/tests/verify_admin_mcp_oauth_authorization.sql`

**Interfaces:**
- Consumes: `app_private.current_session_may_administer_catalog() returns boolean`.
- Produces: samma publika RPC-signaturer och datakontrakt som före migrationen, med klientmedveten auth.

- [ ] **Step 1: Fastställ den effektiva definitionen för varje funktion**

För varje namn i Task 1:s `required_function`, hitta den sista migrationen som definierar funktionen:

```powershell
rg -n "create or replace function app_private\.(create_catalog_prompt|upsert_catalog_prompt_variant|publish_catalog_prompt|create_catalog_package|upsert_catalog_package_variant|upsert_catalog_package_metadata|add_prompt_to_catalog_package|update_catalog_package_item|remove_prompt_from_catalog_package|publish_catalog_package|create_prompt_draft_from_chat|create_package_draft_from_chat|list_draft_catalog_prompts|get_catalog_prompt_by_id|log_admin_write_attempt|unpublish_catalog_prompt|delete_draft_catalog_prompt|unpublish_catalog_package|delete_draft_catalog_package|list_prompt_history|list_package_history|restore_prompt_version|restore_package_version)" supabase/migrations
```

Dokumentera sökresultatet i commitmeddelandets body eller arbetsloggen. Använd den senaste definitionen per signatur, inklusive senare fält som `security_examples`, SEO-metadata och komplett package-variant-historik.

- [ ] **Step 2: Återskapa funktionerna med en enda mekanisk authändring**

Kopiera varje effektiv funktionsdefinition till slutet av den nya migrationen. Byt i varje kopia exakt:

```sql
if not app_private.current_user_is_platform_owner() then
```

mot:

```sql
if not app_private.current_session_may_administer_catalog() then
```

Ändra inga parametrar, returtyper, valideringar, SQL-satser, feltexter eller publika wrappers. `log_admin_write_attempt` använder redan den utökade definitionen från Task 2 och ska inte dupliceras en andra gång.

- [ ] **Step 3: Lägg ett representativt bypass-test**

I SQL-testet: sätt plattformsägaren med okänd OAuth-klient och anropa en läs-RPC som annars skulle avslöja drafts:

```sql
select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a099'
  )::text,
  true
);

do $$
begin
  perform public.list_draft_catalog_prompts();
  raise exception 'unapproved OAuth client unexpectedly reached catalog admin RPC';
exception
  when others then
    if sqlerrm = 'unapproved OAuth client unexpectedly reached catalog admin RPC' then
      raise;
    end if;
end
$$;
```

Sätt därefter godkänd klient `...a001` och verifiera att samma RPC inte
ger authfel. Testet accepterar en tom resultatlista:

```sql
select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a001'
  )::text,
  true
);

do $$
declare
  v_rows jsonb;
begin
  select coalesce(jsonb_agg(row_to_json(item)), '[]'::jsonb)
    into v_rows
    from public.list_draft_catalog_prompts() item;
  if jsonb_typeof(v_rows) <> 'array' then
    raise exception 'approved OAuth client did not receive an array';
  end if;
end
$$;
```

- [ ] **Step 4: Kör hela SQL-testet i grönt läge**

```powershell
psql $env:SUPABASE_LOCAL_DB_URL -v ON_ERROR_STOP=1 -f .\supabase\tests\verify_admin_mcp_oauth_authorization.sql
```

Förväntat: exit code 0, fem kontextscenarier passerar, bypass nekas, godkänd klient accepteras och alla 23 funktioner hittas med nya grinden.

- [ ] **Step 5: Kontrollera att den generella hjälpfunktionen är orörd**

```powershell
git diff --unified=0 HEAD^ -- supabase/migrations | Select-String "current_user_is_platform_owner"
```

Förväntat: funktionen anropas i den nya kataloggrinden men ingen `create or replace function app_private.current_user_is_platform_owner()` finns i diffen.

- [ ] **Step 6: Commit**

```powershell
git add $migrationPath supabase/tests/verify_admin_mcp_oauth_authorization.sql
git commit -m "security: bind catalog admin RPCs to approved OAuth clients"
```

### Task 4: Verifiera audit och revokering end-to-end lokalt

**Files:**
- Modify: `supabase/tests/verify_admin_mcp_oauth_authorization.sql`

**Interfaces:**
- Consumes: `public.log_admin_write_attempt(text, uuid, text, jsonb)`.
- Produces: bevis för aktörs-id, klient-id, avstängning och bakåtkompatibel webbsession.

- [ ] **Step 1: Lägg till ett misslyckande test för auditidentiteten**

Med godkänd klient och plattformsägare:

```sql
select set_config(
  'request.jwt.claim.sub',
  '00000000-0000-0000-0000-000000000001',
  true
);
select set_config(
  'request.jwt.claims',
  json_build_object(
    'sub', '00000000-0000-0000-0000-000000000001',
    'role', 'authenticated',
    'aud', 'authenticated',
    'client_id', '00000000-0000-0000-0000-00000000a001'
  )::text,
  true
);

select public.log_admin_write_attempt(
  'admin_mcp_oauth_test',
  null,
  'success',
  jsonb_build_object('fixture', true)
);

do $$
declare
  v_row app_private.admin_write_attempts;
begin
  select *
    into v_row
    from app_private.admin_write_attempts
   where tool = 'admin_mcp_oauth_test'
   order by created_at desc
   limit 1;

  if v_row.actor_user_id <> '00000000-0000-0000-0000-000000000001'::uuid then
    raise exception 'audit actor mismatch';
  end if;
  if v_row.oauth_client_id <> '00000000-0000-0000-0000-00000000a001' then
    raise exception 'audit client mismatch';
  end if;
end
$$;
```

- [ ] **Step 2: Lägg till omedelbar klientrevokering**

Avaktivera testklienten och verifiera både kontext och audit med detta block:

```sql
reset role;
update app_private.admin_mcp_oauth_clients
   set enabled = false
 where client_id = '00000000-0000-0000-0000-00000000a001';
set local role authenticated;

select pg_temp.assert_admin_allowed(false, 'revoked OAuth client');

do $$
begin
  perform public.log_admin_write_attempt(
    'admin_mcp_oauth_revoked_test',
    null,
    'rejected',
    jsonb_build_object('fixture', true)
  );
  raise exception 'revoked OAuth client unexpectedly wrote audit';
exception
  when others then
    if sqlerrm = 'revoked OAuth client unexpectedly wrote audit' then
      raise;
    end if;
end
$$;

reset role;
update app_private.admin_mcp_oauth_clients
   set enabled = true
 where client_id = '00000000-0000-0000-0000-00000000a001';
set local role authenticated;
select pg_temp.assert_admin_allowed(true, 're-enabled OAuth client');
```

Den slutliga `rollback` tar bort både fixture- och auditdata.

- [ ] **Step 3: Kör komplett lokalt schema- och testflöde från ren databas**

Ta reda på stödda CLI-kommandon:

```powershell
npx supabase db reset --help
npx supabase db lint --help
```

Kör därefter repots dokumenterade rena återställning, hela
`verify_admin_mcp_oauth_authorization.sql` och relevanta befintliga
katalogtester:

```powershell
psql $env:SUPABASE_LOCAL_DB_URL -v ON_ERROR_STOP=1 -f .\supabase\tests\verify_catalog_core.sql
psql $env:SUPABASE_LOCAL_DB_URL -v ON_ERROR_STOP=1 -f .\supabase\tests\verify_admin_mcp_oauth_authorization.sql
```

Förväntat: båda kommandona ger exit code 0. Sök dessutom efter `ERROR`,
`WARNING` och oväntade tomma resultat i hela utskriften.

- [ ] **Step 4: Kör advisors/lint**

Använd `supabase db advisors --help` om installerad CLI stödjer det; annars
Supabase MCP `get_advisors`. Åtgärda nya security-definer-, grant- eller
RLS-varningar som migrationen orsakar. Befintliga varningar dokumenteras men
maskeras inte som nya.

- [ ] **Step 5: Commit**

```powershell
git add supabase/tests/verify_admin_mcp_oauth_authorization.sql
git commit -m "test: verify Admin MCP audit identity and revocation"
```

### Task 5: Dokumentera och verifiera i staging

**Files:**
- Modify: `supabase/README.md`
- Modify: `TODO.md`
- Modify: `LOG.md`
- Modify: `DECISIONS.md`

**Interfaces:**
- Consumes: färdig migration och lokala verifieringsresultat.
- Produces: stagingbevis och driftsinstruktion som service- och rolloutplanerna kan förlita sig på.

- [ ] **Step 1: Dokumentera klientgodkännande utan hemligheter**

Lägg till:

```markdown
## Admin-MCP OAuth-klienter

Admin-MCP kräver både rollen `platform_owner` och en aktiv rad i
`app_private.admin_mcp_oauth_clients` när Supabase-token innehåller
`client_id`. Klient-id är inte en hemlighet men ska läggas in som
driftdata efter registrering, aldrig hårdkodas i migrationer.

Spärra en klient genom att sätta `enabled = false`. Ändringen träder i
kraft vid nästa MCP-request eftersom tjänsten inte cachar adminrollen.
```

- [ ] **Step 2: Uppdatera arbetsminnet**

I `DECISIONS.md`: registrera att den generella
`current_user_is_platform_owner()` lämnas orörd och att katalog-RPC:erna
har en egen klientmedveten grind. I `TODO.md`: lägg in kvarvarande
produktionsmigration och första klientgodkännande. I `LOG.md`: skriv exakta
lokala testkommandon och utfall.

- [ ] **Step 3: Applicera på staging med CLI-kommandon som först verifierats via help**

```powershell
npx supabase db push --help
npx supabase migration list --help
```

Kör sedan det dokumenterade stagingprojektets `db push`, följt av
`migration list`. Lägg endast anonymiserade testklienter i stagingtabellen.

- [ ] **Step 4: Kör stagingmatrisen med verkliga Supabase-tokens**

Verifiera genom PostgREST:

- godkänd Admin-MCP-klient + `platform_owner` → kontext `allowed=true`,
- samma användare + Connects `client_id` → `allowed=false`,
- godkänd klient + icke-admin → `allowed=false`,
- avstängd klient → omedelbart `allowed=false`,
- vanlig webbsession utan `client_id` → befintlig adminfunktion fungerar.

Spara endast statuskoder, booleska resultat och anonymiserade klientetiketter i
releaseunderlaget; spara aldrig JWT.

- [ ] **Step 5: Kör advisors i staging och granska diffen**

Bekräfta att tabellen inte kan nås via Data API, att `anon` inte kan köra
kontext-RPC:n och att `authenticated` bara kan läsa sin egen beräknade
kontext. Kör `git diff --check` och repots övriga auth/katalogtester.

- [ ] **Step 6: Commit**

```powershell
git add supabase/README.md TODO.md LOG.md DECISIONS.md
git commit -m "docs: record Admin MCP OAuth database rollout"
```

## Database Plan Completion Gate

Databasdelen är redo för serviceintegration först när:

- migrationen är skapad av CLI och passerar från en ren lokal databas,
- exakt 23 katalogadminfunktioner använder den nya grinden,
- godkänd/okänd/avstängd klient och icke-admin har verifierats,
- audit sparar verklig `auth.uid()` och OAuth-`client_id`,
- webbsession utan `client_id` fungerar,
- stagingtest och advisors är gröna,
- ingen verklig e-postadress, token eller klientidentifierare finns i Git.
