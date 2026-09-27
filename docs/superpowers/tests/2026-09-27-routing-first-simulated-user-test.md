# Simulerat mobilanvändartest — Routing-first UI (DEV, mcp-dev.promptbanken.se)

Testat mot `https://mcp-dev.promptbanken.se/mcp` (endast läsning) via MCP-connectorn `promptbanken-dev`, som anropar samma verktyg/data. Widgetarna renderades lokalt i `dev-harness.html` (360 px bredd) med fixtures byggda av de **riktiga** `structuredContent`-svaren från DEV-anropen. Screenshots och fixtures ligger i denna mapp under `sim/`.

Steg 1 (`get_client_routing_instructions`) lästes och följdes för alla meddelanden. `search_templates`/`recommend_packages`/`list_package_prompts`/`get_template` anropades bara med generella, anonymiserade sökord — aldrig användarens faktiska text.

---

## a) "Jag behöver göra en konsekvensanalys."

**Verktygskedja:**
1. `search_templates(query="konsekvensanalys")` → 6 av 10 toppträffar är steg i samma workflow **Från förslag till konsekvensanalys** (steg 1–6, `sort_order` 1–6).
2. Regeln "flera toppträffar i samma workflow → föreslå hela workflowet" tillämpas → workflow väljs, steg 1 låst via ordningen från `list_package_prompts(fran-forslag-till-konsekvensanalys)`.
3. `get_template(3409ca70-…, "Lås beslutet och nollalternativet")` → kompakt rad "✓ Lås beslutet och nollalternativet · används nu" (verifierat i widget, se screenshot).
4. Första arbetsfrågan ställs direkt ur promptens steg 1 (t.ex. "Vad är det konkreta beslutet som ska prövas?").

**Text till användaren (kort):** "Det här är ett helt arbetsflöde – Från förslag till konsekvensanalys (6 steg). Vi börjar med att låsa beslutet och nollalternativet. Vad är det konkreta beslutet som ska prövas, och vad händer om inget ändras?"

**Widget:** `sim/screenshots/shot-a-template-view.png` — kompakt bekräftelserad, inget stort mallkort återges.

**PASS** — nås på ett enda user-input, ingen paket-/katalogvisning krävdes, kompakt rad OK.

---

## b) "Hjälp mig svara på ett mejl från en invånare."

**Verktygskedja:**
1. `search_templates(query="svara på mejl från invånare")` → klar toppträff, enskild mall: **📧 Svar på medborgarmejl** (`d2850766-…`).
2. `get_template(d2850766-…)` direkt → kompakt rad "✓ 📧 Svar på medborgarmejl · används nu".
3. Första fältfrågan ställs (mallen har `parameter_schema` med `ton`/`roll`/`malgrupp`; standardvärden `handläggare`/`invånare`/`tydlig och vänlig` finns) — fråga efter mejlets innehåll/sammanfattning.

**Text till användaren:** "Jag skriver ett svar till invånaren. Klistra in (eller sammanfatta) vad mejlet handlade om, så tar jag fram ett utkast."

**Widget:** `sim/screenshots/shot-b-template-view.png`.

**PASS** — enskild mall, ett user-input, kompakt rad OK.

---

## c) "Vad finns för chefer?"

**Verktygskedja:**
1. `recommend_packages(role="chef")` → `role_recognized=true`, 18 paket i `recommended_areas`.

**Text till användaren:** "Här är några paket som passar chefer. Vill du utforska något av dem, eller ha hjälp med en specifik uppgift?"

**Widget:** `sim/screenshots/shot-c-package-cards2.png` — exakt **5 kort** visas + knappen **"Visa fler (2)"** (18 paket delas 5+5+5+3, filtret räknar 7 arbetsflöden ⇒ "Visa fler (2)" på första sidan av 7). Filterknappar "Alla / Arbetsflöden / Samlingar" syns också.

**PASS** — paketkort, topp 5 + "Visa fler" bekräftat i faktisk widget-rendering.

---

## d) "Vi ska införa ett nytt arbetssätt men vet inte om vi ska pilota först."

**Verktygskedja:**
1. `search_templates(query="nytt arbetssätt pilot")` → 37 träffar, spridda över flera paket (forandringsledning, behov-till-effekt, data-till-forbattring, fran-behov-till-validerad-produkt, forbattringside-till-synlig-effekt …) — **ingen** dominant enskild mall eller sammanhängande workflow-kedja.
2. Routing är osäker → inget automatiskt val. Presentera 2–3 alternativ i text, inget paketkort, ingen mall aktiveras ännu.

**Text till användaren:** "Det här kan angripas på några olika sätt beroende på var ni är:
- **Pilot eller skarp drift?** — bedömer om ni bör pilota, testa i liten skala eller köra skarpt direkt.
- **Pilotdesign** — om ni redan vet att det blir en pilot och vill utforma den (målgrupp, tidsram, mätning).
- Om det är del av ett större förändringsarbete: workflowet **Från behov till effekt**, steget *Planera införandet*.
Vilket stämmer bäst?"

**Widget:** ingen (textalternativ, inget verktyg utöver `search_templates`).

**PASS** — 2–3 alternativ presenterade i text, ingen förhastad mallstart.

---

## e) "Jag är på steg 2 i Från behov till effekt."

**Verktygskedja:**
1. `list_package_prompts(package_slug="behov-till-effekt", current_step=2)` → steg 2 = **Beskriv nuläge och målbild** (`57e2d09b-…`), `template_count`=6.
2. `get_template(57e2d09b-…)` → arbetsfrågan ur steget (nuläge/börläge/effekter).

**Text till användaren:** "Steg 2 av 6: Beskriv nuläge och målbild. Vad är nuläget idag, och vad ska vara annorlunda när ni är klara?"

