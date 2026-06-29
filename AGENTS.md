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
