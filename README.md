# Promptbanken MCP

Promptbanken MCP är en minimal MCP-server som exponerar Promptbankens kommunala promptar som skills. Servern kör ingen AI-modell. Den levererar skill-metadata, promptmallar, hälsostatus och routinginstruktioner till en MCP-klient.

Projektet är byggt för två driftlägen:

- `hosted`: publik eller delad server där användarens uppgift och dokumenttext inte ska skickas till MCP-servern.
- `local`: lokal installation på användarens egen maskin där servern även kan routa, riskkontrollera och kompilera prompts lokalt.

## Snabbstart

Från repo-roten:

```powershell
npm run setup:python
npm run dev
```

`npm run dev` startar MCP över stdio och sätter `PROMPTBANKEN_MCP_MODE=local` om variabeln inte redan är satt.

För HTTP/SSE lokalt:

```powershell
npm run setup:python
npm run serve
```

`npm run serve` startar servern på `http://127.0.0.1:8000` och sätter `PROMPTBANKEN_MCP_MODE=hosted` om variabeln inte redan är satt.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

Exempel på svar:

```json
{
  "status": "ok",
  "service": "promptbanken-mcp",
  "version": "1.2.0",
  "mode": "hosted",
  "catalog": "open",
  "plan": "public",
  "message": "Detta är den öppna katalogen. Autentisera med API/MCP-nyckel för användar- eller Pro-mallar på app.promptbanken.se.",
  "catalog_prompt_count": 66
}
```

`catalog_prompt_count` är antalet publicerade mallar i den öppna katalogen
(samma data som `list_templates` returnerar), cachat 5 minuter server-side —
inte antalet legacy-`skills.json`-poster (de ligger i `legacyAuthenticated`
och är onåbara för ett publikt `/mcp`-anrop). Fältet utelämnas helt om
katalogen inte går att nå och ingen cachad siffra finns.

## Workspace-skills från Supabase

MCP-servern kan komplettera de statiska promptmallarna med användarens egna prompts från Supabase. Funktionen aktiveras via miljövariabler på servern och en MCP-nyckel som klienten skickar med varje anrop.

### Miljövariabler (server)

| Variabel | Beskrivning |
|---|---|
| `SUPABASE_URL` | Supabase-projektets URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role-nyckel — exponeras aldrig i frontend |

Lägg variablerna i `.env` (ingår i `.gitignore`) eller sätt dem i drift-/containerkonfigurationen (se `docker-compose.yml`).

### Klientkonfiguration

Klienten skickar sin MCP-nyckel som HTTP-headern `X-MCP-Key` i varje anrop — nyckeln sätts inte som miljövariabel på servern:

```json
{
  "mcpServers": {
    "promptbanken": {
      "url": "https://mcp.promptbanken.se/mcp/key",
      "headers": { "X-MCP-Key": "pb_mcp_..." }
    }
  }
}
```

### Generera en MCP-nyckel

1. Logga in i admin-UI:t.
2. Gå till **Inställningar → MCP-nycklar**.
3. Klicka **Ny nyckel** och välj ett namn.
4. Kopiera nyckeln direkt — den visas bara en gång.
5. Klistra in nyckeln som `X-MCP-Key` i MCP-klientens konfiguration.

Free-plan tillåter max en aktiv nyckel per workspace.

### Hur det fungerar

