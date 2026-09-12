# Fristående Admin-MCP med Supabase OAuth

**Status:** Godkänd av Peter 2026-09-11. Implementationsplan finns i tre
samordnade delar under `docs/superpowers/plans/`.

## Sammanfattning

Promptbankens administrativa MCP-yta flyttas till en ny, fristående tjänst
och ett nytt repo: `promptbanken-admin-mcp`. Tjänsten får den publika adressen
`https://admin-mcp.promptbanken.se/mcp`, använder samma Supabase OAuth 2.1-
server och samtyckessida som Promptbanken Connect, men har egen OAuth-klient,
egen container och en separat verktygsyta.

Användaren loggar in med sitt vanliga Promptbanken-konto. Behörigheten avgörs
inte av e-postadressen `wenstrompeter@gmail.com`, utan av det stabila användar-
id:t och rollen `platform_owner` i `public.profiles`. En OAuth-session får
dessutom bara använda administratörsbehörigheten när dess `client_id` finns i
en privat tillåtelselista. På så sätt får en vanlig Connect-token aldrig
administratörsrättigheter bara för att kontots ägare råkar vara
`platform_owner`.

Den nya tjänsten agerar alltid som den inloggade användaren mot Supabase. Den
har ingen `service_role`-nyckel, ingen statisk adminnyckel och ingen sparad
refresh token. Därmed får RLS, RPC-kontroller och auditlogg den verkliga
användaridentiteten.

## Bakgrund och nuläge

Tre funktioner behöver hållas isär:

| Yta | Nuvarande syfte | Beslut |
| --- | --- | --- |
| Promptbanken Open | Publika, anonyma läsverktyg | Förblir oförändrad |
| Promptbanken Connect | Inloggade användares egna data och arbetsyta | Förblir oförändrad inför review |
| Dagens `/admin` i Open-servern | Katalogadministration med statisk nyckel och gemensam refresh token | Ersätts efter verifierad övergång |

Dagens adminlösning autentiserar anroparen med `PROMPTBANKEN_ADMIN_KEY`, men
utför databasoperationerna med en gemensam `SUPABASE_ADMIN_REFRESH_TOKEN`.
Det innebär att Supabase ser tjänstekontot, inte den faktiska personen som
anropade MCP:t. Den modellen ska avvecklas.

Connect har redan fungerande byggblock för OAuth protected resource metadata,
JWKS-validering och användartoken mot Supabase. De mönstren får återanvändas i
den nya koden, men Connects process, repo, verktyg och publika kontrakt ska
inte utökas.

## Mål

- Interaktiv OAuth-inloggning via `app.promptbanken.se/oauth/consent`.
- Endast `platform_owner` genom en uttryckligen godkänd Admin-MCP-klient får
  tillgång till adminverktygen.
- Varje Supabase-anrop och varje skrivning kan härledas till verklig
  `auth.uid()`.
- Adminverktygen exponeras aldrig från Open eller Connect.
- Open 1.2.2 och Connect ska kunna köras, granskas och rullas tillbaka
  oberoende av den nya tjänsten.
- Driftsättning och återställning ska kunna ske utan avbrott för Open och
  Connect.

## Icke-mål

- Ingen ny administratörs-UI i första versionen.
- Ingen e-postbaserad behörighetsregel.
- Ingen ny Supabase-instans eller separat användarkatalog.
- Ingen ändring av Connects sex verktyg eller review-yta.
- Ingen ändring av Opens nio publika verktyg inom detta projekt.
- Ingen automatisk reservväg från OAuth till statisk nyckel.
- Ingen självbetjäning för godkännande av OAuth-klienter i första versionen.

## Arkitekturbeslut

### Vald lösning

En separat Python/Starlette-baserad MCP-tjänst skapas i repot
`promptbanken-admin-mcp`. Den återanvänder verifierade koncept från Connect,
men inte dess körande process eller verktygsregister. Tjänsten körs i en egen
Docker-container på VPS:en och lyssnar internt på port `8012`.

