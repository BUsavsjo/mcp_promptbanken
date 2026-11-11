# Exempel: första svaret

Användaren skriver:

> Vi har statistik över arbetsbelastning och kostnader. Hjälp mig identifiera mönster och möjliga förbättringar.

Det här är ett *medelstort* uppdrag. Frågan är bred och datan är okänd. Ett bra första svar:

---

Det hjälper jag dig gärna med. Innan jag letar mönster vill jag förstå frågan och granska datan. Annars riskerar vi att dra slutsatser som datan inte bär.

Så här arbetar jag: jag kontrollerar datakvaliteten först, räknar alla tal i en körd beräkning (inte i huvudet), skiljer det datan visar från det jag tolkar, och säger tydligt vad datan inte kan svara på. Jag hittar inte på siffror.

Jag tar frågorna en i taget. Den första:

**Vilken fråga vill ni ha svar på?** Till exempel (a) var arbetsbelastningen är högst, (b) om belastningen hänger ihop med kostnaderna, (c) hur det har förändrats över tid, (d) något annat, beskriv med egna ord.

Efter ditt svar frågar jag vad datan innehåller (kolumner, period, enhet, system) och om den har personuppgifter, som i så fall ska avidentifieras eller aggregeras först.

Om du kan lägga in en CSV-fil och jag kan köra kod, kör jag en lokal datakontroll som visar saknade värden, dubbletter, summor och avvikande värden. Annars går vi igenom en checklista tillsammans.

Var vi är: **Fas 1 av 7, analysfrågan.**

---

Observera vad svaret *inte* gör: det drar inga slutsatser om belastning eller kostnad, räknar inget på gissning och ber inte om personuppgifter.

## Om verktygen från Promptbanken finns

Skillen kan göra ett uppslag utan användarens data, till exempel `list_package_prompts("data-till-forbattring")`, och använda stegens upplägg som stöd för frågorna. Svaret till användaren blir likadant.
