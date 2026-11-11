# Metod: från produktidé till validerad MVP

Det här är skillens egen arbetsgång. Den fungerar utan några andra verktyg. Läs bara det avsnitt du behöver för det steg ni är i.

## Principer

- Börja i behovet, inte i lösningen. En lösning är en hypotes.
- Det billigaste testet först. Bygg inte för att ta reda på om något är värt att bygga, om det går att ta reda på på annat sätt.
- Fakta, observation, antagande, hypotes och rekommendation är fem olika saker. Märk dem.
- Hitta aldrig på användar-, marknads- eller valideringsdata. Okänt är okänt.
- Rådgivande: alternativ med en rekommendation. Användaren beslutar.
- Beslutskriterier skrivs före testet, inte efter.

## Läs av innan du frågar (inventering)

Gör en tyst lista över det du behöver och markera varje punkt som **given**, **framgår av underlaget** eller **saknas**:
idén i en mening, problemet och vem som har det, vad som används i dag, målgrupp, vem som betalar, vad som redan testats eller sagts av riktiga användare, begränsningar (tid, pengar, team), och vad användaren vill ha hjälp med just nu.

Fråga bara om det som **saknas** och som ändrar nästa vägval. Ställ en fråga i taget när svaret styr nästa fråga. Erbjud ett förslag att rätta ("Jag antar att det är lärare som använder den och skolan som betalar. Stämmer det?"). Räcker underlaget: gör arbetet och redovisa antagandena.

## Steg 1. Förstå behovet

Det du behöver veta:
- Vad är problemet, för vem, hur ofta och hur illa? Vad är det som händer i verkligheten?
- Vad gör människor i dag? Varför räcker det inte?
- Vad är observerat (någon har sett eller hört det) och vad är antaget?
- Vad har kostat tid eller pengar på grund av problemet?

Formulering: *[Vem] har problemet [vad] i situationen [när]. Idag löser de det genom [hur], vilket fungerar dåligt för att [varför].* Ingen lösning i formuleringen.

Märk varje påstående fakta, observation eller antagande. Finns inga observationer alls: säg det, det är en viktig upptäckt.

## Steg 2. Målgrupp och köpare

- Vem hjälper produkten främst? Avgränsa till en grupp du kan nå.
- Vem använder, vem köper och vem betalar? Det kan vara tre olika.
- I vilken situation är behovet så viktigt att någon byter eller köper?
- Hur når ni dem?

**Grind A (finns det något att bygga för?).** Väg: Är problemet verkligt och tillräckligt stort? Finns en identifierbar köpare? Är behovet akut nog för att någon ska agera? Ge ett besked (se grindarna i `SKILL.md`). Saknas observationer eller en köpare: rekommendera ett billigt test (fem samtal) före allt annat.

## Steg 3. Produktlöfte

- Vilket värde skapar produkten, för vem, jämfört med vad de gör i dag?
- Varför skulle de välja den?

Formulering: *För [målgrupp] som [behov] är [produkt] en [typ] som [värde]. Till skillnad från [alternativ] gör den [skillnad].* Skriv det så att det går att pröva: går det att visa för någon och se om de förstår och vill ha det?

## Steg 4. Produktspår

Ta fram tre spår, och ett av dem ska **inte** vara att bygga:
1. **Bygg** en egen produkt.
2. **Köp eller anpassa** något befintligt, eller kombinera verktyg.
3. **Lös utan produkt:** en manuell tjänst, en ändrad rutin eller ett dokument.

För varje spår: vad löser det, vad kostar det i tid, pengar och förvaltning, vad är risken och vad lär ni er snabbast. Rekommendera ett och förklara varför. Lås inte funktioner eller teknik.

**Grind B (är det en produkt som är svaret?).** Väg spåren mot varandra. Räcker ett befintligt alternativ eller en rutin: rekommendera det.

## Steg 5. Kärnflödet

- Vad är användarens viktigaste resa, från start till uppnått resultat? Beskriv i fem till åtta steg.
- Vilka steg är kärnan, och vilka är stödfunktioner (inloggning, inställningar, rapporter)?
- Var uppstår värdet? Vad måste fungera för att resultatet ska uppnås?

