# Promptbanken Open: arbetsflöde för möten

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens anteckningar, transkribering, namn, ärenden, beslut eller dokument till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Arbetsflöde som hör till skillen

| Paket (slug) | Typ | Använd när | Steg |
| --- | --- | --- | --- |
| `fran-mote-till-genomforande` | workflow | Huvudflödet. Kan starta både före och efter mötet. | 1 Lås mötets resultat, 2 Bygg agendan, 3 Sortera råa mötesanteckningar (valfritt), 4 Verifiera beslut, uppdrag och öppna frågor (kärnsteget), 5 Gör beslut och uppdrag handlingsbara, 6 Planera kommunikationen, 7 Skapa genomförandekortet, 8 Följ upp genomförandet |

Stegens namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellen.

## Så använder du det

1. **Starta där användaren är.** Finns anteckningar: gå direkt till steg 3 eller 4. Ska mötet hållas: steg 1–2. Små uppgifter behöver ingen mall alls.
2. `get_package` med `fran-mote-till-genomforande` ger introduktionen, `list_package_prompts` stegen i ordning. Vid ett steg: `get_template` med stegets id. Du kan också söka med `search_templates` och allmänna ord, till exempel "mötesanteckningar beslut".
3. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt, med användarens underlag som bara du ser.
4. Mallen är stöd. Skillens regler gäller före mallens: fråga inte om sådant som redan framgår, och förväxla aldrig förslag, uppdrag och beslut. Ber en mall om något som strider mot det: följ skillen.
5. Gör som mest ett uppslag per steg.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketet och stegen ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
