# MCP capability segmentation and public catalog cleanup

## Syfte

Gör om den hostade MCP-ytan på `https://mcp.promptbanken.se/mcp` från en
verktygstäthet med blandade produktgränser till en kapabilitetsstyrd
verktygsmodell med:

- en tydlig publik katalog för Promptbanken
- ett tydligt personligt Valv
- stöd för paketaktivering och kopiering från Promptbanken till Valvet
- arkitekturell förberedelse för framtida organisationsytor utan att bygga dem nu

Etapp 1 omfattar publik katalog, befintligt personligt Valv,
paketaktivering och kopiering från Promptbanken till Valvet.
Organisationsfunktioner ligger utanför implementationen men förbereds i
arkitektur, namngivning och behörighetsmodell.

## Verifierade fakta

- `mcp_promptbanken` är den hostade MCP-servern på `mcp.promptbanken.se`.
- `promptbanken` äger den kurerade katalogen, den delade Supabase-databasen
  och Valvets datamodell.
- `valvet_promptbanken` är en separat produkt-/webbyta för det personliga
  Valvet, men använder samma konto, databas, MCP-nycklar och workspace-modell.
- Valvet är inte bara "egna objekt" utan har redan produktstöd för:
  - paketaktivering
  - bläddring i kataloginnehåll
  - kopiering från Promptbanken till Valvet
- Nuvarande hostade MCP-yta exponerar publika katalogverktyg, privata
  workspace-/Pro-verktyg och Valvet-verktyg i samma verktygsrum.

## Antaganden

- Det finns inga kända skarpa Free-/Pro-klienter på den moderna
  MCP-endpointen.
- Eventuell äldre användning bedöms främst kunna finnas på SSE-endpointen.
- Trafiken ska inventeras innan kompatibilitetslagret utesluts eller SSE tas bort.

## Problemformulering

Nuvarande MCP-yta har tre huvudsakliga produktproblem:

1. För många verktyg syns samtidigt i den öppna ytan, vilket försämrar
   modellens verktygsval.
2. Produktgränsen mellan Promptbanken och Valvet är inte tydlig nog i
   verktygsnamn, verktygsbeskrivningar eller exponering.
3. Katalogmodellen uttrycks inte tillräckligt som dynamisk data i Supabase,
   vilket gör MCP-ytan mindre stabil som produktgränssnitt.

Målet i etapp 1 är att lösa dessa problem utan att överimplementera
framtida organisationsfunktioner.

## Produktgränser

### Promptbanken

Promptbanken äger den öppna, kurerade katalogen:

- publicerade paket
- publicerade mallar
- katalogsökning
- rollbaserade paketrekommendationer
- skill-/arbetsättsmetadata för klienthjälp

Promptbanken är en katalogprodukt, inte ett personligt lagringsutrymme.

### Valvet

Valvet äger användarens personliga arbetsbank:

- egna objekt
- uppdatering och arkivering av egna objekt
- aktivering/deaktivering av paket i den personliga ytan
- kopiering av katalogmallar till fristående Valv-kopior
- personlig kvot- och usage-logik

Valvet är en personlig produkt ovanpå samma konto, workspace och MCP-nyckel,
men med egen produktlogik.

### Organisation (framtida fas)

Organisation reserveras arkitekturellt men byggs inte i etapp 1.
Framtida workspace-skrivning, granskning och publicering ska utformas så att:

- skrivande organisationsanrop alltid kräver explicit `workspace_id`
- servern aldrig gissar arbetsyta
- roller styr create/update/review/approve/publish

## Endpointstrategi

En gemensam modern endpoint behålls:

`/mcp`

Samma endpoint ska stödja:

- publik anslutning utan nyckel
- personlig Free-/Pro-anslutning med MCP-nyckel
- framtida organisationsanslutning med arbetsytebehörigheter

`tools/list` är en produkt- och UX-yta, inte en säkerhetsmekanism.
Behörighet ska alltid verifieras på serversidan vid själva anropet i
`tools/call` och motsvarande interna payload-funktioner/RPC-vägar.

Om klientstöd finns ska servern på sikt kunna signalera
`notifications/tools/list_changed` när kapabiliteter ändras, annars får
klienten återansluta. Detta är önskvärt men inte ett krav för etapp 1.

## Slutlig verktygsmodell för etapp 1

### Publika verktyg

- `health_check`
- `list_packages`
- `get_package`
- `search_templates`
- `get_template`
- `recommend_packages`
- `list_skills`
- `get_skill`

Dessa verktyg ska vara synliga utan nyckel och arbeta mot publicerat,
öppet kataloginnehåll.

### Personliga Valv-verktyg

- `get_my_capabilities`
- `copy_template_to_vault`
- `list_my_items`
- `search_my_items`
- `get_my_item`
- `create_my_item`
- `update_my_item`
- `archive_my_item`
- `list_activated_packages`
- `activate_package`
- `deactivate_package`

