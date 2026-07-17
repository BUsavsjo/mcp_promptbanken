# Projekt: Promptbanken MCP

## Syfte
Projektet gör Promptbankens kommunala promptar tillgängliga som skills via en minimal MCP-server.

## Bakgrund
Kommunala användare behöver kunna hitta och använda gemensamma promptmallar på ett sätt som är enkelt, säkert och tydligt. Hosted-läget ska kunna publiceras utan att användarens uppgift, dokumenttext eller annan känslig indata skickas till servern.

## Mål
- Exponera promptmallar och skill-metadata via MCP och read-only REST-endpoints.
- Stödja både publik hosted-drift och lokal användning.
- Hålla hosted-läget metadata-only.
- Ge klienter tillräcklig metadata för lokal routing, riskkontroll och promptkompilering.
- Dokumentera drift, säkerhet, loggning och tillägg av nya promptar.

## Avgränsning
Projektet ska inte köra någon AI-modell eller fungera som ett stort projektnav. Servern var till 2026-07-12 helt read-only; den har sedan dess smala, uttryckliga write-undantag: `save_workspace_prompt` för en klientgenererad och GDPR-granskad Pro-mall samt Valvets `save_my_item`, `update_my_item` och `archive_my_item` för den autentiserade nyckelägarens egna promptar/assistenter. Rå användarchatt ska fortfarande inte skickas till eller sparas av servern. Denna första arbetsminnesversion ska bara bestå av lokala markdown-filer i repot.

## Nuläge
Projektet innehåller en MCP-server i `mcp-server/`, promptmallar i `mcp-server/prompts/`, skill-katalog i `mcp-server/skills.json`, Docker-stöd och npm-script i rotens `package.json`.

Plan B för Valvet utvecklas i worktreet/branchen `worktree-valvet-plan-b`. Task 1–3 är implementerade: RPC-klienten `vault.py`, tre läsverktyg och tre skrivverktyg med MCP-, REST- och hosted-guard-stöd.

## Nästa större steg
Kör Plan B Task 4: full end-to-end-verifiering mot staging med riktiga Free- och Pro-testnycklar när Plan A:s RPC:er är applicerade där.
