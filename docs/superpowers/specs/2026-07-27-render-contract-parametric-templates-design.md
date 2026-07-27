# Renderingskontraktet för den öppna MCP-ytan: read-only katalog, klienten renderar

## Revisionshistorik

- **v1 (2026-07-27, förmiddag):** byggd på en FELAKTIG premiss — att
  server-side rendering och `binding_overrides` inte fanns i koden.
  Grundorsaken var att undersökningen läste en förlegad lokal checkout
  (`7cf5008`) istället för `origin/main`.
- **v2 (2026-07-27, kväll, detta dokument):** omskriven mot en verifierad
  bild av `origin/main` (`6c51fa4`) plus en live-verifiering mot
  produktionscontainern. v1:s beslut om `binding_overrides` och rendering
  är **upphävda och ersatta** av besluten nedan. Peters explicita
  arkitekturbeslut (2026-07-27 kväll) väger tyngre än v1 och gäller
  framåt.

## Syfte

Fastställa det slutgiltiga kontraktet för Promptbanken Öppen (den publika,
nyckellösa MCP-ytan) INNAN kod ändras. Peters beslut, ordagrant:

> Öppen endpoint är strikt read-only. Klienten äger all logik för
> ifyllning, tolkning och sammanfogning. Servern levererar bara
> katalogdata, metadata och malltext. Ingen rendering, ingen sparning,
> ingen modifiering, ingen användarspecifik state i öppna endpointen.
> `context_keys`, roller, målgrupp och ton på serversidan används bara för
> filtrering, rekommendation och variantval — inte för att bygga en
> färdig prompt.

## Verifierad nulägesbild (mot `origin/main` = `6c51fa4`, INTE den lokala
## arbetskopian, som är förlegad och inte ska pushas/rebasas/cherry-pickas)

### A. Server-side rendering finns redan i produktion — och ska kopplas ur

`mcp-server/server/catalog_renderer.py` (tillagd i `d8ed2cf`, 2026-07-26)
implementerar `resolve_bindings()` + `render_template_text()` med riktig
`binding_overrides`-logik (when/set-regler), `default_bindings`, och
tonböjning (`TONE_FORMS`, `ton_neutrum`). Den anropas från
`_catalog_prompt_to_template` (`mcp_server.py:410`) och
`_catalog_package_to_payload` (`mcp_server.py:432`), vilket gör att
**alla sex katalog-payloadfunktioner** renderar text idag:
`_list_templates_payload`, `_search_templates_payload`,
`_get_template_payload`, `_list_packages_payload`, `_get_package_payload`,
`_list_package_prompts_payload`.

Dessa payload-funktioner tar INTE emot `mcp_key` eller profil — de
används identiskt av öppna ytan (`/mcp`) och nyckelautentiserade ytan
(`/mcp/key`). Konsekvens: rendering kan inte stängas av "bara för öppna
ytan" med en enkel villkorssats — det krävs antingen att renderingen tas
bort helt (öppet + autentiserat), eller att profil/nyckel träs ned genom
sex funktioner till renderaren. **Beslut: ta bort helt**, se Beslut 1.

Webbappen (`promptbanken`-repot) påverkas INTE — den hämtar katalogen
direkt via Supabase-RPC och har sin egen klientsidiga renderare
(`script.js`: `resolvePromptBindings`, `renderPromptTemplate`,
`replaceInputMarkers`). Den saknar dock `ton_neutrum`-logiken som
`catalog_renderer.py` har — server och webb producerar redan idag olika
text för samma mall, en trolig delförklaring till användartestets
"inkonsekvent renderad text"-observation.

### B. En andra, ofiltrerad exponeringsyta: FastMCP:s `/sse`-register

Utöver den handrullade JSON-RPC-vägen (`_tool_definitions()` /
`_PUBLIC_OPEN_TOOL_NAMES`, som redan korrekt filtrerar till 9 publika
verktyg för `/mcp`) finns en HELT SEPARAT registreringsväg: FastMCP:s
egna `@mcp.tool()`-dekoratorer, som driver `/sse` + `/messages/`-rutterna
(monterade i samma Starlette-app, proxade publikt och nyckellöst av
Caddy — bekräftat i `/etc/caddy/Caddyfile` på VPS:en). FastMCP har ingen
per-request auth-filtrering; alla `@mcp.tool()`-funktioner registreras
ovillkorligt.