```text
MCP-klient
   |
   | OAuth 2.1 + PKCE
   v
app.promptbanken.se/oauth/consent
   |
   | Supabase access token
   v
admin-mcp.promptbanken.se/mcp
   |  1. verifiera JWT
   |  2. verifiera platform_owner + godkänt client_id
   |  3. vidarebefordra samma bearer-token
   v
Supabase RPC + RLS + audit (auth.uid = verklig användare)
```

### Avvisade alternativ

1. **Lägga adminverktygen i Connect.** Minst kod på kort sikt, men blandar en
   reviewad användartjänst med plattformsadministration och gör verktygsytan
   svårare att granska och begränsa.
2. **Behålla admin i Open-containern men byta auth.** Delar fortfarande
   process, deploy och felområde med den publika tjänsten.
3. **Ny Supabase-instans.** Ger mer drift och dubbla identiteter utan att lösa
   ett faktiskt datasepareringsbehov.

## Publikt gränssnitt

Endast följande routes exponeras på `admin-mcp.promptbanken.se`:

| Route | Syfte |
| --- | --- |
| `/healthz` | Enkel hälsokontroll utan känsliga detaljer |
| `/.well-known/oauth-protected-resource/mcp` | OAuth protected resource metadata |
| `/mcp` | Streamable HTTP MCP-endpoint |

Övriga routes ska ge 404. `/mcp` accepterar högst 64 KiB request body.

Protected resource metadata ska peka på Promptbankens Supabase OAuth issuer
som authorization server. Ett anrop utan giltig token ska svara `401` och
annonsera resource metadata med `WWW-Authenticate`. Ett giltigt men
otillåtet anrop ska svara `403`.

## Autentisering

Tjänsten verifierar access token lokalt mot Supabase JWKS och kontrollerar:

- tillåten signaturalgoritm och giltig signatur,
- exakt issuer,
- audience `authenticated`,
- `exp` och övriga relevanta tidsclaims,
- icke-tomt `sub`,
- icke-tomt `client_id` för OAuth-baserad Admin-MCP-trafik.

Okänd nyckel-id får utlösa en kontrollerad JWKS-refresh en gång. Om JWKS eller
Supabase inte kan verifieras ska tjänsten stänga åtkomsten, inte falla tillbaka
till cachad behörighet efter dess giltighetstid eller till statisk nyckel.

Tjänsten ska inte lagra access token eller refresh token permanent. Den
inkommande access token används oförändrad i Supabase-anropet tillsammans med
projektets publika/publishable nyckel.

## Auktorisering i två lager

Administratörsåtkomst kräver samtidigt:

1. användarens `sub` motsvarar en profil med rollen `platform_owner`, och
2. tokenens `client_id` finns och är aktiv i Admin-MCP:s privata
   tillåtelselista.

Kontrollen ska finnas både i MCP-tjänsten för snabba och tydliga `403`-svar
och i Supabase för att ett direkt RPC-anrop inte ska kunna kringgå den.

### Privat klientlista

En migration i `promptbanken`-repot skapar:

```sql
app_private.admin_mcp_oauth_clients (
    client_id text primary key,
    label text not null,
    enabled boolean not null default true,
    approved_by uuid references auth.users(id),
    created_at timestamptz not null default now()
)
```

Tabellen får ingen Data API-exponering och inga direkta rättigheter för
`anon` eller `authenticated`. Första klienten läggs till manuellt enligt
deploy-runbook när dess verkliga `client_id` finns. Identifieraren får aldrig
antas eller hårdkodas i migrationen.

### Sessionsmedveten katalogadminregel

Den generella `app_private.current_user_is_platform_owner()` används av många
andra RLS-policyer och ska **inte** ändras i detta projekt. Att göra den
klientmedveten skulle annars kunna ändra Peters vanliga Connect- och
webbåtkomst trots att tjänsternas kod lämnas orörd.

Migrationen skapar i stället en ny central funktion, exempelvis
`app_private.current_session_may_administer_catalog()`, som kräver:

- att `app_private.current_user_is_platform_owner()` är sann, och
- om JWT:n har `client_id`, att detta id är aktivt i
  `app_private.admin_mcp_oauth_clients`, och
- om JWT:n saknar `client_id`, att vanlig webbadministration och den gamla
  reservlösningen får fortsätta fungera under övergången.

