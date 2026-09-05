# Beslut

## 2026-09-05 - Promptbanken Connect byggs som en separat OAuth-tjänst

### Beslut
Promptbanken Connect byggs i `connect-server/` med egen startpunkt,
beroenden och framtida host. Promptbanken Open 1.2.2, dess `mcp-server/` och
dess driftkonfiguration ändras inte av Connect-arbetet medan Open är under
granskning.

Connect använder OAuth 2.1 med authorization code och PKCE via Supabase OAuth
Server. Access tokens verifieras med asymmetrisk signatur via JWKS samt mot
issuer, audience, utgångstid och `sub`. Supabases OAuth-access-token har
standardmålgruppen `authenticated`; OAuth-klientens identitet finns i
`client_id`. OAuth-auktorisering ersätter inte RLS eller serverns egen
behörighetskontroll.

### Följd
Connect använder samma Creator-bibliotek som användaren ser på
`app.promptbanken.se`: egna Creator-prompter, sparade biblioteks-prompter,
paket och delningar. All läsning går via Creator-RPC:er med anroparens
OAuth-token och publishable key; ingen separat datakopia eller
service-rollnyckel införs. Första leveransen ger läsparitet. Under beta får
inloggade användare sedan skrivverktyg, och efter beta kontrolleras Pro per
skrivverktyg. Full design finns i
`docs/superpowers/specs/2026-09-05-connect-creator-library-design.md`.

## 2026-08-30 - `area` är paketets slug, inte en egen kategori — och workflow slutar vid effektuppföljning

### Beslut 1: ingen separat områdestaxonomi
I den öppna katalogen **är `area` paketets slug**. `_open_catalog_areas()`
(`mcp_server.py`) bygger listan av områden från publicerade paketslugs, och
`_catalog_area_index()` stämplar varje prompts `area`/`area_label` från det
paket den är medlem i. En prompt som inte ligger i något paket får
`area: null` — den är fortfarande publicerad och sökbar (`list_templates`
läser alla publicerade prompts oberoende av paket), men tappar sitt
områdesfält och kan dyka upp som `null` i `recommended_areas` för okända
roller.

**Följd:** "flytta en prompt till ett annat område" finns inte som operation.
Det som finns är "flytta en prompt till ett annat paket". Ett handover-förslag
om att sätta `area = processer` på workflowstegen byggde på fel premiss och
genomfördes inte.

**Följd 2:** `recommend_packages` rekommenderar områden, alltså paket. Ett nytt
paket blir automatiskt ett nytt rekommenderbart område så snart det publiceras
— men syns bara för en roll om paketets slug läggs till i `_AREA_ROLES` i
`package_recommendations.py`.

### Beslut 2: `Från behov till effekt` är sex steg, inte sju
Workflowet slutar vid steg 6 (`Bestäm hur effekten ska följas upp`). Efter
steg 6 har förändringen normalt inte genomförts, så det finns inget utfall att
utvärdera — ett obligatoriskt utvärderingssteg där tvingar fram en utvärdering
av något som inte hänt. `Utvärdera och justera` är därför en **fristående
specialistmall** i collectionen `Verksamhetsutveckling och processer`, dit
användaren återkommer när förändringen varit i drift och det finns
uppföljningsdata. Steg 6:s text pekar vidare dit.

Grundprincipen bakom uppdelningen: **collection = verktygslåda, workflow =
arbetssätt.**

### Beslut 3: `behov-till-effekt` rekommenderas bara för `verksamhetsutvecklare`
Tills vidare. `utredare`, `samordnare` och `chef` är rimliga tillägg men
ändrar deras rekommendationslistor, så de lades inte till utan eget beslut.

## 2026-08-08 - Ingen CI/staging idag — direkt-till-prod för både kod och databas, med en live-koll-regel efter RPC-migrationer

### Beslut
Varken `mcp_promptbanken`-koden eller databasen (`promptbanken`-repots
Supabase-migrationer) har någon staging-miljö eller CI-pipeline. Flödet är
och förblir: lokal ändring → branch → merge main → `vps-deploy`-skillen
bygger om och startar om direkt på prod-VPS:en. Migrationer går på samma
sätt rakt mot produktions-Supabase (`supabase db push`, eller manuell SQL
i Studio när CLI:n kollisionerar — se STATUS.md för flera exempel).

Detta ändras inte i sig — rimligt för nuvarande drift/teamstorlek. Vad som
skärps: de publika MCP-verktygen (`search_templates`, `get_template`,
`list_templates`, `list_packages`, `get_package`, `list_package_prompts`,
`recommend_packages`) läser live från RPC:er i `promptbanken`-repot. En
migration som ändrar en sådan RPC:s outputform bryter det frysta publika
kontraktet **utan att någon deploy sker i det här repot** — inget bygge,
inget kontraktstest fångar det per automatik.

**Ny regel:** efter varje migration som rör en RPC de publika verktygen
anropar (`get_pro_templates_for_mcp_key`, `list_published_prompts`,
`get_published_prompt`, `list_published_package_prompts`, m.fl.), gör en
direkt live-koll — `tools/call` mot minst `search_templates` och
`get_template` på riktig prod — innan migrationen räknas som klar. Vänta
inte på nästa manuella test.

