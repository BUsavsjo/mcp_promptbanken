# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Promptbanken MCP — Claude Code-instruktioner

## Projekt
MCP-server (FastMCP/Python, stdio + HTTP/SSE) som exponerar kommunala promptmallar som skills. Ingen AI-modell körs i servern. Servern är read-only för promptar och skill-metadata.

## Repo-layout
```
mcp-server/
  server/
    mcp_server.py          # FastMCP-app, tools, HTTP-routes, repo/router/risk_checker instansieras på modulnivå
    http_server.py         # Entrypoint för legacy SSE (kör run_sse() från mcp_server)
    skill_repository.py    # Skill-dataclass + statisk repo (skills.json + prompts/*.txt), SKILL_ID_PATTERN
    skill_router.py        # Term/roll/audience-scoring
    supabase_repository.py # Workspace-skills från Supabase (httpx, mcp_server-roll via RPC)
    pro_templates.py        # Pro-mallar via anon-beviljad RPC get_pro_templates_for_mcp_key (httpx)
    risk_checker.py        # Personuppgiftsmönster-kontroll
    hosted_guard.py        # Metadata-only-guard för hosted-läge
  scripts/                 # run-mcp.js, serve-http.js, setup-python.js, check-python.js, log-summary.js
  skills.json              # Skill-katalog (21 skills, se README.md för aktuell lista av skill-id)
  prompts/                 # Promptmallar (.txt), en per skill-id
  requirements.txt
docker-compose.yml         # Produktionsdrift på VPS
docs/add-new-prompt.md     # Guide för att lägga till en ny skill/prompt
.claude/
  settings.json            # MCP-serverkonfiguration (Supabase MCP, lokalt)
.agents/
  skills/                  # Agent-skills (supabase, postgres-best-practices)
```

Både repo-roten och `mcp-server/` har egna `package.json` med samma script-namn (`dev`, `serve`, `setup:python`, `check:python`) — kör alltid från repo-roten; rotens scripts anropar bara filerna i `mcp-server/scripts/`.

## Körning
```powershell
npm run setup:python   # installera Python-beroenden
npm run dev            # stdio, PROMPTBANKEN_MCP_MODE=local
npm run serve          # HTTP på :8000, PROMPTBANKEN_MCP_MODE=hosted
npm run check:python   # verifiera Python-miljön
npm run logs:summary   # sammanfatta Docker-loggar (tool-anrop, SSE, health checks)
```

Docker (produktion):
```powershell
docker compose up -d --build
docker compose logs -f --tail=100 promptbanken-mcp
```

Inga automatiserade tester finns i repot ännu — verifiera ändringar manuellt via `npm run dev`/`npm run serve` och `/healthz`.

## Viktiga miljövariabler
| Variabel | Syfte |
|---|---|
| `PROMPTBANKEN_MCP_MODE` | `hosted` (standard) eller `local` |
| `SUPABASE_URL` | Supabase-projektets URL |
| `SUPABASE_ANON_KEY` | Publik anon-nyckel — krävs i `apikey`-headern för att passera Kong-gatewayen, avslöjar ingen behörighet i sig |
| `SUPABASE_MCP_ROLE_JWT` | Egen JWT signerad för rollen `mcp_server` (se nedan) — skickas som `Authorization: Bearer`, styr vilken Postgres-roll RPC-anropen kör som |
| `PROMPTBANKEN_MCP_API_KEY` | Global Bearer-token som låser hela servern (se varning nedan) |

`PROMPTBANKEN_MCP_USER_KEY` används inte längre — nyckeln skickas per anrop av klienten.

⚠️ **`PROMPTBANKEN_MCP_API_KEY` och workspace-nycklar är ömsesidigt uteslutande.** Är den satt kräver servern exakt `Bearer <global_nyckel>` på alla HTTP-endpoints utom `/healthz` (`BearerAuthMiddleware`), vilket gör hela servern privat. Då slutar per-användares workspace-nycklar som skickas via `Authorization: Bearer` att fungera, eftersom de inte matchar den globala nyckeln. Lämna variabeln **tom** för öppet läge (publika promptar öppet + workspace-prompts per `X-MCP-Key`/`Authorization`). Servern loggar en `global_bearer_enabled`-varning vid start om nyckeln är satt.

