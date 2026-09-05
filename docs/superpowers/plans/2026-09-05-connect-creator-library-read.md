# Promptbanken Connect Creator Library Read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Låt en OAuth-inloggad AI läsa samma egna Creator-prompter, biblioteksreferenser, paket och delningar som användaren ser på `app.promptbanken.se`.

**Architecture:** En smal Supabase-RPC läser en specifik egen prompt under `auth.uid()`; befintliga Creator-RPC:er står för listor, paket, delningar och levande referenser. Den fristående Connect-tjänsten anropar RPC:erna med användarens OAuth-token, normaliserar resultaten till MCP och ersätter den tidiga Valvet-/workspace-prototypen. Promptbanken Open 1.2.2 berörs inte.

**Tech Stack:** PostgreSQL/Supabase RPC och RLS, Python 3.12, httpx, Starlette, PyJWT, pytest, Docker Compose och Caddy.

**Spec:** `docs/superpowers/specs/2026-09-05-connect-creator-library-design.md`

## Global Constraints

- Arbeta i två isolerade grenar: `codex/connect-creator-read-rpcs` i Promptbanken-repot och den befintliga `codex/connect-oauth-bootstrap` i MCP-repot.
- Den enda publika Connect-adressen är `https://connect.promptbanken.se/mcp`.
- Använd OAuth-access-token och `CONNECT_SUPABASE_PUBLISHABLE_KEY`; använd aldrig service-rollnyckel.
- Varje Supabase-anrop för användardata ska använda `Authorization: Bearer <access_token>` och låta `auth.uid()` avgöra ägarskap.
- Behåll Open 1.2.2, `mcp-server/`, dess Docker-container och `https://mcp.promptbanken.se/mcp` oförändrade.
- Första leveransen är read-only. Lägg inte till create, update, delete, share eller entitlementkod.
- MCP-fel ska vara på svenska och får aldrig inkludera token, SQL eller prompttext från ett misslyckat anrop.
- Verifiera databasändringar med de rollback-wrappade SQL-scenarierna i `supabase/tests/` innan de körs mot produktion.

---

## File Structure

### Promptbanken-repot

- `supabase/migrations/20260905100000_connect_creator_read_rpc.sql` — den enda nya läs-RPC:n, begränsad till en egen `content_items`-prompt.
- `supabase/tests/verify_connect_creator_read.sql` — rollback-wrappad kontroll av egen åtkomst, främmande id, Valvet-kopia och levande Valvet-referens.

### MCP-repot, Connect-grenen

- `connect-server/connect_service/data.py` — Supabase-RPC-klient och normalisering av Creator-resultat.
- `connect-server/connect_service/app.py` — Connects läsverktyg, scheman, argumentvalidering och JSON-RPC-fel.
- `connect-server/tests/test_data.py` — isolerade tester av RPC-anrop, token-header, normalisering och ogiltiga UUID:n.
- `connect-server/tests/test_app.py` — MCP-kontraktet för Creator-bibliotekets verktyg.
- `connect-server/README.md` — den faktiska Connect-ytan och klientadressen.

### Befintliga databaskontrakt som återanvänds

- `list_my_creator_prompts()`
- `list_my_library_prompts()`
- `list_my_creator_package_drafts()`
- `list_creator_package_draft_items(uuid)`
- `get_referenced_library_prompt(uuid, text[])`
- `get_referenced_library_package(uuid, text[])`
- `list_my_creator_shares()`

---

### Task 1: Ägarbunden detalj-RPC för en biblioteksprompt

**Files:**
- Create: `C:/Users/petwen/OneDrive - Höglandsförbundet/Projekt/promptbanken/supabase/migrations/20260905100000_connect_creator_read_rpc.sql`
- Create: `C:/Users/petwen/OneDrive - Höglandsförbundet/Projekt/promptbanken/supabase/tests/verify_connect_creator_read.sql`

**Interfaces:**
- Produces: `public.get_my_connect_library_prompt(p_content_item_id uuid)`, med en rad per egen prompt och fälten `id`, `title`, `slug`, `summary`, `content`, `category`, `status`, `visibility`, `module`, `is_library_reference`, `source_prompt_id`, `updated_at`.
- Consumes: `auth.uid()`, `public.content_items` samt befintliga `get_referenced_library_prompt` och `get_referenced_library_package`.

- [ ] **Step 1: Skriv den misslyckande databasverifieraren**

Skapa en rollback-wrappad SQL-fil med två användare och två personliga workspaces, enligt mönstret i `verify_library_reference_prompts.sql`. Lägg in följande fixturer för ägare A:

