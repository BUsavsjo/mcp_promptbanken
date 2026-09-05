# Promptbanken Connect: Creator-bibliotek Design

## Syfte

Promptbanken Connect ska vara den OAuth-skyddade MCP-anslutning där en användares AI arbetar med samma privata bibliotek som användaren ser och förvaltar i Creator på `app.promptbanken.se`. Connect ersätter inte Creator-gränssnittet och skapar ingen separat kopia av innehållet.

Den publika Open-connectorn 1.2.2 ligger utanför detta arbete. Den fortsätter att exponera den granskade, publika katalogen på sin befintliga adress.

## Produktregler

- En enda Connect-adress används av alla abonnemang: `https://connect.promptbanken.se/mcp`.
- Connect Free får läsa användarens bibliotek. Connect Pro får också skapa och förvalta det.
- Under beta får användaren Pro-funktionerna utan betalspärr. Entitlement ska kontrolleras per skrivverktyg, så att beta kan avslutas utan ny MCP-adress eller nytt verktygskontrakt.
- Användaren får bara se och ändra data som Creator redan ger samma användare åtkomst till. OAuth-identiteten och Supabase RLS/RPC:ernas `auth.uid()`-kontroller är auktoritetskällan.
- Connect använder endast OAuth-access-token och Supabases publishable key. Ingen service-rollnyckel får läggas till i tjänsten eller dess driftmiljö.
- Alla skrivoperationer ska vara tydliga för AI-klienten. Radering, återkallad delning och publiceringsnära handlingar kräver en uttrycklig `confirm: true`-parameter i själva verktygsanropet.

## Innehåll som är Mitt bibliotek

| Objekt | Källa i Supabase | Betydelse i Connect |
| --- | --- | --- |
| Egna Creator-prompter | `list_my_creator_prompts()` | Användarens författade prompter i Creator, oavsett om de är utkast, under granskning eller publicerade. |
| Sparade biblioteks-prompter | `list_my_library_prompts()` | Egna Valvet-poster, inklusive levande referenser och egna kopior av publicerat innehåll. |
| Egna paket | `list_my_creator_package_drafts()` och `list_creator_package_draft_items(uuid)` | Paket med ordnade promptposter. En levande paketreferens läses via `get_referenced_library_package(uuid, text[])`. |
| Egna delningar | `list_my_creator_shares()` | Aktiva och avslutade delningar, med typ, etikett, giltighet och användningsstatistik. |

En prompt eller ett paket som tillhör någon annan blir aldrig synligt enbart för att dess id anges i ett verktygsanrop. Ett uteblivet eller tomt svar presenteras som att objektet inte finns eller inte är tillgängligt.

## Arkitektur och dataflöde

1. MCP-klienten registrerar sig hos Supabase OAuth Server och genomför authorization code med PKCE. Användaren samtycker i den befintliga sidan `app.promptbanken.se/oauth/consent`.
2. Klienten skickar access-token till Connect. Connect verifierar signatur, issuer, audience, utgångstid och `sub` mot Supabases JWKS.
3. Connect skickar samma access-token i `Authorization: Bearer` till Supabase REST RPC-endpoints tillsammans med publishable key.
4. Creator-RPC:n avgör genom `auth.uid()` vad användaren äger eller får läsa. Connect filtrerar inte fram behörighet med ett klientskickat användar-id.
5. Connect formar det RLS-skyddade svaret till ett stabilt MCP-resultat.

Connects Python-repository får en generell RPC-metod för `POST /rest/v1/rpc/<function>`. Den ersätter den nuvarande direkta tabelläsningen för Creator-data. Direkta REST-läsningar av `content_items` får bara vara kvar om en befintlig Creator-RPC saknas och dess RLS-policy har verifierats med två olika användare.

## MCP-kontrakt, läsning

Följande läsverktyg är första leveransen. `get_connect_context` behålls för felsökning av inloggning.

| Verktyg | Indata | Resultat |
| --- | --- | --- |
| `get_connect_context` | inga | Verifierad `user_id` och anslutningsnivå. |
| `list_my_library` | valfritt `kind`: `prompt`, `package` eller `all`; valfritt `limit` 1–100 | En sida med normaliserade biblioteksposter. Varje post har `id`, `kind`, `title`, `summary`, `status`, `updated_at` och referensmarkering. |
| `get_my_library_prompt` | `prompt_id` UUID | Full prompttext och metadata för en egen Creator-prompt eller egen Valvet-post. |
| `list_my_packages` | valfritt `limit` 1–100 | Paket med `id`, titel, sammanfattning, status, pakettyp, antal poster och referensmarkering. |
| `get_my_package` | `package_id` UUID | Paketets metadata och dess promptar i sparad ordning. En levande referens returnerar det aktuella publicerade paketets innehåll. |
| `list_my_shares` | valfritt `include_inactive` boolean, standard `false` | Användarens delningar med typ, målobjekt, etikett, giltighet, aktiv-status, visningar och kopior. |

