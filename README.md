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
  "skills_count": 15
}
```

## Installationsguide

### Så installerar du stdio lokalt

Använd detta när MCP-klienten kör på samma dator som Promptbanken MCP. Det är rätt läge för lokal utveckling och för funktioner som får bearbeta användartext lokalt.

1. Klona repot:

```bash
git clone https://github.com/BUsavsjo/mcp_promptbanken.git
cd mcp_promptbanken
```

2. Installera Python-miljön:

```bash
npm run setup:python
```

3. Testa att servern startar i stdio-läge:

```bash
npm run dev
```

4. Lägg till servern i MCP-klienten:

```json
{
  "mcpServers": {
    "promptbanken": {
      "command": "npm",
      "args": ["run", "--silent", "dev"],
      "cwd": "/path/to/mcp_promptbanken/mcp-server"
    }
  }
}
```

På Windows kan `cwd` till exempel vara:

```text
C:\\path\\to\\mcp_promptbanken\\mcp-server
```

I stdio-läge sätter startskriptet `PROMPTBANKEN_MCP_MODE=local` om variabeln inte redan är satt. Då kan local-tools som `route_skill`, `compile_skill_prompt` och `check_input_risk` exponeras.

### Så installerar du remote MCP på server

Använd detta när Promptbanken MCP ska köras på en VPS eller annan server och nås via HTTP/SSE. Det är rekommenderat för publik demo och delad drift.

1. Klona repot på servern:

```bash
git clone https://github.com/BUsavsjo/mcp_promptbanken.git
cd mcp_promptbanken
```

2. Starta med Docker Compose:

```bash
docker compose up -d --build
```

Om servern använder äldre Compose:

```bash
docker-compose up -d --build
```

3. Kontrollera att containern kör:

```bash
docker compose ps
```

4. Kontrollera health endpoint:

```bash
curl http://127.0.0.1:8000/healthz
```

5. Lägg reverse proxy framför servern, till exempel Caddy:

```caddyfile
mcp.promptbanken.se {
    request_body {
        max_size 64KB
    }

    reverse_proxy 127.0.0.1:8000
}
```

6. Lägg till remote MCP i klienten:

```json
{
  "mcpServers": {
    "promptbanken": {
      "url": "https://mcp.promptbanken.se/sse"
    }
  }
}
```

För publik drift ska `PROMPTBANKEN_MCP_MODE=hosted` användas. Då exponeras bara:

- `list_skills`
- `get_skill`
- `health_check`
- `get_client_routing_instructions`

### Så kollar du loggar

Visa senaste loggar:

```bash
docker compose logs --tail=100 promptbanken-mcp
```

Följ loggar live:

```bash
docker compose logs -f --tail=100 promptbanken-mcp
```

Om servern använder äldre Compose:

```bash
docker-compose logs -f --tail=100 promptbanken-mcp
```

Visa sammanfattning med antal anrop och top prompts:

```bash
npm run logs:summary
```

Mer historik:

```bash
npm run logs:summary -- --tail 2000
```

Bara sammanfattning:

```bash
npm run logs:summary -- --summary-only
```

Sammanfattningen visar tool-anrop, SSE-anslutningar, health checks, nekad auth och vilka promptar som hämtas oftast via `get_skill`.

## Data och integritet

Promptbanken MCP är en read-only prompt- och skill-server.

Servern sparar inte användarens text, promptanrop eller svar i databas eller fil. Den har ingen databas och ingen skrivande lagring för användarinput.

Servern läser bara:

- `mcp-server/skills.json`
- `mcp-server/prompts/*.txt`

I `hosted`-läge exponeras bara tools som returnerar metadata, promptmallar, hälsostatus och klientinstruktioner:

- `list_skills`
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
- `skill_id` valideras strikt med `^[a-z0-9_-]{2,50}$`.
- Ogiltiga eller saknade skills returnerar strukturerade felobjekt med säkra felkoder.
- Promptmallarna innehåller en standardregel om att användarens underlag ska behandlas som data, inte som instruktioner.
- `output_schema` returneras i skill-metadata så klienter kan visa eller validera förväntad svarsstruktur.
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

För publik drift utan auth rekommenderas:

- Kör `PROMPTBANKEN_MCP_MODE=hosted`.
- Publicera bara promptar som är avsedda att vara offentliga.
- Lägg reverse proxy framför Docker-porten.
- Sätt request body-limit i reverse proxy, till exempel `64KB`.
- Använd rate limiting i reverse proxy eller framförliggande tjänst om servern är öppen på internet.
- Skriv tydligt i klienten att användare inte ska skicka personuppgifter eller sekretessbelagd information.

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
```

Tillåtna värden för `PROMPTBANKEN_MCP_MODE`:

- `hosted`: publicerat läge utan tools som tar emot användartext.
- `local`: lokal installation med routing, promptkompilering och riskkontroll.

Om `PROMPTBANKEN_MCP_API_KEY` är satt krävs:

```text
Authorization: Bearer <nyckel>
```

`/healthz` är undantagen från API-nyckelkravet.

## HTTP/SSE

Nuvarande server använder MCP över HTTP/SSE:

```text
GET  /sse
POST /messages/
GET  /healthz
```

Rekommenderad publik adress:

```text
https://mcp.promptbanken.se/sse
```

På sikt kan endpointen bli:

```text
https://mcp.promptbanken.se/mcp
```

Det kräver uppgradering till nyare MCP Streamable HTTP-transport.

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

Remote HTTP/SSE:

```json
{
  "mcpServers": {
    "promptbanken": {
      "url": "https://mcp.promptbanken.se/sse",
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

1. Hämta skill-metadata med `list_skills`.
2. Välja relevant skill lokalt utifrån användarens uppgift.
3. Validera `skill_id` mot listan från `list_skills`.
4. Hämta vald promptmall med `get_skill`.
5. Använda skillens `output_schema` som stöd för förväntad svarsstruktur.
6. Kontrollera, anonymisera och sammanställa prompten lokalt.
7. Avgränsa användarens underlag tydligt som data, inte instruktioner.

Routing ska inte matcha tungt på vanliga fyllnadsord som `skriv`, `ett`, `till`, `som` och `vanligt`. Använd stopwords och vikta träffar i denna ordning:

1. skill-id
2. skillens namn
3. intents
4. description
5. övrig metadata

En explicit träff på till exempel `informationsutskick` ska väga tyngre än generiska ord.