Samtliga security-definer-funktioner för katalogadministration,
versionshistorik och adminaudit ska använda den nya funktionen i stället för
den generella plattformsägarkontrollen. Katalogtabellerna har redan RLS utan
direkta policies och återkallade rättigheter för `anon`/`authenticated`, så
de godkända RPC:erna är den enda normala vägen för direkta klientanrop.

Den sista punkten ovan är avsiktlig för bakåtkompatibilitet under cutover.
Efter att den gamla `/admin`-lösningen tagits bort ska regeln om token utan
`client_id` omprövas separat; den ska inte skärpas i samma release som första
driftsättningen.

Databaskontrollen ska läsa claims från den av Supabase verifierade
request-kontexten, inte från MCP-tjänstens egna HTTP-fält.

## Verktygskontrakt

Admin-MCP exponerar exakt följande 21 verktyg och inga Open- eller
Connect-verktyg:

1. `get_admin_context`
2. `admin_create_prompt`
3. `admin_upsert_prompt_variant`
4. `admin_list_draft_prompts`
5. `admin_get_prompt`
6. `admin_publish_prompt`
7. `admin_unpublish_prompt`
8. `admin_delete_draft_prompt`
9. `admin_create_package`
10. `admin_upsert_package_variant`
11. `admin_upsert_package_metadata`
12. `admin_add_prompt_to_package`
13. `admin_update_package_item`
14. `admin_remove_prompt_from_package`
15. `admin_publish_package`
16. `admin_unpublish_package`
17. `admin_delete_draft_package`
18. `admin_list_prompt_history`
19. `admin_restore_prompt_version`
20. `admin_list_package_history`
21. `admin_restore_package_version`

De 20 befintliga `admin_*`-verktygens namn, argument, JSON Schema och
`confirm: true`-krav ska först låsas med karakteriseringstester och därefter
porteras utan omtolkning. Destruktiva operationer samt publicering,
avpublicering och återställning behåller explicit bekräftelse.

`get_admin_context` är read-only och returnerar endast den information som
behövs för begriplig klientstatus: användar-id, visnings-/e-postidentifiering
om den redan finns i den verifierade profilen, aktuell roll, OAuth `client_id`
och att klienten är godkänd. Den returnerar aldrig rå JWT, refresh token,
nyckelmaterial eller fullständiga claims.

Ett versionsstyrt `mcp-contract.json` i det nya repot är normerande för exakt
verktygslista, metadata och input schemas.

## Supabase-anrop och dataintegritet

- Varje verktygsanrop skapar en Supabase-klient eller ett request-scope med
  användarens inkommande bearer-token.
- Ingen `service_role`-nyckel eller delad adminsession finns i containern.
- Befintliga katalog-RPC:er fortsätter vara den enda skrivvägen; tjänsten gör
  inte direkta tabellskrivningar.
- Servern ska inte försöka återskapa RLS-regler i applikationskod. Dess
  rollkontroll är ett första lager; databasen är sista auktoritetsgränsen.
- Timeout, svarsstorlek och felöversättning ska vara begränsade så att ett
  Supabase-fel inte låser MCP-processen eller läcker intern SQL.

## Audit och loggning

Dagens `app_private.admin_write_attempts` innehåller inte aktörens användar-id.
Migrationen utökar därför auditmodellen så att varje adminskrivning minst
sparar:

- `actor_user_id uuid`, hämtad från `auth.uid()` i databasen,
- OAuth `client_id` när claimen finns,
- verktygsnamn, mål-id, utfall och tidpunkt,
- befintlig säker detalj/snapshot utan hemligheter.

Auditfunktionen ska själv läsa aktör och klientclaim från request-kontexten;
MCP-klienten får inte ange dessa fält som argument. Kolumnen behöver vara
nullable för befintliga rader i den bakåtkompatibla migrationen, men
auditfunktionen ska avvisa varje ny skrivning där `auth.uid()` saknas.

Applikations- och proxyloggar får inte innehålla Authorization-header,
cookies, access/refresh tokens, full e-postadress eller interna stack traces.
Loggar ska använda korrelations-id, verktygsnamn, utfall och grov latens.
IP-adress ska inte sparas i den dedikerade accessloggen för denna host.

