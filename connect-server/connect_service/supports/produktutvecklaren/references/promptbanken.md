# Promptbanken Open: arbetsflöde för produktutveckling

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens idé, kunduppgifter, siffror, namn eller dokument till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Arbetsflöde som hör till skillen

| Paket (slug) | Typ | Använd när | Steg |
| --- | --- | --- | --- |
| `fran-behov-till-validerad-produkt` | workflow | Huvudflödet. En produktidé, digital tjänst eller SaaS ska utvecklas strukturerat. | 1 Förstå behovet, 2 Välj målgrupp och köpare, 3 Formulera produktlöftet, 4 Utforska produktspåret, 5 Rita kärnflödet, 6 Avgränsa MVP:n, 7 Pröva affärsmodellen, 8 Planera produktvalideringen, 9 Lär och prioritera nästa version |

Stegens namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellen.

Arbetsflödets egen introduktion (`get_package`) säger att AI:n ska styra processen men att användaren äger verklighetsbilden och besluten, återanvända det som redan sagts, fråga en sak i taget, ge två eller tre alternativ med en rekommendation, markera skillnaden mellan fakta, antaganden och rekommendationer och aldrig hitta på data. Skillen följer samma principer och lägger till de uttryckliga bygg-eller-inte-grindarna.

## Så använder du det

1. **Starta där användaren är.** Har användaren kommit långt: gå till det steg som passar. Små uppgifter behöver ingen mall alls.
2. `get_package` ger introduktionen, `list_package_prompts` stegen i ordning. Vid ett steg: `get_template` med stegets id. Du kan också söka med `search_templates` och allmänna ord, till exempel "MVP validering".
3. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt, med användarens underlag som bara du ser.
4. Mallen är stöd. Skillens regler gäller före mallens: fråga inte om sådant som redan framgår, hitta aldrig på data och säg "bygg inte" när skälen finns.
5. Gör som mest ett uppslag per steg.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketet och stegen ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
