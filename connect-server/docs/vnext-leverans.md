# Connect DEV vNext – leverans

Datum: 2026-11-11
Gren: `feat/connect-dev-vnext` (bygger på `codex/connect-write-flow`)
Driftsatt: `connect-dev.promptbanken.se`, image `promptbanken-connect:vnext-candidate`
Status: DEV. Ingen produktionsdeploy och ingen katalogpublicering.

## Vad som är byggt

### Nio specialister som dynamiska metodstöd
- `scripts/sync_supports.py` kopierar de nio skillsen oförändrade från den
  auktoritativa källan `promptbanken/agent-skills` (`origin/main`
  `70cc52284edc`) till `connect_service/supports/`.
- Med följer metod (`SKILL.md`), referenser, mallar och skript. Ikoner och
  `agents/openai.yaml` tas inte med.
- `manifest.json` håller id, namn, `use_when`, `not_when`, version,
  källcommit och sha256 per fil. Connect vägrar starta om en fil avviker
  från manifestet. `.gitattributes` hindrar Git från att ändra radslut.
- Metodtexten skrivs aldrig om. Skillsen är skrivna för Opens verktyg, så
  `get_support` skickar med en översättning (`tool_mapping`), till exempel
  `get_template` → `get_open_item`.
- Beroenden redovisas per stöd: resurser, Open-verktyg, kodkörning
  (Verksamhetsanalytikerns `profilera.mjs`) och andra skills (Processkartan).

### Automatisk aktivering
- **A. Ren MCP:** `initialize` skickar `instructions`, och `get_connect_context`
  returnerar stödindex, routingregler och förbättringsregler.
  Verktygsbeskrivningarna säger när de ska användas.
- **B. MCP plus aktiverings-skill:** `plugin/skills/promptbanken-connect/SKILL.md`
  är en liten skill utan egna metoder. Den hämtar allt från Connect. Paketet
  finns i `plugin/` med `mcp.json` som pekar på Connect DEV.
- Båda sätten använder samma katalog.
- MCP-prompts (`prompts/list`, `prompts/get`) ger manuellt val av specialist
  som komplement.

### Personlig arbetsprofil, egna arbetssätt och förbättring över tid
- Allt lagras som privata Creator-prompter med kategorierna
  `connect-profil` och `connect-arbetssatt`, via befintliga RPC:er. Det finns
  ingen ny databasmodell och ingen migrering.
- Varje dokument har en läsbar del och ett `connect-data`-block med version
  och de tio senaste versionerna.
- **Profil:** roll, arbetskontext, språk, ton, skrivprinciper, struktur och
  kvalitetsregler.
- **Personliga regler:** varje regel gäller `all`, ett stöd eller ett `mitt:`-id,
  och kan aktiveras, inaktiveras eller tas bort.
- **Eget arbetssätt:** kan skapas från grunden eller som anpassning av en
  specialist (`extends`). Det kan inaktiveras eller tas bort (arkiveras).
- **Kombination:** `get_support` returnerar grundmetoden, användarens
  tillämpliga regler, profilen och en uttrycklig prioriteringsordning. Säkerhet
  och metodens grundregler går före personliga preferenser.
- **Uppdatering av en grundmetod** påverkar inte personliga anpassningar,
  eftersom de lagras separat och kombineras först vid hämtning.
- **Förhandsvisning:** alla sparverktyg visar exakt diff utan `confirmed`
  och sparar först med `confirmed: true` och `request_id`.
- **Versioner:** `expected_version` skyddar mot överskrivning. Historiken
  visas med `get_my_history`, och `restore_my_version` återställer som en ny
  version, så att inget går förlorat.
- **Överlappande regler** flaggas i `possible_overlaps`. Ingenting slås ihop
  utan godkännande.
- **Integritetskontroll:** sparningar med personnummer, e-postadress eller
  telefonnummer blockeras.

### Nya verktyg
`get_connect_context` (utökat), `get_support`, `get_open_item`,
`save_my_profile`, `save_my_way_of_working`, `get_my_history` och
`restore_my_version`. De 19 tidigare verktygen är oförändrade.

### Övrigt i protokollet
- Versionsförhandling (`2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`).
- `notifications/*` besvaras med 202, och `ping` stöds.

