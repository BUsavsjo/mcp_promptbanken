# Metod: från verksamhetsdata till analys och uppföljning

Det här är skillens egen arbetsgång. Den fungerar utan några andra verktyg. Läs bara det avsnitt du behöver för den fas ni är i.

## Principer

- Frågan styr analysen. Data som inte hör till frågan är brus.
- Kvalitet först. En elegant analys av dålig data är ett elegant fel.
- Tal kommer från beräkningar som går att granska.
- Beskriv, tolka, förklara: tre olika steg med tre olika säkerhetsnivåer.
- Hellre ett ärligt "det kan vi inte veta" än en slutsats datan inte bär.

## Säkerhetsnivåer i språket

| Formulering | Betyder | Kräver |
| --- | --- | --- |
| "Datan visar att ..." | En observation som går att räkna fram. | Tal, n, period och beräkning. |
| "Datan tyder på att ..." | En rimlig tolkning. Andra tolkningar kan finnas. | Minst en alternativ förklaring prövad. |
| "Det kan bero på ..." | En hypotes. Inte prövad. | Hur den kan prövas. |
| "Datan kan inte säga ..." | En gräns. | Vad som skulle behövas för att veta. |

Använd aldrig "beror på", "orsakas av" eller "leder till" om inte orsaken är prövad (till exempel genom ett test).

## Fas 1. Analysfrågan

Frågor:
- Vad vill ni veta, med era ord? Vem frågar, och vad ska de göra med svaret?
- Vilket beslut eller vilken förbättring stöds? Vad skulle svaret kunna ändra?
- Vilken period, vilka enheter och vilken population gäller frågan?
- Vilka slutsatser kan datan rimligen bära? (En tabell över kostnader per månad kan visa nivåer och förändring, inte *varför*.)

Formulering: *Vi vill veta [fråga] för [population/period] för att besluta [beslut].*

## Fas 2. Datakvalitet

Gå igenom, och redovisa det du hittar:

1. **Vad är datan?** System, uttagsdatum, vem som tagit ut den, urval, version.
2. **Definitioner:** vad räknas per kolumn och rad? Har definitionen ändrats under perioden (nytt system, ny kodning, ny rutin)?
3. **Enheter:** kronor, tkr, timmar, minuter, antal, procent? Blandas de?
4. **Period och jämförbarhet:** kalenderår eller läsår? Är månader jämförbara (arbetsdagar, semestrar, säsong)? Saknas perioder?
5. **Saknade värden:** hur många, i vilka kolumner, och är de slumpmässiga eller systematiska?
6. **Dubbletter:** exakta, eller samma ärende registrerat två gånger?
7. **Avvikande värden:** möjliga mätfel, inmatningsfel eller verkliga extrema fall? Ta inte bort dem utan att fråga.
8. **Summor:** stämmer delsummor mot totalen? Stämmer antalet rader mot det system uppgiften kom från?
9. **Personuppgifter och små celler:** identifierande kolumner, grupper med färre än fem.

Kör `scripts/profilera.mjs` för 4–9 om du kan köra kod. Använd `assets/datakontroll.md` som checklista.

**Stopp-regel.** Säg tydligt om datan inte kan bära frågan, till exempel om perioden är för kort, om definitionen ändrats mitt i, om för många värden saknas eller om det rör sig om för få fall. Förklara vad som skulle behövas och hur det kan samlas in.

## Fas 3. Mönster och avvikelser

Räkna, beskriv, tolka inte än.

- **Nivå:** summa, medelvärde, median. Använd median när fördelningen är skev eller har extrema värden. Visa gärna både och.
- **Förändring över tid:** absolut förändring och procentuell förändring. Skilj **procent** från **procentenheter** (en ökning från 10 % till 12 % är 2 procentenheter, och 20 % relativt).
- **Skillnad mellan grupper:** visa absoluta tal tillsammans med andelar, och n per grupp.
- **Fördelning:** spridning, avvikande värden, koncentration (står tio procent av fallen för hälften av tiden?).
- **Säsong och kalender:** jämför samma period mellan år, inte bara månad mot månad.
- **Små urval:** under ungefär 30 observationer per grupp visar mönster en riktning, inte en säker skillnad. Säg det.