**Live-verifierat 2026-07-27** (skript kört inne i produktionscontainern
mot `http://127.0.0.1:8000/sse` med `mcp`-SDK:t):

- `/sse` exponerar **28 verktyg**, inklusive samtliga skriv-/valv-/privata
  verktyg (`save_workspace_prompt`, `activate_package`,
  `deactivate_package`, `copy_template_to_valvet`, `list_my_items`,
  `save_my_item`, `update_my_item`, `archive_my_item`,
  `list_active_packages`, `list_my_prompts`, `list_my_private_prompts`,
  `list_my_shared_workspaces`, `list_shared_workspace_prompts`,
  `search_my_items`, `get_my_item`), mot 9 på den handrullade ytan.
- **Men:** anrop utan nyckel avvisas korrekt på applikationsnivå —
  `deactivate_package` → `"MCP-nyckel krävs (X-MCP-Key eller
  Authorization)."`, `list_my_items` → `workspace_status: "no_key"`, tom
  lista. **Ingen faktisk skriv- eller läsåtkomst till andras data är
  möjlig via `/sse` utan giltig nyckel.** Risken är bekräftat begränsad
  till **exponering av verktygsnamn/scheman**, inte dataåtkomst.
- Caddy-åtkomstloggen (`/var/log/caddy/mcp_access.log`, 4002 rader vid
  kontrolltillfället) visar **574 träffar på `/sse`** och **978 på
  `/messages`**, med User-Agent-strängar `openai-mcp/1.0.0` och
  `Claude-User` bland avsändarna — d.v.s. **riktiga externa MCP-klienter
  använder `/sse` aktivt idag.** `/sse` kan därför INTE tas bort utan att
  riskera en brytande förändring för kända, aktiva integrationer. Det
  finns ingen separat nyckelautentiserad SSE-rutt (bara `/sse` +
  `/messages`, ingen `/sse/key`) — de 19 icke-publika verktygen saknar
  alltså redan idag en legitim autentiserad SSE-användning att bevara.

### C. GDPR-motsägelse i hosted-guarden

`mcp-server/server/hosted_guard.py` (rad ~56, 58, 59) tillåter uttryckligen
`input_text`-argumentet för `get_template`, `get_package` och
`list_package_prompts`, och validerar det som godtycklig sträng. Detta
motsäger direkt serverns egen instruktionstext (`mcp_server.py:1295`,
`get_client_routing_instructions`) om att inte skicka personuppgifter
till den öppna MCP-servern. Ett read-only-kontrakt ska stänga den dörren.

### D. Övrigt oförändrat från v1 (fortfarande giltigt)

- `context_keys` → profilvariant-val i Supabase-RPC:erna
  (`catalog.py:50-97`) är en fungerande, oberoende mekanism för urval —
  INTE sammansättning av text. Behålls och blir den enda sanktionerade
  kontext-mekanismen framåt (se Beslut 2).
- Rollmatchning (`package_recommendations.py`): statisk dict, hanterar
  redan särskrivna sammansättningar men inte hopskrivna
  ("kommunikationschef"). Ofarlig fallback vid okänd roll. Se Beslut 3,
  oförändrat från v1.
- `list_templates` returnerar full `prompt_text` utan `fields`/`limit`.
  Se Beslut 4, oförändrat från v1.
- Äldre mallar saknar `risk_level`/`area`/`tags`/`output_format`,
  fallback till missvisande default-värden. Se Beslut 5, oförändrat från
  v1.

## Beslut 1: Ta bort server-side rendering helt — öppet OCH autentiserat

`render_template_variant`-anropen i `_catalog_prompt_to_template`
(`mcp_server.py:410`) och `_catalog_package_to_payload` (`:432`), samt
hjälpfunktionen `_render_bindings()` (`:225-244`), tas bort. Payloaden
innehåller inte längre `rendered_prompt_text`/`rendered_intro_text`.
Klienten får `prompt_text`/`intro_text` + `parameter_schema` +
`default_bindings` + `binding_overrides` (rådata, oförändrade från
Supabase) och gör ifyllningen lokalt — exakt som webbappen redan gör.