**Widget:** `sim/screenshots/shot-e-stepper-step2.png` — header visar **"Steg 2 av 6"**, titel "Beskriv nuläge och målbild", **"Nästa: Utforma förändringen"** — allt bekräftat i faktisk DOM-snapshot.

**PASS** — ett user-input, `list_package_prompts(current_step)` → `get_template`, ingen extra katalogvisning. `template_count` (6) matchar antalet steg (6).

---

## f) "Kör superplan: ta fram en plan för digitala signaturer." (Superplan-skill)

**Verktygskedja (enligt `plugin/skills/superplan/SKILL.md`):**
1. `list_package_prompts(package_slug="superplanlage", include_prompt_text=true)` — **ett** anrop i början, hämtar alla 4 faser (`utforska-och-las-riktningen`, `specificera-resultatet`, `utfor-specifikationen`, `verifiera-resultatet`) med full `prompt_text`.
2. **Ingen** separat `get_template` per fas (skillen förbjuder det uttryckligen — det skulle avslöja fasnamn/rendera ett mallkort).
3. Fas 1 (riktning) körs som intern instruktion: max tre frågor, inget fasnamn nämns för användaren.

**Text till användaren:** "Digitala signaturer — vilken typ av dokument/flöde gäller det (avtal, beslut, blanketter), och finns det redan krav på e-legitimation/BankID eller är det öppet?" (inga fasnamn, inget "Superplan steg 1 av 4" nämns för användaren, i linje med skillen).

**Widget:** `sim/screenshots/shot-f-superplan-stepper.png` — bekräftat: bannern visar bara rubriken **"Superplanläge"**, ingen steglista, inga steg-titlar (widgeten går in i "instruction-loading"-läge eftersom `current_step` är `null`). Inget `template-view`-kort renderas för någon fas (inget `get_template`-anrop gjordes över huvud taget för faserna).

**PASS** — instruction-loading-läge (header only, ingen steglista) och inga mallkort för Superplan-faser.

---

## Sammanfattning per kriterium

| Meddelande | Ett user-input till första arbetsfråga | Paketkort / textalternativ korrekt | Kompakt bekräftelse / stepper-fält | Verdict |
|---|---|---|---|---|
| a) Konsekvensanalys | PASS | PASS (helt workflow, ej enskilt steg) | PASS | **PASS** |
| b) Medborgarmejl | PASS | PASS (enskild mall) | PASS | **PASS** |
| c) Vad finns för chefer | – | PASS (5 kort + "Visa fler (2)") | – | **PASS** |
| d) Pilot eller ej | – | PASS (2–3 textalternativ, ingen auto-mall) | – | **PASS** |
| e) Steg 2 i Från behov till effekt | PASS | PASS (ingen extra katalogvisning) | PASS ("Steg 2 av 6", "Nästa: …") | **PASS** |
| f) Superplan (digitala signaturer) | PASS (instruction-loading, ej steglista) | PASS (inga fasnamn/mallkort) | PASS (header-only) | **PASS** |

`template_count` = paketets stegantal i samtliga testade paket (6=6 för både konsekvensanalys och behov-till-effekt). Inget dubbelt stort mallkort observerades efter aktivering — `get_template` renderar alltid den korta "✓ … · används nu"-raden, inte om det stora paket-/kortlayouten.

## Övergripande verdict

Mobilflödet blir **inte** behov → paket → mall → använd när direkt routing är möjlig. I samtliga tydliga fall (a, b, e) landar flödet på första arbetsfrågan efter ett enda user-meddelande, utan att användaren tvingas öppna paket eller bläddra i katalogen. Vid genuint oklar routing (d) ges korrekt 2–3 alternativ i text i stället för att gissa. Utforskningsfrågan (c) använder paketkort som avsett (topp 5 + "Visa fler"), och Superplan (f) håller sin interna struktur helt dold enligt skillens regler.

## UX-fynd (prioriterat)

1. **(Hög)** Paket-svaret för `recommend_packages("chef")` innehåller 18 paket i `recommended_areas` men bara 7 fullständiga kort i `packages`-arrayen (workflow-filtret räknar mot alla 18 för "Visa fler (2)" trots att bara 7 kort faktiskt finns laddade i fixturen) — om klienten någon gång binder "Visa fler"-räknaren mot `recommended_areas.length` snarare än faktiskt hämtade kort riskerar den att visa fel antal eller ett tomt nästa-steg. Bör verifieras mot produktionens faktiska pagineringslogik, inte bara dev-fixturen.
2. **(Medel)** Vid osäker routing (d) finns ingen maskinläsbar signal (t.ex. `ambiguous=true`) i `search_templates`-svaret som talar om för klienten att den bör växla till textalternativ i stället för att bara titta på antal träffar (37 träffar) — routingbeslutet vilar helt på klientmodellens egen tolkning av `client_flow`-texten, vilket är skört om en svagare klientmodell används.
3. **(Låg, mobil läsbarhet)** I `workflow-stepper`-widgeten vid `current_step=2` är "Nästa: …"-raden och "Visa alla steg"-kontrollen visuellt lätta att missa på 360 px bredd (liten kontrastskillnad mot bakgrund i screenshot) — värt en snabb kontrastcheck för WCAG AA på mobil.

## Filer
- Rapport: denna fil.
- Fixtures (riktiga strukturerade svar): `sim/fixtures/real-*.json`
- Testvärd: `sim/dev-harness.html` (+ `sim/.preview/*.html` widget-bygg)
- Screenshots: `sim/screenshots/shot-a-template-view.png`, `shot-b-template-view.png`, `shot-c-package-cards2.png`, `shot-e-stepper-step2.png`, `shot-f-superplan-stepper.png`