- Servern hashar nyckeln (sha256) och verifierar den via RPC:n `app_private.verify_mcp_key`.
- Om nyckeln är giltig hämtas aktiva prompts för workspacet via RPC:n `app_private.get_workspace_prompts`.
- Workspace-skills läggs sist i `list_skills`-svaret, märkta med `"category": "Arbetsyta"`.
- Om nyckeln saknas eller är ogiltig (inklusive återkallad) visas inga workspace-skills, men de publika skillsen visas alltid — katalogen blockeras aldrig helt.
- `list_skills_simple` och REST-endpointen `GET /api/v1/skills` inkluderar då fälten `"workspace_status": "invalid_key"` och `"workspace_message": "API-nyckeln är ogiltig eller återkallad. Endast publika mallar visas."` så att klienten kan informera användaren om att nyckeln inte fungerar, istället för att det tyst ser ut som att inga privata prompts finns. Skickas ingen nyckel alls utelämnas båda fälten helt (oförändrat beteende).
- `GET /healthz` (och MCP-verktyget/JSON-RPC-metoden `health_check`) returnerar alltid `catalog`/`plan`/`message` baserat på samma nyckel: `plan` är `public`/`free`/`pro`, `catalog` är `open`/`workspace`/`pro`. Utan nyckel eller med en ogiltig/återkallad nyckel visas `public`/`open`. Till skillnad från `workspace_status` på `/api/v1/skills` utelämnas dessa fält aldrig — `health_check` ska alltid ge en fullständig bild av katalogläget.
- `list_my_prompts`/REST `GET /api/v1/my-prompts` listar **bara** den anropande nyckelns egna sparade prompts (`source == "workspace"`), separat från `list_skills`/`list_skills_simple` som blandar in dem bland de publika mallarna. Löser att MCP-klienter (t.ex. ChatGPT) annars inte hittar "mina prompts" utan att känna till `source`-fältet eller `workspace_`-id-prefixet. Utan nyckel: `"workspace_status": "no_key"`. Med ogiltig/återkallad nyckel: `"workspace_status": "invalid_key"`. Med giltig nyckel: `"workspace_status": "ok"` och en lista med `id`/`display_name`/`description`/`category`/`risk_level`/`risk_message` per sparad prompt (hämta full prompttext separat via `get_skill(id, include_prompt=true)`).
- RPC:n `verify_mcp_key` skiljer idag inte på orsak (saknad/återkallad/inaktiverat workspace) — `workspace_status` är därför generisk (`invalid_key`), inte `revoked_key` specifikt. Se `TODO.md` för en eventuell utökning av RPC:n.
- Statiska skills fungerar alltid, oavsett om Supabase-integration är konfigurerad.

### Kontextstyrda Pro-verktyg (Pro + Delad arbetsyta)

Tre verktyg speglar den kontextstyrda MCP-modellen som infördes i `promptbanken`-repot 2026-07-06 ("Pro + Delad arbetsyta") och anropar samma nyckelhash-baserade RPC:er (`get_workspace_prompts_for_key`, `list_shared_workspaces_for_key`) som den lokala stdio-servern där — se `mcp-server/server/pro_templates.py`:

- `list_my_private_prompts`/REST `GET /api/v1/my-private-prompts` — nyckelns egna privata Pro-prompts (personlig yta). Returnerar aldrig andra medlemmars privata prompts eller organisationsprompts.
- `list_my_shared_workspaces`/REST `GET /api/v1/my-shared-workspaces` — discovery: vilka delade arbetsytor (`shared_workspace_addons`) nyckelns ägare är medlem i (`id` + `name`).
- `list_shared_workspace_prompts(workspace_id)`/REST `GET /api/v1/shared-workspaces/{workspace_id}/prompts` — delade mallar från EN specifik delad arbetsyta. Kräver ett `workspace_id` från `list_my_shared_workspaces`; en personlig Pro-nyckel kan aldrig läsa en yta den inte tillhör (spärren sitter i RPC:n, inte bara i klienten).

Alla tre returnerar `"workspace_status": "no_key"` + tom lista utan `X-MCP-Key`/`Authorization`.

### Valvet — personligt prompt/assistant-valv (2026-07-16)

Sex verktyg för nyckelns egna Valvet-insättningar (`mcp-server/server/vault.py`), skilda från `list_my_prompts`/`save_workspace_prompt` genom en egen `module='valvet'`-markering i `promptbanken`-repots `content_items`:

