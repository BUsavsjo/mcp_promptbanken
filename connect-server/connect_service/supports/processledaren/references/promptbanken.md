# Promptbanken Open: arbetsflöden för processarbete

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens beskrivning, ärenden, dokument, namn eller andra uppgifter till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Paket som hör till skillen

| Paket (slug) | Typ | Använd när | Innehåll |
| --- | --- | --- | --- |
| `processledarens-verktygslada` | collection | Huvudstödet. Välj enskilda mallar per fas. | Vad behöver jag göra som processledare nu?, Tydlig uppdragsformulering, Kartlägg ett verksamhetsflöde, Nuläge-börläge-gap, RACI-matris, Workshopplaneraren, Facilitatorn, Från workshop till nästa steg, Utvärdera och justera |
| `processer` | collection | Kompletterande mallar för rutin, orsak och uppföljning. | Rutin till processpaket, Processkarta i Mermaid, RACI-matris, Nuläge-börläge-gap, Årshjul, 5 varför, Rutiner & anvisningar, Utvärdera och justera, Skapa checklista |

Stegens namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellen.

## Mallar som är särskilt användbara

Sök fram dem med `search_templates` (de har stabila titlar, men id kan ändras):

| Mall (titel) | Fas | Notering |
| --- | --- | --- |
| Från samtal till processflöde | 2 | Underlaget är en transkribering, mötesanteckning eller ett samtal. Ger roller, steg, beslutspunkter, osäkerheter och verifieringsfrågor. Hoppa över Mermaid-delen om du använder Processkartan-skillen. |
| Kartlägg ett verksamhetsflöde | 2 | Underlaget är en beskrivning som ska kartläggas steg för steg med ansvar, information och systemstöd. |
| Från beskrivning till processkarta | 3 | Gör en processbeskrivning till Processkartans JSON. Använd den **bara** om Processkartan-skillen saknas och användaren vill ha en karta, och låt den hantera formatet. |
| Nuläge-börläge-gap | 5 | |
| RACI-matris | 6 | |
| Workshopplaneraren, Facilitatorn, Från workshop till nästa steg | 2, 4 | När flera aktörer behöver bidra till kartläggningen. |

## Så använder du dem

1. Välj utifrån uppgiften. Liten uppgift: ingen mall behövs. Annars hämta bara mallen för den fas ni är i.
2. `search_templates` med allmänna ord, till exempel "processkartläggning samtal" eller "RACI ansvar". Skicka inte `role` när uppgiften är tydlig.
3. `get_template` med mallens id.
4. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt.
5. Mallen är stöd. Skillens regler (nuläge före lösning, inga påhittade roller eller tider, Processkartan-skillen för kartan) gäller före mallens.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketen och mallarna ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