```sql
insert into public.content_items (
  id, workspace_id, owner_user_id, created_by, type, module,
  title, slug, content, status, visibility
) values
  ('c2000000-0000-0000-0000-000000000001', :owner_workspace, :owner, :owner,
   'prompt', 'kommun', 'Creator-prompt', 'creator-prompt', 'Creator-text', 'draft', 'private'),
  ('c2000000-0000-0000-0000-000000000002', :owner_workspace, :owner, :owner,
   'prompt', 'valvet', 'Egen kopia', 'egen-kopia', 'Kopierad text', 'draft', 'private');
```

Som `authenticated` användare A ska filen kontrollera att båda raderna returneras med rätt `module` och `content`. Som användare B ska samma funktionsanrop med A:s UUID ge noll rader. Fixturen ska också skapa en publicerad katalogprompt, lägga till den via `add_catalog_prompt_to_library`, kontrollera att detalj-RPC:n markerar `is_library_reference = true`, och att `get_referenced_library_prompt` ger den aktuella katalogtexten.

- [ ] **Step 2: Kör verifieraren innan migrationen**

Kör filen mot staging med Supabase SQL Editor eller `supabase db test`. Bekräfta att den misslyckas eftersom `get_my_connect_library_prompt(uuid)` ännu inte finns.

- [ ] **Step 3: Implementera den smala RPC:n**

Skapa migrationen med exakt denna kontraktsform. Den returnerar inga rader för ett främmande eller okänt id; därmed kan Connect använda samma 404-svar för båda fallen.

```sql
create or replace function public.get_my_connect_library_prompt(
    p_content_item_id uuid
)
returns table (
    id uuid,
    title text,
    slug text,
    summary text,
    content text,
    category text,
    status text,
    visibility text,
    module text,
    is_library_reference boolean,
    source_prompt_id uuid,
    updated_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select ci.id, ci.title, ci.slug, ci.summary, ci.content, ci.category,
           ci.status::text, ci.visibility::text, ci.module,
           ci.library_ref_catalog_prompt_id is not null,
           coalesce(ci.library_ref_catalog_prompt_id, ci.source_template_id),
           ci.updated_at
      from public.content_items ci
     where ci.id = p_content_item_id
       and ci.owner_user_id = (select auth.uid())
       and ci.type = 'prompt'
       and ci.module in ('kommun', 'valvet')
       and ci.status <> 'archived';
$$;

revoke all on function public.get_my_connect_library_prompt(uuid) from public;
grant execute on function public.get_my_connect_library_prompt(uuid) to authenticated;
```

- [ ] **Step 4: Kör verifieraren och kontrollera RLS-fallet**

Kör `verify_connect_creator_read.sql` igen. Samtliga resultatrader ska ha `ok = true`, särskilt den främmande användarens nollradsresultat och referensens live-text. Kontrollera att `rollback` lämnar databasen utan fixturer.

- [ ] **Step 5: Granska migrationen och committa Promptbanken-grenen**

Kontrollera att migrationen använder `security definer`, tom `search_path`, explicit `auth.uid()` och begränsad `authenticated`-grant. Kör därefter:

```powershell
git add supabase/migrations/20260905100000_connect_creator_read_rpc.sql supabase/tests/verify_connect_creator_read.sql
git commit -m "feat(connect): add Creator library read RPC"
```

### Task 2: Byt Connects dataadapter till Creator-RPC:er

**Files:**
- Modify: `connect-server/connect_service/data.py`
- Modify: `connect-server/tests/test_data.py`

**Interfaces:**
- Consumes: `get_my_connect_library_prompt`, de sju befintliga Creator-RPC:erna och en OAuth-access-token.
- Produces:

```python
class SupabaseConnectRepository:
    def list_library(self, *, access_token: str, kind: str = "all", limit: int = 50) -> list[Mapping[str, object]]: ...
    def get_library_prompt(self, *, access_token: str, prompt_id: str) -> Mapping[str, object] | None: ...
    def list_packages(self, *, access_token: str, limit: int = 50) -> list[Mapping[str, object]]: ...
    def get_package(self, *, access_token: str, package_id: str) -> Mapping[str, object] | None: ...
    def list_shares(self, *, access_token: str, include_inactive: bool = False) -> list[Mapping[str, object]]: ...
```

- [ ] **Step 1: Skriv de misslyckande adaptertesterna**

Ersätt testdubbletten med en `RecordingHttpClient.post(path, *, headers, json)` och skriv följande tester:

```python
def test_list_library_calls_creator_and_valvet_rpcs_with_callers_token(): ...
def test_get_library_prompt_rejects_invalid_uuid_without_http_call(): ...
def test_get_library_prompt_resolves_live_catalog_reference(): ...
def test_get_package_keeps_draft_item_order(): ...
def test_get_package_resolves_live_reference_package(): ...
def test_list_shares_excludes_inactive_by_default(): ...
```

För varje RPC-anrop ska testet kräva exakt headers:

```python
{
    "apikey": "sb_publishable_test",
    "Authorization": "Bearer oauth-access-token",
    "Content-Type": "application/json",
}
```