**Varför:** 2026-08-05-buggen (`save_prompt_for_key` skrev `status='draft'`,
läsvägen filtrerade på `status='published'`, varje sparad rad blev
permanent oläsbar) låg dold i flera dagar innan ett Peters ChatGPT-test
hittade den — ingen automatisk signal fångade RPC-driften. Efter
OpenAI-publicering är kostnaden för den typen av tyst regression högre:
en extern granskare eller skarp ChatGPT-användare kan stöta på den innan
vi själva gör det.

## 2026-08-08 - Det frysta publika kontraktet väger tyngre efter OpenAI-publicering

### Beslut
2026-07-31 beslutades att `/mcp`s nio publika, anonyma verktyg är ett
"fryst publikt kontrakt" (se posten nedan). Sedan Promptbanken Open MCP
gick live i OpenAI:s ChatGPT app directory (ansökan inskickad 2026-08-08,
se `LOG.md`) väger den frysningen tyngre:

- **Namn, inputschema och outputform på de nio existerande verktygen får
  inte ändras** utan att räkna med att det kan trigga en OpenAI-
  omgranskning eller bryta den redan publicerade appen. En sådan ändring
  kräver ett medvetet beslut, inte en rutinmässig refaktorering.
- **Nya verktyg är fortfarande additivt okej** — precis som innan.
- **Beskrivningstexter** (tool-beskrivningar, `health_check`-meddelanden,
  `app_info` i `chatgpt-app-submission.json`) ska hållas fria från
  hårdkodade tal och reklam för icke-exponerade funktioner (se separat
  beslut nedan, samma datum) — en extern granskare läser exakt de
  strängarna som appens självbeskrivning.
- **Release notes** skrivs per `SERVICE_VERSION`-bump från och med nu
  (mönster etablerat vid 1.2.0→1.2.1), så varje framtida OpenAI-
  omgranskning har ett facit över vad som ändrats.

**Varför:** innan publicering var kontraktsbrott bara en risk mot egna
klienter (Claude Code, andra MCP-klienter). Efter publicering är OpenAI:s
granskningsprocess och den skarpa ChatGPT-appen också beroende av att
kontraktet håller — kostnaden för att bryta det steg påtagligt samma dag
som ansökan skickades in.

## 2026-08-08 - Publika verktygsbeskrivningar får aldrig hårdkoda katalogstorlek eller reklamera icke-exponerade funktioner

### Beslut
`search_templates`s docstring/HTTP-beskrivning hade hårdkodat "42 full
prompts" — katalogen är dynamisk (var 72 vid fyndet) och talet drev direkt
isär från verkligheten igen så fort en admin publicerade fler mallar.
Omskrivet till "without fetching every full prompt", ingen siffra alls.
Samtidigt hade `health_check`s öppna `no_key`-meddelande en rad om att
autentisera för Pro/Free-mallar på app.promptbanken.se — men den öppna,
publika MCP-ytan exponerar bara läsverktygen mot den öppna katalogen, inte
Pro/Free-flödet. Meddelandet reklamerade en funktion anroparen inte kan nå
via den här ytan. Borttaget.

