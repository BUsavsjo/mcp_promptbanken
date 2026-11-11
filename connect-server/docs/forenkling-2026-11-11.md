# Förenkling av Connect DEV – 2026-11-11

Gren: `feat/connect-dev-simplify` (bygger på `feat/connect-dev-vnext`).
Miljö: endast Connect DEV (`connect-dev.promptbanken.se`). Ingen ändring i PROD.

Produktlöfte: **Din AI. Ditt sätt att arbeta.** Användaren ska aldrig behöva
förstå MCP, prompter, specialister eller routing.

## Steg A – nuläge

### 1. Rätt stöd vid rätt uppgift

| Fynd | Konsekvens |
| --- | --- |
| Instruktionen (`SERVER_INSTRUCTIONS`) är en lång mening som blandar tre fall: enkel fråga, arbete i flera steg och personlig anpassning. | Modellen får ingen tydlig beslutsregel för när Connect *inte* ska användas, och ingen regel för "nästa gång vill jag …". |
| Inget sätt att välja specialist uttryckligen beskrivs i verktygskontraktet (bara som MCP-prompts). | "Använd Utredaren" fungerar bara om modellen gissar rätt. |
| `superplan` har `use_when` på triggerfraser ("hjälp mig hela vägen"), medan regeln säger "välj inte på enstaka sökord". | Motsägelse i indexet. |
| Inaktiva egna arbetssätt listas bland valbara stöd. | Modellen kan välja något användaren stängt av. |
| Plugin-skill och README antyder automatisk aktivering. | Om ChatGPT eller Claude anropar Connect avgör klienten, inte Connect. Det får inte lovas. |
| Katalogsökning matchar hela frasen (`data.py`). | Flerordsfrågor som metoderna själva föreslår ger alltid noll träffar. |

### 2. Anpassning genom vanligt samtal

Byggstenarna finns: `save_my_profile` (regler med `applies_to`),
`save_my_way_of_working`, förhandsvisning, `expected_version`, historik och
`get_support` som slår ihop regler med metoden.

| Fynd | Konsekvens |
| --- | --- |
| Inget säger hur "Jag vill alltid …" ska översättas till rätt verktyg och fält. | Modellen måste själv lista ut regel vs arbetssätt och `applies_to`. |
| Förhandsvisningen är en teknisk diff (`rule.r1`, `before/after`). | Användaren ser fältnamn i stället för en fråga på svenska. |
| Ingen verifiering efter sparning. En återanvänd `request_id` svarar `saved` fast inget sparades (bekräftat i test). | Användaren kan få höra "sparat" när det inte är sant. |
| Regler som gäller "all" når bara modellen via `get_support`. | En sparad regel ("kortare sammanfattningar") används inte vid uppgifter utan specialist. |

### 3. Friktion

| Fråga | Svar (från kod och migreringar) |
| --- | --- |
| Utan profil? | Fungerar. `profile.exists: false`; första sparade önskemålet skapar profilen. Ingen spärr. |
| Blockeras personliga arbetssätt av kvoten? | **Ja.** Profil och varje arbetssätt sparas som privata Creator-prompter (`module='kommun'`, standard). Triggern `enforce_content_access_model` räknar dem mot `workspaces.max_prompts` = **3 på Free**. |
| Kan ett Free-konto med tre prompter använda grundläggande personalisering? | **Nej.** Första sparningen av en regel skapar en profilprompt och nekas. |
| Skiljer felen på kvot, behörighet och tekniskt fel? | **Nej.** Allt utom kvot och Open-referens blir "Ändringen kunde inte genomföras". 401/403, 5xx och valideringsfel ser likadana ut. |
| Kan användaren ändra eller avaktivera? | Ja, tekniskt (`rules.update active:false`, `active:false` på arbetssätt, historik). Men inget i kontraktet berättar det för modellen på ett sätt användaren förstår. |

### Filer som behöver ändras

