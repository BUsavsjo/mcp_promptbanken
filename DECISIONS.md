# Beslut

## 2026-06-30 - Hosted-servern ska vara öppen utan global Bearer-nyckel

### Beslut
`PROMPTBANKEN_MCP_API_KEY` lämnas tom i produktions-`.env`. `/sse` och `/mcp` är därmed helt öppna utan Bearer-krav och visar Promptbankens publika prompts till vem som helst.

### Skäl
Avsedd produktdesign: ett helt öppet läge för de publika promptarna, och ett separat per-användarläge där en privat `X-MCP-Key`-header (inte den globala Bearer-nyckeln) lägger till användarens egna workspace-prompts. De två mekanismerna är oberoende — `PROMPTBANKEN_MCP_API_KEY` är ett globalt på/av-skydd för hela servern, `X-MCP-Key` är en per-anrops-identifierare mot Supabase.

### Konsekvens
Alla HTTP-endpoints utom `/healthz` är nåbara utan autentisering så länge `PROMPTBANKEN_MCP_API_KEY` är tom. Om servern någon gång ska låsas ned helt (t.ex. vid missbruk) är vägen dit att sätta ett värde där — men det måste kommuniceras till alla klienter i förväg eftersom det då blir ett krav överallt utom `/healthz`, inte bara för workspace-funktionen.

## 2026-06-30 - README ska beskriva RPC-baserad Supabase-integration, inte tabellbaserad

### Beslut
`README.md` uppdaterades till att beskriva den RPC-baserade nyckelverifieringen (`X-MCP-Key`-header, `app_private.verify_mcp_key`, `app_private.get_workspace_prompts`) istället för den äldre tabellbaserade modellen (`mcp_keys`-tabell, `PROMPTBANKEN_MCP_USER_KEY`-env).

### Skäl
README hade inte hängt med när arkitekturen ändrades (dokumenterat i `CLAUDE.md`). Detta skapade en risk att någon kör den stale migrationen `20240629_create_mcp_keys.sql` eller konfigurerar fel miljövariabel.

### Konsekvens
Migrationsfilen `supabase/migrations/20240629_create_mcp_keys.sql` ligger kvar i repot men är dokumenterad som ej använd. Den faktiska migrationen ägs av `promptbanken`-repot. Det är ännu inte verifierat live att RPC-funktionerna finns i den riktiga databasen — se `TODO.md`.

## 2026-06-15 - Lokalt arbetsminne

### Beslut
Vi valde att införa ett enkelt lokalt arbetsminne med markdown-filer i projektroten.

### Skäl
Projektet ska kunna återstartas snabbt utan ett större projektnav, MCP-lager eller central agent. Markdown-filer är enkla att läsa, versionshantera och uppdatera stegvis.

### Konsekvens
Framtida kodagenter ska läsa arbetsminnesfilerna innan större ändringar och uppdatera dem när nuläge, beslut eller nästa steg förändras.
