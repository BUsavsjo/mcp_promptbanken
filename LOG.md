# Logg

## 2026-06-30

### Gjort
- Granskade om Supabase-integrationen är klar. Slutsats: koden (`supabase_repository.py`) är skriven mot ett RPC-baserat schema (`app_private.verify_mcp_key`, `app_private.get_workspace_prompts`) som enligt `CLAUDE.md` ägs av det separata `promptbanken`-repot — inte verifierat live i denna session eftersom Supabase-MCP inte var ansluten.
- Uppdaterade `README.md`-avsnittet "Workspace-skills från Supabase" så det matchar den faktiska arkitekturen: `X-MCP-Key`-header per anrop (inte `PROMPTBANKEN_MCP_USER_KEY`-env), RPC-baserad nyckelverifiering (inte `mcp_keys`-tabellen), och en tydlig notis om att migrationen i det här repot är stale.

### Nuläge
- README var inaktuellt och beskrev en äldre arkitektur (tabellen `mcp_keys`, env-variabeln `PROMPTBANKEN_MCP_USER_KEY`) som inte längre stämmer med koden.
- Det är fortfarande inte verifierat att RPC-funktionerna faktiskt finns migrerade i den riktiga Supabase-databasen — det kräver tillgång till `promptbanken`-repot eller en ansluten Supabase-MCP.

### Nästa steg
- Verifiera RPC-funktionerna mot live-databasen (se `TODO.md`).
- Ta ställning till om den gamla `mcp_keys`-migrationen ska tas bort.

### Frågetecken
- Ska den stale migrationsfilen `20240629_create_mcp_keys.sql` tas bort helt, eller bara stå kvar som dokumenterat ej använd?

## 2026-06-15

### Gjort
- Skapade ett enkelt lokalt arbetsminne i projektroten.
- La till `PROJECT.md`, `TODO.md`, `LOG.md`, `DECISIONS.md`, `AGENTS.md` och `DATA-SAFETY.md`.
- Utökade `.gitignore` med skydd för hemligheter, lokal data, exporter, cache och vanliga byggartefakter.

### Nuläge
- Projektet är en minimal MCP-server för Promptbanken.
- Hosted-läget är avsett att vara metadata-only.
- Local-läget kan hantera användartext lokalt.
- Det fanns redan lokala ändringar i repot innan arbetsminnet skapades.

### Nästa steg
- Läs `PROJECT.md`, `TODO.md` och senaste posten i `LOG.md` vid nästa återstart.
- Verifiera att `.gitignore` inte blockerar filer som faktiskt ska versionshanteras.
- Fortsätt med verifiering av Streamable HTTP och hosted/local-lägen.

### Frågetecken
- Vilken MCP-klient ska vara primär målmiljö för verifiering?
- Ska arbetsminnet senare få en återkommande rutin, till exempel uppdatering inför varje commit?
