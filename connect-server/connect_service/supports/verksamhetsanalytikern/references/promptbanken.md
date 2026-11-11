# Promptbanken Open: arbetsflöden för verksamhetsanalys

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md` och skriptet `scripts/profilera.mjs`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens data, tabeller, siffror, namn, ärenden eller dokument till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens data stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Arbetsflöden som hör till skillen

| Paket (slug) | Typ | Använd när | Steg |
| --- | --- | --- | --- |
| `data-till-forbattring` | workflow | Huvudflödet. Verksamhetsdata ska bli hypoteser, test och uppföljning. | 1 Avgränsa analysfrågan, 2 Granska datans kvalitet, 3 Hitta mönster och avvikelser, 4 Formulera prövbara hypoteser, 5 Utforma ett förbättringstest, 6 Bestäm hur effekten ska följas upp, 7 Utvärdera när det finns utfallsdata |
| `ekonomisk-uppfoljning` | collection | Ekonomiskt utfall, prognos eller avvikelser ska analyseras eller rapporteras. | Analysera budgetutfall och prognos, Skriv en avvikelsekommentar, Förklara ekonomiläget för ledningsgruppen |
| `fran-ide-till-beslutsbart-business-case` | workflow | Bara när en investering eller förändring ska prövas ekonomiskt. | 1 Lås beslutet och jämförelsealternativen, 2 Skilj fakta från antaganden, 3 Bygg kostnads- och nyttobilden, 4 Stressa business caset, 5 Värdera nytta, risk och osäkerhet, 6 Skapa beslutsbart business case |

Stegens namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellen.

## Så använder du dem

1. **Välj utifrån uppgiften.** Liten fråga: ingen mall behövs. Data till förbättring: `data-till-forbattring`. Ekonomiskt utfall: `ekonomisk-uppfoljning`. Investeringsbeslut: `fran-ide-till-beslutsbart-business-case`.
2. `get_package` ger introduktionen, `list_package_prompts` stegen. Vid ett steg: `get_template` med stegets id. Du kan också söka med `search_templates` och allmänna ord, till exempel "datakvalitet analysfråga".
3. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt, med användarens data som bara du ser.
4. Mallen är stöd. Skillens regler (kvalitetsstopp, tal från beräkning, observation skild från orsak) gäller före mallens.
5. Ber en mall om en beräkning du inte kan köra: räkna steg för steg och märk "handräknad", eller be användaren verifiera.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketen och stegen ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
