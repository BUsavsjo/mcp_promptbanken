# Valvet: förtydliga status "draft" i MCP-ytan

## Syfte

Testfynd (P0-1, "Förtydliga draft i Valvet") konstaterade att `save_my_item`
sparar nya Valvet-poster med `status: 'draft'`, och att ordet kan misstolkas
som att posten inte är sparad eller inte syns — trots att den redan är
fullt sparad, sökbar och privat. Denna spec adresserar **bara MCP-ytan**
(tool-beskrivningar, JSON-svar, README/CLAUDE.md-dokumentation i
`mcp_promptbanken`-repot) — alltså det AI-klienter (Claude, ChatGPT m.fl.)
läser och kan relä vidare till användaren i chatten.

Uttryckligen **inte** i scope (andra ytor med samma bakomliggande
`content_items.status`-fält, men annan kod/repo):
- `promptbanken/admin.html` kommun-modulens "Utkast"-statuspills — annan
  modul (`module='kommun'`), annan skrivväg, inte `save_my_item`.
- `valvet_promptbanken`-webappen — visar idag ingen statustext alls i
  `renderItemRow()`, så det finns inget att förtydliga där ännu.

## Bakgrund

Genomgång av kod (2026-07-18) visade tre konkreta problem, alla i
`mcp_promptbanken/mcp-server/server/mcp_server.py`:

1. **Ingen förklaring i svaret.** `save_my_item`/`list_my_items`/
   `get_my_item` returnerar raden rakt av (inkl. `status`) utan någon
   förklarande text. En AI-klient som läser `"status": "draft"` har inget
   att gå på förutom ordet självt.
2. **Missvisande enum.** Det hostade JSON-RPC-schemat för `list_my_items`
   (rad ~1262) exponerar `status`-filtret som
   `enum: ["draft", "review", "published", "archived"]`. Men
   `update_my_item` har inget `status`-argument alls (varken i schemat
   eller i `vault.update_item()`), och webbappen
   (`valvet_promptbanken/src/vault.js`) sätter bara `'draft'` vid skapande
   och `'draft'` vid återställning — aldrig `'review'`/`'published'`.
   De två värdena är alltså tekniskt närvarande i databasens enum men
   funktionellt oåtkomliga för Valvet i Fas 1. Att lista dem som giltiga
   filter antyder ett arbetsflöde som inte finns.
3. **Status och synlighet sammanblandas implicit.** Valvet-poster har
   ingen egen `visibility`-kolumn eller motsvarande koncept — till skillnad
   från kommun-modulen är de **alltid** privata till den ägande nyckeln,
   oavsett status. Det står ingenstans uttryckligen, vilket gör det lätt
   att anta att `draft` (eller någon annan status) styr vem som ser posten.

Servern har två parallella verktygsdefinitioner för samma tools — en
uppsättning `@mcp.tool()`-dekorerade funktioner med docstrings (läses av
lokala stdio-klienter) och en manuell JSON-RPC-lista med egna
`description`/`inputSchema`-fält (läses av hostade HTTP-klienter). Detta
är befintligt mönster i filen (redan duplicerat för alla verktyg), inte
något denna spec ändrar på — båda kopiorna uppdateras i synk.

## Ändringar

### `mcp-server/server/mcp_server.py`

**Lokala docstrings** (oförändrad funktionssignatur, bara texten):

- `list_my_items` (~rad 527-529): lägg till en mening om att poster är
  privata och sparade oavsett status.
- `save_my_item` (~rad 1793-1796): lägg till en mening om att `draft` bara
  beskriver redigeringsläge — posten är fullt sparad och privat direkt.

**Hostade JSON-RPC tool-definitioner** (`_tool_definitions()`):

- `list_my_items` (~rad 1251-1266):
  - `description` får samma förtydligande som ovan.
  - `inputSchema.properties.status.enum` smalnas av till
    `["draft", "archived"]`.
  - Ny `description` på `status`-fältet: att `review`/`published` finns i
    databasens enum men är reserverade för ett framtida
    gransknings-/publiceringsflöde och inte går att sätta via Valvets
    MCP-verktyg idag.
- `save_my_item` (~rad 1313-1317): `description` får samma förtydligande
  som den lokala docstringen.

Alla texttillägg skrivs på engelska, i linje med befintlig språkkonvention
för verktygsbeskrivningar i denna fil (dokumentation i README/CLAUDE.md
förblir svensk).

Inga ändringar i `vault.py`, RPC-anropen, eller databasens enum —
`review`/`published` tas inte bort ur `content_item_status`-typen (ägs av
`promptbanken`-repot), bara ur det som Valvets MCP-schema annonserar som
giltiga filtervärden. RPC-lagret validerar inte `status`-parametern mot
enumen (den används bara i ett `WHERE status = p_status`-villkor om satt),
så avsmalningen ändrar inget serverbeteende — bara vad en klient
informeras om att den får skicka.

### `README.md`

Ny underrubrik "Status" i Valvet-avsnittet (efter befintlig verktygslista,
~rad 121):

- `draft` (standard vid skapande) och `archived` beskrivs som de enda
  aktiva/nåbara statusarna i Fas 1.
- Explicit mening: posten är fullt sparad och privat till nyckelns ägare
  omedelbart vid `save_my_item` — `draft` uttrycker bara redigeringsläge,
  inte om posten finns eller vem som ser den.
- `review`/`published` nämns som reserverade databasvärden, inte
  exponerade av något Valvet-verktyg (webb eller MCP) i Fas 1.

### `CLAUDE.md`

En mening tillagd i det befintliga "Write: Valvet"-avsnittet som pekar
till samma statuskonvention, så framtida ändringar i detta repo inte
råkar återinföra `review`/`published` som skenbart giltiga utan att först
bygga stöd för dem i `update_my_item`.

## Testplan

Manuell verifiering (inga automatiserade tester i repot):

1. `tools/list` över `/mcp` (hostat läge) — bekräfta att `list_my_items`s
   `status`-enum bara innehåller `draft`/`archived`, och att båda
   `description`-fälten (verktyg + status-property) innehåller den nya
   förklarande texten.
2. `npm run dev` (lokalt stdio-läge) — bekräfta att `list_my_items`/
   `save_my_item`s docstrings (synliga via klientens verktygsintrospektion,
   t.ex. Claude Desktops verktygsvy) innehåller samma förklaring.
3. Anropa `save_my_item` mot staging, bekräfta att svaret fortfarande
   innehåller `status: "draft"` oförändrat (ingen fältstruktur ändras,
   bara beskrivningstexter/enum i schemat).
4. Läs igenom README.md/CLAUDE.md-diffen för att bekräfta konsekvent
   terminologi mot koden.

## Dokumentation

`TODO.md` får en ny post under "Klart" när ändringen är verifierad, med
hänvisning till denna spec.
