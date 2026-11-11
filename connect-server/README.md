# Promptbanken Connect

Promptbanken Connect är en separat, OAuth-skyddad MCP-anslutning till samma
privata Creator-bibliotek som användaren hanterar på `app.promptbanken.se`.
Den ligger avsiktligt utanför `mcp-server/`, som innehåller Promptbanken Open
1.2.2 under granskning.

## Anslutningsadress

Använd en MCP-klient med OAuth mot:

```text
https://connect.promptbanken.se/mcp
```

Anslutningen öppnar Promptbankens Supabase-samtycke på
`app.promptbanken.se/oauth/consent`. Open har fortsatt sin separata adress och
påverkas inte av Connect.

## Vad Connect kan läsa

Efter inloggning kan AI-klienten:

- bekräfta den anslutna användaren med `get_connect_context`;
- lista Creator-prompter, sparade biblioteks-prompter och paket med
  `list_my_library`;
- hämta en specifik prompt inklusive aktuell text för en levande Open-referens
  med `get_my_library_prompt`;
- lista och hämta användarens paket, med promptarna i deras sparade ordning,
  via `list_my_packages` och `get_my_package`;
- lista egna aktiva eller avslutade delningar med `list_my_shares`.

Connect använder alltid anroparens OAuth-token och Supabases publishable key.
Alla dataläsningar går genom Creator-RPC:er som kontrollerar `auth.uid()`.
Tjänsten har ingen service-rollnyckel och inga skrivverktyg i denna release.

## Arbetslager (vNext, DEV)

Connect DEV levererar Promptbankens nio specialister som metodstöd, plus
användarens arbetsprofil, personliga regler och egna arbetssätt:

- `get_connect_context` returnerar stödindex, profil och regler för val av stöd.
- `get_support(id, resource?)` returnerar metoden kombinerad med personliga regler.
- `get_open_item` läser Open-innehåll med text, som metoderna hänvisar till.
- `save_my_profile` och `save_my_way_of_working` visar förhandsvisning utan
  `confirmed` och sparar med `confirmed: true`.
- `get_my_history` och `restore_my_version` hanterar versioner.

Som standard exponerar Connect bara dessa sju verktyg (`CONNECT_TOOL_PROFILE=core`).
Med `CONNECT_TOOL_PROFILE=full` visas även de 19 Creator-verktygen för
bibliotek, paket och delningar.

Metoderna synkas oförändrade från `promptbanken/agent-skills`:

```powershell
git -C <promptbanken> archive origin/main agent-skills | tar -x -C <tmp>
python scripts/sync_supports.py --source <tmp>/agent-skills --commit <sha>
```

Aktiverings-skill och plugin finns i `plugin/`, och eval-sviten i
`evals/connect_auto_cases.json` (räknas med `scripts/score_evals.py`).
Leverans, avvikelser och rollback beskrivs i `docs/vnext-leverans.md`.

## Lokal kontroll

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall connect_service
```

För att köra tjänsten krävs följande miljövariabler. Lägg dem i den lokala
miljön, aldrig i Git:

| Variabel | Innehåll |
| --- | --- |
| `CONNECT_RESOURCE_URL` | Den publika URL:en för Connects `/mcp`, till exempel `https://connect.promptbanken.se/mcp`. |
| `CONNECT_SUPABASE_PUBLISHABLE_KEY` | Projektets publishable key för RLS-skyddade RPC-läsningar. Det är inte en service-nyckel. |
| `CONNECT_AUTHORIZATION_SERVER` | Valfri override för OAuth-serverns issuer. Standard är Promptbankens verifierade issuer. |
| `CONNECT_TOKEN_ISSUER` | Valfri override för tokenens issuer. |
| `CONNECT_TOKEN_AUDIENCE` | Valfri override för tokenens målgrupp. Supabases standard är `authenticated`. |
| `CONNECT_JWKS_URL` | Valfri override för OAuth-serverns JWKS-endpoint. |
| `CONNECT_TOOL_PROFILE` | `core` (standard, sju verktyg) eller `full` (även Creator-biblioteket). |

Starta därefter med `python -m connect_service` eller `docker-compose up --build`.

## Kvar före första klientanslutningen

1. Genomför en riktig authorization-code-med-PKCE-runda från en MCP-klient och
   kontrollera verktygslistan efter samtycke.
2. Kontrollera OAuth Apps och avvisa okända klienter. Dynamisk registrering
   innebär att användaren alltid ska granska appnamn och redirect-adress på
   samtyckessidan.
3. Nästa produktfas är beta-skrivningar: entitlement per verktyg,
   idempotens och uttrycklig bekräftelse för ändringar och delningar.