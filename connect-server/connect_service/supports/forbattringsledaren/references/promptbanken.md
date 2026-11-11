# Promptbanken Open: arbetsflöden för förbättringsarbete

Den här filen beskriver hur skillen kan använda Promptbankens öppna katalog. Allt här är valfritt. Skillen fungerar fullt ut med `references/metod.md`.

Katalogen är öppen, gratis och kräver ingen inloggning. Den nås med verktygen `search_templates`, `list_packages`, `get_package`, `list_package_prompts` och `get_template`, till exempel via en MCP-koppling till Promptbanken Open eller via Promptbanken-pluginet.

## Sekretess: det här skickar du aldrig

Skicka aldrig användarens text, dokument, siffror, namn, ärenden eller andra uppgifter till katalogens verktyg. Sök med några allmänna ord om typen av uppgift. Användarens underlag stannar i samtalet. Mallar läses och fylls i lokalt av dig.

## Arbetsflöden som hör till skillen

| Paket (slug) | Typ | Använd när | Steg |
| --- | --- | --- | --- |
| `forbattringside-till-synlig-effekt` | workflow | Huvudflödet. Ett avgränsat problem ska bli en synlig förbättring. | 1 Avgränsa förbättringsproblemet, 2 Formulera förbättringsmål, 3 Kartlägg orsaker, 4 Bestäm mätning och baslinje, 5 Välj förändringsidé och hypotes, 6 Planera PGSA-test, 7 Dokumentera och studera utfallet, 8 Agera och välj nästa väg, 9 Sammanfatta förbättringsresan, 10 Välj hur resultatet ska användas |
| `forsta-komplext-problem` | workflow | Fas 0. Problemet har flera orsaker, aktörer och beroenden. | Avgränsa problemet, Se vad som påverkar problemet, Hitta vad som håller problemet kvar, Hitta var förändring kan göra skillnad, Välj nästa väg |
| `behov-till-effekt` | workflow | Användaren utgår från ett behov eller en tänkt lösning, eller förändringen behöver planeras för införande och effektuppföljning. | Förstå behovet, Beskriv nuläge och målbild, Utforma förändringen, Gör förändringen genomförbar, Planera införandet, Bestäm hur effekten ska följas upp |

Stegens namn kan ändras när katalogen uppdateras. Slå alltid upp aktuell lista med `list_package_prompts` i stället för att lita på tabellen.

### Skillens faser och huvudpaketets steg

Huvudpaketet `forbattringside-till-synlig-effekt` har tio steg och skillen åtta faser (plus fas 0). Använd den här mappningen när du hämtar stöd för en fas:

| Fas i skillen | Steg i huvudpaketet |
| --- | --- |
| 0 Förstå ett komplext problem | Använd paketet `forsta-komplext-problem` |
| 1 Avgränsa problemet | 1 Avgränsa förbättringsproblemet |
| 2 Mål och mått | 2 Formulera förbättringsmål och 4 Bestäm mätning och baslinje |
| 3 Orsaker | 3 Kartlägg orsaker |
| 4 Förändringsidé och hypotes | 5 Välj förändringsidé och hypotes |
| 5 Planera ett litet test | 6 Planera PGSA-test |
| 6 Studera utfallet | 7 Dokumentera och studera utfallet |
| 7 Agera | 8 Agera och välj nästa väg |
| 8 Förbättringskort | 9 Sammanfatta förbättringsresan och 10 Välj hur resultatet ska användas |

Paketet tar mätning och baslinje efter orsaksanalysen. Skillen tar den i fas 2, före orsakerna, eftersom baslinjen ska vara känd innan något ändras. Skillens ordning gäller.

## Så använder du dem

1. **Välj arbetsflöde utifrån uppgiften**, inte utifrån rollen. Liten uppgift: använd inget paket alls, `references/metod.md` räcker. Medel: `forbattringside-till-synlig-effekt`. Komplext: börja med `forsta-komplext-problem`. Utgår användaren från ett behov eller en färdig idé: `behov-till-effekt`.
2. `get_package` med paketets slug ger introduktionen. `list_package_prompts` ger stegen i ordning.
3. När ni når ett steg: `get_template` med stegets id.
4. **Servern renderar aldrig en färdig prompt.** Du får `prompt_text`, parametrar och standardvärden. Du fyller i, tolkar och sammanfogar själv, lokalt, med användarens uppgifter som bara du ser.
5. Använd mallen som stöd för att fråga rätt och sortera. Resultatet följer skillens regler och leveranser, inte mallens format.

## Hitta mer

`search_templates` med allmänna ord, till exempel "mätning baslinje" eller "orsaksanalys fiskben". Skicka inte `role` om uppgiften redan är tydlig.

## Om verktygen saknas eller inte svarar

Fortsätt med `references/metod.md`. Nämn det inte som ett problem, be inte användaren installera något och påstå aldrig att du har hämtat en mall som du inte hämtat.

## Kontrollerad mot katalogen

Paketen och stegen ovan är kontrollerade mot Promptbankens öppna katalog (`mcp.promptbanken.se`) i oktober 2026.
