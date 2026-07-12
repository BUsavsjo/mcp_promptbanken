# Logg

## 2026-07-12

### Gjort
- Designade och byggde `save_workspace_prompt`: första write-verktyget i den hostade servern, Pro-gated, se `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md` och plan `docs/superpowers/plans/2026-07-12-save-workspace-prompt-write.md`.
- Ny RPC `app_private.save_prompt_for_key` i `promptbanken`-repot: pinnad `search_path`, rate limit + observability via `app_private.mcp_write_attempts`, idempotens via `idempotency_key`, innehållsvalidering, återanvänder `enforce_content_access_model`-triggern oförändrad via en transaktionslokal `auth.uid()`-koppling.
- Porterade `check_input_risk` från lokala `promptbanken/mcp-server/` hit — behövdes för att "generalisera → check → godkänn → spara"-flödet ska fungera mot den publika adressen. Fann och städade en pre-existing duplicerad `SERVER_MODE=="local"`-gated registrering av samma tool under vägen.
- Ny REST-endpoint `POST /api/v1/my-prompts`, första POST-endpointen i detta repo.
- Uppdaterade `hosted_guard.py`s allowlist för de två nya verktygen.
- **Bugg hittad under staging-verifiering och fixad samma dag:** log-innan-raise-mönstret i `save_prompt_for_key` persisterade aldrig avvisade försök (Postgres rullar tillbaka hela transaktionen vid `raise exception`). Löst med en ny separat RPC `app_private.log_write_attempt`, anropad av Python som ett eget HTTP-anrop efter att felet fångats. Se `DECISIONS.md`.
- Verifierat end-to-end mot staging med en dedikerad Pro-testnyckel (samtliga 6 utfall i `mcp_write_attempts` korrekta efter fixen).

### Nästa steg
- Deploya till produktion (Task 8 i planen) efter merge till `main`.
- Framtida: delning till `shared_workspace_addons` via write, semantisk dubblettdetektering, `search_path`-uppstädning på de äldre läs-RPC:erna, IP-baserad rate limit för ogiltig-nyckel-spam — se speccens "Uttryckligen utanför scope v1" och `TODO.md`.

## 2026-07-08

### Gjort
- Jämförde vad som är byggt i den hostade servern mot `promptbanken`-repots plan-läge och senaste utveckling. Hittade gapet: `promptbanken` bytte 2026-07-06 till "Pro + Delad arbetsyta"-modellen och byggde tre nya MCP-tools i sin lokala server (`list_my_private_prompts`, `list_my_shared_workspaces`, `list_shared_workspace_prompts`) som aldrig portades till den hostade `mcp_promptbanken`-servern — explicit noterat som öppen punkt i `promptbanken/TODO.md`.
- Portade alla tre verktygen hit: nya funktioner `list_private_prompts`/`list_shared_prompts`/`list_shared_workspaces` i `pro_templates.py` (samma anon-beviljade RPC-mönster som `list_pro_templates`, anropar `get_workspace_prompts_for_key`/`list_shared_workspaces_for_key`), nya `@mcp.tool()`-funktioner + `tools/call`-dispatch + REST-endpoints i `mcp_server.py`, och nya poster i `hosted_guard.py`s allowlist.
- Generaliserade `HostedMetadataGuard.inspect_tool_args()` — den hårdkodade tidigare att bara `get_skill` fick ha argument alls, vilket hade blockerat `list_shared_workspace_prompts(workspace_id)`. Bytt mot en `elif`-kedja per tool istället för ett `tool_name != "get_skill"`-specialfall.
- Verifierat manuellt: `ast.parse` på alla tre ändrade filer, importerat `mcp_server`-modulen och kört payload-funktionerna utan nyckel (ger korrekt `workspace_status: no_key`), samt kört `HostedMetadataGuard` mot giltiga/ogiltiga tool-anrop (rätt avvisning av saknat `workspace_id`, rätt avvisning av oväntat argument på ett nollargument-tool, `get_skill` fortsatt opåverkad).
- Uppdaterade README.md och CLAUDE.md med de nya verktygen/endpointerna.

