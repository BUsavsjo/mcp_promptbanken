# Beslut

## 2026-07-25 - hostad katalog läser nu publika katalog-RPC:er med context_keys

### Beslut
Den hostade MCP-serverns öppna katalog ska inte längre läsa den äldre
`get_pro_templates_for_mcp_key`-ytan för vanliga kataloganrop. I stället
ska `list_templates`/`search_templates`/`get_template` vara
bakåtkompatibla verktygsnamn ovanpå de nya publika katalog-RPC:erna
`list_published_prompts`/`get_published_prompt`, med valfri
`context_keys: string[]`. Paket exponeras additivt som nya tools:
`list_packages`, `get_package`, `list_package_prompts`.

### Skäl
Användarsidan behövde profilkombinationer som `["kommun", "skola"]`
utan att bryta befintliga MCP-klienter som redan använder
`list_templates`-familjen. Att behålla namnen men byta datakälla ger
lägst migrationsrisk och låter webb, databas och hostad MCP spegla samma
publicerade katalog.

### Konsekvens
Hosted guard och JSON-RPC-scheman måste tillåta `context_keys`, och
template-svaren mappas via ett tunt adapterlager från den nya
katalogmodellen till ungefär samma shape som tidigare. Live-deploy och
extern verifiering återstår efter denna kodändring.

## 2026-07-20 - search_templates: role som rankningssignal, inte filter

### Beslut
Peters andra omtest samma dag hittade att `role` i `search_templates`
fortfarande filtrerade bort mallar utanför rollens rekommenderade områden
(t.ex. `query=driftstörning` + `role=IT-samordnare...` + `area=kommunikation`
gav noll träffar). `allowed_areas`-hårdfiltret i `_search_templates_payload`
togs bort och ersattes med en `+5`-poängbonus som läggs till EFTER
query-poängens inklusions-gräns — role kan därmed bara omrangordna redan
relevanta träffar, aldrig lägga till eller ta bort någon. `recommend()`
utökades additivt med `matched_role`/`role_match_source`
(`"exact"`/`"compound"`/`null`)/`recommended_areas` för felsökning.
`SERVICE_VERSION` höjt till `1.2.0`. Se
`docs/superpowers/specs/2026-07-20-search-templates-role-ranking-design.md`.

### Skäl
Peters prioritetsordning var uttrycklig: area/risk_level är hårda filter,
query avgör relevans, role påverkar bara rangordningen. Föregående
implementation blandade ihop "role som rekommendation" med "role som
filter", vilket gjorde exakta träffar (rätt sökord, fel område enligt
rollen) osynliga trots att de var korrekta.

### Konsekvens
Ren beteendefix ovanpå redan deployad funktionalitet (`84a7c46`), ingen ny
yta, inga nya input-parametrar. Verifierat med fixture-skript för båda
filerna samt fullt liveanrop mot produktion med Peters exakta
acceptanstabell.

## 2026-07-20 - search_templates: OR/poängsatt matchning + rollmatchning på delord

### Beslut
Peters omtest av `search_templates`/`recommend_packages` (samma dag som de
lades till) hittade två brister:

1. `search_templates` krävde att ALLA sökordstoken matchade (AND) — en
   naturligt formulerad mening ("informera personalen om en driftstörning")
   gav 0 träffar trots att kärnordet ("driftstörning") fanns i katalogen,
   eftersom orden "personalen"/"om"/"en" inte matchade något.
2. `recommend_packages`/`search_templates(role=...)` krävde att HELA
   rollsträngen normaliserad var exakt lika med ett känt rollnamn — en
   sammansatt titel som "IT-samordnare barn och utbildning" kändes inte
   igen trots att "samordnare" ensamt gjorde det.

Fix 1 (`mcp_server.py`, `_search_templates_payload`): bytt från AND-krav
till poängsatt OR — varje sökordstoken (tokeniserad med `re.findall(r"\w+",
...)`, filtrerad genom `SkillRouter.STOPWORDS`/`_normalize` — samma
stoppordslista `route_skill` redan använder, ingen ny lista) ger +2 om den
matchar titel/taggar eller +1 om den matchar syfte/outputformat/area_label;
mall inkluderas om poäng > 0 (dvs. minst ETT ord matchar), resultat
sorteras poäng-fallande (stabil sortering behåller ursprunglig
`sort_order` vid lika poäng). Ingen hårdkodad lista över "innehållsord att
strunta i" (t.ex. "informera"/"personalen" som Peter föreslog som exempel)
— den generiska stoppordslistan (funktionsord: och/för/med/om/en osv.)
räcker för att lösa exakt samma testfall utan risken att av misstag
utesluta riktiga sökord i framtida frågor.

Fix 2 (`package_recommendations.py`, `recommend()`): rollsträngen
tokeniseras nu med samma `SkillRouter._terms()` (delar på icke-ordtecken,
filtrerar korta ord/stoppord) istället för att jämföras som en hel sträng.
Matchar ett känt rollnamn (t.ex. "samordnare") mot NÅGOT delord i den
inskickade rollen. Fixar även `recommend_packages` (inte bara
`search_templates`), samma bakomliggande funktion.

### Skäl
Peters omtest visade konkret att den tidigare implementationen var för
strikt för hur riktiga MCP-klienter/användare faktiskt formulerar sig —
tekniskt fungerande sökning som i praktiken kräver att användaren redan
plockat ut "rätt" enstaka sökord är inte token-effektiv i praktiken.

### Konsekvens
Ren kvalitetsfix av redan deployad funktionalitet, ingen ny yta. Verifierat
i tre lager (samma metod som ursprungsimplementationen): 19 enhetstester
(inkl. regressionstest att stavfelstolerans och tidigare gröna testfall
fortfarande fungerar), smoke-test mot riktig produktions-Supabase-data med
Peters exakta repro-frågor, samt full HTTP/JSON-RPC-runda mot en lokalt
startad hosted-server.

