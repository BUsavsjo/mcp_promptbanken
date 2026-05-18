# Promptbanken MCP Server

Minimal MCP-server som exponerar Promptbankens promptar som skills.

## Starta lokalt

Stdio-lage:

```powershell
npm run setup:python
npm run dev
```

HTTP/SSE-lage:

```powershell
npm run setup:python
npm run serve
```

Servern lyssnar som standard pa port `8000`.

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
PROMPTBANKEN_MCP_API_KEY=byt-till-en-lang-slumpad-nyckel
```

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

- `list_skills`
- `get_skill`
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
