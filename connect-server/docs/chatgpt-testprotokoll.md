# Manuellt testprotokoll – Connect DEV i vanlig ChatGPT-chatt

Syfte: mäta om ChatGPT **av sig själv** använder Connect när en vanlig
användare skriver som vanligt.

## Viktigt att förstå före testet

- **Ett lyckat direkt MCP-anrop bevisar inte automatisk aktivering.** Om
  testaren ber ChatGPT att "använda Connect" eller "testa get_support" visar
  det bara att verktyget fungerar. Det säger inget om vad Maria får när hon
  skriver "Utred det här".
- **Om Connect anropas avgör ChatGPT.** Ett uteblivet anrop är klientens
  verktygsval, inte ett backendfel. Notera det som "ej aktiverat", aldrig som
  "Connect trasigt".
- De automatiska testerna (`tests/test_user_scenarios.py`,
  `tests/test_acceptance.py`) verifierar kontraktet och livscykeln. De kan
  inte mäta ChatGPT:s val.

## Förberedelser

1. Använd ett **isolerat testkonto** i Promptbanken dev, inte ett riktigt
   användarkonto. Använd bara påhittade uppgifter, inga personuppgifter eller
   riktiga dokument.
2. I ChatGPT: Inställningar → Appar och kopplingar → Connect DEV
   (`https://connect-dev.promptbanken.se/mcp`). Uppdatera kopplingen så att
   verktygslistan är aktuell (sju verktyg).
3. Kontrollera att kontot inte har gamla testregler: be i en separat chatt om
   att visa dina sparade regler, eller börja från ett nytt testkonto.
4. Starta **en ny chatt per testfall**. Nämn aldrig Promptbanken, Connect,
   specialister eller verktyg i testmeddelandet.

## Testfall

För varje fall: skriv meddelandet ordagrant, svara naturligt på eventuella
följdfrågor och notera resultatet i tabellen nedan.

| # | Meddelande (ny chatt) | Förväntat |
| --- | --- | --- |
| 1 | Vad är skillnaden mellan en konsekvensanalys och en riskanalys? | Inget Connect-anrop. Kort svar. |
| 2 | Utred för- och nackdelar med att centralisera administrationen. | Connect anropas, Utredaren hämtas. Kort start, en fråga i taget. |
| 3 | Nästa gång vill jag ha kortare sammanfattningar. | Förhandsvisning: "Ny regel … gäller alla uppgifter. Vill du spara det?" Svara **ja**. "Sparat." |
| 4 | Mina utredningar ska alltid börja med en problembeskrivning. | Förhandsvisning "… gäller Utredaren". Svara **ja**. |
| 5 | Hjälp mig planera en workshop för 20 personer. | Workshopledaren. Kortare sammanfattning följer med; problembeskrivningsregeln gör det inte. |
| 6 | Så här vill jag göra leverantörssvar framöver: tacka först, svara i max tre stycken och avsluta med nästa steg. | Förhandsvisning "Nytt arbetssätt: ”Leverantörssvar” …". Svara **ja**. |
| 7a | Sluta med de korta sammanfattningarna. | Förhandsvisning "Stänger av regeln …". Svara **ja**. |
| 7b | Ångra det, gå tillbaka till hur det var innan. | Förhandsvisning av återställning. Svara **ja**. Regeln är på igen. |
| 8 | (ny chatt) Utred om vi ska införa digitala signaturer. | Svaret börjar med en problembeskrivning och är kort. |
| N1 | Skriv om det här mejlet så att det blir vänligare: "Vi kan inte leverera i tid." | Inget Connect-anrop. |
| N2 | Översätt "beslutsunderlag" till engelska. | Inget Connect-anrop. |
| N3 | Nästa gång vill jag … (svara **nej** på förhandsvisningen) | Inget sparas. Kontrollera i en ny chatt att regeln saknas. |

Fler fall finns i `evals/connect_auto_cases.json` (72 fall, positiva och
negativa). Räkna träffsäkerhet med `scripts/score_evals.py`.

## Vad som noteras per fall

| Fält | Värden |
| --- | --- |
| Connect anropat? | ja / nej |
| Hämtat stöd | id eller "inget" |
| Rätt enligt förväntat? | ja / nej / delvis |
| Teknikord synliga för användaren? | ja (vilka) / nej |
| Sparat utan ja? | ja (= allvarligt fel) / nej |
| Kommentar | fritt |

## Tolkning

- **Automatisk aktivering**: andel positiva fall där rätt stöd hämtades utan
  att testaren nämnde Connect. Mål enligt eval-sviten: minst 85 %.
- **Falsk aktivering**: andel negativa fall där Connect ändå anropades. Mål:
  högst 5 %.
- **Personaliseringskedjan** (3 → 5 → 7 → 8) är godkänd först när alla
  stegen fungerar i nya chattar.

## Efter testet

Återställ testkontot: be om att ta bort testreglerna och arbetssättet (med
förhandsvisning och ja), eller arkivera dem på app.promptbanken.se (dev).
