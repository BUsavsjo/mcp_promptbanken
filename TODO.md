# TODO

## Nästa steg
- [ ] Verifiera att Streamable HTTP-endpointen `/mcp` fungerar med tänkt MCP-klient.
- [ ] Kontrollera att hosted-läget bara exponerar metadata-only tools.
- [ ] Testa att nya promptmallar i `mcp-server/prompts/` är korrekt registrerade i `mcp-server/skills.json`.
- [ ] Gå igenom `.gitignore` efter verkliga arbetsflöden och justera om anonymiserad exempeldata behöver versionshanteras.
- [ ] Verifiera mot `promptbanken`-repots Supabase-projekt att RPC-funktionerna `app_private.verify_mcp_key` och `app_private.get_workspace_prompts` faktiskt är migrerade och fungerar end-to-end med en riktig MCP-nyckel.
- [ ] Ta ställning till om den stale migrationen `supabase/migrations/20240629_create_mcp_keys.sql` (tabellen `mcp_keys`) ska tas bort ur det här repot.

## Senare
- [ ] Dokumentera rekommenderat klientflöde för lokal routing mer praktiskt om klientimplementation tillkommer.
- [ ] Utvärdera om hosted metadata-guard ska köras i `block` efter drift med `warn`.
- [ ] Lägg till fler fokuserade tester om serverns API-yta växer.

## Klart
- [x] Skapade lokalt arbetsminne med markdown-filer i projektroten.
