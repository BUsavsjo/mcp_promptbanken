---
name: superplan
description: Driver ett uppdrag från idé till färdigt och kontrollerat resultat med Promptbankens Superplanläge. Använd när användaren vill ha hjälp hela vägen ("kör superplan", "hjälp mig hela vägen", "ta fram det här åt mig") eller beskriver ett komplext uppdrag utan tydlig väg framåt. Använd inte för en enkel fråga eller när användaren bara vill hitta en enskild mall.
---

# Superplan

Superplan tar användaren från en idé eller ett uppdrag till ett färdigt resultat som kontrolleras mot det användaren har godkänt. Instruktionerna för varje fas finns i Promptbankens katalog och hämtas med Promptbankens MCP-verktyg. Den här skillen beskriver bara hur flödet drivs; den innehåller inga egna fasinstruktioner.

## Hämta faserna

1. Anropa `list_package_prompts` med `package_slug: "superplanlage"` en gång i början. Svaret ger fasernas `id` och `title` i ordning.
2. Anropa `get_template` med fasens `id` först när fasen nås. Följ fasens `prompt_text` som din instruktion för just den fasen.
3. Faserna är, i ordning: riktning, specifikation, utförande med routing, verifiering. Följ fasernas egna regler för när användaren ska bekräfta och när du går vidare utan att fråga.

## Håll processen i bakgrunden

- Nämn inte fasnamn, mallnamn, steg eller intern status om användaren inte frågar. Användaren ska uppleva framdrift, inte ett formulär.
- Superplan visas inte som en steglista.

## Routa till specialister

- Sök med `search_templates` och skicka bara allmänna, anonymiserade sökord som beskriver vilken sorts uppgift det är.
- Rekommendera ett alternativ i taget. Visa högst tre alternativ när flera är lika bra.
- Är specialisten ett arbetsflöde: anropa `list_package_prompts` för det paketet och ange `current_step` när användaren är på ett visst steg, så att användaren ser var i flödet hen är. Hämta varje stegs text med `get_template` när steget nås.
- Starta aldrig en ny specialist utan att användaren har valt den.

## Integritet

- Skicka aldrig användarens egen text, dokumentinnehåll, ärendeuppgifter, personuppgifter eller sekretessbelagd information till Promptbanken. Katalogen tar bara emot allmänna sökord, paketnamn och id:n.
- Kombinera mallens instruktion med användarens material endast i samtalet.

## Fortsätta i en ny chatt

Framsteg sparas inte mellan chattar. Vill användaren fortsätta ett tidigare Superplan-uppdrag: be om den senaste riktningen eller arbetsöverenskommelsen (inklistrad eller sammanfattad), avgör vilken fas som återstår och fortsätt därifrån.

## Om Promptbanken inte svarar

Säg tydligt att Promptbankens katalog inte gick att nå. Erbjud att fortsätta utan katalogen med ett enkelt upplägg: riktning, överenskommelse, utförande, kontroll. Hitta aldrig på innehåll i Promptbankens mallar.
