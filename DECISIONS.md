# Beslut

## 2026-07-17 - Valvets skrivverktyg utökar 2026-07-12-mönstret till en tvådelad Free/Pro-modell

### Beslut
Valvets tre skrivverktyg (`save_my_item`, `update_my_item`, `archive_my_item`)
följer samma smala, loggade write-mönster som `save_workspace_prompt`
(2026-07-12), men `save_my_item` är öppet för Free-nycklar också (5
sparningar/kalendermånad), inte bara Pro. `update_my_item`/`archive_my_item`
förblir Pro-only. Loggningen delar samma `app_private.mcp_write_attempts`-
tabell som `save_workspace_prompt`, nu med en `tool`-kolumn så flera
write-verktygs kvoter/rate limits inte blandas ihop.

### Skäl
Free-planens hela värde är att kunna spara ett fåtal egna promptar/assistenter
utan att uppgradera — att kräva Pro för `save_my_item` hade gjort Valvet
meningslöst för Free-användare. `update`/`archive` är däremot mer krävande
att göra säkert (optimistic locking, arkiv-status) och bedömdes inte vara
kärnvärdet för en gratisanvändare, så de förblev Pro-only i linje med det
smala mönster 2026-07-12-beslutet efterlyste för framtida write-tools.

### Konsekvens
Servern har nu två write-verktyg med olika plan-gating-nivåer istället för
ett enhetligt Pro-only-mönster. Framtida write-tools måste fortsätta
motivera sin egen plan-gräns explicit (se 2026-07-12-beslutet) — detta är
inte en generell sänkning av write-gränsen till Free.

## 2026-07-17 - log_write_attempt ska aldrig parsa RPC-svarets body

### Beslut
`vault.log_write_attempt` gör ett rått `httpx.post` + `raise_for_status()`
utan att anropa `.json()` på svaret, istället för att gå via den delade
`_call_rpc`-hjälparen som de övriga fem Valvet-funktionerna använder.

### Skäl
Upptäckt live mot staging under Plan B Task 4: `log_write_attempt`-RPC:n
returnerar `void` (HTTP 204 No Content, tom body). `_call_rpc` anropar alltid
`.json()` på svaret, vilket kastar `JSONDecodeError` på en tom 204-body —
fångas av `except Exception`, men loggas som
`vault_log_write_attempt_failed`, trots att `raise_for_status()` redan hade
passerat och loggraden faktiskt skrevs. Samma fälla undveks redan i den
äldre `pro_templates.log_write_attempt` (gör aldrig `.json()`), men
`vault.py` (Task 1) återanvände `_call_rpc` för bekvämlighet utan att märka
att den funktionen antar en icke-tom JSON-body.

### Konsekvens
`_call_rpc` är fortfarande rätt val för alla Valvet-RPC:er som faktiskt
returnerar en rad/lista (`list_items`, `search_items`, `get_item`,
`save_item`, `update_item`, `archive_item`) — bara void-RPC:er (just
`log_write_attempt`) ska gå direkt via `httpx.post`. Framtida void-RPC:er i
detta repo bör följa samma mönster, inte `_call_rpc`.

## 2026-07-12 - Loggning av avvisade write-försök flyttad till ett separat RPC-anrop

### Beslut
`app_private.save_prompt_for_key` loggar inte längre avvisade försök
(ogiltig nyckel, inte Pro, rate limit, m.fl.) inifrån sin egen transaktion.
En ny funktion, `app_private.log_write_attempt`, gör bara en ren INSERT utan
någon validering som kan kasta fel, och anropas av Python-lagret som ett
eget, separat HTTP/PostgREST-anrop efter att ett fel fångats.

### Skäl
Upptäckt under live-verifiering mot staging 2026-07-12: den ursprungliga
`insert ... ; raise exception ...`-ordningen loggade aldrig något i praktiken.
Postgres rullar tillbaka HELA transaktionen när en `raise exception` inte
fångas, vilket river upp loggposten som skrevs bara ögonblick innan i samma
anrop. Bara `success`-vägen (som aldrig raisar) persisterade sin loggrad.
Konsekvens: rate limit-räknaren (baserad på antal loggade försök senaste 60
sekunderna) räknade i praktiken bara lyckade skrivningar — kunde aldrig
faktiskt bromsa en nyckel som upprepade gånger skickar ogiltig indata eller
missar risk-check-godkännandet, vilket var hela poängen med gränsen.

### Konsekvens
En separat RPC-transaktion per loggpost innebär en liten extra
nätverksrundtripp vid avvisade anrop (aldrig vid lyckade), och loggningen är
"best effort" — om `log_write_attempt`-anropet i sig misslyckas (nätverksfel
m.m.) sväljs det tyst i Python (`log_write_attempt` i `pro_templates.py`)
snarare än att krascha användarens svar. Rate limit-räknaren missar därför
fortfarande spam av rent ogiltiga nyckelhashar (de avvisas redan innan
räknarens SELECT körs i `save_prompt_for_key`) — men skyddar korrekt mot en
giltig Pro-nyckel som missbrukas upprepade gånger, vilket är det
säkerhetsrelevanta scenariot.

## 2026-07-12 - Smalt, Pro-gated write-undantag från read-only-gränsen

### Beslut
Servern fick sitt första write-verktyg, `save_workspace_prompt`, trots den
tidigare uttalade "servern är read-only"-gränsen i `PROJECT.md`/`CLAUDE.md`.

### Skäl
Användaren vill kunna säga "spara det här som en mall" i valfri MCP-klient
(Claude, ChatGPT, Copilot) mot den publikt nåbara adressen, inte bara från en
lokalt körande stdio-process. Verktyget är avsiktligt smalt: bara en enda
skrivväg, bara Pro-nycklar, `visibility` hårdkodad till privat, och innehållet
är avsett att redan vara klientgeneraliserat (namn/personnummer borttaget)
innan det når servern — se `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md`.

### Konsekvens
Servern är inte längre strikt metadata-only. Framtida write-tools måste
motivera samma smala, loggade, Pro-gated mönster explicit — detta beslut är
inte en generell öppning för godtycklig skrivning.

## 2026-07-08 - Kontextstyrda Pro-verktyg porterade in med samma tillitsmodell som list_pro_templates

### Beslut
De tre nya verktygen (`list_my_private_prompts`, `list_my_shared_workspaces`, `list_shared_workspace_prompts`) lades till i `pro_templates.py`, inte i `supabase_repository.py`, och anropar RPC:erna direkt med bara `SUPABASE_URL`/`SUPABASE_ANON_KEY` — ingen `mcp_server`-roll/JWT.

### Skäl
`promptbanken`-repot beviljade `get_workspace_prompts_for_key` och `list_shared_workspaces_for_key` direkt till `anon` (samma modell som `get_pro_templates_for_mcp_key`): nyckelns sha256-hash är i sig beviset på behörighet. Det skiljer sig från den äldre `get_workspace_prompts` (i `supabase_repository.py`), som kräver den begränsade `mcp_server`-rollen. Att blanda in de nya funktionerna i `supabase_repository.py` hade felaktigt antytt att de behöver samma JWT-baserade rollväxling.

### Konsekvens
Om `promptbanken`-repot i en framtida migration ändrar behörighetsmodellen för dessa RPC:er (t.ex. kräver en roll istället för ren anon-grant) måste `pro_templates.py` uppdateras separat från `supabase_repository.py`.

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
