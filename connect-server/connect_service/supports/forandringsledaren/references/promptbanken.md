# Promptbanken Open: arbetsflöden för förändringsledning

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens text, organisation, personal, dokument, namn eller andra uppgifter till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Paket som hör till skillen

| Paket (slug) | Typ | Använd när | Innehåll |
| --- | --- | --- | --- |
| `forandringsledning` | collection | Huvudstödet. Välj enskilda mallar per fas. | Införandeplan, Intressentkarta, Pilotdesign, Pilot eller skarp drift?, Förankringsplan, Risk inför driftsättning |
| `behov-till-effekt` | workflow | Förändringen utgår från ett behov, och ni vill gå hela vägen till genomförbarhet, införande och effektuppföljning. | 1 Förstå behovet, 2 Beskriv nuläge och målbild, 3 Utforma förändringen, 4 Gör förändringen genomförbar, 5 Planera införandet, 6 Bestäm hur effekten ska följas upp |

## Mallar per fas

| Fas | Mall (titel) | Paket |
| --- | --- | --- |
| 2 Berörda | Intressentkarta | `forandringsledning` |
| 4 Ansvar, 5 Risker | Gör förändringen genomförbar | `behov-till-effekt` |
| 6 Förankring | Förankringsplan | `forandringsledning` |
| 7 Pilot eller skarp drift | Pilot eller skarp drift?, Pilotdesign | `forandringsledning` |
| 8 Införande | Införandeplan, Planera införandet, Risk inför driftsättning | `forandringsledning`, `behov-till-effekt` |
| 9 Uppföljning | Bestäm hur effekten ska följas upp, Utvärdera och justera | `behov-till-effekt` (Utvärdera och justera finns även i `processer` och `data-till-forbattring`) |

Mottagarkapacitet (fas 3) har ingen egen mall i katalogen. Den görs med skillens egen metod och `assets/mottagarkapacitet.md`.

Stegens och mallarnas namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellerna.

## Så använder du dem

1. Välj utifrån uppgiften. Liten uppgift: ingen mall behövs. Annars hämta bara mallen för den fas ni är i.
2. `get_package` ger introduktionen, `list_package_prompts` stegen. Vid ett steg: `get_template` med stegets id. Du kan också söka med `search_templates` och allmänna ord, till exempel "pilot införande".
3. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt.
4. Mallen är stöd. Skillens regler (mottagarkapacitet, utsagt ansvar, pilot med beslutspunkt) gäller före mallens.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketen och mallarna ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
