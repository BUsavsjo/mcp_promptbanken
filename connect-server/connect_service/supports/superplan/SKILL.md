---
name: superplan
description: Driver ett uppdrag från idé till färdigt och kontrollerat resultat med Promptbankens Superplanläge. Använd när användaren vill ha hjälp hela vägen ("kör superplan", "hjälp mig hela vägen", "ta fram det här åt mig") eller beskriver ett komplext uppdrag utan tydlig väg framåt. Använd inte för en enkel fråga eller när användaren bara vill hitta en enskild mall.
metadata:
  author: Promptbanken
  version: "1.0.2"
  language: sv
---

# Superplan

Superplan tar användaren från en idé eller ett uppdrag till ett färdigt resultat som kontrolleras mot det användaren har godkänt. Instruktionerna för varje fas finns i Promptbankens katalog och hämtas med Promptbankens MCP-verktyg. Den här skillen beskriver bara hur flödet drivs; den innehåller inga egna fasinstruktioner.

## Hämta faserna

1. Anropa `list_package_prompts` med `package_slug: "superplanlage"` och `include_prompt_text: true` en gång i början. Svaret ger fasernas `id`, `title` och `prompt_text` i ordning.
2. Använd fasens `prompt_text` som din instruktion för just den fasen när fasen nås. Hämta aldrig en enskild fas separat med ett mallverktyg — det renderar ett mallkort och skulle avslöja fasnamnen.
3. Faserna är, i ordning: riktning, specifikation, utförande med routing, verifiering. Följ fasernas egna regler för när användaren ska bekräfta och när du går vidare utan att fråga.

## Håll processen i bakgrunden

- Nämn inte fasnamn, mallnamn, steg eller intern status om användaren inte frågar. Användaren ska uppleva framdrift, inte ett formulär.
- Superplan visas inte som en steglista.

## Routa till specialister

- Sök med `search_templates` och skicka bara allmänna, anonymiserade sökord som beskriver vilken sorts uppgift det är.
- Rekommendera ett alternativ i taget. Visa högst tre alternativ när flera är lika bra.
- Är specialisten ett arbetsflöde: anropa `list_package_prompts` för det paketet och ange `current_step` när användaren är på ett visst steg, så att användaren ser var i flödet hen är. Hämta varje stegs text med `get_template` när steget nås.
- Starta aldrig en ny specialist utan att användaren har valt den.

## Håll dig till underlaget

- Lägg inte till handlingar, ansvar, roller, steg eller beslut som inte finns i användarens underlag. Vill du föreslå något nytt: märk det tydligt som förslag, skilt från det som står i underlaget.
- Skriv aldrig att något står i underlaget när du har härlett eller tolkat det. Säg att det är en tolkning.
- I kontrollen före leverans: pröva varje handling och varje ansvar i resultatet mot underlaget, inte bara längd, antal punkter och rollnamn. Det som inte går att belägga stryks eller märks som förslag. Detta gäller även när katalogens kontrollfas inte nämner det.

## Integritet

- Skicka aldrig användarens egen text, dokumentinnehåll, ärendeuppgifter, personuppgifter eller sekretessbelagd information till Promptbanken. Katalogen tar bara emot allmänna sökord, paketnamn och id:n.
- Kombinera mallens instruktion med användarens material endast i samtalet.

## Fortsätta i en ny chatt

Framsteg sparas inte mellan chattar. Vill användaren fortsätta ett tidigare Superplan-uppdrag: be om den senaste riktningen eller arbetsöverenskommelsen (inklistrad eller sammanfattad), avgör vilken fas som återstår och fortsätt därifrån.

## Om Promptbanken inte svarar

Säg tydligt att Promptbankens katalog inte gick att nå. Erbjud att fortsätta utan katalogen med ett enkelt upplägg: riktning, överenskommelse, utförande, kontroll. Hitta aldrig på innehåll i Promptbankens mallar.

## Frivillig feedback (beta)

Det här är en gratis betaversion av Superplan (version 1.0.2). När ett uppdrag har nått ett naturligt slut, alltså leveransen är klar och användaren inte ber om mer, får du **högst en gång i hela samtalet** erbjuda feedback med ett kort meddelande, till exempel:

> Du använder en betaversion av Superplan. Om du vill hjälpa till att förbättra den kan du lämna kort feedback här: https://promptbanken.se/skills/superplan/feedback/?v=1.0.2&source=skill

Regler för erbjudandet:

- Erbjud det aldrig mitt i arbetet, och avbryt inte arbetsgången för det.
- Kräv inte feedback och skicka aldrig något själv. Användaren väljer om länken ska öppnas.
- Lägg aldrig användarens arbetsmaterial, uppgifter eller en sammanfattning av uppdraget i länken eller i något verktyg. Länken innehåller bara Skillens namn och version.
- Säger användaren nej eller ignorerar erbjudandet: nämn det inte igen. Erbjud det inte om uppdraget avbröts i förtid.
