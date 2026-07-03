# TODO

## Säkerhet — prioriterad lista
1. [ ] **(Low, defense-in-depth)** `HostedMetadataGuardMiddleware` (`mcp_server.py`) buffrar hela request body i minnet utan egen övre gräns i Python-koden. Verifierat 2026-07-01: Caddyfilen har redan `request_body { max_size 64KB }` på exakt `/messages/*` och `/mcp`, så produktionen är skyddad idag. Kvarstående risk är bara om servern någon gång exponeras utan Caddy framför (t.ex. direkt mot porten, eller en annan reverse proxy utan samma gräns) — överväg ett hårdkodat tak i koden själv så skyddet inte är beroende av proxykonfigurationen.
2. [ ] **(Low)** Utvärdera om hosted metadata-guard ska köras i `block` istället för `warn` efter en tids drift utan `hosted_payload_warning`-träffar (redan i "Senare" nedan, men hör ihop med säkerhetsläget).
3. [ ] **(Low)** Verifiera att `PROMPTBANKEN_MCP_ALLOWED_ORIGINS` faktiskt är satt i produktion — `OriginValidationMiddleware` släpper igenom requests helt utan `Origin`-header eller om variabeln är tom, vilket är korrekt för server-till-server-klienter men bör vara ett medvetet val, inte standard.
4. [ ] **(Low)** Städa bort den övergivna dubblettklonen på VPS:en (`/home/wenstrompeter/mcp_promptbanken/mcp_promptbanken/`) — otrackad, oanvänd av Docker Compose, men ökar attackytan om den av misstag pekas ut av något.

## Nästa steg
- [ ] Testa att nya promptmallar i `mcp-server/prompts/` är korrekt registrerade i `mcp-server/skills.json`.
- [ ] Gå igenom `.gitignore` efter verkliga arbetsflöden och justera om anonymiserad exempeldata behöver versionshanteras.
- [ ] Kör `caddy fmt --overwrite` på `/etc/caddy/Caddyfile` (kosmetisk formateringsvarning vid reload).

## Senare
- [ ] Dokumentera rekommenderat klientflöde för lokal routing mer praktiskt om klientimplementation tillkommer.
- [ ] Utvärdera om hosted metadata-guard ska köras i `block` efter drift med `warn`.
- [ ] Lägg till fler fokuserade tester om serverns API-yta växer.
- [ ] Utöka `app_private.verify_mcp_key` (i `promptbanken`-repot) med en explicit reason-kod (t.ex. `revoked`/`not_found`/`disabled`) så `workspace_status` kan bli mer specifik än dagens generiska `invalid_key`. Kräver ny migration i `promptbanken`-repot.

## Klart
- [x] Nytt verktyg `list_my_prompts` + REST `GET /api/v1/my-prompts` — listar bara den anropande nyckelns egna sparade prompts (`source == "workspace"`), separat från `list_skills`/`list_skills_simple`. Löste att MCP-klienter (bekräftat med ChatGPT) inte hittade "mina prompts" eftersom de var blandade in bland publika mallar utan egen ingång. `workspace_status`: `no_key`/`invalid_key`/`ok`.
- [x] Lade till `catalog`/`plan`/`message`-fält i `health_check` (REST `/healthz` och MCP-verktyget) — visar `public`/`free`/`pro` baserat på `X-MCP-Key`/`Authorization`-nyckelns plan, alltid närvarande (inte utelämnat som `workspace_status`). Se `docs/superpowers/specs/2026-07-03-health-check-catalog-status-design.md` för designen.
- [x] Exponerade Promptbanken Pro-mallar i den hostade servern: nytt verktyg `list_pro_templates` + REST `GET /api/v1/pro-templates` (`mcp-server/server/pro_templates.py`), anropar RPC:n `get_pro_templates_for_mcp_key` (i `promptbanken`-repot, beviljad till `anon`). Lade till i `_tool_definitions()`, JSON-RPC-dispatchen och hosted-guardens allowlist. Löser TODO-punkten i `promptbanken`-repot om att Pro-mallarna saknades i den publika/hostade servern.
- [x] Lade till `workspace_status`- och `workspace_message`-fält i `list_skills_simple` och REST `GET /api/v1/skills` — visar `"invalid_key"` + ett läsbart svenskt meddelande när en `X-MCP-Key`/`Authorization`-nyckel skickas men inte matchar ett aktivt workspace (täcker återkallad, felstavad eller inaktiverad nyckel), utan att blockera de publika skillsen. Båda fälten utelämnas helt om ingen nyckel skickas. Se README för detaljer och känd begränsning (RPC:n skiljer inte ut orsak ännu).
- [x] Fixade timing-attack-sårbarhet i `BearerAuthMiddleware`/`_mcp_key_from_request` (`mcp_server.py`) — jämförelse av `PROMPTBANKEN_MCP_API_KEY` mot `Authorization`-headern använde `!=`/`==` (icke-konstant tid), bytt till `hmac.compare_digest` på båda ställena, 2026-07-01.
- [x] Roterade Supabase JWT-secreten (var exponerad i klartext i en chattsession 2026-07-01).
- [x] Tog bort den gamla `SUPABASE_SERVICE_ROLE_KEY`-raden ur `.env` på VPS:en.
- [x] Tog bort den stale migrationen `supabase/migrations/20240629_create_mcp_keys.sql` (oanvänd `mcp_keys`-tabell, ersatt av RPC-baserad nyckelverifiering) ur repot.
- [x] Ersatte service-role-nyckeln med begränsad `mcp_server`-roll (execute-only på de två RPC:erna) — verifierat end-to-end med riktig `X-MCP-Key` mot produktion, 2 workspace-skills kom igenom korrekt.
- [x] Skapade lokalt arbetsminne med markdown-filer i projektroten.
- [x] Mergade `feature-mcp-streamable` till `main` och deployade på VPS:en (mcp.promptbanken.se).
- [x] Verifierat att Streamable HTTP-endpointen `/mcp` fungerar live via Caddy (POST `tools/list` gav korrekt svar).
- [x] Verifierat att hosted-läget bara exponerar metadata-only tools (`list_skills`, `list_skills_simple`, `get_skill`, `health_check`, `get_client_routing_instructions`) — inga lokala verktyg läckte ut.
- [x] Uppdaterade Caddyfile med routes för `/mcp`, `/api/v1/*` och `/openapi.json`.
