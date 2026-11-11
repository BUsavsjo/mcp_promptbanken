# Promptbanken Open: paket och mallar för workshops

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens deltagare, ämne, anteckningar, namn eller dokument till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Paketet som hör till skillen

| Paket (slug) | Typ | Innehåll |
| --- | --- | --- |
| `workshop-och-facilitering` | collection | Workshopplaneraren, Hitta rätt workshopövning, Facilitatorn, Rädda workshopen, Från workshop till nästa steg, Reflektionsfrågor, Samtalskompas, Diskussionsfrågor |

Det är åtta mallar. Välj enskilda mallar för det steg ni är i, inte hela samlingen.

| Steg i skillen | Mall (titel) |
| --- | --- |
| Planera | Workshopplaneraren |
| Hitta övning | Hitta rätt workshopövning |
| Facilitatorstöd | Facilitatorn |
| Rädda | Rädda workshopen |
| Följ upp | Från workshop till nästa steg |
| Frågor och samtalsstöd | Reflektionsfrågor, Diskussionsfrågor, Samtalskompas |

Mallarna *Workshopplaneraren*, *Facilitatorn* och *Från workshop till nästa steg* finns även i paketet `processledarens-verktygslada`.

Namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellerna.

## Så använder du dem

1. Välj utifrån uppgiften. En liten fråga behöver ingen mall.
2. `list_package_prompts` med `workshop-och-facilitering` visar mallarna. Vid ett steg: `get_template` med mallens id. Du kan också söka med `search_templates` och allmänna ord, till exempel "workshop övningar".
3. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt.
4. **Skillens frågelogik gäller före mallens.** *Workshopplaneraren* kräver idag fyra fasta frågor i fast ordning och ett första svar med bara fråga 1. *Rädda workshopen* kräver att första svaret bara frågar vad som händer. Hoppa över det när användaren redan har svarat. Använd mallarna för innehållet (upplägg, övningar, struktur), inte för frågeordningen.
5. Gör som mest ett uppslag per steg.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketet och mallarna ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