`catalog_renderer.py` som FIL tas INTE bort i denna omgång — den kopplas
bara ur anropskedjan. Den är den enda platsen med fungerande
tonböjningslogik (`ton_neutrum`), och tas bort permanent (eller flyttas
till webbappens JS) i en separat, senare uppgift när det är klarlagt att
ingen framtida yta behöver den.

`role`/`audience`/`tone`/`input_text`-argumenten tas bort ur
inputschemat för `get_template`, `get_package`, `list_package_prompts`
(både FastMCP-signaturer och JSON-RPC `inputSchema`), eftersom de blir
meningslösa utan rendering — och `input_text` dessutom är en GDPR-risk
(se Beslut 1b).

## Beslut 1b: `input_text` tas bort ur hosted-guardens allowlist

`hosted_guard.py` ska inte längre acceptera `input_text` för något
publikt katalogverktyg. Stäng motsägelsen mot den egna
integritetsinstruktionen.

## Beslut 2: Ingen `binding_overrides`-mekanism byggs SEPARAT — den som
## finns i `catalog_renderer.py` tas ur bruk, inte vidareutvecklas

Till skillnad från v1:s (felaktiga) premiss fanns redan en fungerande
`binding_overrides`-motor. Den kopplas ur enligt Beslut 1, inte in.
`context_keys` → profilvariant-radval förblir den enda mekanismen för
kontext på serversidan. Om Supabase-katalogdata redan har
`binding_overrides`-fält per rad (den gjorde det, för renderaren), kan
klienten läsa och tillämpa dem själv — samma sätt webbappen redan gör
det (`script.js`).

## Beslut 3 — SSE-exponeringen: gate, ta inte bort

**Peters beslut, verifierat och bekräftat genomförbart:**

- Öppen/publik hosted-tjänst ska INTE exponera FastMCP-registret med 28
  verktyg.
- SSE-implementationen behålls i kod (aktiva connectorer — `openai-mcp`,
  Claude — använder den), men läggs bakom en explicit
  `SERVER_MODE`/feature-gate.
- I hosted/public-läge (vilket är det enda läge produktionen kör) ska
  FastMCP:s registrerade verktygsmängd begränsas till SAMMA 9-verktygslista
  som den handrullade publika ytan (`_PUBLIC_OPEN_TOOL_NAMES`): `health_check`,
  `get_client_routing_instructions`, `list_templates`, `search_templates`,
  `get_template`, `list_packages`, `get_package`, `list_package_prompts`,
  `recommend_packages`.
- `/sse`-ENDPOINTEN tas inte bort — den förblir nåbar för befintliga
  connectorer, men serverar bara den publika verktygsmängden. Eftersom
  ingen autentiserad `/sse`-variant existerar idag finns inget legitimt
  användningsfall som förloras genom att begränsa registret.
- Om en autentiserad SSE-yta blir ett verkligt behov senare (extern
  klient som vill nå Valvet/skriv-verktyg via SSE snarare än
  `/mcp/key`), är det ett eget, namngivet beslut med egen spec — inte en
  bieffekt av denna städning.

## Beslut 4: Rollmatchning — oförändrat från v1

Liten substring-precisionsfix i `package_recommendations.py::recommend()`
för hopskrivna sammansättningar. Ingen generell NLP. Se v1-motivering,
fortfarande giltig.

## Beslut 5: `list_templates` metadata-only-läge — oförändrat från v1

`fields: str = "full" | "summary"`, default `"full"` för
bakåtkompatibilitet. Ingen paginering i denna fas.

## Beslut 6: Metadata-backfill för äldre mallar — oförändrat från v1,
## fortsatt prioriterad

Ren innehållsuppgift i Supabase, inte en kodändring. Se v1-motivering.

## Kontraktsbeskrivningar som ska ändras

1. `mcp_server.py:1294` (routing-instruktionen) — ta bort hänvisningen
   till `rendered_prompt_text`/`rendered_intro_text`; ersätt med
   instruktion om att klienten alltid får rådata och gör ifyllnaden
   lokalt.
2. `mcp_server.py:1292` — ta bort render-argumenten ur
   `get_template`-exempelanropet.
3. Tool-beskrivningar i `_tool_definitions()` för `get_template`
   (`~1983-1988`), `get_package` (`~2017-2022`), `list_package_prompts`
   (`~2040-2046`) — ta bort påståenden om `rendered_*`-fält.