## Felmodell

| Situation | Resultat |
| --- | --- |
| Token saknas, är trasig eller utgången | `401 Unauthorized` + OAuth resource metadata |
| Token är giltig men användaren saknar `platform_owner` | `403 Forbidden` |
| Token är giltig men `client_id` saknas/inte är godkänt | `403 Forbidden` |
| Supabase/JWKS kan inte verifieras | Fail closed; `401` eller temporärt tjänstefel utan intern detalj |
| Felaktiga verktygsargument | MCP `InvalidParams` utan databasdetaljer |
| Databasens auth/RLS avvisar anropet | Sanitiserat MCP-fel; originalet loggas inte med känslig data |
| Oväntat serverfel | Generiskt MCP internal error + korrelations-id |

## Container och reverse proxy

Den nya tjänsten får egen compose-definition, image och container med:

- intern port `8012`, endast nåbar via Caddy och localhost-nätet,
- `restart: unless-stopped`,
- healthcheck mot `/healthz`,
- read-only root filesystem och separat skrivbar temporär katalog vid behov,
- borttagna Linux capabilities och `no-new-privileges`,
- explicita CPU-/minnesgränser anpassade efter verifierad last,
- endast nödvändiga miljövariabler för Supabase URL, publishable key, issuer,
  audience, JWKS och serverkonfiguration.

Caddy terminerar TLS för `admin-mcp.promptbanken.se`, tillåter bara de tre
routes som anges ovan, sätter rimliga timeouts och 64 KiB body-gräns samt
redigerar bort känsliga headers/cookies och IP från accessloggen.

## Teststrategi och acceptanskriterier

### 1. Enhetstester

- giltig och ogiltig signatur, issuer, audience, `exp`, `sub` och `client_id`,
- JWKS key rotation och fail-closed-beteende,
- roll- och klientallowlist,
- argumentvalidering, `confirm`-krav och sanerade fel,
- ingen token eller känslig identitet i loggar.

### 2. Kontraktstester

- `tools/list` innehåller exakt de 21 beslutade verktygen,
- alla input schemas matchar det versionsstyrda kontraktet,
- Open innehåller fortsatt exakt sina nio publika verktyg och inga
  `admin_*`-verktyg,
- Connect innehåller fortsatt exakt sina sex verktyg och inga
  `admin_*`-verktyg,
- oanmälda/otillåtna anrop ger rätt 401/403 och OAuth metadata.

### 3. Säkerhetstester

- vanlig Connect-token nekas även när den tillhör en `platform_owner`,
- Admin-MCP-token för icke-admin nekas,
- Admin-MCP-token för godkänd `platform_owner` tillåts,
- avstängd eller okänd Admin-MCP-klient nekas både i tjänsten och direkt av
  Supabase-RPC,
- utelämnad klientclaim kan inte användas mot Admin-MCP-endpointen,
- tjänsten fungerar utan `service_role`, statisk adminnyckel och refresh token.

### 4. End-to-end

Med en separat testslug genomförs:

1. OAuth discovery och samtycke via Promptbanken,
2. `get_admin_context`,
3. skapa och läsa draft,
4. verifiera att auditloggen innehåller rätt `auth.uid()` och `client_id`,
5. radera testdraft med explicit bekräftelse,
6. verifiera att ingen testdata återstår.

Produktion är godkänd först när samtliga fyra nivåer passerar och resultaten
sparats i releaseunderlaget.

## Produktionsförutsättningar

VPS:ens rootdisk hade vid kartläggningen bara cirka 101 MB ledigt. Ingen ny
image får byggas innan utrymme har frigjorts. Minst 600 MB ledigt är ett hårt
golv inför build; över 1 GB är rekommenderat för rimlig driftmarginal.

Den publika Open 1.2.2-serverns kända kontraktsavvikelse för
`search_templates.inputSchema.properties.area.enum` hör till en separat
baseline-release. Den ska vara åtgärdad och Open ska ge 62/62 innan Admin-MCP-
utrullningen börjar, så att en gammal avvikelse inte blandas ihop med den nya
tjänsten.