- `list_my_items`/REST `GET /api/v1/vault/items` — nyckelns egna Valvet-insättningar (personligt prompt/assistant-valv, `module='valvet'`). Utesluter arkiverade om inte `status=archived` skickas explicit.
- `search_my_items`/REST `GET /api/v1/vault/items/search?query=...` — söker titel/innehåll/kategori bland nyckelns Valvet-insättningar.
- `get_my_item`/REST `GET /api/v1/vault/items/{id}` — hämtar en insättning i sin helhet, inklusive `updated_at` (krävs för `update_my_item`).
- `save_my_item`/REST `POST /api/v1/vault/items` — skapar en ny insättning. Kräver `idempotency_key`. Free-nycklar: max 5 sparningar/kalendermånad. Pro: ingen månadskvot.
- `update_my_item`/REST `PATCH /api/v1/vault/items/{id}` — uppdaterar en insättning. Pro-only. Kräver `expected_updated_at` (optimistic locking — avvisas med tydligt fel om posten ändrats sedan den hämtades).
- `archive_my_item`/REST `POST /api/v1/vault/items/{id}/archive` — arkiverar eller (med `restore:true`) återställer en insättning. Pro-only. Kräver `confirm:true`.

**Status:** en Valvet-post har alltid en av `draft`/`review`/`published`/`archived` i databasens enum, men bara `draft` (standard vid skapande) och `archived` går att nå via Valvets verktyg i Fas 1 — `list_my_items`s `status`-filter accepterar bara dessa två. Posten är fullt sparad och privat till nyckelns ägare direkt vid `save_my_item`; `draft` beskriver bara redigeringsläge, inte om posten finns eller vem som ser den (Valvet-poster har ingen egen synlighetskolumn — de är alltid privata). `review`/`published` är reserverade för ett framtida gransknings-/publiceringsflöde; ingen klient (webb eller MCP) kan sätta dem idag.

### Supabase-migration

RPC-funktionerna och tabellerna för detta ägs av `promptbanken`-repot, inte detta repo. Migrationen ligger där under `supabase/migrations/20240629_mcp_rpc_functions.sql`.

## Publiceringsgräns

| Yta | Endpoint | Auth | Verktyg | Publiceras hos OpenAI |
|---|---|---|---|---|
| Promptbanken Öppen | `/mcp` | Ingen | Publik katalog, read-only | Ja |
| Valvet kompatibilitet | `/mcp/key` | `X-MCP-Key` eller Bearer MCP-nyckel | Free/Pro Valvet | Nej |
| Valvet framtida | `/mcp` | OAuth 2.1 | Publik katalog + personligt Valv | Efter separat release |

Paketaktivering ingår för både Free och Pro; planerna skiljs genom kvoter.

### Auth för `/mcp/key`

`/mcp` är fortsatt anonym; den globala spärren undantar den publika ytan.

Det finns exakt två giltiga lägen för `/mcp/key`:

1. Om `PROMPTBANKEN_MCP_API_KEY` är TOM: använd workspace/user key via `X-MCP-Key: <nyckel>` eller `Authorization: Bearer <workspace-nyckel>`.
2. Om `PROMPTBANKEN_MCP_API_KEY` är SATT: middleware kräver `Authorization: Bearer <global-nyckel>` och användarens workspace-nyckel måste samtidigt skickas separat via `X-MCP-Key: <workspace-nyckel>`.

## Data och integritet

Den publika `/mcp`-ytan är en read-only prompt- och skill-server. `/mcp/key` kan även exponera autentiserade workspace- och Valvet-tools.

På den öppna `/mcp`-ytan sparas inte användarens råtext, promptanrop eller svar. För `/mcp/key` lagrar läsverktyg inte råtext, men uttryckliga create/update/copy/activate/deactivate-anrop skriver den data användaren valt till Valvet/Supabase.

Den öppna `/mcp`-ytan läser bara:

- `mcp-server/skills.json`
- `mcp-server/prompts/*.txt`

På den publika `/mcp`-ytan exponeras bara tools som returnerar metadata, promptmallar, hälsostatus och klientinstruktioner:

- `health_check`
- `get_client_routing_instructions`
- `list_templates`
- `search_templates`
- `get_template`
- `list_packages`
- `get_package`
- `list_package_prompts`
- `recommend_packages`

