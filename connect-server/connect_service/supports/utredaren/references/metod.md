# Metod: strukturerad utredning

Det här är skillens egen arbetsgång. Den fungerar utan några andra verktyg. Läs bara det avsnitt du behöver för den fas ni är i.

## Principer

- Frågan först. En utredning utan avgränsad fråga blir en uppsats.
- Spårbarhet före elegans. Hellre en trubbig mening med källa än en slipad utan.
- Visa osäkerheten. En lucka du redovisar är värd mer än en slutsats du inte kan stå för.
- Proportionerligt: djupet följer beslutets vikt och reversibilitet.
- Mänskligt beslut. Du levererar underlag och en märkt bedömning.

## De fyra beteckningarna

| Beteckning | Betyder | Exempel |
| --- | --- | --- |
| **Fakta** | Belagt i en källa du har läst. Anges med E-nummer. | "Kostnaden var 1,2 mnkr 2024 [E3]." |
| **Antagande** | Rimligt men inte belagt. Anges med varför det antas. | "Vi antar att volymen är oförändrad." |
| **Bedömning** | Tolkning av fakta, av dig eller användaren. Anges vem som bedömer och på vilken grund. | "Bedömning: risken är låg eftersom [E2] visar ...". |
| **Kunskapslucka** | Vi vet inte, och vad som behövs för att veta. | "Okänt hur många ärenden som berörs. Behöver uppgift från enheten." |

Ett påstående utan källa är aldrig Fakta. En siffra utan källa är en Kunskapslucka eller ett Antagande.

## Fas 1. Avgränsa frågan

Frågor:
- Vilken fråga ska besvaras? Går den att besvara med ett underlag, eller är den för bred?
- Vilket beslut eller vilken åtgärd ska underlaget stödja? Vem beslutar och när?
- Vad ingår och vad ingår inte?
- Vad är nuläget? Vad är **nollalternativet** (vad händer om vi inte gör något)?
- Vilka alternativ ska jämföras? Finns det fler än användaren nämnt?

Formulering: *Utredningen ska besvara [fråga] för att stödja [beslut] hos [beslutsfattare]. Den omfattar [ingår] men inte [ingår inte].*

Är frågan egentligen "hur gör vi det bättre" (förbättringsproblem) eller "hur genomför vi det vi beslutat" (införande): säg det och föreslå rätt arbetssätt.

## Fas 2. Planera

- Källtyper: författningar och föreskrifter, rättspraxis, forskning och utvärderingar, officiell statistik, jämförbara verksamheter, interna dokument, intervjuer.
- Aktualitet: hur gammalt får underlaget vara för att fortfarande gälla?
- Kriterier för alternativen: nytta, kostnad, risk, genomförbarhet, rättssäkerhet, likabehandling, tid.
- Vad kan jag göra här: söka på nätet, öppna länkar, läsa uppladdade filer? Säg det rakt. Kan du inte söka: be användaren leverera källor eller bekräfta att du arbetar bara med det de ger.
- Stoppregel: när är underlaget tillräckligt? ("Tre oberoende källor per huvudpåstående" eller "alla alternativ har belagda kostnadsuppgifter".)

## Fas 3. Samla underlag: evidensloggen

För varje källa en rad i `assets/evidenslogg.md`:
- **E-nummer**, **källa** (titel, utgivare, år, länk eller filnamn), **typ**, **datum**,
- **vad den belägger** (en mening),
- **läst:** ja (hela eller delar) / endast sammanfattning / ej tillgänglig.

Regler:
- Ta bara med en källa som "läst" om du faktiskt har läst den i samtalet. Annars "ej läst" och använd den inte som belägg.
- Hämtar du från webben: notera datum och det du faktiskt såg.
- Skriv aldrig ett citat från minnet. Citera bara text du har framför dig.

## Fas 4. Värdera källorna

Bedöm kort, per källa: relevans för frågan, direkthet (belägger den frågan eller något närliggande?), aktualitet, oberoende (vem har intresse?), transparens (hur togs uppgiften fram?) och överförbarhet (gäller den hos oss?). Gör inte bedömningen mekanisk: en ung men direkt källa kan väga tyngre än en gammal men stor.

## Fas 5. Syntes

- Gruppera fynd efter fråga eller kriterium, inte efter källa.
- Redovisa samsyn och skillnader. Vid motsägelse: ange båda uppgifterna, källorna och vad som kan förklara skillnaden.
- Märk varje slutsats (Fakta, Antagande, Bedömning, Kunskapslucka).
- Bedöm hur säkert varje huvudfynd är: väl belagt, delvis belagt, omtvistat eller obelagt.
- Saknas källstöd för en viktig del: gå tillbaka till fas 3 eller redovisa luckan.

## Fas 6. Alternativ och konsekvenser

1. **Berörda och perspektiv:** vilka grupper, verksamheter och funktioner påverkas direkt och indirekt? Vilka perspektiv måste med (medborgare, medarbetare, ekonomi, juridik, arbetsmiljö, dataskydd, miljö)?
2. **Konsekvenser per alternativ**, jämfört med nollalternativet: positiva, negativa, oklara. Direkta och indirekta.
3. **Princip och likabehandling:** skapar beslutet en princip? Vilka jämförbara fall finns? Vad blir följden om samma sak tillämpas där?
4. **Risker, beroenden och kunskapsluckor:** sannolikhet, konsekvens, åtgärd. Det som måste verifieras före beslut.
5. Upprepa inte samma sak i flera delar. Skriv varje konsekvens en gång.

## Fas 7. Underlaget

Följ `assets/underlag.md`. Principer:
- Börja med en sammanfattning på högst en halv sida som en beslutsfattare kan läsa ensam.
- Fynd och bedömningar i skilda avsnitt.
- Alternativ med samma kriterier, så de går att jämföra.
- Förslag (om användaren vill ha ett) står sist, märkt **Bedömning**, med villkor och vad som behöver kontrolleras. Formulera aldrig ett beslut som om det vore fattat.
- Avsluta med osäkerheter och kunskapsluckor, och vad som behövs för att täppa till dem.

## När underlaget är dåligt eller saknas

- **Inga källor tillgängliga:** leverera ett *arbetsunderlag* med frågor, kriterier och luckor, tydligt märkt "ej källbelagt". Presentera det inte som en utredning.
- **Motsägande uppgifter:** redovisa motsägelsen och be användaren avgöra vilken uppgift som gäller.
- **Frågan är för bred:** föreslå uppdelning och välj en del.
- **Önskat svar redan bestämt:** utred ändå med nollalternativ och motargument. Säg det vänligt men tydligt.
- **Begäran om rättslig slutsats:** redovisa vilka bestämmelser som kan vara relevanta *om de finns i underlaget*, och markera att en jurist måste bedöma.
