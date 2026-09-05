# Promptbanken Connect

Detta är en fristående startpunkt för Promptbanken Connect. Den ligger avsiktligt
utanför `mcp-server/`, som innehåller Promptbanken Open 1.2.2 under granskning.

## Vad som fungerar i denna första leverans

- MCP-resursmetadata på `/.well-known/oauth-protected-resource/mcp`.
- Bearer-token krävs för `POST /mcp` och felaktiga eller saknade tokens får en
  OAuth-utmaning med rätt resurs-URL.
- `get_connect_context` returnerar den verifierade användaridentiteten.
- `list_my_library` listar den inloggade användarens aktiva privata poster i
  Valvet. `list_shared_workspace_prompts` listar aktiva delade poster i de
  arbetsytor användaren är medlem i. `get_connect_item` hämtar en specifik
  RLS-synlig post.
- Samtliga dataanrop går till Supabase med anroparens OAuth-token och en
  publishable key. Connect använder aldrig service-nyckel och skriver inte.
- Driftverifieraren använder Supabase JWKS och kräver signatur, utgivare,
  målgrupp, utgångstid och användaridentitet.
- `GET /healthz` är öppen för driftkontroll. Övriga MCP-anrop kräver Bearer-
  token.

## Lokal kontroll

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

För att köra tjänsten krävs följande miljövariabler. Lägg dem i den lokala
miljön, aldrig i Git:

| Variabel | Innehåll |
| --- | --- |
| `CONNECT_RESOURCE_URL` | Den publika URL:en för Connects `/mcp`, till exempel `https://connect.promptbanken.se/mcp`. |
| `CONNECT_SUPABASE_PUBLISHABLE_KEY` | Projektets publishable key för RLS-skyddade REST-läsningar. Det är inte en service-nyckel. |
| `CONNECT_AUTHORIZATION_SERVER` | Valfri override för OAuth-serverns issuer. Standard är Promptbankens verifierade issuer. |
| `CONNECT_TOKEN_ISSUER` | Valfri override för tokenens issuer. |
| `CONNECT_TOKEN_AUDIENCE` | Valfri override för tokenens målgrupp. Supabases standard är `authenticated`. |
| `CONNECT_JWKS_URL` | Valfri override för OAuth-serverns JWKS-endpoint. |

Starta därefter med `python -m connect_service`.

Se `.env.example` för kompletta konfigurationsvärden. Kör lokalt med
`docker-compose up --build` eller `python -m connect_service`.

## Kvar före första riktiga anslutning

1. Lägg Connect på sin egen host och proxyregel: `connect.promptbanken.se` →
   denna container på `127.0.0.1:8010`. Open-routen ändras inte.
2. Genomför en riktig authorization-code-med-PKCE-runda från en MCP-klient.
3. Kontrollera i OAuth Apps att den registrerade klienten, dess redirect-URL
   och samtyckesinformationen är korrekta. Avvisa okända appar.
4. Följ upp dynamiskt registrerade appar regelbundet. OAuth-scopes styr bara
   OIDC-information; RLS är fortsatt dataskyddet.
5. Planera skrivverktyg som en separat fas med idempotens, tydliga
   användarbekräftelser och ändringslogg.