Privata och skrivande tools hör till den key-authenticated `/mcp/key`-ytan och publiceras inte hos OpenAI.

Klienten ska då göra skill-routing, riskkontroll, anonymisering och promptkompilering lokalt. Skicka inte användarens uppgift, dokumenttext, personuppgifter eller sekretessbelagd information till den öppna `/mcp`-ytan.

I `local`-läge kan servern dessutom exponera tools som tar emot användartext:

- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

Texten bearbetas då bara på användarens egen maskin. Servern skickar inte vidare användarinput till externa AI-leverantörer.

## Säkerhet

Hosted-läget är den rekommenderade ytan för publik drift.

Viktiga säkerhetsbeslut:

- Servern kör ingen AI-modell och kan därför inte promptinjiceras i klassisk mening.
- Den öppna `/mcp`-ytan tar inte emot rå användartext för routing, riskkontroll eller promptkompilering.
- Hosted-läget har en metadata-guard på `/messages/` som varnar payload-fritt om klienten skickar oväntade tools eller argument.
- `skill_id` valideras strikt med `^[a-z0-9_-]{2,50}$`.
- Ogiltiga eller saknade skills returnerar strukturerade felobjekt med säkra felkoder.
- Promptmallarna innehåller en standardregel om att användarens underlag ska behandlas som data, inte som instruktioner.
- `output_schema` returneras i skill-metadata så klienter kan visa eller validera förväntad svarsstruktur.
- `display_name`, `category`, `example_phrases` och `risk_message` returneras så klienter kan bygga en enklare användarvy.
- Docker-driften binder bara porten till `127.0.0.1:8000`.
- Containern kör read-only, utan extra Linux capabilities och med `no-new-privileges:true`.

Exempel på strukturerat fel:

```json
{
  "error": {
    "code": "INVALID_SKILL_ID",
    "message": "Skill id contains invalid characters",
    "safe_to_show_user": true
  }
}
```

För publik drift rekommenderas:

- Kör `PROMPTBANKEN_MCP_MODE=hosted`.
- Publicera bara promptar som är avsedda att vara offentliga.
- Lägg reverse proxy framför Docker-porten.
- Sätt request body-limit i reverse proxy, till exempel `64KB`.
- Använd rate limiting i reverse proxy eller framförliggande tjänst om servern är öppen på internet.
- Skriv tydligt i klienten att användare inte ska skicka personuppgifter eller sekretessbelagd information.

### Hosted metadata-guard

Hosted MCP är avsett som metadata-only. Det betyder att klienten bara ska anropa katalog-, health- och mallhämtningstools. Servern har därför en guard före MCP-transportens `/messages/`-handler.

I standardläge varnar guarden utan att blockera:

```text
PROMPTBANKEN_MCP_HOSTED_GUARD=warn
```

Den loggar bara teknisk avvikelse, till exempel:

```text
hosted_payload_warning path=/messages reason=unexpected_arguments method=tools/call tool=get_skill
```

Den loggar inte request body eller användartext.

Tillåtna hosted-tools och argument:

```text
list_skills: {}
list_skills_simple: {}
health_check: {}
get_client_routing_instructions: {}
get_skill: { skill_id, include_prompt }
```

När klientkedjan är verifierad kan guarden sättas i blockläge:

```text
PROMPTBANKEN_MCP_HOSTED_GUARD=block
```

Blockläge kan påverka klienter som skickar extra kontext eller rå användartext i MCP-meddelanden. Det är rätt beteende för strikt metadata-only, men bör testas mot aktuell klient innan publik drift.

### Följ upp metadata-guard i drift

Rekommenderat arbetssätt är att köra guarden i `warn` ett tag, analysera loggarna och därefter besluta om klienten kan spärras hårdare.

1. Kör med soft guard:

```env
PROMPTBANKEN_MCP_HOSTED_GUARD=warn
```

2. Följ loggar live:

```bash
docker compose logs -f --tail=100 promptbanken-mcp
```

