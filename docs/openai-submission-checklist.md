# OpenAI Submission Checklist

## Server
- [ ] Produktions-URL: `https://mcp.promptbanken.se/mcp`
- [ ] Anonym `initialize`, `tools/list` och samtliga nio publika `tools/call` fungerar
- [ ] Inga privata eller skrivande verktyg syns eller kan anropas
- [ ] Verktygsnamn, svenska titlar, beskrivningar, scheman och annotations är verifierade

## Listing
- [ ] Plugin-namn och kort beskrivning är slutgranskade
- [ ] Logotyp är kvadratisk och godkänd för publicering
- [ ] Privacy policy har publik HTTPS-URL
- [ ] Användarvillkor har publik HTTPS-URL
- [ ] Supportkontakt och support-URL fungerar

## Review Evidence
- [ ] Testprompt för att söka en mall är dokumenterad med förväntat svar
- [ ] Testprompt för att lista paket är dokumenterad med förväntat svar
- [ ] Testprompt för rollrekommendation är dokumenterad med förväntat svar
- [ ] Testprompt utan träff ger tom lista utan fel
- [ ] Test av privat verktygsnamn ger säkert MCP-fel utan sidoeffekt

## Security
- [ ] Loggar innehåller inte rå prompttext, MCP-nycklar eller personuppgifter
- [ ] Rate limiting och timeout-beteende är verifierat
- [ ] Privacy- och routinginstruktionen förbjuder rå persondata till den öppna MCP:n

## Verification Log

### 2026-07-26 - Task 5 lokal verifiering

Verifierat lokalt i worktreet `feat/openai-publication-readiness`. Ingen SSH,
VPS-deploy, push eller annan liveändring har gjorts.

- PASS: `mcp-server/.venv/Scripts/python.exe -m unittest discover -s mcp-server/tests -v` - 35 tester, 0 fel.
- PASS: `npm run check:python` - `python -m compileall server` utan fel.
- PASS: lokal hosted-server på `127.0.0.1:8765` - anonym `initialize` och `tools/list` på `/mcp` svarade 200. `tools/list` gav exakt nio publika read-only verktyg med annotations.
- PASS: samma lokala `/mcp`-lista förblev publik när en syntetisk MCP-nyckel skickades. Privat `list_my_items` på `/mcp` avvisades med JSON-RPC `-32601`.
- PASS: `/mcp/key` med syntetisk ogiltig MCP-nyckel avvisades före verktygslistning med JSON-RPC `-32001`. De publika statiska anropen `health_check` och `get_client_routing_instructions` svarade 200.
- EJ KÖRT: `docker-compose build`. Docker-klient och Compose finns lokalt, men Docker-daemonen var inte nåbar (`dockerDesktopLinuxEngine` saknas).
- EJ KÖRT: giltigt Free- eller Pro-nyckeltest på `/mcp/key`, samt kataloganrop som kräver Supabase. Ingen `.env`-fil eller relevant testnyckel/miljövariabel fanns lokalt.

Kvar efter merge och push: bygg och deploy i den godkända releaseordningen, VPS-/produktionsrök av `/mcp` och `/mcp/key` med en dedikerad giltig Free- och Pro-testnyckel, samt samtliga öppna verktygsanrop mot produktionskatalogen. Server-, Listing-, Review Evidence- och Security-checkboxarna ovan är medvetet fortfarande omarkerade; lokala resultat är inte produktions- eller submissionsbevis.
