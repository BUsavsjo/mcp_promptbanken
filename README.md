# Promptbanken MCP

Minimal MCP-server som exponerar Promptbankens kommunala promptar som skills.

Servern kor ingen AI-modell sjalv. Den levererar skill-metadata, prompttext, enkel routing och riskkontroll till en MCP-klient.

## Struktur

```text
mcp-server/
  package.json
  requirements.txt
  skills.json
  prompts/
  server/
  scripts/
```

Rotens `package.json` ar en tunn genvag till `mcp-server/`.

## Starta

Fran repo-roten:

```powershell
npm run setup:python
npm run dev
```

Eller direkt i MCP-paketet:

```powershell
cd mcp-server
npm run setup:python
npm run dev
```

`npm run dev` startar en MCP stdio-server. Den ska normalt startas av din MCP-klient och kan se ut att vanta i terminalen.

## MCP-konfiguration

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

## Tools

- `list_skills`
- `get_skill`
- `route_skill`
- `compile_skill_prompt`
- `check_input_risk`

## Kontroll

```powershell
npm run check:python
```