Om servern använder äldre Compose:

```bash
docker-compose logs -f --tail=100 promptbanken-mcp
```

3. Leta särskilt efter:

```text
hosted_payload_warning
```

Exempel:

```text
hosted_payload_warning path=/messages reason=unexpected_arguments method=tools/call tool=get_skill
```

Tolkning:

- Inga `hosted_payload_warning`: klienten verkar följa metadata-only-flödet.
- `unexpected_arguments`: klienten skickar extra argument, potentiellt råtext.
- `unexpected_tool`: klienten försöker anropa ett tool som inte ska finnas i hosted, till exempel `route_skill`.
- `invalid_skill_id`: klienten skickar ett ogiltigt skill-id.
- `invalid_json` eller `invalid_message_shape`: något skickar trasigt eller oväntat format.

Normala MCP-protokollmetoder som `initialize`, `notifications/initialized`, `tools/list`, `resources/list` och `ping` ska inte räknas som rå användartext. De behövs för att klienten ska kunna ansluta och upptäcka tools.

4. Sammanfatta loggar efter en tids drift:

```bash
npm run logs:summary -- --tail 10000 --summary-only
```

5. Sök direkt efter guard-varningar:

```bash
docker compose logs --tail=10000 promptbanken-mcp | grep hosted_payload_warning
```

Om servern använder äldre Compose:

```bash
docker-compose logs --tail=10000 promptbanken-mcp | grep hosted_payload_warning
```

Om varningar förekommer: behåll `warn`, analysera klientbeteendet och justera klienten så att routing, riskkontroll och promptkompilering sker lokalt.

Om inga varningar förekommer under verklig användning kan guarden testas i blockläge:

```env
PROMPTBANKEN_MCP_HOSTED_GUARD=block
```

Starta sedan om containern och verifiera att klienten fortfarande kan använda `list_skills`, `list_skills_simple`, `get_skill`, `health_check` och `get_client_routing_instructions`.

## Loggning

Loggningen är teknisk och ska inte innehålla känsliga payloads.

Det som loggas:

- serverstart, driftläge och antal skills
- HTTP-serverns host, port och läge
- `/healthz`-anrop
- SSE connect/disconnect och anslutningens varaktighet
- tool-namn, till exempel `list_skills`, `get_skill`, `health_check`
- `skill_id` vid `get_skill`, eftersom skill-id kommer från en strikt allowlist/validerad identifierare
- om `include_prompt` är `true` eller `false`
- nekad auth som teknisk händelse
- hosted metadata-guard-varningar med orsak, metod och tool-namn
- i local-läge: booleska flaggor som `has_user_input=True`, inte själva texten

Det som inte ska loggas:

- request body
- användarens uppgift eller dokumenttext
- prompttext
- kompilerade prompts
- personuppgifter
- bearer tokens eller headers
- klient-IP

Loggnivå styrs med:

```env
MCP_LOG_LEVEL=INFO
```

Visa Docker-loggar:

```bash
docker compose logs -f --tail=100 promptbanken-mcp
```

Om servern använder äldre Compose:

```bash
docker-compose logs -f --tail=100 promptbanken-mcp
```

Sammanfatta loggar:

```bash
npm run logs:summary
npm run logs:summary -- --tail 2000
npm run logs:summary -- --summary-only
```

Sammanfattningsskriptet visar senaste loggrader, antal tool-anrop, antal SSE-anslutningar, health checks, nekad auth och vilka promptar som hämtas oftast via `get_skill`. Det bygger bara på tekniska loggrader och läser inte request body, prompttext eller användartext.

## Skills

Skills definieras i `mcp-server/skills.json` och pekar på promptmallar i `mcp-server/prompts/`.

För teknisk katalog används `list_skills`. För en enklare användarvy används `list_skills_simple`, som grupperar mallarna i kategorier och visar exempel på vad användaren kan skriva.

När en ny prompt läggs till ska guiden i `docs/add-new-prompt.md` följas.

### Mallkatalogen (öppen)

