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
  "version": "1.1.0",
  "mode": "hosted",
  "skills_count": 16
}
```

## Data och integritet

Promptbanken MCP är en read-only prompt- och skill-server.

Servern sparar inte användarens text, promptanrop eller svar i databas eller fil. Den har ingen databas och ingen skrivande lagring för användarinput.

Servern läser bara:

- `mcp-server/skills.json`
- `mcp-server/prompts/*.txt`

I `hosted`-läge exponeras bara tools som returnerar metadata, promptmallar, hälsostatus och klientinstruktioner:

- `list_skills`
- `list_skills_simple`
- `get_skill`
- `health_check`
- `get_client_routing_instructions`

Klienten ska då göra skill-routing, riskkontroll, anonymisering och promptkompilering lokalt. Skicka inte användarens uppgift, dokumenttext, personuppgifter eller sekretessbelagd information till hosted-servern.

I `local`-läge kan servern dessutom exponera tools som tar emot användartext:

- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

Texten bearbetas då bara på användarens egen maskin. Servern skickar inte vidare användarinput till externa AI-leverantörer.

## Säkerhet

Hosted-läget är den rekommenderade ytan för publik drift.

Viktiga säkerhetsbeslut:

- Servern kör ingen AI-modell och kan därför inte promptinjiceras i klassisk mening.
- Hosted-läget tar inte emot rå användartext för routing, riskkontroll eller promptkompilering.
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

Nuvarande skill-id:

- `anteckningar`
- `beslutsunderlag`
- `checklista`
- `diskussionsfragor`
- `faq`
- `informationsutskick`
- `kallelse`
- `klarsprak`
- `mejl`
- `nyckelord`
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
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lång-slumpad-nyckel
PROMPTBANKEN_MCP_VERSION=1.1.0
PROMPTBANKEN_MCP_HOSTED_GUARD=warn
PROMPTBANKEN_MCP_ALLOWED_ORIGINS=https://mcp.promptbanken.se
```

Tillåtna värden för `PROMPTBANKEN_MCP_MODE`:

- `hosted`: publicerat läge utan tools som tar emot användartext.
- `local`: lokal installation med routing, promptkompilering och riskkontroll.

Om `PROMPTBANKEN_MCP_API_KEY` är satt krävs:

```text
Authorization: Bearer <nyckel>
```

`/healthz` är undantagen från API-nyckelkravet.

## MCP och REST

Primär remote MCP-yta är Streamable HTTP på en enda endpoint:

```text
POST /mcp
GET  /mcp
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
      "url": "https://mcp.promptbanken.se/mcp",
      "headers": {
        "Authorization": "Bearer byt-till-en-lång-slumpad-nyckel"
      }
    }
  }
}
```

Om ingen `PROMPTBANKEN_MCP_API_KEY` är satt på servern kan `headers` utelämnas.

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