### Nuläge
- Committat (`d127f5b`) och pushat till `origin/main`. Användaren har deployat till VPS:en (`mcp.promptbanken.se`).
- End-to-end-verifierat mot produktion med en riktig Pro-nyckel som är medlem i en delad arbetsyta ("demoyta", `00f21df9-a140-4b85-8070-7d8032d28604`):
  - `GET /api/v1/my-shared-workspaces` → gav ytan korrekt.
  - `GET /api/v1/shared-workspaces/{workspace_id}/prompts` → gav den delade mallen ("demo", `content: "demo yta shared"`).
  - Samma endpoint med ett påhittat `workspace_id` → tom lista, inte andras mallar. Säkerhetsgränsen håller i produktion.
  - `GET /api/v1/my-private-prompts` → gav nyckelns egna två privata mallar.
  - Utan nyckel (bägge nya endpoints) → `workspace_status: "no_key"` + tom lista, ingen krasch.
- Testnyckeln var en dedikerad testnyckel (inte en nyckel i produktionsbruk) och är återkallad efter testet, eftersom den stod i klartext i chattsessionen.

### Nästa steg
- Inga kvarstående steg för denna del av portningen. Nästa naturliga steg om projektet fortsätter i samma spår: bygg motsvarande kontextverktyg-stöd i eventuella klientintegrationer/dokumentation som pekar mot den hostade adressen (t.ex. `mcp.html` i `promptbanken`-repot, som idag bara nämner de äldre verktygen).

## 2026-07-01

### Gjort
- Säkrade upp Supabase-åtkomsten: service-role-nyckeln (bypassar RLS helt, läs/skriv på alla tabeller) ersatt med en dedikerad Postgres-roll `mcp_server` som bara får `execute` på `app_private.verify_mcp_key` och `app_private.get_workspace_prompts` — inget annat.
- Ny migration `promptbanken/supabase/migrations/20260701_mcp_server_role.sql`: skapar rollen, ger `usage` på `app_private`-schemat och `execute` på de två funktionerna, samt `grant mcp_server to authenticator` så PostgREST kan växla roll. Rent additiv, rör inga befintliga rättigheter för `anon`/`authenticated`/`public` — verifierat att promptbankens frontend (anon/publishable-nyckel, RPC `ensure_personal_workspace`, tabellerna `content_items`/`api_keys` via RLS) inte berörs alls.
- Upptäckte under testning att Supabase har två separata auktoriseringslager: `apikey`-headern valideras av gatewayen (Kong) mot projektets kända nycklar (`anon`/`service_role`) och känner inte till anpassade roller, medan `Authorization: Bearer` är det PostgREST läser `role`-claim från för att välja Postgres-roll. Löst genom att skicka `SUPABASE_ANON_KEY` (publik, ofarlig) i `apikey` och en egen `mcp_server`-signerad JWT (`SUPABASE_MCP_ROLE_JWT`) i `Authorization`.
- Uppdaterade `supabase_repository.py`, `docker-compose.yml` och `CLAUDE.md` att använda de nya env-variablerna istället för `SUPABASE_SERVICE_ROLE_KEY`. Committat och pushat till `main` (`a9304b4`).
- Verifierat end-to-end i produktion: byggde om och startade om containern på VPS:en, curl mot `/mcp` med en riktig `X-MCP-Key` gav 23 skills totalt (21 publika + 2 workspace-prompts), containerloggarna visade `200 OK` på båda RPC-anropen.

### Frågetecken/kvarstående
- JWT-secreten (från Dashboard → Settings → API) stod i klartext i en chattsession under detta arbetspass — inte roterad än, se `TODO.md`.
- Den gamla `SUPABASE_SERVICE_ROLE_KEY`-raden i `.env` på VPS:en bör tas bort helt om den inte redan är det (ersatt av de två nya variablerna).

### Kringgått verktygsproblem
- `docker-compose up -d --force-recreate` (och även vanlig `up -d --build` vid recreate) kraschar med `KeyError: 'ContainerConfig'` på denna VPS — känd bugg i standalone `docker-compose` 1.29.2 mot images byggda med senare BuildKit-metadata. Kringgås med `docker-compose stop <tjänst> && docker-compose rm -f <tjänst> && docker-compose up -d <tjänst>` istället för `--force-recreate`.
- VPS:en har bara den äldre standalone `docker-compose` (bindestreck), inte `docker compose`-pluginet (mellanslag) — se [[project_vps_docker_compose_version]].

## 2026-06-30