Semantik:

- `create_my_item` skapar ett nytt personligt objekt
- `update_my_item` ändrar ett befintligt objekt med optimistisk låsning
- `archive_my_item` arkiverar eller återställer
- `copy_template_to_vault` är ett separat katalog-till-Valv-flöde med källspårning

### Framtida organisationsverktyg

Inte implementerade i etapp 1, men namnmodellen ska lämna utrymme för t.ex.:

- `list_my_workspaces`
- `search_workspace_items`
- `get_workspace_item`
- `create_workspace_item`
- `update_workspace_item`
- `archive_workspace_item`
- `submit_for_review`
- `approve_item`
- `publish_item`
- `list_item_versions`
- `restore_item_version`

## Segmentering och kapabilitetsmodell

Segmentering sker i två lager:

### 1. Exponering

`tools/list` filtreras efter anropskontext så att klienten bara ser
verktyg som är relevanta för dess kapabiliteter.

### 2. Auktorisering

`tools/call` och bakomliggande serverlogik kontrollerar alltid behörighet
oavsett vad klienten såg i `tools/list`.

### Kapabilitetsnivåer i etapp 1

- Utan nyckel:
  - `public_catalog`
- Med giltig Free-nyckel:
  - `public_catalog`
  - `personal_vault`
- Med giltig Pro-nyckel:
  - `public_catalog`
  - `personal_vault`

Skillnaden mellan Free och Pro i etapp 1 ligger främst i:

- kvoter
- usage-fält
- eventuellt utökat kataloginnehåll
- planberoende tillgång till workspace-synligt innehåll

Den ligger inte i helt olika basverktyg för det personliga Valvet.

## `get_my_capabilities`

`get_my_capabilities` blir introspektionsverktyget för personliga klienter.
Det ska minst beskriva:

- plan
- capability-grupper
- usage/kvoter
- om workspace-synligt kataloginnehåll är tillgängligt
- om skrivoperationer är tillåtna
- relevanta begränsningar för MCP-nycklar och månadskvoter

Detta verktyg ersätter att klienten behöver gissa produktnivå från
felmeddelanden eller indirekta svar.

## Datamodell i Supabase

Etapp 1 ska i första hand bygga vidare på den faktiska modell som redan finns
i `promptbanken`, inte ersätta den med en ny generell polymorf design.

### Grundprincip

Promptbanken-katalog och Valvet ska vara separata produktlager ovanpå samma
databas, där separeringen bärs av kombinationen av:

- `module`
- `visibility`
- `status`
- workspace-koppling
- ägarskap
- källspårning

### Katalog

Promptbanken-katalogen representerar systemägda och publicerade objekt som kan
listas, sökas och hämtas via publika katalogverktyg.

Paket och mallar ska betraktas som dynamisk data i Supabase. Nya publicerade
paket eller mallar ska kunna tillkomma utan att MCP-serverns verktygslista
växer eller ändras.

### Valvet

Valvet representerar personliga objekt i användarens/workspacets privata yta.
De ska fortsätta vara fristående från katalogen även om de ursprungligen skapats
genom kopiering från den.

### Kopiering från katalog till Valvet

`copy_template_to_vault` ska skapa en fristående Valv-kopia.
Kopian får inte skrivas över när originalmallen ändras.

Kopian ska spara minst:

- `source_template_id`
- `source_version`
- kopieringstidpunkt

Detta ska räcka för framtida användarinformation om att en ny version av
originalmallen finns.

### Paketaktivering

Paketaktivering ska vara en separat relation per workspace/användaryta, inte
en egenskap på katalogpaketet självt.

Aktivering styr:

- vad som visas/expanderas i Valvets personliga yta
- vilka paket användaren valt att arbeta aktivt med i Valvet

Aktivering ska inte ändra den publika katalogens grunddefinition.

## RLS- och säkerhetsprinciper

Alla privata och workspace-bundna data ska skyddas av RLS eller motsvarande
serverstyrt behörighetslager i Supabase.

Etapp 1 ska minst säkerställa:

- att publika katalogfrågor bara returnerar publicerat innehåll
- att användaren bara kan läsa och ändra sina egna Valv-objekt enligt gällande modell
- att workspace-bunden aktivering bara påverkar rätt workspace
- att MCP-nyckelns plan och rättigheter styr usage/kvoter på serversidan
- att service-role eller motsvarande aldrig exponeras mot MCP-klienten
- att alla mutationer valideras på serversidan

Särskilt viktigt:

- `tools/list` får aldrig betraktas som ett säkerhetslager
- `workspace_id` ska inte börja användas i skrivande organisationsmönster utan
  explicit medlemskapskontroll
- kopieringsflödet måste säkerställa att användaren bara får kopiera till sitt
  eget Valv

## Migreringsstrategi

Etapp 1 ska vara brytande på verktygsnivå men konservativ på databasnivå.

### Steg A: nulägesinventering

Dokumentera:

- nuvarande endpoints (`/mcp`, `/sse`, REST-ytor)
- samtliga exponerade MCP-verktyg
- hur verktygslistan byggs i dag
- hur autentisering och plan tolkas
- hur katalogdata och Valv-data lagras
- faktisk eller möjlig kvarvarande SSE-användning

Inga brytande ändringar ska göras innan inventeringen är genomförd.

### Steg B: ny primär verktygsmodell

Inför den nya verktygsmodellen och capability-segmenterad `tools/list`.
Gamla namn ska inte vara primära i `tools/list`.

Om kompatibilitetslager behövs ska det avgöras efter trafikinventering,
inte antas från början.

### Steg C: stabil publik katalog

Säkerställ att publika verktyg arbetar mot dynamisk katalogdata i Supabase:

- `list_packages`
- `get_package`
- `search_templates`
- `get_template`
- `recommend_packages`

Nya publicerade paket och mallar ska kunna bli synliga utan att MCP-serverns
verktygsmodell ändras.

### Steg D: tydligt personligt Valv

Flytta in befintliga Valv-funktioner under den nya semantiken:

- `create_my_item`
- `update_my_item`
- `archive_my_item`
- `copy_template_to_vault`
- paketaktivering
- usage/capabilities

Valvet ska vara en sammanhängande personlig verktygsgrupp, inte en blandad rest
från tidigare Promptbanken-/Pro-/write-funktioner.

## Klassificering av ändringar

### Kan göras direkt

- capability-styrd `tools/list`
- nya primära verktygsnamn
- förbättrade verktygsbeskrivningar
- tydligare produktgrupper
- `get_my_capabilities`
- söksvar med bättre matchförklaring/kvalitetsindikatorer om det behövs för etapp 1
- dokumentation och SSE-inventering

### Kräver datamigrering eller RPC-justering

- om paketmodellen i Supabase inte ännu räcker för `list_packages`/`get_package`
- om `copy_template_to_vault` saknar tillräcklig källspårning
- om usage/kvotdata behöver exponeras tydligare för `get_my_capabilities`

### Kräver kompatibilitetslager

- bara om inventeringen visar faktisk kvarvarande användning av äldre
  verktygsnamn eller SSE-klienter

### Bör vänta till organisationsfasen

- review-/approve-/publish-flöden
- versionsåterställning för workspace-objekt
- arbetsyteadministration
- flerrollsbehörighet för gemensam redigering
- full organisationskatalog i MCP

## SSE-endpointen

SSE-endpointen ska inte tas bort på antagande.

Den ska först inventeras och dokumenteras:

- aktuell sökväg
- vilka verktyg den exponerar
- om den har trafik
- om det finns dokumenterade klienter
- om loggar kan visa senaste användning utan att exponera känsliga uppgifter

Efter inventeringen kan en enkel avvecklingsmodell användas:

1. mät/kontrollera trafik
2. dokumentera faktisk användning
3. behåll kort övergång bara om aktiv användning finns
4. lägg tydlig styrning mot `/mcp`
5. avveckla SSE när den inte längre behövs

## Acceptanskriterier för etapp 1

Minst följande ska verifieras:

1. Anrop utan nyckel ser endast publika katalogverktyg.
2. Publik användare kan lista paket och söka mallar.
3. Nya publicerade paket i Supabase visas utan kodändring i verktygsregistret.
4. Publik användare kan inte läsa privata Valv-objekt.
5. Giltig Free-nyckel visar tillåtna Valv-verktyg.
6. Giltig Pro-nyckel visar rätt kapabiliteter, usage och eventuellt utökat kataloginnehåll.
7. Ogiltig eller återkallad nyckel ger tydligt och säkert fel.
8. Kvoter kontrolleras på servern.
9. En kopierad mall blir en självständig Valv-kopia.
10. Uppdatering av originalmallen skriver inte över Valv-kopian.
11. Alla mutationer är idempotenta där dubbelanrop kan uppstå.
12. Publika frågor returnerar endast publicerat innehåll.
13. Verktygsbeskrivningarna hjälper modellen välja rätt verktyg.
14. SSE-endpointens status är inventerad och dokumenterad.
15. Befintliga tester fortsätter fungera eller ersätts med tydligt motiverad verifiering.

## Uttryckligen utanför scope i etapp 1

- full organisationsbank
- review-/approve-/publish-flöde
- versionsåterställning för organisationsobjekt
- bred ommodellering av hela databasen om befintlig modell räcker
- överkonstruerat kompatibilitetslager innan faktisk trafik verifierats

## Rekommenderad fortsättning

Nästa steg efter denna spec är en implementationplan för etapp 1 med fyra
huvuddelar:

1. nulägesanalys och SSE-inventering
2. capability-segmenterad verktygsmodell på `/mcp`
3. publik katalog via stabil Supabase-baserad datakälla
4. tydlig personlig Valv-grupp med paketaktivering och kopiering
