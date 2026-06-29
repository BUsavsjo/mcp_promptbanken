# Logg

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
