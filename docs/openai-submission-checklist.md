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

### Reproducerbar lokal HTTP-smoke

Port `8765` valdes för en isolerad lokal smoke så att processen inte kan
kollidera med Docker-/produktionsstandardens port `8000`. Kör från repo-roten
i ett separat PowerShell-fönster och låt processen vara igång under anropen:

```powershell
$env:PROMPTBANKEN_MCP_MODE = 'hosted'
$env:MCP_HOST = '127.0.0.1'
$env:MCP_PORT = '8765'
Push-Location mcp-server
.\.venv\Scripts\python.exe -m server.http_server
```

Följande anrop använder en uttryckligt syntetisk ogiltig nyckel. Den är inte en
test- eller produktionsnyckel. Inga råa promptdata skickas i dessa bodies.

```powershell
$baseUrl = 'http://127.0.0.1:8765'
$syntheticKeyHeader = @{ 'X-MCP-Key' = 'local-invalid-test-key' }

# 1. Anonym /mcp tools/list: HTTP 200 och exakt nio publika namn.
$toolsListBody = @'
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
'@
$toolsList = Invoke-WebRequest -Uri "$baseUrl/mcp" -Method Post -ContentType 'application/json' -Body $toolsListBody -UseBasicParsing
$actualNames = @((($toolsList.Content | ConvertFrom-Json).result.tools | ForEach-Object name) | Sort-Object)
$expectedNames = @('get_client_routing_instructions','get_package','get_template','health_check','list_package_prompts','list_packages','list_templates','recommend_packages','search_templates') | Sort-Object
Compare-Object $expectedNames $actualNames

# 2. Privat verktyg på /mcp, även med header: JSON-RPC-fel -32601.
$privateCallBody = @'
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_my_items","arguments":{}}}
'@
$privateCall = Invoke-WebRequest -Uri "$baseUrl/mcp" -Method Post -ContentType 'application/json' -Headers $syntheticKeyHeader -Body $privateCallBody -UseBasicParsing
($privateCall.Content | ConvertFrom-Json).error.code

# 3. Ogiltig nyckel på /mcp/key tools/list: JSON-RPC-fel -32001.
$keyToolsListBody = @'
{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}
'@
$keyToolsList = Invoke-WebRequest -Uri "$baseUrl/mcp/key" -Method Post -ContentType 'application/json' -Headers $syntheticKeyHeader -Body $keyToolsListBody -UseBasicParsing
($keyToolsList.Content | ConvertFrom-Json).error.code
```

Observerat 2026-07-26: första anropet gav HTTP 200; `Compare-Object` gav ingen
utdata och listan var exakt de nio namnen ovan. Det privata anropet gav
`-32601`, och `/mcp/key` med den syntetiska nyckeln gav `-32001`. Processen
stoppades efter smoketesten. Inga nycklar eller rå promptdata loggades.

Kvar efter merge och push: bygg och deploy i den godkända releaseordningen, VPS-/produktionsrök av `/mcp` och `/mcp/key` med en dedikerad giltig Free- och Pro-testnyckel, samt samtliga öppna verktygsanrop mot produktionskatalogen. Server-, Listing-, Review Evidence- och Security-checkboxarna ovan är medvetet fortfarande omarkerade; lokala resultat är inte produktions- eller submissionsbevis.