4. FastMCP-docstrings (`mcp_server.py:923-925, 949-951, 965-967`).
5. `privacy_instruction`/`client_flow`-texten (`mcp_server.py:1300-1317`)
   — skärp så den inte längre motsägs av `input_text`-argumentet.
6. `mcp-server/mcp-contract.json` — dokumentera `/sse` explicit (idag
   helt frånvarande ur kontraktet trots att den är en aktiv, publik yta)
   med samma 9-verktygslista som `/mcp`, ELLER notera uttryckligen att
   `/sse` är en transportvariant av samma publika profil.

## Regressionstester som behövs INNAN kodändring (se arbetsordning nedan)

1. **Read-only-kontrakt för katalogpayloads:** assertera att svaret från
   `_list_templates_payload`/`_get_template_payload`/`_get_package_payload`/
   `_list_package_prompts_payload` INTE innehåller `rendered_prompt_text`
   eller `rendered_intro_text`, men FORTFARANDE innehåller `prompt_text`,
   `parameter_schema`, `default_bindings`, `binding_overrides`.
2. **Identiskt katalogsvar oavsett auth:** samma `tools/call` via
   `_handle_mcp_message` med `tool_profile="public"` och
   `tool_profile="key_authenticated"` (mockad giltig nyckel) ska ge
   byte-identiskt katalogsvar.
3. **FastMCP-registret mot public-listan (den viktigaste nya kontrollen):**
   ```python
   tools = asyncio.run(mcp.list_tools())
   assert {t.name for t in tools} <= PUBLIC_TOOLS  # i hosted-läge
   ```
   Hade fångat SSE-exponeringen. Läggs till i
   `test_openai_publication_contract.py`.
4. **`hosted_guard` blockerar `input_text`:** positivt test att
   `get_template`/`get_package`/`list_package_prompts` med `input_text`
   ger en warning (t.ex. `reason == "unexpected_argument"`), inte tyst
   godkännande.
5. Invertera/ta bort de 4 testerna i `test_catalog_renderer.py` och de 3
   renderings-asserterande testerna i `test_catalog_context_tools.py`
   (rad ~122, ~211, ~244 i nuvarande version) som idag kodar in det gamla
   beteendet.

## Arbetsordning (Peters beslut, 2026-07-27 kväll)

1. ~~Verifiera live vad `/sse` exponerar och om tom nyckel avvisas.~~ **KLART.**
2. ~~Kontrollera Caddy-konfiguration och loggar efter befintliga `/sse`-klienter.~~ **KLART.**
3. ~~Uppdatera specen mot verifierat nuläge.~~ **Detta dokument.**
4. Lägg till kontraktstester (se listan ovan) INNAN kodändring.
5. Gatea `/sse` (Beslut 3).
6. Koppla ur renderingen från samtliga katalogfunktioner (Beslut 1).
7. Ta bort renderingsargumenten och `rendered_*`-fälten ur svarskontraktet
   (Beslut 1, 1b).
8. Kör regressionstest mot både öppen och nyckelautentiserad yta.

**Ingen produktionskod ändras förrän steg 4 (kontraktstester) är skrivna
och Peter har godkänt att gå vidare till steg 5.**

## Öppna osäkerheter (ej gissade, kräver uppföljning)

- Om någon publicerad mall i Supabase förlitar sig på
  `ton_neutrum`-omskrivningen (`catalog_renderer.py`, skriver om "ett
  {{ton}}") för att bli grammatiskt korrekt. Om ja måste mallens källtext
  i Supabase justeras innan renderingen kopplas ur permanent, annars får
  klienten ogrammatisk rå text.
- Om `openai-mcp`/`Claude-User`-klienterna som setts i loggen förlitar sig
  på att kunna SE (inte anropa) några av de 19 icke-publika verktygen —
  osannolikt givet att anropen ändå skulle faila, men inte
  hundraprocentigt uteslutet utan att fråga OpenAI/Anthropic-sidan.

## Icke-mål

- Ingen ny `binding_overrides`-tabell eller override-logik byggs.
- Ingen generell svensk yrkestitel-NLP.
- Ingen paginering (`limit`/`offset`) på `list_templates` i denna fas.
- `/sse`-endpointen tas inte bort, bara dess exponerade verktygsmängd
  begränsas.