## Steg 6. Avgränsa MVP

Sortera i fyra högar:
- **Nödvändigt** för att kärnflödet ska fungera.
- **Differentierare:** det som skiljer produkten från alternativen och måste testas.
- **Senare:** bra, men inte nödvändigt för att lära sig något.
- **Bort:** sådant som inte hör hemma i produkten.

Fråga: vad ska MVP:n lära er? En MVP utan en lärfråga är en liten produkt, inte ett test. Håll den så liten att den går att bygga eller simulera snabbt. Finns ett sätt att få svaret utan kod (prototyp, manuell tjänst): säg det.

## Steg 7. Affärsmodell

- Hur skapas intäkt (eller finansiering)? Vem betalar, för vad och när (betalpunkt)?
- Vad är gratis och vad kostar? Varför skulle någon betala?
- Antaganden om pris, volym och kundtyp: lista dem som antaganden och gör dem testbara.
- Offentlig sektor: vem äger budgeten, krävs upphandling, vad blir de löpande kostnaderna och vem förvaltar?
- Räkna inte fram intäkter som bygger på påhittade volymer. Visa vilka antaganden som driver resultatet.

## Steg 8. Planera valideringen

För varje viktigt antagande, i ordning efter hur mycket det skulle förändra beslutet:
- Vad ska vara sant? (hypotes)
- Hur testas det billigast? (samtal, manuell tjänst, landningssida, prototyp, förbeställning)
- Vilka testas, och hur många?
- Vilken **signal** räknas (beteende, inte bara åsikter)? Betalning, tid, förbeställning och återkomst väger tyngre än "låter bra".
- **Beslutskriterier i förväg:** vad krävs för att gå vidare, justera eller sluta? Skriv tröskeln innan testet.

**Grind C (ska ni bygga?).** Är antagandena för osäkra, rekommendera test först. Saknas ett avbrottsvillkor: lägg till ett.

Mall: `assets/valideringsplan.md`.

## Steg 9. Lär och prioritera nästa version

När det finns resultat:
- Vad visade valideringen egentligen? Observationer, tolkning, osäkerhet.
- Skilj **signal** (vad människor gjorde) från **önskemål** (vad de sa att de ville ha).
- Jämför med beslutskriterierna ni satte. Flytta inte målstolparna efteråt.
- Välj nästa steg: **bygg vidare**, **justera**, **byt riktning** eller **avsluta**. Avsluta är ett resultat, inte ett misslyckande.
- Prioritera nästa version efter lärande, effekt och risk.

## Produktbeslut: så formulerar du "bygg inte"

Ett produktbeslut har fyra delar: rekommendation (Bygg, Testa först, Ändra riktning, Bygg inte), skäl (tre punkter, varje märkt fakta eller antagande), vad som skulle ändra bedömningen, och nästa steg. Mall: `assets/produktbeslut.md`.

Exempel: *Min rekommendation: bygg inte ännu. Skäl: (1) Ni har inte pratat med någon som har problemet (antagande). (2) Ett befintligt verktyg täcker troligen 80 procent av behovet (antagande, ej kontrollerat). (3) Ingen köpare är identifierad. Det som skulle få mig att ändra mig: fem samtal där minst tre beskriver samma problem och två säger att de skulle betala. Nästa steg: boka de fem samtalen.*

## När underlaget är dåligt eller saknas

- **Bara en idé, inga observationer:** gå till steg 1 och 2 och rekommendera samtal före allt annat.
- **Användaren är säker på att idén är bra:** bekräfta inte. Visa vad som är fakta och vad som är antagande och vad som skulle få dig att ändra dig.
- **Användaren har redan byggt:** börja vid validering (steg 8) och fråga vad som faktiskt används.
- **Användaren bara vill ha en funktionslista:** ge den, men koppla den till behov och MVP-gränser, och säg vad som saknar stöd.
- **Siffror om marknaden efterfrågas:** hitta inte på. Visa hur de kan tas fram eller vilka antaganden en uppskattning vilar på.
