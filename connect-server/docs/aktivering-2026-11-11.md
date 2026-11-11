# Connect DEV – tillförlitlig aktivering och personlig AI (2026-11-11)

Gren: `feat/connect-dev-activation` (från `codex/connect-write-flow`).
Driftsatt: `connect-dev.promptbanken.se`, image
`promptbanken-connect:simplify-candidate`. Ingen ändring i PROD.

## Bedömning: READY WITH KNOWN LIMITATIONS

Kontraktet, livscykeln och felhanteringen fungerar och är verifierade både
automatiskt och live på DEV. Automatisk aktivering i vanlig ChatGPT-chatt är
fortfarande inte uppmätt.

## Ändrade filer och funktioner

| Fil | Ändring | Typ |
| --- | --- | --- |
| `connect_service/work_layer.py` | `ROUTING_RULES`: uttrycklig prioritetsordning (namngiven > eget arbetssätt > specialist > fråga) och att ett eget arbetssätt med `extends` ersätter sin specialist | Förbättring |
| | `HOW_TO_APPLY` (nytt) i `get_support` för specialister och egna arbetssätt: skala efter uppgiften, metodens struktur i bakgrunden, kvalitetskraven alltid kvar | Förbättring |
| | `adaptation_hint` i `get_support` när ett aktivt eget arbetssätt bygger på specialisten | Förbättring |
| | `HOW_TO_PERSONALIZE`: steg för att ångra | Förbättring |
| | `restore`: förhandsvisning med `confirm_text` och `saved_text` | **Fel** (förhandsvisningen saknade text för användaren) |
| | `_check_version`: förklarar att inget sparades, visar nuvarande och angiven version | Förbättring |
| `connect_service/personal.py` | Saknat regel-id listar användarens regler; "ändrar ingenting" blev "Det gäller redan. Inget har ändrats." | Förbättring |
| `tests/test_user_scenarios.py` (ny) | 26 regressionstester för de åtta scenarierna, negativa fall och bakåtkompatibilitet | Test |
| `docs/chatgpt-testprotokoll.md` (ny) | Manuellt protokoll för vanlig ChatGPT-chatt | Dokumentation |

Tidigare samma dag (redan mergat i `codex/connect-write-flow`): förenkling
till sju kärnverktyg, `confirm_text`, verifiering efter sparning,
felklassning, rättning av återanvänt `request_id`, tömd sammanfattning,
flerordssökning och vänlig historik utan profil.

## Tester

### Automatiska: 123 gröna

| Område | Täckning |
| --- | --- |
| MCP-kontrakt | Sju verktyg i `core`, biblioteksverktyg nekas, `full` ger 26; inget verktyg tar fri uppgiftstext |
| Routinglogik | Tre lägen, enkel fråga utan Connect, val vid namn, prioritetsordning, Superplan inte på ord |
| Metodhämtning | Alla nio stöd, oförändrad metodtext, `how_to_apply` med kvalitetskrav kvar |
| Konfliktregler | Eget arbetssätt före specialist, `adaptation_hint`, inaktivt arbetssätt erbjuds inte |
| Profilens livscykel | Förhandsvisa → spara → hämta → tillämpa → inaktivera → historik → återställa → ny konversation |
| Regelomfång | Global regel når alla nio och egna arbetssätt; specialistregel läcker inte till de åtta andra eller till orelaterade arbetssätt |
| Fel | Saknad profil, tom historik, saknat regel-id, versionskonflikt, redan avstängd regel, kvot, personuppgifter |
| Negativa | Inget skrivs utan `confirmed: true` |
| Bakåtkompatibilitet | Profil sparad i tidigare format laddas, tillämpas, har historik och kan sparas vidare |

### Live på DEV (testkonto, syntetiska regler)

| Steg | Resultat |
| --- | --- |
| Saknat regel-id `r9` | "Hittar ingen regel med id r9. Användarens regler: r1 …; r2 …" |
| Versionskonflikt | "Inget sparades: inställningarna har ändrats sedan de lästes (nu version 3, angiven 1) …" |
| Workshopledaren | `how_to_apply` med; inga regler läckte (r1 av, r2 bara Utredaren) |
| Återställ version 2 | Förhandsvisning "Går tillbaka till version 2. Slår på regeln ”Kortare sammanfattningar” igen. Vill du spara det?", sparad och verifierad som version 4 |
| Ny kontext | `always_apply` innehåller r1 igen |

