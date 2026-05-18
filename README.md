# Promptbanken MCP

Minimal MCP-server som exponerar Promptbankens kommunala promptar som skills.

Servern kor ingen AI-modell sjalv. Den levererar skill-metadata, prompttext, enkel routing och riskkontroll till en MCP-klient.

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

Containern lyssnar pa port `8000`.

## VPS

Skapa DNS:

```text
mcp.promptbanken.se -> VPS:ens publika IP
```

Satt API-nyckel pa VPS i `.env` bredvid `docker-compose.yml`:

```env
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lang-slumpad-nyckel
```

Exempel med Caddy:

```caddyfile
mcp.promptbanken.se {
    reverse_proxy 127.0.0.1:8000
}
```

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