`list_library` ska kombinera `list_my_creator_prompts`, `list_my_library_prompts` och `list_my_creator_package_drafts`, ta bort `content` från listresultat, ange `kind` som `prompt` eller `package`, sortera `updated_at` fallande och begränsa efter sortering.

- [ ] **Step 2: Kör adaptertesterna och bekräfta rött läge**

```powershell
Set-Location connect-server
python -m pytest tests/test_data.py -q
```

Förväntat: testerna misslyckas eftersom adaptern fortfarande gör `GET /rest/v1/content_items` och saknar Creator-metoderna.

- [ ] **Step 3: Implementera en gemensam RPC-klient**

Ersätt `HttpClient.get` med `HttpClient.post`. Lägg till en privat metod som alltid använder den som anroparens access-token:

```python
def _rpc(
    self, access_token: str, function_name: str, payload: Mapping[str, object] | None = None
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
```

Validera alla id:n med `UUID(value)` innan `_rpc` anropas. Begränsa `kind` till `all`, `prompt` och `package`; begränsa `limit` till 1–100 i applikationslagret.

- [ ] **Step 4: Implementera normaliserad läsning**

`list_library` ska läsa de tre list-RPC:erna och skapa följande listpost:

```python
{
    "id": str(row["id"]),
    "kind": "prompt" | "package",
    "title": row["title"],
    "summary": row.get("summary"),
    "status": row["status"],
    "updated_at": row["updated_at"],
    "is_library_reference": bool(row.get("is_library_reference", False)),
}
```

`get_library_prompt` ska först anropa `get_my_connect_library_prompt`. Om `is_library_reference` är sant ska den sedan anropa `get_referenced_library_prompt` med `p_content_item_id` och `p_context_keys: ["generell"]` och ersätta titel, sammanfattning och `content` med referensens live-data. Annars returneras RPC:ns egen `content`.

`get_package` ska hitta paketet i `list_my_creator_package_drafts`. För ett eget paket ska den anropa `list_creator_package_draft_items`, behålla `position` och hämta varje prompt via `get_my_connect_library_prompt`; för en referens ska den anropa `get_referenced_library_package` och normalisera dess `item_title`, `item_summary`, `item_prompt_text` och `item_sort_order`.

`list_shares` ska anropa `list_my_creator_shares` och filtrera bort `is_active = false` när `include_inactive` är falskt.

- [ ] **Step 5: Kör adaptertesterna och committa**

```powershell
Set-Location connect-server
python -m pytest tests/test_data.py -q
git add connect_service/data.py tests/test_data.py
git commit -m "feat(connect): read Creator library through RPCs"
```

### Task 3: Exponera Creator-biblioteket som MCP-verktyg

**Files:**
- Modify: `connect-server/connect_service/app.py`
- Modify: `connect-server/tests/test_app.py`

**Interfaces:**
- Consumes: repositorymetoderna från Task 2.
- Produces: MCP-verktygen `list_my_library`, `get_my_library_prompt`, `list_my_packages`, `get_my_package` och `list_my_shares`.

- [ ] **Step 1: Skriv det misslyckande MCP-kontraktet**

Uppdatera fake-objektet `Library` i `test_app.py` så att det implementerar de fem metoderna från Task 2. Skriv tester för att `tools/list` returnerar exakt följande verktygsnamn tillsammans med `get_connect_context`:

```python
[
    "get_connect_context",
    "list_my_library",
    "get_my_library_prompt",
    "list_my_packages",
    "get_my_package",
    "list_my_shares",
]
```

Testa en framgångsrik `tools/call` för varje läsverktyg, ogiltiga `prompt_id`/`package_id`, `kind="annat"`, `limit=0`, `limit=101` och att ett `None` från repositoryt returnerar JSON-RPC-fel `-32004` med texten `Objektet finns inte eller är inte tillgängligt.`

- [ ] **Step 2: Kör appkontraktet och bekräfta rött läge**

```powershell
Set-Location connect-server
python -m pytest tests/test_app.py -q
```

Förväntat: det gamla verktygsnamnet `list_shared_workspace_prompts` och den gamla direkta posthämtningen gör att kontraktet inte stämmer.

- [ ] **Step 3: Implementera verktygsscheman och validering**

Ta bort `list_shared_workspace_prompts` och `get_connect_item` ur Connects `tools/list` och dispatcher. Behåll `get_connect_context`.

Lägg till följande indata:

```python
list_my_library: {"kind": "all|prompt|package", "limit": 1..100}
get_my_library_prompt: {"prompt_id": "UUID"}
list_my_packages: {"limit": 1..100}
get_my_package: {"package_id": "UUID"}
list_my_shares: {"include_inactive": true|false}
```

Validera typ och intervall före repository-anrop. Vid valideringsfel ska svaret vara:

