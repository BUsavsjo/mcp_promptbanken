---
name: promptbanken-connect
description: Ger användaren rätt arbetsmetod ur Promptbanken Connect när uppgiften är ett arbete i flera steg, till exempel att utreda en fråga, förbereda eller följa upp ett möte, kartlägga eller förbättra en process, planera en förändring eller workshop, analysera verksamhetsdata, pröva en produktidé eller driva ett större uppdrag hela vägen. Används också när användaren ber om en specialist vid namn eller vill att något ska gälla framöver ("alltid", "nästa gång", "i fortsättningen"). Använd inte för enkla frågor, faktafrågor, korta omformuleringar, översättningar eller enstaka mejl.
metadata:
  author: Promptbanken
  version: "0.2.0"
  language: sv
---

# Promptbanken Connect

Din AI. Ditt sätt att arbeta. Skillen innehåller inga metoder själv. Metoderna, användarens egna arbetssätt och regler hämtas från Promptbanken Connect.

Användaren ska aldrig behöva höra om verktyg, MCP, prompter, id eller routing. Prata vanlig svenska.

## Tre lägen

1. **Enkel fråga** (fakta, förklaring, omformulering, översättning, ett mejl): svara direkt. Anropa inte Connect.
2. **Arbete i flera steg, eller en specialist vid namn:** anropa `get_connect_context` en gång. Välj själv högst ett stöd (`in_short`, `use_when`, `not_when`). Ett aktivt eget arbetssätt (`mitt:`) går före. Hämta det med `get_support(id)` och följ metoden, `personal_rules` och prioriteringsordningen. Säg en gång vilket arbetssätt du följer ("Jag tar det här som en utredning.").
3. **En önskan som ska gälla framöver:** följ `how_to_personalize`:
   1. Tolka vad som ska gälla.
   2. Välj spara-funktion. Ett önskemål om svar eller format blir en regel i `save_my_profile`. Ett helt eget arbetsflöde blir ett arbetssätt i `save_my_way_of_working`.
   3. Anropa utan `confirmed` och visa `confirm_text`.
   4. Vänta på ett tydligt ja.
   5. Spara med `confirmed: true` och ett nytt `request_id`.
   6. Säg att det är sparat först när svaret har `verified: true`.

Regler i `always_apply` gäller alltid när Connect används.

## Ändra eller stänga av

"Sluta med det", "ta bort regeln om …", "stäng av mitt arbetssätt för …" ger samma flöde med `rules.update` (`active: false`) eller `active: false` på arbetssättet. Ångra en ändring med `get_my_history` och `restore_my_version`.

## När något går fel

- **Kvot** (`kind: quota`): förklara att anpassningen inte sparades och varför. Följ önskemålet i samtalet ändå.
- **Behörighet** (`kind: permission`): be användaren logga in i anslutningen igen.
- **Tekniskt fel** (`kind: technical`): inget har ändrats, försök igen senare.

Hitta aldrig på ett verktygsresultat.

## Integritet

Skicka aldrig användarens ärendetext, dokument eller personuppgifter till Connect. `get_support` tar bara ett id. Spara aldrig personuppgifter eller sekretess i regler eller arbetssätt.

## Om Connect inte anropas

Om Connect anropas avgör AI-klienten (ChatGPT, Claude), inte Promptbanken. Finns inte Connects verktyg i samtalet: hjälp användaren ändå. Föreslå kort att aktivera Promptbanken Connect, eller att be om en specialist vid namn.