### Gjort
- Granskade om Supabase-integrationen är klar. Slutsats: koden (`supabase_repository.py`) är skriven mot ett RPC-baserat schema (`app_private.verify_mcp_key`, `app_private.get_workspace_prompts`) som enligt `CLAUDE.md` ägs av det separata `promptbanken`-repot — inte verifierat live i denna session eftersom Supabase-MCP inte var ansluten.
- Uppdaterade `README.md`-avsnittet "Workspace-skills från Supabase" så det matchar den faktiska arkitekturen: `X-MCP-Key`-header per anrop (inte `PROMPTBANKEN_MCP_USER_KEY`-env), RPC-baserad nyckelverifiering (inte `mcp_keys`-tabellen), och en tydlig notis om att migrationen i det här repot är stale.

### Nuläge
- README var inaktuellt och beskrev en äldre arkitektur (tabellen `mcp_keys`, env-variabeln `PROMPTBANKEN_MCP_USER_KEY`) som inte längre stämmer med koden.
- Det är fortfarande inte verifierat att RPC-funktionerna faktiskt finns migrerade i den riktiga Supabase-databasen — det kräver tillgång till `promptbanken`-repot eller en ansluten Supabase-MCP.

### Nästa steg
- Verifiera RPC-funktionerna mot live-databasen (se `TODO.md`).
- Ta ställning till om den gamla `mcp_keys`-migrationen ska tas bort.

### Frågetecken
- Ska den stale migrationsfilen `20240629_create_mcp_keys.sql` tas bort helt, eller bara stå kvar som dokumenterat ej använd?

### Deploy till produktion (samma dag, senare på passet)
- Mergade `feature-mcp-streamable` → `main` (fast-forward, `76611bd` → `9ddd0f7`) och pushade till GitHub.
- På VPS:en (`mcp.promptbanken.se`, Caddy + Docker Compose v1 på `/home/wenstrompeter/mcp_promptbanken`): `git pull origin main`, satte upp `.env` med `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`, uppdaterade `/etc/caddy/Caddyfile` med routes för `/mcp`, `/api/v1/*`, `/openapi.json`, körde `docker-compose up -d --build`.
- Verifierade live: `/healthz` (skills_count 21), `/api/v1/skills` (öppen), `/sse` + `/messages/*` (befintlig klient återanslöt automatiskt utan problem), `/mcp` POST `tools/list` (gav exakt de 5 hosted metadata-tools, inga lokala läckte ut).
- Verifierade `/mcp` även från en riktig extern klient (ChatGPT) mot `https://mcp.promptbanken.se/mcp` utan nyckel — fungerar.
- Hittade och fixade en stale dubblettklon av repot inuti sig självt på VPS:en (`mcp_promptbanken/mcp_promptbanken/`, otrackad, oanvänd av Docker Compose) — lämnad orörd, städning är ett separat TODO.
- README hade fel i `SUPABASE_URL`-formatet under arbetet (en `/rest/v1/`-svans som skulle dubblera Supabase RPC-anropens path) — fångades och rättades innan rebuild.

### Beslut under deployen
- `PROMPTBANKEN_MCP_API_KEY` (global Bearer-token) lämnas medvetet tom i produktion. Servern ska vara helt öppen för `/sse` och `/mcp` (visar Promptbankens publika prompts), medan `X-MCP-Key`-headern per anrop är den separata mekanismen som lägger till en användares privata workspace-prompts ovanpå de öppna. Se [[project_promptbanken_overview]].

## 2026-06-15

### Gjort
- Skapade ett enkelt lokalt arbetsminne i projektroten.
- La till `PROJECT.md`, `TODO.md`, `LOG.md`, `DECISIONS.md`, `AGENTS.md` och `DATA-SAFETY.md`.
- Utökade `.gitignore` med skydd för hemligheter, lokal data, exporter, cache och vanliga byggartefakter.

### Nuläge
- Projektet är en minimal MCP-server för Promptbanken.
- Hosted-läget är avsett att vara metadata-only.
- Local-läget kan hantera användartext lokalt.
- Det fanns redan lokala ändringar i repot innan arbetsminnet skapades.

### Nästa steg
- Läs `PROJECT.md`, `TODO.md` och senaste posten i `LOG.md` vid nästa återstart.
- Verifiera att `.gitignore` inte blockerar filer som faktiskt ska versionshanteras.
- Fortsätt med verifiering av Streamable HTTP och hosted/local-lägen.

### Frågetecken
- Vilken MCP-klient ska vara primär målmiljö för verifiering?
- Ska arbetsminnet senare få en återkommande rutin, till exempel uppdatering inför varje commit?