- `connect_service/work_layer.py` – instruktioner, routingregler, kort beskrivning per stöd, personaliseringsflöde, läsbar förhandsvisning, verifiering efter sparning, kvotfel för anpassningar, filtrering av inaktiva arbetssätt.
- `connect_service/data.py` – felklassning (kvot, behörighet, validering, tekniskt) och sökning på flera ord.
- `connect_service/app.py` – `update_my_prompt` ska behålla sammanfattning och kategori som inte skickas med.
- `plugin/skills/promptbanken-connect/SKILL.md` – samma enkla flöde, ärligt om aktivering.
- `tests/test_work_layer.py`, `tests/test_data.py`, `tests/test_app.py` – acceptansscenarierna.
- `README.md`, denna fil, samt repo-rotens `TODO.md`, `LOG.md`, `DECISIONS.md`.

### Produktbeslut som krävs (blockerande, ej genomförda)

**B1. Ska personliga anpassningar räknas mot Free-kvoten på 3 privata prompter?**
Nuläge: ja, profil + varje arbetssätt tar en plats. Ett Free-konto med tre
prompter kan inte spara en enda personlig regel. Detta motsäger löftet
"Ditt sätt att arbeta" för Free-användare.

Alternativ (alla kräver en migrering i `promptbanken` och därför ett beslut):

1. **Undanta Connect-profilen** (kategori `connect-profil`, högst en per användare) från räkningen. Grundläggande personalisering fungerar alltid; egna arbetssätt räknas fortfarande. *Rekommenderas.*
2. Undanta både profil och arbetssätt, med ett eget tak (t.ex. 5 arbetssätt på Free).
3. Behåll nuläget och säg tydligt att anpassningar kostar en promptplats.

Tills beslut finns: Connect visar ett begripligt kvotmeddelande (alternativ 3 i
kommunikation, inget ändrat i kvoterna).

**B2. Säkerhet före PROD (känd sedan tidigare, påverkar inte DEV-arbetet).**
Connect-token är en generell Supabase `authenticated`-token
(PRODUCT.md, verifierat 2026-09-22). Inget av detta arbete ändrar det, och
Connect får inte flyttas till PROD innan det är löst.

## Steg B – genomfört

Driftsatt på Connect DEV som `promptbanken-connect:simplify-candidate`
(byggd från arbetskatalogen, gren `feat/connect-dev-simplify`).
Rollback: `cp docker-compose.yml.before-simplify docker-compose.yml && docker-compose rm -sf connect && docker-compose up -d connect`
i `~/promptbanken-connect-dev`.

### Ändringar

| Område | Ändring |
| --- | --- |
| Rätt stöd | Instruktion i tre lägen; regel för val av specialist vid namn; `in_short` per specialist; Superplan inte på enstaka ord; inga löften om automatisk aktivering; bara aktiva arbetssätt är valbara. |
| Anpassning genom samtal | `how_to_personalize` (tolka, välj, visa, fråga, spara, använd); `confirm_text` på svenska i varje förhandsvisning; läsning efter sparning och `verified: true`; `always_apply` i kontexten. |
| Friktion | Felen har `kind` (quota, permission, validation, technical); begripligt kvotbesked för anpassningar; profilnot när profil saknas. |
| Buggar | Återanvänt `request_id` rapporterades som sparat; `update_my_prompt` tömde `summary`; flerordssökning gav noll träffar. |

### Resultat

