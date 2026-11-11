---
name: promptbanken-connect
description: Ger användaren rätt arbetsmetod ur Promptbanken Connect när uppgiften är ett arbete i flera steg, till exempel att utreda en fråga, förbereda eller följa upp ett möte, kartlägga eller förbättra en process, planera en förändring eller workshop, analysera verksamhetsdata, pröva en produktidé eller driva ett större uppdrag hela vägen. Använder även användarens egna sparade arbetssätt och personliga regler. Använd inte för enkla frågor, faktafrågor, korta omformuleringar, översättningar eller enstaka mejl.
metadata:
  author: Promptbanken
  version: "0.1.0"
  language: sv
---

# Promptbanken Connect

Den här skillen innehåller inga metoder själv. Metoderna, användarens egna arbetssätt och personliga regler finns i Promptbanken Connect och hämtas med Connects verktyg. Det finns en auktoritativ källa, så skillen behöver inte uppdateras när en metod ändras.

## Så väljer du stöd

1. Anropa `get_connect_context` en gång i samtalet, utan argument.
2. Läs `supports` och `my_ways_of_working`. Välj högst ett stöd vars `use_when` passar uppgiften och vars `not_when` inte utesluter den. Ett aktivt eget arbetssätt (`mitt:`) går före ett gemensamt stöd när det passar.
3. Passar inget stöd, eller är uppgiften en enkel fråga: svara direkt utan stöd.
4. Passar två stöd lika bra: ställ en kort fråga om vad användaren vill uppnå.
5. Hämta det valda stödet med `get_support(id)`. Följ metoden, användarens `personal_rules` och prioriteringsordningen i svaret. Hämta resurser med `get_support(id, resource)` när metoden hänvisar till en fil.
6. Säg kort vilket arbetssätt du följer första gången. Visa inte verktygsnamn eller interna steg.

## Integritet

- Skicka aldrig användarens ärendetext, dokument eller personuppgifter till Connects verktyg. `get_support` tar bara ett id.
- Spara bara personliga regler eller arbetssätt efter att användaren har sett en förhandsvisning och sagt ja.

## Personliga regler och egna arbetssätt

- En enstaka korrigering gäller bara uppgiften. Visar användaren uttryckligen en återkommande preferens ("alltid", "i fortsättningen"): fråga om den ska sparas som personlig regel.
- Vill användaren ha en egen AI för en återkommande uppgift: föreslå namn, syfte, när det ska och inte ska användas, arbetsinstruktion och kvalitetsregler, och koppla till en gemensam metod med `extends` när det passar.
- Visa alltid förhandsvisningen (`save_my_profile` eller `save_my_way_of_working` utan `confirmed`) och spara med `confirmed: true` först efter ett tydligt ja.
- Versioner visas med `get_my_history` och återställs med `restore_my_version`.

## Om verktygen saknas

Finns inte Connects verktyg i den här konversationen: säg kort att Promptbanken Connect behöver vara aktiverad och hjälp användaren så gott det går ändå. Hitta aldrig på ett verktygsresultat.
