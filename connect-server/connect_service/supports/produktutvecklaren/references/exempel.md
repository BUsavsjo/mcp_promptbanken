# Exempel: första svaret

## Idé med lite underlag

Användaren skriver:

> Jag har en idé om en app där föräldrar kan se vad deras barn gjort i skolan under dagen. Är det värt att bygga?

Skillen frågar inte efter sådant som redan stod i texten (idén, att det gäller föräldrar och skola). Ett bra första svar:

---

Det är en tydlig idé, och frågan om den är värd att bygga går att svara på utan att bygga något. Jag går igenom det i steg och stannar vid tre punkter där jag ger dig ett uttryckligt besked: bygga, testa först, ändra riktning eller låta bli.

Så här ser det ut hittills. Observationer: inga ännu. Antaganden: att föräldrar vill veta detta, att skolor kan och vill leverera informationen och att någon betalar.

Det som avgör mest nu är vem som skulle betala och vad som används i dag. Skolor har redan lärplattformar och meddelandefunktioner som ofta ger föräldrar viss insyn. Därför frågar jag först:

**Vet du vad föräldrar och skolor använder i dag för att följa vad barnen gör, och har du pratat med någon som har problemet?**

Svara kort på det du vet. Resten markerar jag som antaganden. Något besked om att bygga eller inte ger jag först vid grinden, när det finns underlag att väga.

Var vi är: **Steg 1 av 9, förstå behovet.** Skriv inga namn på enskilda barn eller familjer.

---

Observera vad svaret *inte* gör: det hittar inte på marknadsdata, hyllar inte idén och ställer bara en fråga.

## Användaren har redan svarat

Om användaren i första meddelandet har skrivit "jag har pratat med tio föräldrar, åtta sa att de vill ha detta, men ingen skulle betala" ska skillen inte fråga om samtal eller betalningsvilja. Den ska notera att åtta av tio önskar det (observation, önskemål, inte signal), att ingen skulle betala (observation) och gå direkt till köpare och finansiering: "Vem skulle i stället betala, skolan eller kommunen?" Och väga grind A utifrån det.

## Om verktygen från Promptbanken finns

Skillen kan göra ett uppslag utan användarens text, till exempel `get_package("fran-behov-till-validerad-produkt")` och `list_package_prompts("fran-behov-till-validerad-produkt")`, och använda stegen som stöd. Svaret till användaren blir likadant.
