# Agentinstruktioner

## Roll
Du hjälper till att utveckla detta projekt stegvis och hålla projektets arbetsminne uppdaterat.

## Arbetssätt
- Läs `PROJECT.md`, `TODO.md` och senaste posten i `LOG.md` när du återupptar projektet.
- Gör små, testbara ändringar.
- Förklara större vägval innan du genomför dem.
- Följ befintlig filstruktur.
- Skriv dokumentation på svenska.
- Håll projektet enkelt och begripligt.
- Föreslå inte ny komplexitet utan tydlig nytta.
- Uppdatera `README.md` om körsätt, installation eller användning ändras.
- Uppdatera `TODO.md` när nya uppgifter uppstår eller blir klara.
- Uppdatera `LOG.md` efter varje arbetspass.
- Uppdatera `DECISIONS.md` när ett vägval eller beslut fattas.
- Uppdatera `PROJECT.md` om syfte, mål, nuläge eller avgränsning ändras.

## Efter varje arbetspass
Avsluta alltid med en kort status:

1. Vad ändrades?
2. Vad fungerar?
3. Vad återstår?
4. Vad är nästa rekommenderade steg?
5. Vilka filer har uppdaterats?

## Säkerhet
- Lägg aldrig personuppgifter, elevdata, rådata, exporter, API-nycklar, tokens eller `.env`-filer i Git.
- Använd anonymiserad exempeldata.
- Kontrollera `.gitignore` innan nya datafiler läggs till.
- Om projektet hanterar data från skola, frånvaro, betyg, elevregister eller andra verksamhetssystem ska du vara extra försiktig.

## Teknisk kontext
Se `CLAUDE.md` för fullständig teknisk dokumentation: repo-layout, körning, miljövariabler, Supabase-integration och kodkonventioner.

## Egen testtrafik mot MCP-servern
- Varje anrop du själv gör mot `/mcp` eller `/mcp/key` för test, kontroll eller felsökning (prod `mcp.promptbanken.se`, dev `mcp-dev.promptbanken.se`) ska skicka headern `X-Promptbanken-Analytics: off`. Annars sparas anropet i `library_usage_events` och snedvrider adminstatistiken.
- Gäller curl, egna skript, kontraktstester och livekontroller. `mcp-server/scripts/check_live_open.py` och kontraktstest-skillen `promptbanken-mcp-contract-test` skickar den redan. Lägg till den i varje nytt skript som anropar servern.
- `/sse` läser inte headern och kan inte räknas bort. Använd `/mcp` för egna tester när det räcker.
- Headern är ingen hemlighet och ger ingen behörighet. Den stänger bara av statistiken för just det anropet.
- Logga aldrig söktext från MCP-anrop. Integritetspolicyn (`privacy-mcp-en.html`, avsnitt 5.1) lovar att bara söktextens längd sparas.
- Statistik från före 2026-11-10 innehåller egen testtrafik.

## Supabase MCP
Projektet har Supabase MCP kopplat (`supabase`-server i `.claude/settings.json`).
Använd Supabase MCP-tools för att:
- Köra migreringar (`supabase/migrations/`)
- Granska tabellstruktur (`mcp_keys`, `workspaces`, `content_items`)
- Debugga RLS-policies

## Agent-skills
Installerade i `.agents/skills/`:
- `supabase` — Supabase-specifika instruktioner
- `supabase-postgres-best-practices` — Postgres best practices för Supabase
