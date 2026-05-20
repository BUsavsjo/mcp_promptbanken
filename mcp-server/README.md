# Promptbanken MCP Server

Minimal MCP-server som exponerar Promptbankens promptar som skills.

Hosted-versionen anvander client-side skill routing. Det betyder att MCP-servern bara skickar metadata, promptmallar och instruktioner till klienten. Anvandarens uppgift, dokumenttext och annan indata ska inte skickas till hosted-servern.

## Data och integritet

Servern ar read-only och sparar inte anvandarens text, promptanrop eller svar i databas eller fil.

Den laser bara:

- `skills.json`
- `prompts/*.txt`

I hosted-lage bearbetar servern inte anvandarens uppgiftstext i minnet. Den exponerar bara:

- `list_skills`
- `get_skill`
- `get_client_routing_instructions`

MCP-klienten ska i stallet hamta skill-metadata och promptmallar och sedan gora routing, riskkontroll, anonymisering och promptkompilering lokalt.

Client-side routing ska filtrera bort vanliga stopwords som `skriv`, `ett`, `till`, `som` och `vanligt`. Vikta traffar hogst i skill-id och skillens namn, darefter intents, description och sist ovrig metadata. En explicit traff pa exempelvis `informationsutskick` ska darfor ranka den skillen fore generiska alternativ.

I local-lage, nar anvandaren installerar och kor servern pa egen maskin, kan servern aven exponera:

- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

Dessa tools tar emot anvandartext och bearbetar den i minnet pa den lokala maskinen. Bearbetningen anvands for routing, promptkompilering och enkel riskkontroll av monster som personnummer, e-postadress, telefonnummer och arendenummer.

Servern kor ingen AI-modell och skickar inte vidare anvandarinput till externa AI-leverantorer.

Docker-driften ar hardad for demo:

- containern kor som icke-root
- filsystemet ar read-only
- porten binds bara till `127.0.0.1:8000`
- `no-new-privileges:true`
- `cap_drop: ALL`
- `/tmp` ar temporar `tmpfs`

Logga inte `user_input`, `user_task`, hela prompts eller personuppgifter.

## Starta lokalt

Stdio-lage:

```powershell
npm run setup:python
npm run dev
```

`npm run dev` satter `PROMPTBANKEN_MCP_MODE=local` om variabeln inte redan ar satt.

HTTP/SSE-lage:

```powershell
npm run setup:python
npm run serve
```

Servern lyssnar som standard pa port `8000`.

`npm run serve` satter `PROMPTBANKEN_MCP_MODE=hosted` om variabeln inte redan ar satt.

## HTTP-endpoints

```text
GET  /sse
POST /messages/
GET  /healthz
```

Nuvarande Python-SDK anvander MCP SSE-transport for remote HTTP. Rekommenderad publik URL ar:

```text
https://mcp.promptbanken.se/sse
```

Om klienten enbart accepterar nyare Streamable HTTP behover transporten uppgraderas. Da blir sannolik endpoint:

```text
https://mcp.promptbanken.se/mcp
```

## Miljo

```text
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_LOG_LEVEL=INFO
PROMPTBANKEN_MCP_MODE=hosted
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lang-slumpad-nyckel
```

Tillatna lagen:

- `hosted`: publicerat lage, ingen tool-yta som tar emot anvandartext
- `local`: lokal installation, tools for routing, promptkompilering och riskkontroll aktiveras

Om `PROMPTBANKEN_MCP_API_KEY` ar satt kravs:

```text
Authorization: Bearer <nyckel>
```

## Docker

Fran repo-roten:

```powershell
docker compose up -d --build
```

Eller direkt:

```powershell
docker build -t promptbanken-mcp ./mcp-server
docker run -p 8000:8000 --name promptbanken-mcp promptbanken-mcp
```

I `docker-compose.yml` binds porten bara till `127.0.0.1:8000`, sa publik trafik ska ga via Caddy. Containern kor som icke-root, read-only, utan extra capabilities och med `no-new-privileges`.

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

## Tools

Hosted:

- `list_skills`
- `get_skill`
- `get_client_routing_instructions`

Local:

- `list_skills`
- `get_skill`
- `get_client_routing_instructions`
- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

## Centrala filer

- `skills.json`
- `prompts/*.txt`
- `server/mcp_server.py`
- `server/http_server.py`
- `server/skill_repository.py`
- `server/skill_router.py`
- `server/risk_checker.py`
- `Dockerfile`
