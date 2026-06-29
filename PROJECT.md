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
Projektet ska inte köra någon AI-modell, spara användarinput eller fungera som ett stort projektnav. Denna första arbetsminnesversion ska bara bestå av lokala markdown-filer i repot.

## Nuläge
Projektet innehåller en MCP-server i `mcp-server/`, promptmallar i `mcp-server/prompts/`, skill-katalog i `mcp-server/skills.json`, Docker-stöd och npm-script i rotens `package.json`.

Aktuell branch vid skapandet av arbetsminnet är `feature-mcp-streamable`. Det finns lokala ändringar i projektet som inte ingår i detta arbetsminne.

## Nästa större steg
Verifiera streamable HTTP-flödet och den publika hosted-konfigurationen, inklusive att hosted-läget fortsätter vara metadata-only.
