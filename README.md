# Promptbanken MCP

Minimal MCP-server som exponerar Promptbankens kommunala promptar som skills.

Servern kor ingen AI-modell sjalv. Den levererar skill-metadata, prompttext, enkel routing och riskkontroll till en MCP-klient.

## Data och integritet

Promptbanken MCP ar en read-only prompt- och skill-server.

Servern sparar inte anvandarens text, promptanrop eller svar i databas eller fil. Den har ingen databas och ingen skrivande lagring for anvandarinput.

Det servern laser fran disk:

- `skills.json` med skill-metadata
- `prompts/*.txt` med prompttexter

Det servern bearbetar i minnet nar ett tool anropas:

- uppgiftstext i `route_skill`
- eventuell `user_task` och `user_input` i `compile_skill_prompt`
- text i `check_input_risk`

Bearbetningen anvands bara for att:

- valja relevant skill
- bygga en prompt att skicka tillbaka till MCP-klienten
- kontrollera enkla monster som personnummer, e-postadress, telefonnummer och arendenummer

Servern kor ingen AI-modell och skickar inte vidare anvandarinput till nagon extern AI-leverantor.

Docker-containern ar hardad for read-only drift:

- `read_only: true`
- ingen publik direktport, bara `127.0.0.1:8000`
- `no-new-privileges:true`
- alla Linux capabilities tas bort med `cap_drop: ALL`
- temporar skrivyta endast via `tmpfs` pa `/tmp`

Loggning ska hallas teknisk. Logga inte `user_input`, `user_task`, hela prompts eller personuppgifter. For publik demo: be anvandare att inte skicka personuppgifter eller sekretessbelagd information.

## Struktur

```text
mcp-server/
  Dockerfile
  package.json
  requirements.txt
  skills.json
  prompts/
  server/
  scripts/
```

Rotens `package.json` ar en tunn genvag till `mcp-server/`.

## Lokal utveckling

Stdio-lage for lokal MCP-klient:

```powershell
npm run setup:python
npm run dev
```

HTTP/SSE-lage for lokal VPS-test:

```powershell
npm run setup:python
npm run serve
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

## Produktionsadress

Rekommenderad publik adress:

```text
https://mcp.promptbanken.se/sse
```

Nuvarande server anvander MCP over HTTP/SSE:

```text
GET  /sse
POST /messages/
GET  /healthz
```

`/sse` ar MCP-klientens anslutningspunkt. `/messages/` anvands internt av MCP-transporten. `/healthz` ar for driftkontroll.

Pa sikt kan endpointen bli:

```text
https://mcp.promptbanken.se/mcp
```

Det kraver uppgradering till nyare MCP Streamable HTTP-transport.

## Docker

Bygg och starta:

```powershell
docker compose up -d --build
```

Stoppa:

```powershell
docker compose down
```

Containern publiceras bara pa VPS:ens localhost:

```text
127.0.0.1:8000
```

Publik trafik ska ga via Caddy, inte direkt till Docker-porten.

## VPS

Skapa DNS:

```text
mcp.promptbanken.se -> VPS:ens publika IP
```

For publik demo kan servern koras utan API-nyckel. Da utelamnas `.env` eller lamnas variabeln tom.

For intern eller langre drift, satt API-nyckel pa VPS i `.env` bredvid `docker-compose.yml`:

```env
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lang-slumpad-nyckel
```

Exempel med Caddy:

```caddyfile
mcp.promptbanken.se {
    reverse_proxy 127.0.0.1:8000
}
```

For demo utan API-nyckel: publicera bara promptar som ar avsedda att vara offentliga, logga inte anvandarinput och skriv tydligt att anvandare inte ska skicka personuppgifter eller sekretessbelagd information.

Starta pa VPS:

```bash
docker compose up -d --build
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

## Tools

- `list_skills`
- `get_skill`
- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

## Kontroll

```powershell
npm run check:python
docker compose config --quiet
```