Verktyget `list_templates` och REST-endpointen `GET /api/v1/pro-templates` hämtar hela Promptbanken-mallkatalogen via RPC:n `get_pro_templates_for_mcp_key` (definierad i `promptbanken`-repot, `supabase/migrations/20260703100000_pro_templates_for_mcp_key.sql`). Katalogen är öppen sedan 2026-07-19 (se `DECISIONS.md`) — ingen nyckel eller plan krävs, alla mallar returneras alltid med fullständig `prompt_text`. RPC-namnet, REST-pathen (`/pro-templates`) och Python-modulen (`pro_templates.py`) är historiska och byts inte i denna omgång — bara det MCP-verktygsnamn klienter ser (`list_pro_templates` → `list_templates`).

`search_templates(query?, role?, area?, risk_level?, limit?)` och `get_template(template_id)` (2026-07-20, se `DECISIONS.md`) löser att klienter annars måste hämta alla 42 kompletta promptar via `list_templates` bara för att hitta en mall. Ingen ny RPC eller REST-endpoint — filtrerar klient-sidigt (i Python-processen, samma anrop till `get_pro_templates_for_mcp_key`) ovanpå samma data som `list_templates`/`recommend_packages` redan använder. `search_templates` returnerar lättviktiga sammanfattningar (utan `prompt_text`) med `total_matches`/`returned`; `role`-parametern återanvänder samma rollmappning som `recommend_packages` och begränsar till matchande områden bara om rollen känns igen (`role_recognized: true` i svaret), annars ingen begränsning. `get_template(template_id)` hämtar en enskild mall i sin helhet (med `prompt_text`) för vald träff.

RPC:n är beviljad direkt till `anon` — att känna till nyckelns sha256-hash är i sig beviset på behörighet (samma modell som `verify_mcp_key`), så det krävs bara `SUPABASE_URL`/`SUPABASE_ANON_KEY`, ingen `SUPABASE_MCP_ROLE_JWT`.

Nuvarande skill-id:

- `alt_text_bild`
- `anteckningar`
- `beslutsunderlag`
- `checklista`
- `diskussionsfragor`
- `enkel_infografik`
- `faq`
- `ikon_symbolbild`
- `illustration_informationsutskick`
- `informationsutskick`
- `kallelse`
- `klarsprak`
- `mejl`
- `nyckelord`
- `presentationstitelbild`
- `reflektion`
- `rutin`
- `sammanfattning`
- `samtalskompas`
- `tydlighetskoll`
- `tvaversioner`

## Struktur

```text
.
|-- docker-compose.yml
|-- package.json
|-- README.md
`-- mcp-server/
    |-- Dockerfile
    |-- package.json
    |-- requirements.txt
    |-- skills.json
    |-- prompts/
    |-- scripts/
    `-- server/
```

Rotens `package.json` är en tunn genväg till script i `mcp-server/`.

## Kommandon

```powershell
npm run setup:python   # skapa/uppdatera lokal Python-miljö
npm run dev            # starta MCP över stdio i local-läge
npm run serve          # starta HTTP/SSE-server i hosted-läge
npm run check:python   # kontrollera Python-miljön
npm run logs:summary   # visa loggar, antal anrop och top prompts
```

Docker:

```powershell
docker compose up -d --build
docker compose ps
docker compose down
```

Kontroll:

```powershell
npm run check:python
docker compose config --quiet
```

## Miljövariabler

```text
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_LOG_LEVEL=INFO
PROMPTBANKEN_MCP_MODE=hosted
PROMPTBANKEN_MCP_API_KEY=
PROMPTBANKEN_MCP_VERSION=1.1.0
PROMPTBANKEN_MCP_HOSTED_GUARD=warn
PROMPTBANKEN_MCP_ALLOWED_ORIGINS=https://mcp.promptbanken.se
```

Tillåtna värden för `PROMPTBANKEN_MCP_MODE`:

- `hosted`: publicerat läge utan tools som tar emot användartext.
- `local`: lokal installation med routing, promptkompilering och riskkontroll.

