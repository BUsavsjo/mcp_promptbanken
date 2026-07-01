# TODO

## Nästa steg
- [ ] Testa att nya promptmallar i `mcp-server/prompts/` är korrekt registrerade i `mcp-server/skills.json`.
- [ ] Gå igenom `.gitignore` efter verkliga arbetsflöden och justera om anonymiserad exempeldata behöver versionshanteras.
- [ ] Ta ställning till om den stale migrationen `supabase/migrations/20240629_create_mcp_keys.sql` (tabellen `mcp_keys`) ska tas bort ur det här repot.
- [ ] Rotera Supabase JWT-secreten om den anses exponerad (stod i klartext i en chattsession 2026-07-01) — kräver omloggning för alla användare, gör vid lågtrafik.
- [ ] Ta bort den gamla `SUPABASE_SERVICE_ROLE_KEY`-raden ur `.env` på VPS:en helt (om den fortfarande ligger kvar bredvid de nya variablerna).
- [ ] Städa bort den övergivna dubblettklonen på VPS:en (`/home/wenstrompeter/mcp_promptbanken/mcp_promptbanken/`) — otrackad, oanvänd av Docker Compose, men rör ingen brådska.
- [ ] Kör `caddy fmt --overwrite` på `/etc/caddy/Caddyfile` (kosmetisk formateringsvarning vid reload).

## Senare
- [ ] Dokumentera rekommenderat klientflöde för lokal routing mer praktiskt om klientimplementation tillkommer.
- [ ] Utvärdera om hosted metadata-guard ska köras i `block` efter drift med `warn`.
- [ ] Lägg till fler fokuserade tester om serverns API-yta växer.

## Klart
- [x] Ersatte service-role-nyckeln med begränsad `mcp_server`-roll (execute-only på de två RPC:erna) — verifierat end-to-end med riktig `X-MCP-Key` mot produktion, 2 workspace-skills kom igenom korrekt.
- [x] Skapade lokalt arbetsminne med markdown-filer i projektroten.
- [x] Mergade `feature-mcp-streamable` till `main` och deployade på VPS:en (mcp.promptbanken.se).
- [x] Verifierat att Streamable HTTP-endpointen `/mcp` fungerar live via Caddy (POST `tools/list` gav korrekt svar).
- [x] Verifierat att hosted-läget bara exponerar metadata-only tools (`list_skills`, `list_skills_simple`, `get_skill`, `health_check`, `get_client_routing_instructions`) — inga lokala verktyg läckte ut.
- [x] Uppdaterade Caddyfile med routes för `/mcp`, `/api/v1/*` och `/openapi.json`.