**Regel framåt:** verktygsbeskrivningar och statusmeddelanden i den publika
(anonyma, no-key) MCP-ytan får aldrig innehålla siffror som kan drifta
(antal mallar, antal paket) och får aldrig hänvisa till funktioner som
kräver auth/plan den ytan inte själv exponerar. Skriv generiskt ("alla
mallar" istället för "alla 42 mallar") eller hämta talet dynamiskt om det
verkligen behövs.

**Varför:** upptäcktes under förberedelse för OpenAI ChatGPT app directory-
ansökan (se `LOG.md` 2026-08-08) — en extern granskare läser exakt de här
strängarna som appens självbeskrivning, så drift här syns direkt utåt,
inte bara internt.

## 2026-07-31 - Endpoint-strategi inför ChatGPT-publicering: /mcp fryses, Valvet växer via valfri OAuth på samma endpoint

### Beslut
`/mcp` publiceras som den öppna ChatGPT-connectorn och behandlas därefter som
ett fruset publikt kontrakt. När Valvet senare ska nå ChatGPT-användare sker
det genom att lägga *valfri* OAuth på samma `/mcp`-endpoint (anonyma anrop
fortsätter få exakt de nio katalogverktygen, inloggade får Valvet-verktygen
därtill) — inte genom en ny endpoint som `/mcp/vault`. `/mcp/key`
(header-nyckel) förblir spåret för API-klienter (Claude Code, egna
integrationer); OAuth blir ChatGPT-spåret. Endpoints delas per auth-modell
(anonym / nyckel / admin), aldrig per feature.

Tre hårda regler följer av detta:
1. `/mcp` får aldrig göras auth-krävande — den dagen anonyma anrop 401:as
   dör varje publicerad ChatGPT-installation samtidigt.
2. De nio publika verktygens namn och inputscheman är frysta efter
   publicering. Nya verktyg får läggas till (append-only); befintliga får
   aldrig döpas om eller ändras breaking. (`list_pro_templates` →
   `list_templates` hann göras före publicering; efter publicering hade
   samma byte varit en incident.)
3. `/mcp/key` eller `/sse` publiceras aldrig som ChatGPT-URL — `/sse` är
   legacy, `/mcp/key` är fel auth-modell för den öppna katalogen.

### Skäl
Peters mål är att publicera den öppna katalogen i ChatGPT nu och lansera
Valvet mot samma användarbas senare, utan att någonsin klippa av befintliga
kunder. MCP-specen är byggd för valfri auth per anrop, och servern gör redan
mönstret "olika verktygslistor per auth-kontext" (`/mcp` vs `/mcp/key`), så
tillväxtvägen är att lägga OAuth-flödet bredvid — inte att bygga om.
Publicerade ChatGPT-appar kräver dessutom OAuth för användarinloggning
(anpassade headers som `X-MCP-Key` stöds inte i publicerade connectors),
vilket gör OAuth-på-`/mcp` till den enda framkomliga ChatGPT-vägen för
Valvet oavsett.

Feature-uppdelade endpoints förkastades aktivt: två connector-configs per
betalande användare är sämre UX utan säkerhetsvinst — auktoriseringen sitter
redan i RPC-lagret (nyckelhash → plan → kvot), inte i endpoint-pathen.
`tools/list` är UX, inte auktorisering; det är därför kontraktstestet har
`blockedCalls`.

### Konsekvens
`mcp-contract.json`:s public-grupp blir append-only-listan och
kontraktstestet är vakten: larmar om ett publikt verktyg försvinner, byter
namn eller ändrar metadata. Framtida granularitet (t.ex. en
Förvaltnings-nyckel med läsrätt på katalogen men utan Valvet-skrivrätt)
löses med finare scopes i `api_keys.scopes` (`['mcp:read']`,
`['mcp:vault']`) på befintliga endpoints — schemafältet finns redan,
servern kollar bara inte scopes per verktyg än. När MCP-specens
OAuth-stöd tas i bruk byts nyckelmodellen, inte endpoint-strukturen.

## Admin-MCP: JWT-brygga istället för ny nyckeltyp (2026-07-28)

Katalogens write-RPC:er (`create_catalog_prompt` m.fl., 2026-07-21) är redan
`auth.uid()`-gated för `platform_owner`. Istället för att bygga en parallell
MCP-nyckelmodell för admin, håller `/admin`-routen Peters riktiga Supabase
refresh_token som hemlighet och växlar in access-tokens per anrop --
RLS/RPC:er förblir helt oförändrade. Se spec/plan-filerna för fullständig
motivering.

## 2026-07-25 - publik `tools/list` utan nyckel ska bara visa den öppna katalogytan

### Beslut
`tools/list` i hostat läge ska inte längre alltid exponera hela interna
verktygsuppsättningen. När anropet saknar MCP-nyckel ska servern bara
annonsera den publika read-only-katalogen: `health_check`,
`list_templates`, `search_templates`, `get_template`, `list_packages`,
`get_package`, `list_package_prompts`, `recommend_packages`,
`list_skills`, `list_skills_simple`, `get_skill` och
`get_client_routing_instructions`.

### Skäl
Den externa testrapporten 2026-07-25 visade att den öppna connectorns
`tools/list` fortfarande exponerade Valvet-, användar- och skrivverktyg
trots att den publika produkten ska vara en öppen katalog. Att verktygen
senare nekar i `tools/call` är inte tillräckligt — själva verktygsytan är
en del av produktgränsen och påverkar både användarförtroende och
modellens verktygsval.

### Konsekvens
`_tool_definitions()` är nu kapabilitetsstyrd av om en MCP-nyckel finns.
Det här är en verktygsytfix för den öppna connectorn, inte en full
omnamning eller omsegmentering av alla autentiserade flöden. Live-deploy
och extern verifiering återstår.

## 2026-07-25 - `search_templates` ska tåla `null` i katalogmetadata

### Beslut
`search_templates` ska normalisera katalogfält som kan vara `null`
(`title`, `syfte`, `output_format`, `area_label`, `tone_hint`, `tags`)
innan fritextmatchningen byggs, i stället för att anta att alla fält är
strängar eller stränglistor.

### Skäl
Det blockerande P0-felet i den externa testrapporten återgavs lokalt som
en `TypeError` i `_search_templates_payload()` när `weak` byggdes via
`" ".join([...])` och något av katalogfälten var `None`. Katalog-RPC:n
äger datat och kan legitimt returnera `null`; servern måste därför vara
defensiv i adapter-/söklagret.

### Konsekvens
Meningsfull fritextsökning kraschar inte längre på saknade metadatafält.
Fixen ändrar inte rankinglogiken i övrigt och löser inte de separata
P1-frågorna om att `area` fortfarande är `null` i katalogadaptern eller att
kontextinnehållet ännu inte skiljer sig mellan profiler.

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