`PROMPTBANKEN_MCP_API_KEY` är den globala servernyckeln för det SATT-läge som beskrivs i avsnittet **Auth för `/mcp/key`**. Lämna den tom för workspace/user-key-läget. `/mcp` förblir anonym.

`/healthz` är undantagen från API-nyckelkravet.

## MCP och REST

Den publika remote MCP-ytan är Streamable HTTP på `/mcp`. Den key-authenticated kompatibilitetsytan använder `/mcp/key`:

```text
POST /mcp
GET  /mcp
POST /mcp/key
GET  /mcp/key
```

REST-ytan är read-only:

```text
GET  /api/v1/skills
GET  /api/v1/skills/simple
GET  /api/v1/skills/{skill_id}
GET  /api/v1/skills/{skill_id}/prompt
GET  /api/v1/routing-instructions
GET  /openapi.json
```

Legacy HTTP/SSE finns kvar för äldre klienter:

```text
GET  /sse
POST /messages/
GET  /healthz
```

Rekommenderad publik MCP-adress:

```text
https://mcp.promptbanken.se/mcp
```

Legacy-adress:

```text
https://mcp.promptbanken.se/sse
```

## MCP-konfiguration

Lokal stdio:

```json
{
  "mcpServers": {
    "promptbanken": {
      "command": "npm",
      "args": ["run", "--silent", "dev"],
      "cwd": "C:\\path\\to\\promptbanken\\mcp-server"
    }
  }
}
```

Remote Streamable HTTP:

```json
{
  "mcpServers": {
    "promptbanken": {
      "url": "https://mcp.promptbanken.se/mcp/key",
      "headers": {
        "Authorization": "Bearer global-nyckel-...",
        "X-MCP-Key": "pb_mcp_workspace_..."
      }
    }
  }
}
```

Exemplet använder SATT `PROMPTBANKEN_MCP_API_KEY` och skickar globalnyckeln separat från workspace-nyckeln. Använd `/mcp` utan headers för den öppna katalogen. Med TOM `PROMPTBANKEN_MCP_API_KEY` räcker `X-MCP-Key` eller `Authorization: Bearer <workspace-nyckel>` på `/mcp/key`.

## Docker och VPS

`docker-compose.yml` startar servern i `hosted`-läge och binder porten endast till VPS:ens localhost:

```text
127.0.0.1:8000
```

Publik trafik ska gå via reverse proxy, till exempel Caddy:

```caddyfile
mcp.promptbanken.se {
    reverse_proxy 127.0.0.1:8000
}
```

Containern är härdad för read-only drift:

- `read_only: true`
- port bara på `127.0.0.1:8000`
- `no-new-privileges:true`
- `cap_drop: ALL`
- temporär skrivyta via `tmpfs` på `/tmp`

För publik demo kan servern köras utan API-nyckel. För intern eller längre drift, sätt API-nyckel i `.env` bredvid `docker-compose.yml`:

```env
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lång-slumpad-nyckel
```

## Client-side routing

I `hosted`-läge ska klienten:

1. Hämta användarvänlig katalog med `list_skills_simple` eller full metadata med `list_skills`.
2. Välja relevant skill lokalt utifrån användarens uppgift.
3. Validera `skill_id` mot listan från `list_skills`.
4. Hämta vald promptmall med `get_skill`.
5. Använda `display_name`, `category`, `example_phrases`, `risk_message` och `output_schema` i klientens användarvy.
6. Visa topp 2-3 föreslagna mallar om användaren inte valt explicit.
7. Kontrollera, anonymisera och sammanställa prompten lokalt.
8. Avgränsa användarens underlag tydligt som data, inte instruktioner.

Routing ska inte matcha tungt på vanliga fyllnadsord som `skriv`, `ett`, `till`, `som` och `vanligt`. Använd stopwords och vikta träffar i denna ordning:

1. skill-id
2. skillens namn
3. intents
4. description
5. övrig metadata

En explicit träff på till exempel `informationsutskick` ska väga tyngre än generiska ord.
