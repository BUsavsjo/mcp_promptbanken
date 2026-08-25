# Claude Connectors Directory — ansökan

Motsvarigheten till `chatgpt-app-submission.json`, fast för Anthropic. Claude
har ingen JSON-fil att ladda upp: allt matas in i ett webbformulär i
`https://claude.ai/admin-settings/directory/submissions/new`. Den här filen är
därför ett svarsark — varje portalsteg med färdig text att klistra in.

Källor: `https://claude.com/docs/connectors/building/submission`,
`https://claude.com/docs/connectors/building/review-criteria`,
`https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy`
(lästa 2026-08-25).

## Förutsättning som måste lösas först

Portalen ligger under organisationsinställningarna på claude.ai. Den kräver
**Team- eller Enterprise-organisation** — individuella planer (Pro, Max) har
inte de inställningarna alls. Bara Owner/Primary owner får skicka in.

Utan en sådan organisation går ansökan inte att påbörja. Det finns ingen
alternativ väg för remote MCP; desktop extensions (MCPB) har ett eget
formulär, men vår server är hostad, inte lokal.

## Vad som redan uppfyller kraven

Verifierat mot live-servern 2026-08-25 (`tools/list` på
`https://mcp.promptbanken.se/mcp`):

- Nio publika verktyg, samtliga med `annotations.title`, `readOnlyHint: true`,
  `destructiveHint: false`, `openWorldHint: false`. Anthropics vanligaste
  avslagsorsak är just saknade annotations.
- Inget verktygsnamn över 64 tecken.
- Ingen katch-all `api_request` med `method`-parameter — läs och skrivning är
  helt separerade, och skrivytan finns inte på det publika `/mcp`.
- HTTPS, streamable HTTP på `/mcp`, SSE på `/sse`. Samma URL för alla
  användare.
- Egen förstahands-API (Supabase-databasen är vår), serverdomänen matchar
  tjänsten.
- Publicerad integritetspolicy på HTTPS: `privacy-mcp-en.html`, med
  verktyg-för-verktyg-tabellen som OpenAI-granskningen krävde.
- Ingen av de förbjudna kategorierna: inga finansiella transaktioner, ingen
  AI-genererad media, ingen annonsering, ingen läsning av Claudes minne,
  chatthistorik eller användarfiler.

## Steg 2 — Connection

| Fält | Svar |
| --- | --- |
| Server URL | `https://mcp.promptbanken.se/mcp` |
| Transport | Streamable HTTP |
| Samma URL för alla användare? | Ja |

`/sse` finns kvar som bakåtkompatibel yta med exakt samma nio verktyg, men
ange `/mcp` i portalen.

## Steg 3 — Tools

Synkas automatiskt från servern. Alla nio hamnar i read-only-gruppen. Inget
att fylla i, men kontrollera att listan visar exakt dessa och inga fler:

`health_check`, `get_client_routing_instructions`, `list_templates`,
`search_templates`, `get_template`, `list_packages`, `get_package`,
`list_package_prompts`, `recommend_packages`.

Syns ett legacy-verktyg (`list_skills`, `check_input_risk`, `get_skill`,
`route_skill`, `compile_skill_prompt`) har hosted-gaten släppt — avbryt och
rätta servern före inskick.

## Steg 4 — Listing

**Server name** (max 100 tecken):

```
Promptbanken
```

**Tagline** (max 55 tecken):

```
Swedish-language prompt templates for public sector
```

**Description** (max 2 000 tecken):

```
Promptbanken is an open, curated library of ready-to-use prompt templates written for Swedish public-sector work — municipalities, schools, and the organisations around them — and equally usable by companies, associations, and individuals.

Describe a task and the connector finds the matching template, returns its full text, and hands it back for you to fill in locally. Templates are grouped into packages: collections you pick from, and workflows that run as ordered steps from a blank page to a finished result. A role word maps to the package areas that fit that role.

The connector is open and read-only. No account, no sign-in, no key. It publishes nine tools, all of them reads. No write tool exists on this surface, so it cannot store anything.

It receives only what its own parameters define: a search term, a role word, a filter, or the id or slug of a catalogue entry. Case material, documents, and personal data stay in the client and never reach the server. Search terms are not stored — only the length of a query is counted in anonymous usage statistics.

The catalogue content is Swedish, and search and role matching work in Swedish. Tool descriptions and this listing are in English.
```

**Categories** (1–5, exakta namn väljs i portalens lista): Productivity som
förstahandsval; lägg till Education och Writing om de finns.

**Documentation URL**: `https://app.promptbanken.se/mcp.html`
— se gap 2 nedan, sidan är svensk.

**Privacy policy URL**: `https://app.promptbanken.se/privacy-mcp-en.html`

**Support contact**: `https://app.promptbanken.se/support.html`

**Icon**: `promptbanken/docs/bilder/brand/promptbanken-icon-512.png`
(512×512 PNG, kvadratisk).

**URL slug**: `promptbanken` — **permanent efter publicering**, går inte att
ändra sedan.

## Steg 5 — Use cases

**Primary use cases:**

```
1. Finding a prompt for a task at hand. The user describes what they need to write or decide, and the connector returns matching templates from the catalogue, then the full text of the one they pick.

2. Running a guided workflow. A workflow package is an ordered set of steps; the connector returns the steps in order and the full text of each step as it is started.

3. Getting oriented by professional role. A role word returns the package areas written for that role, so a new user sees what is relevant to them without browsing the whole catalogue.
```

**What users need before connecting:**

```
Nothing. The connector is open and requires no account, plan, or key. The web application at app.promptbanken.se offers accounts for saving your own prompts, but nothing on the published connector surface uses them.
```

**Reads, writes, or both:** Reads only.

## Steg 6 — Company

