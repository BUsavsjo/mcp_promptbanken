# Promptbanken MCP Server

Minimal MCP-server som exponerar Promptbankens promptar som skills.

Hosted-versionen använder client-side skill routing. Det betyder att MCP-servern bara skickar metadata, promptmallar, hälsostatus och instruktioner till klienten. Användarens uppgift, dokumenttext och annan indata ska inte skickas till hosted-servern.

## Data och integritet

Servern är read-only och sparar inte användarens text, promptanrop eller svar i databas eller fil.

Den läser bara:

- `skills.json`
- `prompts/*.txt`

I hosted-läge bearbetar servern inte användarens uppgiftstext i minnet. Den exponerar bara:

- `list_skills`
- `list_skills_simple`
- `get_skill`
- `health_check`
- `get_client_routing_instructions`

I local-läge kan servern även exponera:

- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

Dessa local-tools tar emot användartext och ska bara användas på användarens egen maskin.

## Säkerhet

- Servern kör ingen AI-modell.
- Hosted-läget tar inte emot rå användartext.
- `skill_id` valideras med `^[a-z0-9_-]{2,50}$`.
- `get_skill` returnerar strukturerade fel för ogiltigt eller saknat skill-id.
- Promptmallarna instruerar modellen att behandla användarens underlag som data, inte instruktioner.
- Skill-metadata innehåller `output_schema`.
- Skill-metadata innehåller också `display_name`, `category`, `example_phrases`, `risk_message` och `anonymization_level`.
- Docker-driften är read-only, kör som icke-root, binder bara till `127.0.0.1:8000`, använder `no-new-privileges:true` och tar bort Linux capabilities med `cap_drop: ALL`.

## Loggning

Loggningen ska vara teknisk och payload-fri.

Loggas:

- serverstart, driftläge och antal skills
- `/healthz`
- SSE connect/disconnect och varaktighet
- tool-namn
- validerat `skill_id` vid `get_skill`
- `include_prompt`
- nekad auth som teknisk händelse
- i local-läge: booleska flaggor som `has_user_input`, inte fri text

Loggas inte:

- request body
- användartext
- prompttext
- kompilerade prompts
- personuppgifter
- headers, bearer tokens eller klient-IP

Visa loggar:

```bash
docker compose logs -f --tail=100 promptbanken-mcp
```

Visa sammanfattning:

```bash
npm run logs:summary
npm run logs:summary -- --tail 2000
npm run logs:summary -- --summary-only
```

## Starta lokalt

Stdio-läge:

```powershell
npm run setup:python
npm run dev
```

`npm run dev` sätter `PROMPTBANKEN_MCP_MODE=local` om variabeln inte redan är satt.

HTTP/SSE-läge:

```powershell
npm run setup:python
npm run serve
```

Servern lyssnar som standard på port `8000`.

`npm run serve` sätter `PROMPTBANKEN_MCP_MODE=hosted` om variabeln inte redan är satt.

## HTTP-endpoints

```text
GET  /sse
POST /messages/
GET  /healthz
```

Nuvarande Python-SDK använder MCP SSE-transport för remote HTTP. Rekommenderad publik URL är:

```text
https://mcp.promptbanken.se/sse
```

## Miljö

```text
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_LOG_LEVEL=INFO
PROMPTBANKEN_MCP_MODE=hosted
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lång-slumpad-nyckel
PROMPTBANKEN_MCP_VERSION=1.1.0
```

Tillåtna lägen:

- `hosted`: publicerat läge utan tools som tar emot användartext
- `local`: lokal installation där tools för routing, promptkompilering och riskkontroll aktiveras

Om `PROMPTBANKEN_MCP_API_KEY` är satt krävs:

```text
Authorization: Bearer <nyckel>
```

## Docker

Från repo-roten:

```powershell
docker compose up -d --build
```

I `docker-compose.yml` binds porten bara till `127.0.0.1:8000`, så publik trafik ska gå via reverse proxy.

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

## Tools

Hosted:

- `list_skills`
- `list_skills_simple`
- `get_skill`
- `health_check`
- `get_client_routing_instructions`

Local:

- `list_skills`
- `list_skills_simple`
- `get_skill`
- `health_check`
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