Databasmigrationen är delad produktionskod, men dess behörighetsändring ska
vara begränsad till katalogens security-definer-RPC:er. Vanliga Open-anrop,
Connects sex verktyg och övriga webb/RLS-flöden ska därför behålla nuvarande
beteende. Detta verifieras uttryckligen före och efter migrationen.

## Utrullning

1. Starta om VPS:en till installerad ny kärna, verifiera tjänsterna och frigör
   disk enligt separat driftåtgärd.
2. Färdigställ och verifiera Open 1.2.2-baseline separat (62/62).
3. Skapa `promptbanken-admin-mcp`, lås det porterade kontraktet och kör alla
   lokala tester.
4. Lägg Supabase-migrationen för klientlista, sessionsmedveten
   katalogadminregel och utökad audit i `promptbanken`-repot. Verifiera den i
   staging före produktion.
5. Starta Admin-MCP-containern på port 8012 utan publik Caddy-route.
6. Registrera OAuth-klienten, lägg dess verkliga `client_id` i den privata
   listan och kör interna tester.
7. Lägg DNS och Caddy-route för `admin-mcp.promptbanken.se`; kör hela
   kontrakts-, säkerhets- och E2E-sviten.
8. Använd nya Admin-MCP för verkligt adminarbete under en övergångsperiod.
   Gamla `/admin` finns kvar som fryst reserv och får inga nya funktioner.
9. När övergången är verifierad tas gamla `/admin`,
   `PROMPTBANKEN_ADMIN_KEY`, `SUPABASE_ADMIN_REFRESH_TOKEN`, dess persistenta
   tokenvolym och den gamla adminkoden bort i en separat cleanup-release.

## Rollback

Före cleanup kan den nya containern och Caddy-routen stängas av och den gamla
`/admin`-ytan användas tillfälligt. Open och Connect berörs inte.

Databasmigrationen ska vara framåtkompatibel med befintliga webbsessioner och
den gamla adminsessionen under övergången. Klienter kan omedelbart spärras med
`enabled = false`. En databasrollback ska inte vara första åtgärd vid en
incident; stoppa route/container eller spärra klienten först.

Efter cleanup finns ingen automatisk statisk reservväg. Återställning sker då
genom att rulla tillbaka den nya tjänstens image eller spärra/återaktivera
OAuth-klienten, inte genom att återinföra gemensamma refresh tokens.

## Ägarskap och källor till sanning

- `promptbanken-admin-mcp` äger efter cutover tjänstekod, Docker/Caddy-
  exempel, verktygskontrakt och tjänstespecifik dokumentation.
- `promptbanken` äger Supabase-migrationer, roller, RLS/RPC och auditmodell.
- `mcp_promptbanken` äger Open. Den gamla adminkoden är fryst under övergången
  och tas bort efter godkänd cutover.
- Connect-repot äger endast Connect och ändras inte av detta projekt.

Denna designspec ligger i `mcp_promptbanken` eftersom den ersätter den
befintliga adminytan där. När det nya repot skapas ska dess README länka hit
eller en normerande kopia flyttas dit utan att besluten förändras.

## Normativa referenser

- [Supabase: MCP authentication](https://supabase.com/docs/guides/auth/oauth-server/mcp-authentication)
- [Supabase: OAuth 2.1 Server – Getting started](https://supabase.com/docs/guides/auth/oauth-server/getting-started)
- [Supabase: OAuth token security](https://supabase.com/docs/guides/auth/oauth-server/token-security)
- [MCP Authorization specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)

## Beslut som är låsta inför implementationsplanen

- egen tjänst och eget repo,
- URL `admin-mcp.promptbanken.se/mcp` och intern port 8012,
- samma Supabase OAuth issuer/samtyckessida som Connect men egen klient,
- både `platform_owner` och godkänt `client_id` krävs,
- ingen e-postbaserad auktorisering,
- ingen service role, statisk adminnyckel eller sparad refresh token,
- exakt 21 verktyg,
- verklig användare och klient i auditloggen,
- Open och Connect ändras inte under första utrullningen,
- gamla `/admin` tas bort först i en separat, verifierad cleanup-release.