## 2026-07-20 - Nya verktyg search_templates + get_template

### Beslut
Nya MCP-verktyg `search_templates(query?, role?, area?, risk_level?, limit?)`
och `get_template(template_id)` i `mcp_server.py`/`hosted_guard.py`. Ren
klient-sidig filtrering ovanpå samma `get_pro_templates_for_mcp_key`-data som
`list_templates` redan hämtar — ingen ny RPC, ingen ny REST-endpoint, ingen
DB-migration. `search_templates` returnerar sammanfattningar utan
`prompt_text` (id/title/syfte/area/area_label/output_format/tags/risk_level);
`get_template` hämtar en enskild mall i sin helhet. `role`-parametern
återanvänder `package_recommendations.recommend()` (samma logik som
`recommend_packages`) — begränsar bara till matchande områden om rollen
känns igen, annars ingen begränsning (samma "fail open" som
`recommend_packages`). `limit` clampas till [1, antal mallar], default 10.

### Skäl
Peters MCP-användartest 2026-07-20: hela 42-mallarskatalogen (full
`prompt_text` per mall) måste hämtas via `list_templates` idag bara för att
hitta EN mall — dyrt i tokens/latens för klientmodellen och gör det svårare
för ChatGPT/Claude att välja rätt mall. `search_templates`+`get_template`
löser detta utan att ta bort `list_templates` (kvar för klienter som vill
hämta allt på en gång).

### Konsekvens
Ren tilläggsändring, inte brytande — `list_templates` oförändrat. REST-yta
(`/api/v1/*`) fick INGA nya endpoints för sök/hämta-en i denna omgång
(avsiktligt avgränsat till MCP-ytan, som var vad testet gällde) — kan läggas
till senare om webb-/REST-klienter behöver samma funktion.

## 2026-07-20 - MCP-verktyget list_pro_templates omdöpt till list_templates

### Beslut
Verktygsnamnet `list_pro_templates` (aliasbeslutet 2026-07-19 nedan) byts till
`list_templates` — i tools/list-schema, JSON-RPC-dispatch och
`hosted_guard.py`s allowlist i `mcp_server.py`. Peters uttryckliga val efter
att namnet upplevdes förvirrande nu när katalogen är öppen för alla. Modulen
`pro_templates.py`, RPC:n `get_pro_templates_for_mcp_key` och REST-pathen
`/api/v1/pro-templates` byts INTE i denna omgång — internt/historiskt, inte
vad en MCP-klient ser i verktygslistan.

### Skäl
"Alias för bakåtkompatibilitet" räckte inte som förklaring i praktiken —
namnet syns direkt för slutanvändare i MCP-klienters verktygslista och
signalerar felaktigt att något kräver Pro.

### Konsekvens
Brytande ändring för klienter som redan anropar `list_pro_templates` — kräver
ny deploy till `mcp.promptbanken.se` och att befintliga integrationer/cachade
verktygslistor uppdateras. Ej pushat/deployat än — kräver Peters go-ahead
(se konvention i CLAUDE.md/[[promptbanken-live-db-access]]).

## 2026-07-19 - Katalog-Pro avvecklad: hela promptbiblioteket öppet

### Beslut
Produktbeslut 2026-07-19 (delprojekt 6 i Promptbanken/Valvet-visionen):
Pro-gating för att LÄSA katalogen avvecklas helt. Migration
`20260719100000_open_catalog.sql` i promptbanken-repot gör att
`get_pro_templates_for_mcp_key` (och webbens `list_pro_templates()`) alltid
returnerar alla 42 mallar med full `prompt_text` och `is_unlocked=true`,
oavsett nyckel/plan — även utan nyckel. Verktygsnamnet `list_pro_templates`
behålls som alias (befintliga klienter ska inte brytas). Pro-planen finns
kvar men gäller enbart Valvet-gränser (insättningar, nycklar, kvoter) och
egna/delade arbetsytor — inte katalogaccess.

### Skäl
Promptbanken är den öppna, kurerade katalogen; Valvet är användarens privata
arbetsbank och enda ingången för att spara/aktivera. Premiumvärdet ligger i
egna ytor och volym, inte i låst kataloginnehåll.

### Konsekvens
Verktygsbeskrivningarna för `list_pro_templates` (båda definitionsställena)
får inte längre påstå teaser/Pro-krav. Teaser-koden i `pro_templates.py`
behöver inte ändras — RPC:n returnerar aldrig `prompt_text: null` längre.

## 2026-07-18 - Free får update/archive; Pro-only-delen av 2026-07-17-beslutet upphävd

### Beslut
Produktbeslut 2026-07-18: `update_my_item` och `archive_my_item` är öppna för
Free-nycklar. Gaten togs bort i promptbanken-repots migration
`20260718090000_valvet_free_update_archive_via_mcp.sql` (RPC:erna
`update_my_item_for_key`/`archive_my_item_for_key` kräver inte längre
`has_active_pro_entitlement`). `save_my_item`-kvoten (Free 5/kalendermånad)
och `save_workspace_prompt` (Pro-only) är oförändrade.

### Skäl
Update/archive är grundläggande hygien, inte premiumvärde — att spärra dem
bakom Pro innebar att en AI-klient kunde skapa poster på Free men aldrig
rätta eller städa dem.

### Konsekvens
Serverns verktygsbeskrivningar får inte längre säga "Pro-only" för
update/archive. Felklassificeringen `not_pro` i `_classify_vault_write_error`
behålls som skydd ifall RPC-sidan ändras igen.

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