### Blinda klienttester i Claude (subagenter, en ny konversation per fall)

Varje fall kördes av en separat agent som bara fick användarens meddelande
och Connect DEV som installerad koppling. Agenten valde själv om och hur
Connect skulle användas. Detta mäter Claude, inte ChatGPT.

| Fall | Resultat |
| --- | --- |
| 1 Enkel fråga, N1 omskrivning, N2 översättning | Godkänt: inget Connect-anrop |
| 2 Utredning, 3 workshop, 4 dataanalys | Godkänt: rätt specialist, inga tekniska ord |
| 5 Global regel (ja) | Godkänt: `confirm_text` ordagrant, sparat först efter ja, verifierat |
| 6 Specialistregel (ja) | Godkänt: omfång Utredaren |
| 7 Nej till sparning | Godkänt: inget sparat, ingen ny fråga, önskemålet följt i samtalet |
| 8 Utredning i ny konversation | Godkänt: båda reglerna tillämpade, problembeskrivning först |
| 9 Workshop i ny konversation | Godkänt: global regel med, utredningsregeln läckte inte |
| 10 Visa sparade regler | Godkänt: två regler, inte den nekade |
| 11 Eget arbetssätt (ja) | **Underkänt först** (sparades som global regel), godkänt efter rättning |
| 12 Använd arbetssättet i ny konversation | Godkänt: arbetssättet valdes före specialister, alla steg följda |
| 13 Stäng av regel | Godkänt: avstängd, inte borttagen |
| 14 Ångra | Godkänt, men `confirm_text` visade "version 8"; rättat |
| 15a Ta bort regel, 15b ta bort arbetssätt | Godkänt |

Första körningen av fall 5 stoppades av Claude Codes behörighetskontroll
redan vid förhandsvisningen ("Unrequested Commit in a Connected App"), eftersom
förhandsvisning och sparning går genom samma verktyg. Klienter kan alltså
behandla förhandsvisningen som en skrivning. Testet fortsatte efter att
användaren gav tillstånd för de tre spara-verktygen.

### Rättat efter klienttesterna

- `how_to_personalize`: en önskan om en viss typ av uppgift blir ett eget
  arbetssätt, aldrig en regel för alla uppgifter.
- Återställning visar inte versionsnummer för användaren.
- `how_to_apply`: beskriv inte metodens principer ("Så här arbetar jag …").
- `save_my_way_of_working`: beskrivningen anger obligatoriska fält;
  `confirm_text` upprepar inte "när".

### Manuellt i ChatGPT

ChatGPT-testet med kontot `wenstrompeter` stoppades av Free-kvoten. Se
`docs/kvot-felsokning-2026-11-11.md`. Protokoll: `docs/chatgpt-testprotokoll.md`.

## Beroende av ChatGPT:s automatiska verktygsval

- **Om Connect anropas** vid "Utred det här" utan att Connect nämns.
- **Att regler används vid enkla frågor**: dessa besvaras medvetet utan Connect.
- **Att rätt stöd väljs**: Connect ger underlag och ordning men väljer inte.
- **Att `confirm_text` visas ordagrant** och att inget sparas utan ja: servern
  kräver `confirmed: true`, men frågan till användaren ställs av modellen.

Lyckade direkta MCP-anrop bevisar inte automatisk aktivering.

## Migrations- och kompatibilitetsrisker

- Ingen databasmigrering, ingen ny datamodell, `SCHEMA` oförändrat (1).
  Sparade profiler och arbetssätt läses som tidigare (test med äldre dokument).
- Kontexten växte till cirka 11 300 tecken. Testgränsen är 12 000. Fler
  regler eller arbetssätt ökar den; bör följas upp.
- Felmeddelandet för saknat regel-id visar regeltexterna. Det är användarens
  egna regler och skickas bara till användarens egen klient.

## Öppet sedan tidigare

- Produktbeslut B1 (Free-kvoten för anpassningar). Testkontot på DEV har
  `max_prompts = 100`.
- Connect-token är en generell Supabase-token (blockerar PROD, inte DEV).