`list_my_library` är en sammanställd översikt och returnerar inte full prompttext. AI-klienten hämtar en enskild prompt eller ett paket först när den behöver innehållet. Det gör bibliotekssökningen hanterbar och minimerar data i varje MCP-svar.

För att hämta full text för en egen Creator-prompt behöver den första leveransen en smal, ny `authenticated`-RPC i Promptbanken-databasen. Den ska endast acceptera ett UUID, kontrollera att `owner_user_id = auth.uid()` och returnera promptens Creator-fält. Den får inte bredda `list_my_creator_prompts`, som är del av Creators publiceringsflöde. En separat motsvarande RPC används för Valvet-kopior där befintlig läs-RPC inte kan återanvändas.

## MCP-kontrakt, beta-skrivning

Skrivverktygen byggs efter att läsningen har nått Creator-paritet. De använder befintliga Creator-RPC:er där kontraktet redan finns:

| Verktyg | Befintlig Creator-RPC |
| --- | --- |
| `create_my_creator_prompt` | `create_my_creator_prompt(...)` |
| `update_my_creator_prompt` | `update_my_creator_prompt(...)` |
| `create_or_update_my_package` | `upsert_creator_package_draft(...)` |
| `add_prompt_to_my_package` | `add_prompt_to_package_draft(...)` |
| `remove_prompt_from_my_package` | `remove_prompt_from_package_draft(...)` |
| `reorder_my_package` | `reorder_package_draft_items(...)` |
| `create_my_share` | `create_creator_share(...)` |
| `extend_my_share` | `extend_creator_share(...)` |
| `revoke_my_share` | `revoke_creator_share(...)` |
| `delete_my_creator_prompt` | `delete_my_creator_prompt(uuid)` |
| `delete_my_package` | `delete_my_creator_package_draft(uuid)` |

Vart och ett av dessa verktyg ska kontrollera entitlement före sitt Supabase-anrop. Under beta returnerar entitlementkontrollen skrivbehörighet för inloggade användare. Efter beta ska samma kontroll returnera skrivbehörighet endast för Pro. Read-only-verktygen påverkas inte.

Skrivverktyg som har sidoeffekter ska ta en klientgenererad `idempotency_key` UUID och logga verktygsnamn, användar-id, resultat och idempotency-nyckel utan prompttext eller token. En upprepning med samma nyckel ska returnera det tidigare resultatet och inte skapa en ny prompt, ett nytt paket eller en ny delning.

## Fel och säkerhet

- Saknad, utgången eller felaktig token ger HTTP 401 med OAuth-resursutmaning.
- Felaktiga parametrar ger JSON-RPC `-32602` och ett svenskt, specifikt felmeddelande utan intern databasdetalj.
- Ett objekt som inte ägs eller inte är åtkomligt ger samma `-32004`-svar som ett saknat objekt.
- Fel från Supabase mappas till ett generellt, återförsöksbart MCP-fel. Token, prompttext, SQL och interna Supabase-fel får inte läcka.
- Connect ska logga korrelations-id, verktygsnamn och resultatkod. Den får inte logga Authorization-header, OAuth-token eller promptinnehåll.

## Avgränsning

Den här designen ändrar inte Promptbanken Open, den publika katalogen, Open-connectorns Docker-container eller dess MCP-kontrakt. Den bygger inte en chatvy i `app.promptbanken.se`; användaren ser fortsatt sitt bibliotek i Creator medan AI-klienten använder Connects verktyg.

## Verifiering

För varje nytt läsverktyg ska tester täcka:

1. korrekt verktygsschema och normaliserat resultat;
2. att Connect skickar anroparens token, aldrig service-rollnyckel;
3. att ogiltiga UUID:n avvisas utan Supabase-anrop;
4. att en användare inte kan läsa en annan användares prompt, paket eller delning;
5. paketordning och levande referenspaket;
6. att Open 1.2.2:s tool-lista och endpoints är oförändrade.

Skrivfasen lägger dessutom till tester för entitlement, `confirm: true`, idempotens och ägarskap på varje förändring. Före produktion används två separata testkonton mot staging och en riktig OAuth authorization-code-med-PKCE-runda.