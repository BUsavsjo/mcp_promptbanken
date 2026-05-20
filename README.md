# Promptbanken MCP

Promptbanken MCP ar en minimal MCP-server som exponerar Promptbankens kommunala promptar som skills. Servern kor ingen AI-modell. Den levererar skill-metadata, promptmallar och routinginstruktioner till en MCP-klient.

Projektet ar byggt for tva driftlagen:

- `hosted`: publik eller delad server dar anvandarens uppgift och dokumenttext inte ska skickas till MCP-servern.
- `local`: lokal installation pa anvandarens egen maskin dar servern aven kan routa, riskkontrollera och kompilera prompts lokalt.

## Snabbstart

Fran repo-roten:

```powershell
npm run setup:python
npm run dev
```

`npm run dev` startar MCP over stdio och satter `PROMPTBANKEN_MCP_MODE=local` om variabeln inte redan ar satt.

For HTTP/SSE lokalt:

```powershell
npm run setup:python
npm run serve
```

`npm run serve` startar servern pa `http://127.0.0.1:8000` och satter `PROMPTBANKEN_MCP_MODE=hosted` om variabeln inte redan ar satt.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

## Data och integritet

Promptbanken MCP ar en read-only prompt- och skill-server.

Servern sparar inte anvandarens text, promptanrop eller svar i databas eller fil. Den har ingen databas och ingen skrivande lagring for anvandarinput.

Servern laser bara:

- `mcp-server/skills.json`
- `mcp-server/prompts/*.txt`

I `hosted`-lage exponeras bara tools som returnerar metadata, promptmallar och klientinstruktioner:

- `list_skills`
- `get_skill`
- `health_check`
- `get_client_routing_instructions`

Klienten ska da gora skill-routing, riskkontroll, anonymisering och promptkompilering lokalt. Skicka inte anvandarens uppgift, dokumenttext, personuppgifter eller sekretessbelagd information till hosted-servern.

I `local`-lage kan servern dessutom exponera tools som tar emot anvandartext:

- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

Texten bearbetas da bara pa anvandarens egen maskin. Servern skickar inte vidare anvandarinput till externa AI-leverantorer.

Loggning ska hallas teknisk. Logga inte `user_input`, `user_task`, hela prompts eller personuppgifter.

## Skills

Skills definieras i `mcp-server/skills.json` och pekar pa promptmallar i `mcp-server/prompts/`.

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

Rotens `package.json` ar en tunn genvag till script i `mcp-server/`.

## Kommandon

```powershell
npm run setup:python   # skapa/uppdatera lokal Python-miljo
npm run dev            # starta MCP over stdio i local-lage
npm run serve          # starta HTTP/SSE-server i hosted-lage
npm run check:python   # kontrollera Python-miljon
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

Loggsammanfattning:

```powershell
npm run logs:summary
npm run logs:summary -- --tail 2000
npm run logs:summary -- --summary-only
```

Skriptet laser Docker Compose-loggar och visar senaste loggrader, antal tool-anrop och vilka promptar som hamtas oftast via `get_skill`. Det bygger pa tekniska loggrader och laser inte request body, prompttext eller anvandartext.

## Miljovariabler

```text
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_LOG_LEVEL=INFO
PROMPTBANKEN_MCP_MODE=hosted
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lang-slumpad-nyckel
PROMPTBANKEN_MCP_VERSION=1.1.0
```

Tillatna varden for `PROMPTBANKEN_MCP_MODE`:

- `hosted`: publicerat lage utan tools som tar emot anvandartext.
- `local`: lokal installation med routing, promptkompilering och riskkontroll.

Om `PROMPTBANKEN_MCP_API_KEY` ar satt kravs:

```text
Authorization: Bearer <nyckel>
```

`/healthz` ar undantagen fran API-nyckelkravet.

## HTTP/SSE

Nuvarande server anvander MCP over HTTP/SSE:

```text
GET  /sse
POST /messages/
GET  /healthz
```

Rekommenderad publik adress:

```text
https://mcp.promptbanken.se/sse
```

Pa sikt kan endpointen bli:

```text
https://mcp.promptbanken.se/mcp
```

Det kraver uppgradering till nyare MCP Streamable HTTP-transport.

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
        "Authorization": "Bearer byt-till-en-lang-slumpad-nyckel"
      }
    }
  }
}
```

Om ingen `PROMPTBANKEN_MCP_API_KEY` ar satt pa servern kan `headers` utelamnas.

## Docker och VPS

`docker-compose.yml` startar servern i `hosted`-lage och binder porten endast till VPS:ens localhost:

```text
127.0.0.1:8000
```

Publik trafik ska ga via reverse proxy, till exempel Caddy:

```caddyfile
mcp.promptbanken.se {
    reverse_proxy 127.0.0.1:8000
}
```

Containern ar hardad for read-only drift:

- `read_only: true`
- port bara pa `127.0.0.1:8000`
- `no-new-privileges:true`
- `cap_drop: ALL`
- temporar skrivyta via `tmpfs` pa `/tmp`

For publik demo kan servern koras utan API-nyckel. Publicera bara promptar som ar avsedda att vara offentliga och skriv tydligt att anvandare inte ska skicka personuppgifter eller sekretessbelagd information.

For intern eller langre drift, satt API-nyckel i `.env` bredvid `docker-compose.yml`:

```env
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lang-slumpad-nyckel
```

## Client-side routing

I `hosted`-lage ska klienten:

1. Hamta skill-metadata med `list_skills`.
2. Valja relevant skill lokalt utifran anvandarens uppgift.
3. Hamta vald promptmall med `get_skill`.
4. Kontrollera, anonymisera och sammanstalla prompten lokalt.

Routing ska inte matcha tungt pa vanliga fyllnadsord som `skriv`, `ett`, `till`, `som` och `vanligt`. Anvand stopwords och vikta traffar i denna ordning:

1. skill-id
2. skillens namn
3. intents
4. description
5. ovrig metadata

En explicit traff pa till exempel `informationsutskick` ska vaga tyngre an generiska ord.