## Testresultat

| Test | Resultat |
|---|---|
| Enhets- och integrationstester (`pytest`) | 69/69 gröna, varav 33 nya |
| Katalogintegritet: alla nio, alla resurser läsbara, sha256 matchar | Grön, också i containern på VPS:en |
| Live mot Connect DEV med riktig OAuth: `get_connect_context` | Grön: nio stöd, regler och tom profil returneras |
| Live `get_open_item` mot dev-Supabase | Grön: Superplans fyra faser med text; prompt via slug |
| Hälsa efter deploy (`/healthz`), `/mcp` utan token ger 401 | Grön |
| Eval-sviten PB-CONNECT-AUTO (72 fall) | Byggd och kontrollerad, **inte körd i klient** |

## Avvikelser mot definitionen av färdig

Följande är inte verifierat och får inte rapporteras som färdigt.

1. **Automatisk aktivering i vanlig ChatGPT-chatt (punkt 2)** är inte
   uppmätt. Eval-sviten och räkneskriptet finns, men körningen kräver att
   Connect DEV (och för B även aktiverings-skillen) läggs till i ChatGPT och
   att fallen körs där. Ingen påstådd träffsäkerhet finns ännu.
2. **Jämförelsen A mot B och mot vanlig ChatGPT** är inte gjord, av samma skäl.
3. **Skrivflödet live (punkt 3–7)** är testat mot ett bibliotek i minnet som
   efterliknar Creator-RPC:erna. Det är inte kört live, eftersom den här
   sessionens claude.ai-anslutning cachar den gamla verktygslistan.
   Skrivningarna går genom samma RPC:er som de redan driftsatta verktygen
   `create_my_prompt`, `update_my_prompt` och `archive_my_prompt`, och läsningen
   `list_my_creator_prompts` är verifierad live. Fältet `category` används här
   för första gången via Connect.
4. **Befintligt bibliotek, paket och delningar (punkt 8)** täcks av de
   oförändrade testerna. Inget av det är kört live efter deployen.
5. **Testet `PB-CONNECT-AUTO-01`** fanns inte på någon gren. Sviten är byggd
   från grunden och börjar på det id:t.
6. **Påståendet om att MCP från juli 2026 ersätter `initialize`** är inte
   verifierat. Servern stöder fortfarande bara `initialize`. Instruktionerna
   finns därför även i svaret från `get_connect_context` och i
   verktygsbeskrivningarna, så de når modellen oavsett protokollväg.
7. **Integritetskontrollen** fångar bara mönster: personnummer, e-post och
   telefon. Namn och sekretess kan den inte upptäcka. Där bygger skyddet på
   modellens regler och användarens godkännande.
8. **Free-gränsen för privata prompter** gäller även profilen och egna
   arbetssätt.
9. **Stödindexet** är cirka 6 000 tecken, mer än planens mål på cirka 1 500
   token. Den fulla `use_when`-texten behölls eftersom den bär
   träffsäkerheten. Det bör ses över efter klienttestet.

## Drift

- Bygget gjordes på VPS:en med begränsat minne (`-m 220m`), med dev-containern
  stoppad under tiden. Ledigt minne efteråt var cirka 150 MB.
- **Rollback:** i `~/promptbanken-connect-dev`, kör
  `cp docker-compose.yml.before-vnext docker-compose.yml && docker-compose rm -sf connect && docker-compose up -d connect`.
  Den gamla imagen `write-candidate` finns kvar.
- Prod-Connect (stoppad sedan 2026-09-15), Caddy, prod-Supabase och Open är
  orörda.

## Nästa steg och rekommendation

1. Ladda om Connect DEV i ChatGPT och Claude, så att de nya verktygen syns.
2. Kör PB-CONNECT-AUTO i båda lägena och räkna med `scripts/score_evals.py`.
3. Kör personfallen 60–72 manuellt och kontrollera att posterna i
   app.promptbanken.se (dev) ser rimliga ut.
4. **Rekommendation:** intern pilot först när målen (85 % / 5 %) är uppmätta i
   ChatGPT. Blir resultatet för A under målet: pröva B innan något mer byggs.
