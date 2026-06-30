# TODO

## Nästa steg
- [ ] Testa att nya promptmallar i `mcp-server/prompts/` är korrekt registrerade i `mcp-server/skills.json`.
- [ ] Gå igenom `.gitignore` efter verkliga arbetsflöden och justera om anonymiserad exempeldata behöver versionshanteras.
- [ ] Verifiera mot `promptbanken`-repots Supabase-projekt att RPC-funktionerna `app_private.verify_mcp_key` och `app_private.get_workspace_prompts` faktiskt är migrerade och fungerar end-to-end med en riktig workspace-nyckel (`X-MCP-Key`) — `/mcp` och `/api/v1/skills` är nu live i produktion, men ingen workspace-nyckel har testats än.
- [ ] Ta ställning till om den stale migrationen `supabase/migrations/20240629_create_mcp_keys.sql` (tabellen `mcp_keys`) ska tas bort ur det här repot.
- [ ] Städa bort den övergivna dubblettklonen på VPS:en (`/home/wenstrompeter/mcp_promptbanken/mcp_promptbanken/`) — otrackad, oanvänd av Docker Compose, men rör ingen brådska.
- [ ] Kör `caddy fmt --overwrite` på `/etc/caddy/Caddyfile` (kosmetisk formateringsvarning vid reload).

## Senare
- [ ] Dokumentera rekommenderat klientflöde för lokal routing mer praktiskt om klientimplementation tillkommer.
- [ ] Utvärdera om hosted metadata-guard ska köras i `block` efter drift med `warn`.
- [ ] Lägg till fler fokuserade tester om serverns API-yta växer.

## Klart
- [x] Skapade lokalt arbetsminne med markdown-filer i projektroten.
- [x] Mergade `feature-mcp-streamable` till `main` och deployade på VPS:en (mcp.promptbanken.se).
- [x] Verifierat att Streamable HTTP-endpointen `/mcp` fungerar live via Caddy (POST `tools/list` gav korrekt svar).
- [x] Verifierat att hosted-läget bara exponerar metadata-only tools (`list_skills`, `list_skills_simple`, `get_skill`, `health_check`, `get_client_routing_instructions`) — inga lokala verktyg läckte ut.
- [x] Uppdaterade Caddyfile med routes för `/mcp`, `/api/v1/*` och `/openapi.json`.
