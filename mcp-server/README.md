# Promptbanken MCP Server

Minimal MCP-server som exponerar Promptbankens promptar som skills.

Den öppna `/mcp`-ytan använder client-side skill routing. Det betyder att MCP-servern bara skickar metadata, promptmallar, hälsostatus och instruktioner till klienten. Användarens uppgift, dokumenttext och annan indata ska inte skickas till den öppna `/mcp`-ytan.

## Data och integritet

Den publika `/mcp`-ytan är read-only och sparar inte användarens råtext, promptanrop eller svar. `/mcp/key` kan även exponera autentiserade workspace- och Valvet-tools.

För `/mcp/key` lagrar läsverktyg inte råtext, men uttryckliga create/update/copy/activate/deactivate-anrop skriver den data användaren valt till Valvet/Supabase.

Den öppna `/mcp`-ytan läser bara:

- `skills.json`
- `prompts/*.txt`

På den publika `/mcp`-ytan bearbetar servern inte användarens uppgiftstext i minnet. Den exponerar bara:

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

I local-läge kan servern även exponera:

- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

Dessa local-tools tar emot användartext och ska bara användas på användarens egen maskin.

## Säkerhet

- Servern kör ingen AI-modell.
- Den öppna `/mcp`-ytan tar inte emot rå användartext.
- Hosted-läget har en metadata-guard på `/messages/` som varnar payload-fritt om klienten skickar oväntade tools eller argument.
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
- hosted metadata-guard-varningar med orsak, metod och tool-namn
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
POST /mcp
GET  /mcp
POST /mcp/key
GET  /mcp/key
GET  /api/v1/skills
GET  /api/v1/skills/simple
GET  /api/v1/skills/{skill_id}
GET  /api/v1/skills/{skill_id}/prompt
GET  /api/v1/routing-instructions
POST /api/v1/my-prompts             # Pro-gated write: save a new prompt (see save_workspace_prompt tool)
GET  /openapi.json
GET  /sse
POST /messages/
GET  /healthz
```

Rekommenderad publik MCP URL är:

```text
https://mcp.promptbanken.se/mcp
```

`/sse` och `/messages/` finns kvar som legacy HTTP/SSE för äldre klienter.

## Miljö

```text
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_LOG_LEVEL=INFO
PROMPTBANKEN_MCP_MODE=hosted
PROMPTBANKEN_MCP_API_KEY=
PROMPTBANKEN_MCP_VERSION=1.1.0
PROMPTBANKEN_MCP_HOSTED_GUARD=warn
PROMPTBANKEN_MCP_ALLOWED_ORIGINS=https://mcp.promptbanken.se
PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN=  # OpenAI:s app-directory-domänverifieringstoken
```

Tillåtna lägen:

- `hosted`: publicerat läge utan tools som tar emot användartext
- `local`: lokal installation där tools för routing, promptkompilering och riskkontroll aktiveras

`PROMPTBANKEN_MCP_API_KEY` är den globala servernyckeln för det SATT-läge som beskrivs i avsnittet **Auth för `/mcp/key`**. Lämna den tom för workspace/user-key-läget. `/mcp` förblir anonym.

`/healthz`, `/mcp` och `/.well-known/openai-apps-challenge` är undantagna från API-nyckelkravet.

## Docker

Från repo-roten:

```powershell
docker compose up -d --build
```

I `docker-compose.yml` binds porten bara till `127.0.0.1:8000`, så publik trafik ska gå via reverse proxy.

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

Exemplet använder SATT `PROMPTBANKEN_MCP_API_KEY` och skickar globalnyckeln separat från workspace-nyckeln. Med TOM `PROMPTBANKEN_MCP_API_KEY` räcker `X-MCP-Key` eller `Authorization: Bearer <workspace-nyckel>` på `/mcp/key`.

## Tools

Publik `/mcp` (utan auth):

- `health_check`
- `get_client_routing_instructions`
- `list_templates`
- `search_templates`
- `get_template`
- `list_packages`
- `get_package`
- `list_package_prompts`
- `recommend_packages`

Key-authenticated `/mcp/key`:

Privata och skrivande tools, inklusive Valvet-tools och `activate_package`, kräver `X-MCP-Key` eller Bearer MCP-nyckel.

Local:

- `list_skills`
- `list_skills_simple`
- `get_skill`
- `health_check`
- `get_client_routing_instructions`
- `check_input_risk`
- `save_workspace_prompt` (Pro-gated write)
- `route_skill`
- `compile_skill_prompt`

Beskrivning av de tools som inte bara returnerar metadata:

- `check_input_risk(text)` — checks text for common personal-data patterns (personnummer, e-post, telefonnummer, arendenummer); never blocks, only warns.
- `save_workspace_prompt(title, content, category, source, risk_check_passed, idempotency_key)` — Pro-gated write, saves a new prompt into the caller's personal workspace as `visibility='private'`, `status='draft'`. Requires `risk_check_passed=true` (rejected otherwise). Accepts an optional `idempotency_key` (UUID) to make retries safe.

## Centrala filer

- `skills.json`
- `prompts/*.txt`
- `server/mcp_server.py`
- `server/http_server.py`
- `server/skill_repository.py`
- `server/skill_router.py`
- `server/risk_checker.py`
- `Dockerfile`
