# Metod: kartlägga, analysera och förbättra en process

Det här är skillens egen arbetsgång. Den fungerar utan några andra verktyg. Läs bara det avsnitt du behöver för den fas ni är i.

## Principer

- Beskriv hur det faktiskt går till. En karta över hur det borde vara är en önskan, inte ett nuläge.
- En process har en början, ett slut, en mottagare och ett värde. Saknas något av det är avgränsningen fel.
- Ansvar följer roller, inte personer.
- Fråga dem som gör arbetet. Chefens bild och utförarens bild skiljer sig ofta, och båda är värdefulla.
- Förbättra det som orsakar problemet, inte det som är lättast att ändra.

## Fas 1. Uppdrag och avgränsning

Frågor:
- Vilken process, med vilket namn? Var börjar den (vad sätter igång den) och var slutar den (vad är "klart")?
- Vem är mottagare eller kund av resultatet?
- Vem äger processen, och vad får du ändra inom uppdraget?
- Vad är problemet eller syftet? Vem märker det?
- Vad ingår och vad ingår inte? Finns delprocesser som bör kartläggas var för sig?

Är uppdraget otydligt, formulera det: *Syfte, mål, avgränsning, ansvar och mandat, leverans, tidpunkt, uppföljning.*

## Fas 2. Nuläge

För varje steg, fråga:
- Vad görs? (en kort handling, verb först: "Granska ansökan")
- Av vilken roll? (inte vem, utan vilken funktion)
- Vad behövs för att göra det (indata, information, beslut) och vad blir resultatet (utdata)?
- I vilket system eller verktyg? Vad görs för hand?
- Finns en beslutspunkt? Vad avgör, och vilka är utfallen?
- Hur lång tid tar steget, och hur lång tid väntar ärendet innan det? (okänt är ett giltigt svar)
- Vad händer när något är fel, saknas eller avviker?

Tips:
- Börja med huvudflödet (det vanliga), ta undantag efter.
- Hitta slut: alla sätt processen kan ta slut på.
- Hitta slingor: ställen där ärendet går tillbaka (komplettering, omtag).
- Har användaren bara en kort beskrivning: gör rimliga antaganden, redovisa dem och be om rättelse.
- Är underlaget ett samtal eller mötesanteckningar: plocka ut roller, steg och beslut, markera det som är oklart och formulera verifieringsfrågor.

Resultat: `assets/processbeskrivning.md` ifylld.

## Fas 3. Karta

Lämna beskrivningen till Processkartan-skillen. Se `references/processkartan.md`. Efter kartan: gå igenom den med användaren. Stämmer ordningen? Saknas steg, undantag eller slut?

## Fas 4. Analys

Gå igenom kartan och leta efter:
- **Väntan:** ärenden som ligger still. Var, hur länge, varför?
- **Överlämningar:** varje gång ett ärende byter roll finns risk för missförstånd och fördröjning.
- **Dubbelarbete och omtag:** samma uppgift två gånger, komplettering, felrättning.
- **Oklart ansvar:** steg utan ägare, eller med flera.
- **Beslutspunkter utan kriterier:** vem avgör och på vilka grunder?
- **Undantag som blivit regel:** hur stor del går inte huvudflödet?
- **System och information:** manuell inmatning, information som inte följer med, systembrott.
- **Mått:** volym, ledtid, andel omtag. Finns de? Saknas de? Ta aldrig fram siffror som inte finns.

För varje fynd: vad är **observerat** (någon har sett eller mätt), vad är **antagande**, vad är **okänt**? Fyll i `assets/processanalys.md`.

## Fas 5. Börläge och gap

- Beskriv önskat läge i **principer**, till exempel "ett ärende registreras en gång", "varje steg har en ägare", "beslut tas där informationen finns".
- Gör inte börläget till en färdig lösning (ett nytt system). Lösningar kommer i fas 7.
- Gap = skillnaden mellan nuläge och börläge, per princip.
- Vad händer om inget görs? (risk och kostnad för att stå still)

## Fas 6. Ansvar (RACI)

- Lista aktiviteterna (rader) och rollerna (kolumner).
- Fyll i **R** (utför), **A** (ansvarar och beslutar, bara en per aktivitet), **C** (rådfrågas), **I** (informeras).
- Granska: finns det aktiviteter utan A, med flera A, eller roller som är R för allt?
- Markera där ansvaret saknas i underlaget som okänt. Gissa inte.

## Fas 7. Förbättringar

För varje förslag:
- Vilket observerat problem löser det?
- Vad ändras (steg, roll, regel, system, information)?
- Effekt (låg, medel, hög) och ansträngning (låg, medel, hög).
- Beroenden, risker, vem som måste besluta.

Gruppera: **snabba vinster** (låg ansträngning, märkbar effekt), **planerade** (kräver beslut eller resurser), **utreds** (kräver mer underlag). Föreslå högst fem att gå vidare med.

## Fas 8. Uppföljning och nästa steg

- Mått som visar att processen blivit bättre (ledtid, omtag, nöjdhet), ägare och tidpunkt.
- Vad lämnas vidare: ett avgränsat test (Förbättringsledaren), ett införande (Förändringsledaren), en workshop med utförarna.
- Vad återstår att verifiera i verkligheten.

## När underlaget är dåligt eller saknas

- **Nästan inget underlag:** ställ de tre frågorna i fas 1 och föreslå en kort workshop med utförarna. Kartlägg inte på gissning.
- **Motsägande beskrivningar:** lista motsägelserna och be användaren avgöra, eller markera att de ska verifieras.
- **Processen är egentligen flera:** föreslå uppdelning och ta en i taget.
- **Användaren vill direkt ha en lösning:** behandla lösningen som en hypotes i fas 7 och fråga vilket problem den ska lösa.
- **Ansvar är okänt:** lämna det tomt. Ett tomt ansvar är en upptäckt, inte ett fel.
