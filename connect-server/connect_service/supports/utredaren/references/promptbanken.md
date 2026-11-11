# Promptbanken Open: arbetsflöden för utredning

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens text, dokument, frågeställning i detalj, siffror, namn, ärenden eller andra uppgifter till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Arbetsflöden som hör till skillen

| Paket (slug) | Typ | Använd när | Steg |
| --- | --- | --- | --- |
| `fran-fraga-till-researchunderlag` | workflow | Fas 1–5. Frågan kräver källor, källvärdering och syntes. | 1 Avgränsa researchfrågan, 2 Planera researchen, 3 Samla underlag, 4 Värdera källorna, 5 Jämför och syntetisera, 6 Bedöm osäkerhet och kunskapsluckor, 7 Skapa spårbart researchunderlag |
| `fran-forslag-till-konsekvensanalys` | workflow | Fas 6. Ett förslag eller en förändring ska prövas mot nollalternativ, berörda och följdeffekter. | 1 Lås beslutet och nollalternativet, 2 Kartlägg berörda och perspektiv, 3 Analysera konsekvenser, 4 Pröva princip och följdeffekter, 5 Värdera risker och kunskapsluckor, 6 Sammanställ konsekvensanalysen |
| `beslutsberedning` | collection | Fas 7 och efter. Verktygslåda: Beslutsmognad, Saknade delar i underlag, Risk- och konsekvensanalys, Alternativanalys, Beslutsunderlag, Förslag till beslut, Genomförandeplan efter beslut. | Välj enskilda mallar, inte hela samlingen |

Stegens namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellen.

## Så använder du dem

1. **Välj utifrån uppgiften.** Smal fråga: ingen mall behövs. Fråga som kräver källor: `fran-fraga-till-researchunderlag`. Förslag som ska prövas: `fran-forslag-till-konsekvensanalys`. Underlag för ett organ: välj enskilda mallar ur `beslutsberedning`.
2. `get_package` ger introduktionen, `list_package_prompts` stegen i ordning.
3. Vid ett steg: `get_template` med stegets id.
4. **Servern renderar aldrig en färdig prompt.** Du får text, parametrar och standardvärden och fyller i själv, lokalt.
5. Mallen är stöd. Evidensloggen, de fyra beteckningarna och förbudet mot påhittade källor gäller före mallens format. Ber en mall om något du inte kan göra (till exempel att söka på nätet utan verktyg): säg det i stället för att låtsas.
6. **Mallar med rekommendation eller beslutsformulering**, till exempel Beslutsunderlag och Förslag till beslut ur `beslutsberedning`: regel 4 i SKILL.md går före. Fyll i fälten bara om användaren ber om ett förslag, märk dem **Bedömning**, håll dem åtskilda från fynden och skriv aldrig beslutsformuleringen som om beslutet redan var fattat.

## Hitta mer

`search_templates` med allmänna ord, till exempel "konsekvensanalys förslag" eller "källvärdering". Skicka inte `role` när uppgiften är tydlig.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketen och stegen ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