Namn och webbplats för den organisation som äger listningen, plus
kontaktperson för granskningen (förifylld från kontot).

**Beslut som saknas:** listningen ska stå i samma namn som claude.ai-organisationen.
Se gap 3.

Website: `https://app.promptbanken.se`

## Steg 7 — Authentication

Välj **no authentication**. Servern kräver ingen inloggning på den publicerade
ytan, och inget enskilt verktyg ber om autentisering i efterhand.

MCP-nyckeln som Free- och Pro-planerna använder går mot `/mcp/key`, en annan
sökväg som inte ingår i den här listningen. Nämn den inte i portalen — den
skulle bara läsas som att listningen har en dold autentiseringsväg.

## Steg 8 — Data handling

| Fråga | Svar |
| --- | --- |
| API:ets ursprung | Vårt eget förstahands-API |
| Personliga hälsodata | Nej |
| Sponsrat innehåll | Nej |

Databasen ligger i Supabase, EU (Sverige). Det står redan i
`privacy-mcp-en.html`.

## Steg 9 — Test & launch

**Test account setup:**

```
No test account is needed. The connector is open and unauthenticated. Add it as a custom connector with the URL https://mcp.promptbanken.se/mcp — no key, no OAuth, no sign-up step — and every tool is immediately callable. The catalogue is fully populated in production: 66 published templates and 17 packages, which is the same data every user sees.
```

**Testprompter** (samma verifierade fall som OpenAI-ansökan; katalogen är
svensk, så prompterna är svenska):

1. `Hitta en mall i Promptbanken för ett informationsutskick om en förändring i skolan.`
   → `search_templates`, sedan `get_template`. Ger publika sammanfattningar
   inklusive "Skapa informationsutskick"; sammanfattningar bär aldrig
   prompttext, `get_template` ger full `prompt_text`, taggar och risknivå.

2. `Jag är chef. Vilka paket i Promptbanken passar min roll?`
   → `recommend_packages`. `role_recognized: true`, `matched_role: "chef"`,
   fyra områden. En okänd roll ger avsiktligt alla paket med
   `role_recognized: false`, inte ett tomt svar.

3. `Vilka arbetsflöden finns i Promptbanken?`
   → `list_packages` med `package_type="workflow"`. Just nu exakt ett:
   Superplanläge (`superplanlage`).

4. `Visa hur Superplanläge fungerar och vilka steg som ingår.`
   → `get_package`, sedan `list_package_prompts`. Fyra steg i sorteringsordning.

5. `Hitta en Promptbanken-mall som hjälper mig göra om detaljerade systemkrav till funktionskrav inför en upphandling.`
   → `search_templates`, sedan `get_template`.

Portalen kräver också en bekräftelse på att alla verktyg körts själv, via MCP
Inspector eller som custom connector i Claude. Gör den rundan innan inskick
och notera datum här.

## Steg 10 — Compliance

Sju obligatoriska bekräftelser. Vår position på var och en:

| Bekräftelse | Läge |
| --- | --- |
| Directory guidelines | Uppfyllt |
| First-party API usage | Uppfyllt — egen databas, egen domän |
| Financial transactions | Ingen |
| AI media generation | Ingen |
| Prompt injection | Se risk 1 nedan |
| Conversation data collection | Ingen — bara frågelängd i anonym statistik |
| Public documentation | Se gap 2 |

## Risker och gap

### Risk 1 — `get_client_routing_instructions` mot prompt injection-regeln

Anthropic avvisar verktygsbeskrivningar som "direct Claude to pull behavioural
instructions from external sources". Verktyget hämtar per definition en
bootstrap som säger vilket verktyg klienten ska nå efter i vilket läge.

Vår tolkning: regeln träffar *beskrivningar* som styr modellens beteende
utanför verktygets funktion. Här är routningen verktygets funktion, den
deklareras öppet, och den innehåller ingen instruktion som rör något utanför
Promptbanken — tvärtom är dess kärna en integritetsregel som *begränsar* vad
klienten skickar.

Gör inför inskick: läs igenom nyttolasten en gång till och se till att inget
fält formulerar sig som en order till modellen om annat än den här
konnektorn. Blir verktyget ändå flaggat är den billiga rättningen att göra om
svaret till ren beskrivande text om katalogen i stället för imperativ.

### Gap 2 — dokumentationen är svensk

`mcp.html` är på svenska. Anthropic vill ha dokumentation som låter en
granskare testa konnektorn på tio minuter utan förkunskap om produkten, och
granskaren läser engelska. Sidan har visserligen ett eget Claude-avsnitt, men
en granskare som inte kan svenska kommer inte igenom den.

Förslag: en engelsk sida `mcp-en.html` med serveradress, de fem testprompterna
och en kort katalogbeskrivning. Räcker gott — kravet är uppfyllt av ett
blogginlägg eller en hjälpartikel.

### Gap 3 — vem äger listningen

Company-steget vill ha organisationsnamn, och det bör matcha
claude.ai-organisationen som skickar in. Samma öppna fråga som
licensdiskussionen: privatperson eller arbetsgivare. Måste avgöras innan
inskick, inte efter — listningen är publik.

### Gap 4 — Directory Terms

`https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms`
måste läsas och accepteras. För MCPB finns icke-förhandlingsbara
öppen källkod-klausuler; för remote MCP gäller de inte, men läs villkoren
innan du klickar.

## Efter inskick

Status och granskarens återkoppling syns i
`https://claude.ai/admin-settings/directory/submissions`. Eskalering:
`mcp-review@anthropic.com`.

En inskickad server skannas för policyefterlevnad och listas normalt som
**community connector**. Anthropic kan senare lyfta listningen till
**verified review**, där varje verktyg funktionstestas. Det sker automatiskt
och kräver ingen åtgärd av oss.