```python
{"jsonrpc": "2.0", "id": request_id,
 "error": {"code": -32602, "message": "Ogiltiga verktygsargument."}}
```

Använd `_tool_result` för lyckade svar med nycklarna `items`, `prompt`, `package` eller `shares`.

- [ ] **Step 4: Kör hela Connect-testsviten**

```powershell
Set-Location connect-server
python -m pytest -q
python -m compileall connect_service
```

Förväntat: samtliga testfall passerar och kompileringen ger inga syntaxfel.

- [ ] **Step 5: Kontrollera att Open är orörd och committa**

Kontrollera att den här committen inte innehåller någon ändring under `mcp-server/`, `deploy/` eller rotens `docker-compose.yml`:

```powershell
git diff --name-only HEAD~1..HEAD
```

Commita sedan:

```powershell
git add connect_service/app.py tests/test_app.py
git commit -m "feat(connect): expose Creator library read tools"
```

### Task 4: Dokumentera, integrera och verifiera i separat drift

**Files:**
- Modify: `connect-server/README.md`
- Modify: `LOG.md`
- Modify: `TODO.md`

**Interfaces:**
- Consumes: den testade Connect-bilden och produktionsvärdena i den befintliga, oversionerade `connect-server/.env` på VPS:en.
- Produces: en dokumenterad read-only Connect-release och en verifierad separat container på port 8010.

- [ ] **Step 1: Skriv README- och loggförväntningarna före ändring**

Lägg till en kort manuell kontrollista i README med den förväntade verktygsytan och att `https://connect.promptbanken.se/mcp` är klientadressen. I `LOG.md` ska releasen senare dokumentera commit, testresultat, databasverifierare och externa health-/metadata-svar. I `TODO.md` ska nästa fas vara beta-skrivningar med entitlement, idempotens och `confirm: true`.

- [ ] **Step 2: Uppdatera dokumentationen**

Ersätt beskrivningen av den första Valvet-/workspace-prototypen med Creator-bibliotekets verkliga läsfunktioner. Dokumentera att inga skrivverktyg finns i denna release och att OAuth-klienttest med authorization code + PKCE fortfarande ska genomföras manuellt.

- [ ] **Step 3: Kör lokala slutkontroller och committa dokumentationen**

```powershell
Set-Location connect-server
python -m pytest -q
python -m compileall connect_service
git add README.md ..\LOG.md ..\TODO.md
git commit -m "docs(connect): describe Creator library read release"
```

- [ ] **Step 4: Applicera och kontrollera databasmigrationen**

Efter att migrationen har granskats, applicera den mot staging först och kör `verify_connect_creator_read.sql`. Om samtliga rader har `ok = true`, applicera samma migration mot produktion och kör verifieraren igen. Spara inga användaruppgifter eller testfixturer eftersom filen avslutas med `rollback`.

- [ ] **Step 5: Bygg och ersätt endast Connect-containern på VPS:en**

I `~/promptbanken-connect` ska rätt branch hämtas och tjänsten byggas innan containern ersätts. Använd den etablerade säkra ordningen från VPS-deploy-instruktionen: bygg Connect-bilden, stoppa endast `connect`, ta bort endast den gamla Connect-containern och starta endast `connect`. Starta inte om Open-containern och kör inte en generell `docker-compose up -d --build`.

- [ ] **Step 6: Verifiera produktionsytan**

Kör följande kontroller efter deploy:

```text
GET  https://connect.promptbanken.se/healthz
GET  https://connect.promptbanken.se/.well-known/oauth-protected-resource/mcp
POST https://connect.promptbanken.se/mcp utan token  -> 401 + Bearer resource
POST https://connect.promptbanken.se/mcp med OAuth-token, tools/list
POST https://connect.promptbanken.se/mcp med OAuth-token, list_my_library
```

Bekräfta även att `https://mcp.promptbanken.se/mcp` fortfarande har samma Open-tool-lista som före releasen. Dokumentera resultaten i `LOG.md` och committa logg-/TODO-uppdateringen om den inte redan ingick i steg 3.

---

## Plan Self-Review

- **Spec coverage:** Task 1 täcker ägarbunden detaljläsning och referenser. Task 2 täcker Creator-RPC-dataflödet och normalisering. Task 3 täcker MCP-kontrakt och fel. Task 4 täcker dokumentation, databasverifiering, separat Connect-deploy och att Open lämnas orörd.
- **Placeholder scan:** Planen innehåller inga öppna implementationstexter; varje migration, metod, schema, testkommando och commit har ett angivet namn och syfte.
- **Type consistency:** `get_my_connect_library_prompt` används med `p_content_item_id` i databasen och som repositoryns `get_library_prompt(prompt_id=...)`. Paket använder `package_id`, och listsvaret använder konsekvent `items`.