# Checklista: datakontroll

Gå igenom före analysen. Skriv svaret eller "okänt". Kör `scripts/profilera.mjs` för punkterna 5–9 om du kan köra kod.

| Nr | Kontroll | Svar | Anmärkning |
| --- | --- | --- | --- |
| 1 | Vad är datan: system, uttagsdatum, urval, version? | | |
| 2 | Vad räknas per kolumn och rad? Har definitionen ändrats under perioden? | | |
| 3 | Enheter (kronor, tkr, timmar, antal, procent) är konsekventa? | | |
| 4 | Perioden är jämförbar (kalender, läsår, arbetsdagar, säsong)? Saknas perioder? | | |
| 5 | Saknade värden: antal, kolumner, slumpmässiga eller systematiska? | | |
| 6 | Dubbletter: exakta eller samma ärende två gånger? | | |
| 7 | Avvikande värden: mätfel, inmatningsfel eller verkliga fall? | | |
| 8 | Delsummor stämmer mot totalen? Antalet rader stämmer mot källan? | | |
| 9 | Personuppgifter, identifierande kolumner eller grupper med färre än fem? | | |
| 10 | Är urvalet så stort att det går att jämföra grupper? (n per grupp) | | |

## Bedömning

- Kan datan bära frågan? **Ja / Delvis / Nej**
- Om delvis eller nej: vad saknas, och hur kan det samlas in?
- Begränsningar att redovisa i analysen:
