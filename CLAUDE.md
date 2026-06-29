# Promptbanken MCP — Claude Code-instruktioner

## Projekt
MCP-server (FastMCP/Python, stdio + HTTP/SSE) som exponerar kommunala promptmallar som skills. Ingen AI-modell körs i servern. Servern är read-only för promptar och skill-metadata.

## Repo-layout
```
mcp-server/
  server/
    mcp_server.py          # FastMCP-app, tools, HTTP-routes
    skill_repository.py    # Skill-dataclass + statisk repo (skills.json + prompts/*.txt)
    skill_router.py        # Term/roll/audience-scoring
    supabase_repository.py # Workspace-skills från Supabase (httpx, service-role via RPC)
    risk_checker.py        # Personuppgiftsmönster-kontroll
    hosted_guard.py        # Metadata-only-guard för hosted-läge
  skills.json              # Skill-katalog
  prompts/                 # Promptmallar (.txt)
  requirements.txt
docker-compose.yml         # Produktionsdrift på VPS
.claude/
  settings.json            # MCP-serverkonfiguration (Supabase MCP, lokalt)
.agents/
  skills/                  # Agent-skills (supabase, postgres-best-practices)
```

## Körning
```powershell
npm run setup:python   # installera Python-beroenden
npm run dev            # stdio, PROMPTBANKEN_MCP_MODE=local
npm run serve          # HTTP på :8000, PROMPTBANKEN_MCP_MODE=hosted
```

## Viktiga miljövariabler
| Variabel | Syfte |
|---|---|
| `PROMPTBANKEN_MCP_MODE` | `hosted` (standard) eller `local` |
| `SUPABASE_URL` | Supabase-projektets URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role-nyckel (aldrig i frontend) |
| `PROMPTBANKEN_MCP_API_KEY` | Bearer-token för HTTP-endpointskydd |

`PROMPTBANKEN_MCP_USER_KEY` används inte längre — nyckeln skickas per anrop av klienten.

## Supabase-integration
- MCP-nycklar lagras i `api_keys`-tabellen (i `promptbanken`-repot) med `scopes=['mcp']`
- Nyckelverifiering sker via `app_private.verify_mcp_key(p_key_hash)` — RPC med service-role
- Workspace-skills hämtas via `app_private.get_workspace_prompts(p_workspace_id)` — RPC med service-role
- Sha256-hash av rånyckeln skickas till RPC, aldrig rånyckeln
- Migrationerna ligger i `promptbanken`-repot: `supabase/migrations/20240629_mcp_rpc_functions.sql`
- `mcp_keys`-tabellen används inte — ignorera eventuell gammal migration med det namnet

## Nyckelhantering per anrop
Klienten skickar sin MCP-nyckel som HTTP-header `X-MCP-Key` i varje anrop:
```json
{
  "mcpServers": {
    "promptbanken": {
      "url": "https://mcp.promptbanken.se/mcp",
      "headers": { "X-MCP-Key": "pb_mcp_..." }
    }
  }
}
```
- `/mcp` (Streamable HTTP) — stöder `X-MCP-Key`, returnerar statiska + workspace-skills
- `/sse` (SSE, legacy) — returnerar bara de 16 statiska promptarna, ingen nyckelstöd
- `/api/v1/skills` — stöder `X-MCP-Key`

## Driftlägen
- **hosted**: bara metadata-tools (`list_skills`, `get_skill`, `health_check`, m.fl.) — ingen användartext skickas hit
- **local**: även `route_skill`, `compile_skill_prompt`, `check_input_risk`

## Arbetsminnesfiler
Läs dessa innan större ändringar:
- `PROJECT.md` — syfte och mål
- `TODO.md` — pågående och kommande uppgifter
- `LOG.md` — senaste arbetspasset
- `DECISIONS.md` — fattade vägvalsbeslut

Uppdatera alltid `TODO.md`, `LOG.md` och `DECISIONS.md` efter ett arbetspass.

## Konventioner
- Dokumentation på **svenska**
- Inga kommentarer i koden om inte WHY är icke-uppenbart
- Inga nya abstraktioner utan tydlig nytta
- Lägg aldrig API-nycklar, tokens eller `.env`-filer i Git
- Validera alltid `skill_id` med `SkillRepository.is_valid_skill_id()` innan användning
