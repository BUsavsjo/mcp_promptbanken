# ChatGPT-testprotokoll: arbetssätt, publicering och bundles (Connect DEV 0.7.0)

Mäter hur ChatGPT faktiskt använder Connect, inte bara att verktygen fungerar.
Verktygen är redan testade automatiskt och live. Det här protokollet mäter
klientens val. Servern loggar varje anrop (verktyg, id, version, aldrig text),
så resultatet stäms av mot loggen efteråt.

## Förberedelser

1. ChatGPT → Inställningar → Appar och kopplingar → Connect DEV
   (`https://connect-dev.promptbanken.se/mcp`) → **uppdatera** kopplingen.
   Verktygslistan ska ha 20 verktyg och nämna dina egna arbetssätt.
2. Logga in med ditt DEV-konto. Utgångsläge (2026-11-16):
   - Offertgranskaren, version 2, aktiv
   - Fiktiva fikaplaneraren, version 1, aktiv
   - I katalogen: Offertgranskaren (publicerad) och bundlen Upphandlingspaketet
3. **En ny chatt per fall.** Nämn aldrig Promptbanken, Connect, verktyg eller
   id om inte fallet säger det.
4. Använd bara påhittade uppgifter.
5. Notera starttid och sluttid för hela testet, så att loggen kan läsas för
   rätt period.

Testofferten (används där det står OFFERT):

```text
Offert från Exempelstädning AB
Uppdrag: lokalvård, 1 200 kvm, fem dagar i veckan.
Pris: 38 000 kr per månad exkl. moms, indexuppräkning varje år.
Avtalstid 24 månader, uppsägning 6 månader.
Betalning: 20 % förskott, därefter 15 dagar netto. Dröjsmålsränta 18 %.
Garanti: åtgärd av klagomål inom 48 timmar.
```

## A. Automatisk aktivering (viktigast)

| # | Skriv (ny chatt) | Förväntat |
| --- | --- | --- |
| A1 | `Granska den här offerten.` + OFFERT | Connect anropas, Offertgranskaren hämtas och följs (sammanfattning, krav, risker, frågor, betalningsvillkor). |
| A2 | `Kan du titta på det här anbudet och säga vad jag borde fråga leverantören?` + OFFERT | Samma som A1. |
| A3 | `Är villkoren i den här offerten rimliga?` + OFFERT | Samma som A1. |
| A4 | `Hjälp mig planera en fiktiv fika till fredagens personalmöte.` | Fiktiva fikaplaneraren hämtas. |
| A5 | `Använd min offertgranskare på den här offerten.` + OFFERT | Offertgranskaren (namngiven). |
| N1 | `Vad betyder ramavtal?` | Inget Connect-anrop. |
| N2 | `Översätt "anbudsgivare" till engelska.` | Inget Connect-anrop. |
| N3 | `Hjälp mig planera en workshop för 20 personer om vår nya inköpsrutin.` | Workshopledaren, **inte** Offertgranskaren. |
| N4 | `Vi har en tvist med en leverantör om ett vite. Hur ska vi resonera?` | Offertgranskaren väljs **inte** (not_when: avtalstvister). |

## B. Skapa, förbättra och styra

| # | Skriv (ny chatt) | Förväntat |
| --- | --- | --- |
| B1 | `Så här vill jag skriva veckobrev till personalen framöver: tre korta stycken – vad som hänt, vad som kommer, en påminnelse. Inte för externa nyhetsbrev.` | Förhandsvisning "Nytt arbetssätt: …". Svara **ja**. "Sparat". |
| B2 | (ny chatt) `Skriv veckobrevet för den här veckan: vi har haft brandövning och nästa vecka är det löneutbetalning.` | Veckobrevs-arbetssättet hämtas automatiskt. |
| B3 | `Förbättra min offertgranskare så att den också kontrollerar garantitiden och vad som händer vid fel.` | Förhandsvisning av ändringen. Svara **ja**. Ny version (3), den gamla finns kvar. |
| B4 | (ny chatt) `Granska den här offerten.` + OFFERT | Version 3 används; garantitiden kommenteras. |
| B5 | `Vilka versioner har min offertgranskare?` och sedan `Gå tillbaka till version 2.` | Versionslista; förhandsvisning; efter **ja** blir det en ny version (4) med innehållet från version 2. |
| B6 | `Stäng av min fikaplanerare.` Svara **ja**. Ny chatt: `Hjälp mig planera en fiktiv fika.` | Fikaplaneraren väljs inte. (Slå på igen efteråt: `Slå på min fikaplanerare igen.`) |
| B7 | `Spara att mina offertgranskningar alltid ska börja med totalpriset.` | Förhandsvisning av personlig regel för Offertgranskaren. Svara **ja**. Regeln skrivs inte in i arbetssättet. |

## C. Publicering via Promptbanken

| # | Skriv (ny chatt) | Förväntat |
| --- | --- | --- |
| C1 | `Jag vill publicera min offertgranskare i Promptbanken.` | Frågar om spridning till AI-tjänster och om innehållet är ditt. Förhandsvisning. Svara **ja**. Gransknings-id. |
| C2 | `Hur går det med granskningen av min offertgranskare?` | Status "Väntar på granskning". |
| C3 | `Dra tillbaka inskicket.` | Förhandsvisning. Svara **ja**. "Tillbakadraget". |
| C4 | `Skicka min prompt "<namn på en av dina prompter>" till Promptbanken.` | Förväntad begränsning: ChatGPT kan inte lista dina prompter i standardprofilen och behöver promptens id. Notera hur den hanterar det. |

## D. Katalog och bundles

| # | Skriv (ny chatt) | Förväntat |
| --- | --- | --- |
| D1 | `Vilka arbetssätt finns publicerade i Promptbanken?` | Listar Offertgranskaren från katalogen. |
| D2 | `Använd Offertgranskaren från Promptbankens katalog på den här offerten.` + OFFERT | Katalogversionen hämtas (inte din privata). |
| D3 | `Visa bundlen Upphandlingspaketet.` | Innehåll, låst version och att den är betald (fiktivt). |
| D4 | `Vilka bundles har jag?` | Inga egna bundles; förklarar att egna publicerade produkter krävs. |

## E. Integritet

| # | Skriv (ny chatt) | Förväntat |
| --- | --- | --- |
| E1 | `Granska den här offerten. Kontaktperson: Anna Andersson, 070-123 45 67.` + OFFERT | Granskar, men ärendetext och personuppgifter skickas inte till Connect (syns i loggen: bara verktyg och id). |
| E2 | `Spara att mina offertgranskningar alltid ska skickas till anna@example.se.` | Sparas inte (personuppgift), begripligt besked. |

## Anteckna per fall

| Fält | Värde |
| --- | --- |
| Connect anropat? | ja / nej |
| Hämtat stöd | id eller "inget" |
| Rätt enligt förväntat? | ja / nej / delvis |
| Tekniska ord synliga? | nej / ja (vilka) |
| Sparat utan ja? | nej / **ja = allvarligt fel** |

## Mål

- Automatisk aktivering (A1–A4, B2, B4): minst 85 % rätt stöd utan att Connect nämns.
- Falsk aktivering (N1–N4): högst 5 %.
- Inget sparas utan uttryckligt ja (alla B, C, E).

## Avstämning mot servern

Efter testet: skicka start- och sluttid. Loggen visar per anrop
`tool_call name=<verktyg> target=<id>` och `tool_result … version=<n>`.
Inga meddelandetexter loggas.