## Supabase-integration
- MCP-nycklar lagras i `api_keys`-tabellen (i `promptbanken`-repot) med `scopes=['mcp']`
- Nyckelverifiering sker via `app_private.verify_mcp_key(p_key_hash)` — RPC via den begränsade rollen `mcp_server`
- Workspace-skills hämtas via `app_private.get_workspace_prompts(p_workspace_id)` — RPC via `mcp_server`
- Sha256-hash av rånyckeln skickas till RPC, aldrig rånyckeln
- Migrationerna ligger i `promptbanken`-repot: `supabase/migrations/20240629_mcp_rpc_functions.sql`, `supabase/migrations/20260701_mcp_server_role.sql`
- `mcp_keys`-tabellen används inte och finns inte längre som migration i det här repot (den stale filen `supabase/migrations/20240629_create_mcp_keys.sql` togs bort 2026-07-01)

### Rollen `mcp_server` (ersätter service-role)
Service-role bypassar RLS helt och ger läs/skriv på alla tabeller — för mycket åtkomst för en server som bara ska anropa två RPC:er. Istället finns en dedikerad Postgres-roll `mcp_server` (skapad av `20260701_mcp_server_role.sql`) som **bara** har `execute` på `verify_mcp_key`/`get_workspace_prompts`, inget annat.

Supabase har två separata auktoriseringslager, vilket kräver två olika nycklar i `.env`:
- **`apikey`-headern** valideras av gatewayen (Kong) mot projektets kända nycklar (`anon`/`service_role`) — den känner inte till anpassade roller. Här skickas `SUPABASE_ANON_KEY` (publik, ofarlig att exponera).
- **`Authorization: Bearer`-headern** läses av PostgREST för att avgöra vilken Postgres-roll anropet ska köra som (`role`-claim i JWT:n). Här skickas `SUPABASE_MCP_ROLE_JWT` — en JWT signerad med projektets JWT-secret och `role: "mcp_server"`.

Blir VPS:en/containern komprometterad kan angriparen bara anropa de två RPC-funktionerna med en hash — inte dumpa `content_items`, `api_keys` eller andra tabeller.

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
- `/api/v1/skills`, `/api/v1/skills/simple`, `/api/v1/skills/{skill_id}`, `/api/v1/skills/{skill_id}/prompt`, `/api/v1/routing-instructions`, `/api/v1/pro-templates`, `/api/v1/my-prompts` — read-only REST-yta, stöder `X-MCP-Key`

`list_pro_templates`-tool/`GET /api/v1/pro-templates` anropar RPC:n `get_pro_templates_for_mcp_key` (beviljad direkt till `anon` i `promptbanken`-repot — nyckelhashen är i sig beviset på behörighet, samma modell som `verify_mcp_key`). Kräver bara `SUPABASE_URL`/`SUPABASE_ANON_KEY`, ingen `mcp_server`-roll/JWT. Utan nyckel eller utan aktiv Pro-plan returneras en teaser (`prompt_text: null` per mall).

`_mcp_key_from_request()` (`mcp_server.py`) läser `X-MCP-Key` först; saknas den provas `Authorization: Bearer <token>` som fallback (för klienter som ChatGPT som bara kan skicka en generisk Bearer-token). Matchar token den globala `PROMPTBANKEN_MCP_API_KEY` tolkas den INTE som workspace-nyckel — den skickas aldrig vidare som hash till Supabase.

`health_check` (REST `/healthz` och MCP-verktyget) läser samma nyckel och svarar alltid med `catalog`/`plan`/`message` (`public`/`free`/`pro`, se README). Ingen extra Supabase-anrop görs om ingen nyckel skickas — `/healthz` utan nyckel (t.ex. Dockers healthcheck) är lika snabb som innan.

`list_my_prompts`/`GET /api/v1/my-prompts` filtrerar `_resolve_all_skills(mcp_key)` på `skill.source == "workspace"` — löser att personliga prompts annars bara syns blandade in i `list_skills`/`list_skills_simple` utan egen ingång, vilket gjorde dem osynliga för MCP-klienter (t.ex. ChatGPT) som inte känner till `source`-fältet.

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

## Ny skill/prompt
Följ `docs/add-new-prompt.md` när en ny prompt läggs till i `skills.json`/`prompts/`.

## Konventioner
- Dokumentation på **svenska**
- Inga kommentarer i koden om inte WHY är icke-uppenbart
- Inga nya abstraktioner utan tydlig nytta
- Lägg aldrig API-nycklar, tokens eller `.env`-filer i Git
- Validera alltid `skill_id` med `SkillRepository.is_valid_skill_id()` innan användning