| Scenario | Automatiskt (pytest) | Live på DEV |
| --- | --- | --- |
| 1 Enkel fråga, ingen specialist | Godkänt (kontraktet) | Godkänt: blind ny konversation (Claude-subagent) anropade inte Connect |
| 2 Utreda för- och nackdelar | Godkänt | Godkänt: Utredaren valdes, regeln "börja med problemet" följdes |
| 3 Workshop för 20 | Godkänt | Godkänt: Workshopledaren valdes |
| 4 "Nästa gång kortare sammanfattningar" | Godkänt | Godkänt: förhandsvisning "Ny regel: ”Kortare sammanfattningar” – gäller alla uppgifter. Vill du spara det?", sparad och verifierad |
| 5 Regeln i ny konversation | Godkänt | Godkänt: kom tillbaka i `always_apply` och `personal_rules` |
| 6 Free-konto på kvotgränsen | Godkänt | Godkänt: begripligt besked, inget ändrat |
| 7 Nej lämnar inget | Godkänt | Godkänt: biblioteket tomt efter förhandsvisning |
| 8 Avaktivera anpassning | Godkänt | Godkänt, även med kontot på kvotgränsen |
| Återanvänt request_id | Godkänt | Godkänt: ärligt fel i stället för "sparat" |

Totalt 88 automatiska tester gröna (19 nya acceptanstester).

### Kända begränsningar

- **Regler som gäller allt** når bara modellen när Connect anropas. En enkel fråga anropar inte Connect, så "kortare sammanfattningar" används inte där. Det är en följd av läge 1 (enkla frågor utan Connect) och klientens verktygsval; ingen backendbugg.
- **Valet av specialist** görs av klientens modell. Testerna ovan visar att underlaget räcker för Claude; ChatGPT, se nedan.
- **Integritetskontrollen** fångar personnummer, e-post och telefon, inte namn.
- **Metodtexterna** hänvisar fortfarande till Opens gamla verktygsnamn; `tool_mapping` översätter. Ändras i `agent-skills`, inte här.
- **Creator-verktygen** (`create_my_prompt` m.fl.) saknar fortfarande förhandsvisning. Utanför scope.

### ChatGPT-prov (ej genomfört)

Provet i en ny vanlig ChatGPT-konversation utan att nämna Promptbanken är
**inte gjort**. ChatGPT var inte inloggat i den webbläsare testet hade
tillgång till, och Connect DEV behöver vara tillagd som anslutning i
ChatGPT-kontot. Inget resultat redovisas därför, och ett uteblivet anrop från
ChatGPT ska inte tolkas som backendfel.

Så görs provet: ladda om Connect DEV i ChatGPT (ny verktygslista), starta en
ny chatt och skriv scenario 1–5 utan att nämna Promptbanken. Notera per
meddelande om Connect anropas, vilket stöd som hämtas och om sparade regler
används.

### Sju kärnverktyg (2026-11-11, kväll)

Connect exponerar som standard bara de sju verktyg som löftet bygger på:
`get_connect_context`, `get_support`, `get_open_item`, `save_my_profile`,
`save_my_way_of_working`, `get_my_history`, `restore_my_version`.

- Styrs av `CONNECT_TOOL_PROFILE`: `core` (standard) eller `full` (även de 19
  Creator-verktygen för prompter, paket och delningar). Ingen kod är borttagen.
- Anrop till ett verktyg utanför profilen ger `-32601` med ett tydligt besked.
- Metodernas katalogsökning (`search_templates`, `list_packages`) översätts nu
  till `get_open_item` med slug ur metodens referenser, inte till
  `search_open_catalog`.
- Hantering av prompter, paket och delningar sker på app.promptbanken.se.
- Tester: 93 gröna, varav 5 nya för profilen.

### Testkontots tak (endast dev)

2026-11-11: testkontots personliga workspace i `promptbanken-dev`
(`8045d6d0-…`) fick `max_prompts = 100` för att kunna testa Connect utan
Free-taket. Planen är fortfarande `free`. Detta är en testinställning, inte
lösningen på B1. Återställ med
`update public.workspaces set max_prompts = 3 where id = '8045d6d0-5510-487d-a497-b4d26436e9ab';`
Verifierat: fyra aktiva Connect-dokument sparades efter ändringen.

### Redo för användartest?

Ja, som DEV-kandidat för internt test i Claude. För ChatGPT: först efter
provet ovan. För Free-användare med tre prompter: först efter beslut B1.