Presentera varje mönster som: *Observation (med tal, n, period) → är det rimligt att det är stort nog att bry sig om?*

## Fas 4. Hypoteser

För varje tydligt mönster:
1. Ge minst tre möjliga förklaringar. Ta alltid med: tillfällighet, mätfel eller ändrad registrering, något som hände samtidigt, och en verksamhetsförklaring.
2. För varje: vad skulle stödja den, vad skulle motsäga den?
3. Hur kan den prövas? Mer data, en uppdelning, intervjuer med dem som gör arbetet, eller ett litet test.
4. Rangordna efter rimlighet och hur lätt de är att pröva. Skriv att rangordningen är en bedömning.

Samband är inte orsak. Två saker som ökar samtidigt kan ha en tredje orsak, eller sambandet kan vara en tillfällighet.

## Fas 5. Rekommendationer

- Koppla varje rekommendation till en hypotes och ett observerat mönster.
- Föredra minsta användbara steg: **mer data**, **en uppdelning**, **ett avgränsat test** eller **en åtgärd**.
- Ange förväntad effekt som en hypotes och hur den ska mätas. Hitta inte på effektstorlekar.
- Ange risker och vad som kan gå fel.
- Skilj det ni kan göra direkt från det som kräver beslut eller mer analys.

**Ekonomisk uppföljning:** analysera utfall och prognos (budget, utfall, avvikelse, prognos, förklaringar), skilj fakta, antaganden och förklaringar. En avvikelsekommentar är kort och saklig: vad avviker, hur mycket, känd orsak, vad som görs. Prognosbedömningar märks som antaganden. Hitta inte på orsaker.

**Business case (vid investering):** lås beslutet och nollalternativet, separera fakta, uppskattningar och antaganden, bygg kostnads- och nyttobilden (pengar, tid och verksamhetseffekt hålls isär), pröva känslighet i sämre, bas- och bättre scenario, och väg risker och osäkerhet. Visa inte falsk precision (inga decimaler på en gissning). Tid som frigörs är kapacitet, inte automatiskt en besparing.

## Fas 6. Uppföljning

- Indikator, definition, källa, ansvarig, frekvens och tröskel för åtgärd.
- Baslinje (värdet innan) och förutsägelse (förväntat värde efter).
- När gör vi om analysen?
- Vid genomfört test: jämför utfall med baslinje och förutsägelse enligt fas 3–4, redovisa vad som är osäkert och föreslå att behålla, justera eller avsluta.

## Fas 7. Redovisning

Följ `assets/analysrapport.md`. Principer:
- Börja med svaret på frågan, i högst fem rader, med säkerhetsgrad.
- Fynd med tal, n och period. Tolkningar märkta som tolkningar.
- **Vad datan inte visar** är ett eget avsnitt.
- Datakvaliteten redovisas, inte göms.
- Tabeller och siffror är samma som i beräkningarna.

## Räknestöd när du inte kan köra kod

- Skriv ut varje uträkning: `(120 − 100) / 100 = 0,20 = 20 %`.
- Räkna om en gång på ett annat sätt (till exempel summera uppifrån och nerifrån).
- Märk resultatet "handräknad, kontrollera".
- Avrunda först i slutet. Ange alltid antal decimaler.
- Över ungefär 20 värden: be användaren köra beräkningen i kalkylblad eller bekräfta summan.

## När underlaget är dåligt eller saknas

- **Ingen data:** formulera frågan, föreslå vilken data som behövs och hur den kan tas fram. Analysera inte.
- **Datan stöder inte frågan:** säg det och föreslå en annan fråga som datan kan besvara.
- **Användaren vill bekräfta en förutfattad slutsats:** visa vad datan visar, ta fram alternativa förklaringar och vad som skulle motsäga slutsatsen.
- **Motsägande uppgifter:** redovisa motsägelsen och be användaren avgöra vilken som gäller.
- **Tabellen är inklistrad som text:** läs den noga, rapportera hur du tolkat kolumnerna och bekräfta med användaren innan du räknar.
