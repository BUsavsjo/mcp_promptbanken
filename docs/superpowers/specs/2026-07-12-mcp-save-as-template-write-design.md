# MCP write: "Spara detta som mall" (save_workspace_prompt)

## Syfte

Låta en användare i en pågående AI-chatt (Claude, ChatGPT, Copilot eller annan MCP-klient) be modellen "spara det här som en mall" och få en generaliserad, GDPR-kontrollerad prompt sparad i sin egen personliga Pro-arbetsyta i Promptbanken — utan att lämna chatten. Detta är den **hostade** MCP-serverns (detta repo, `mcp_promptbanken`, körs i Docker på `mcp.promptbanken.se`) första write-funktion; servern har hittills varit strikt read-only/metadata-only.

Gated till nycklar med `plan = 'pro'` (skickas per anrop som `X-MCP-Key`/`Authorization`-header, samma som alla andra workspace-tools i detta repo). Free-nycklar kan inte skriva via MCP i denna version.

**Varför hostade servern och inte lokala `promptbanken/mcp-server/`:** användaren vill kunna "spara som mall" från vilken MCP-klient som helst (Claude, ChatGPT, Copilot) mot den publikt nåbara adressen — inte bara från sin egen dator med en lokalt körande stdio-process. Se Beslut nedan för den medvetna omprövningen av read-only-gränsen.

## Beslut: medveten omprövning av read-only-gränsen

`PROJECT.md`/`CLAUDE.md` i detta repo har hittills sagt att servern "aldrig ska ta emot/spara användartext" — en säkerhets-/ansvarsgräns, inte en teknisk begränsning. Detta write-verktyg bryter den gränsen **avsiktligt och smalt**:

- Bara **en** ny skrivväg (`save_workspace_prompt`), inget generellt write-API.
- Bara **Pro-nycklar** kan använda den — Free/publikt är fortfarande helt read-only.
- Innehållet som sparas är **inte** rå användartext från chatten — klientmodellen ska ha generaliserat det (se Flöde) innan det når servern. Servern varken kräver eller kan verifiera detta tekniskt, men det är den avsedda användningen och uttrycks i verktygsbeskrivningen.
- All skrivning loggas (se Loggning) för att kunna upptäcka missbruk i efterhand.

Detta ska antecknas som ett formellt beslut i `DECISIONS.md` när planen implementeras (egen deltask), inte bara i denna spec.

## Bakgrund

All skrivning till `content_items` sker idag via `promptbanken`-repots inloggade webb-frontend (`admin.js`), skyddad av RLS-policyer och triggern `app_private.enforce_content_access_model()` som är hårt knuten till `auth.uid()` (kräver en riktig inloggad Supabase-session). MCP-anrop — vare sig från denna hostade server eller den lokala — har ingen sådan session, bara en `X-MCP-Key`/nyckelhash, verifierad via `app_private.verify_mcp_key(p_key_hash)`. De befintliga läs-RPC:erna i detta repo (`get_pro_templates_for_mcp_key`, `get_workspace_prompts_for_key`, `list_shared_workspaces_for_key`, anropade från `mcp-server/server/pro_templates.py` via `httpx`) löser detta genom att vara egna SECURITY DEFINER-funktioner som litar på nyckelhashen istället för `auth.uid()`. Write-funktionen behöver samma förtroendeväxling, men måste dessutom passera den befintliga INSERT-triggern på `content_items` utan att försvaga den för webbflödet.

**Databasen och migrationerna ägs av `promptbanken`-repot** (`promptbanken/supabase/migrations/`), inte detta repo — detta repo har ingen egen Supabase-databas, det pratar mot samma projekt via `SUPABASE_URL`/`SUPABASE_ANON_KEY`. Den nya RPC:n (`save_prompt_for_key`) skrivs alltså som en migration i `promptbanken`-repot, medan MCP-verktyget/REST-endpointen som anropar den byggs i detta repo.

Servern kör aldrig någon egen AI-modell. Generalisering av innehåll (ta bort namn/personnummer/org-specifika detaljer, ersätta med platshållare, föreslå titel/kategori) och godkännande-steget sker helt på klientmodellens sida (Claude/ChatGPT/Copilot) innan den anropar write-verktyget — servern kan inte tekniskt verifiera att en människa faktiskt godkänt något i en annan klients gränssnitt. Detta är en medveten designbegränsning, inte ett hål: samma modell som redan gäller för `get_client_routing_instructions`-flödet (klienten ansvarar för routing/generalisering, servern bara serverar/tar emot metadata).

## Flöde

1. Användaren ber klientmodellen spara chatten/instruktionen som mall.
2. Klientmodellen (inte servern) generaliserar innehållet: tar bort namn/personnummer/org-specifika detaljer, ersätter med platshållare, föreslår titel + kategori (se Kategorisering för förslagslistan).
3. Klientmodellen visar förslaget för användaren och väntar på godkännande — detta styrs av verktygets beskrivningstext, inte av server-logik.
4. Klientmodellen anropar det befintliga verktyget `check_input_risk` på den genererade mallen (inte råchatten) — detta verktyg finns idag bara i **lokala** `promptbanken/mcp-server/`, inte i detta hostade repo. Se Öppen fråga nedan.
5. Om risk flaggas: klientmodellen visar vad som flaggades, användaren redigerar eller avbryter.
6. Vid godkännande anropar klientmodellen `save_workspace_prompt(title, content, category, source, risk_check_passed, idempotency_key)` med samma `X-MCP-Key`/`Authorization`-header som redan används för läsning i detta repo.
7. Servern validerar nyckel, plan, innehåll och risk-flaggan, skriver posten (eller returnerar en redan existerande post vid idempotent retry), returnerar resultat till klientmodellen som visar det för användaren.

**Öppen fråga att lösa innan/under implementation:** `check_input_risk` finns idag bara som ett `@mcp.tool()` i lokala `promptbanken/mcp-server/server/mcp_server.py` (importerar `RiskChecker` från `risk_checker.py`, ren Python-regex, ingen Supabase-koppling). Detta hostade repo har **ingen** `risk_checker.py` eller motsvarande verktyg alls — `hosted_guard.py`s allowlist tillåter det inte heller idag. Eftersom write-verktyget bara finns här, måste `check_input_risk` porteras hit (ren kod-kopia, samma mönster som `list_pro_templates` porterades från lokala → hostade repot 2026-07-08, se `LOG.md`) **innan** write-flödet är komplett, annars finns inget sätt att köra steg 4 mot den publika adressen. Detta läggs till som en egen task i planen.

Inget mellanlagrat "förslag" hålls kvar på servern mellan steg 3 och 6 — ett enda write-anrop, ingen sessionstate.

## RPC-design (i `promptbanken`-repot)

Ny SECURITY DEFINER-funktion:

```sql
create or replace function app_private.save_prompt_for_key(
    p_key_hash text,
    p_title text,
    p_content text,
    p_category text,
    p_source text default 'manual',
    p_risk_check_passed boolean default false,
    p_idempotency_key uuid default null
) returns public.content_items
language plpgsql
security definer
set search_path = public, app_private, pg_temp
as $$
...
$$;
```

`set search_path = public, app_private, pg_temp` är obligatoriskt — utan pinnad `search_path` kan en SECURITY DEFINER-funktion luras att köra ett skadligt objekt om något skapar ett schema/funktion/tabell med samma namn tidigare i en ohärdad sökväg. Samma uppstädning bör göras på de befintliga läs-RPC:erna (`get_pro_templates_for_mcp_key`, `get_workspace_prompts_for_key`, `list_shared_workspaces_for_key`) som en separat, liten TODO — utanför scope för denna spec.

**Förtroendeväxling utan att ändra befintlig trigger:** funktionen slår upp `workspace_id`/`owner_user_id`/`plan`/`max_prompts` direkt via `api_keys`/`workspaces` (samma mönster som `get_workspace_prompts_for_key` redan gör — inte via `verify_mcp_key`, som saknar `owner_user_id` i sin retur). Avvisar om nyckeln är ogiltig/återkallad eller `plan <> 'pro'`. Innan INSERT sätts en transaktionslokal session-inställning:

```sql
perform set_config('request.jwt.claim.sub', owner_user_id::text, true);
```

`auth.uid()` läser just denna inställning (Supabase/PostgREST-konvention). Eftersom `set_config(..., true)` bara gäller den aktuella transaktionen, och funktionen är SECURITY DEFINER (bara exekverbar av `anon` som en hel, redan validerad enhet — ingen klient kan sätta detta värde själv utan att gå via funktionen), ser den redan existerande triggern `enforce_content_access_model()` ett giltigt `auth.uid()` som matchar `created_by`/`owner_user_id`. Alla befintliga regler (max_prompts-gräns, visibility-regler för personal/pro-workspace, publik-spärr) återanvänds **oförändrade** — ingen duplicerad valideringslogik i den nya funktionen.

**`slug` krävs av `content_items`** (`not null`, unikt per workspace, format `^[a-z0-9][a-z0-9-]{1,120}[a-z0-9]$`, se `20260612120000_initial_schema.sql:128,138-139`). Funktionen genererar en slug från `p_title` med den redan befintliga `app_private.slugify_candidate(p_name text, p_fallback_prefix text)` (samma helper som `create_shared_workspace`/`create_pro_order` redan använder), med kollisions-loop mot `workspace_id`-scopad unikhet precis som de befintliga anroparna gör.

Insert-värden: `workspace_id` (från nyckeln), `type='prompt'`, `title`, `slug` (genererad), `content`, `category`, `visibility='private'` (låst — write-verktyget skriver aldrig `workspace`/`public`, se Skopning), `status='draft'`, `created_by`/`owner_user_id` = `owner_user_id`, `source`, `idempotency_key`.

**Nya kolumner på `content_items`:**
- `source text not null default 'manual' check (source in ('manual', 'chat_extraction'))`
- `idempotency_key uuid` + unikt partiellt index `(workspace_id, idempotency_key) where idempotency_key is not null`

Grant: `execute on function app_private.save_prompt_for_key to anon` — samma förtroendemodell som de befintliga anon-beviljade RPC:erna.

### Valideringsordning i funktionen (varje steg loggar ett försök, se Loggning)

1. Nyckel giltig? Nej → logga `invalid_key`, avvisa.
2. `plan = 'pro'`? Nej → logga `not_pro`, avvisa.
3. Rate limit inte nådd (se Rate limiting)? Nej → logga `rate_limited`, avvisa.
4. `p_title`/`p_content` giltiga (se Innehållsvalidering)? Nej → logga `invalid_input`, avvisa.
5. `p_idempotency_key` angiven och matchar en befintlig rad i samma workspace? Ja → logga `idempotent_hit`, returnera den befintliga raden utan ny INSERT.
6. `p_risk_check_passed = false`? Ja → logga `risk_check_not_passed`, avvisa med tydligt fel.
7. Slug genereras, INSERT (triggern `enforce_content_access_model` körs, kan fortfarande avvisa på `max_prompts`-gräns — logga `limit_reached` i det fallet).
8. Lyckad INSERT → logga `success`.

## Säkerhet

### Rate limiting

Max 10 write-försök per nyckel per 60 sekunder, räknat mot `mcp_write_attempts` (se Loggning) innan något annat görs i funktionen.

### Innehållsvalidering

- `p_title`: `trim(p_title) <> ''`, längd ≤ 200 tecken.
- `p_content`: `trim(p_content) <> ''`, längd ≤ 20 000 tecken.
- `p_category`: `trim(p_category) <> ''`.

Brott → `raise exception`, loggas som `invalid_input`.

## Idempotens

Se RPC-design. `p_idempotency_key` genereras av klientmodellen en gång per godkännande-tillfälle. Retry med samma nyckel returnerar den befintliga raden istället för att krascha på unique-constraint eller skapa en dubblett.

## Risk-check-parameter

`p_risk_check_passed boolean default false`, obligatorisk att sätta `true` efter genomförd `check_input_risk` (se Öppen fråga i Flöde ovan om att portera det verktyget hit). Standard `false` gör att ett anrop som glömmer parametern avvisas tydligt. Varje anrop loggas med sitt `risk_check_passed`-värde — gör avsiktligt kringgående synligt i efterhand, inte omöjligt.

## Loggning / observability (i `promptbanken`-repot, delad av rate limiting och drift)

```sql
create table if not exists app_private.mcp_write_attempts (
    id bigint generated always as identity primary key,
    key_hash text not null,
    workspace_id uuid,
    outcome text not null,
    -- 'success' | 'invalid_key' | 'not_pro' | 'rate_limited' | 'invalid_input'
    -- | 'risk_check_not_passed' | 'limit_reached' | 'idempotent_hit'
    risk_check_passed boolean,
    created_at timestamptz not null default now()
);

create index if not exists mcp_write_attempts_key_hash_created_at
    on app_private.mcp_write_attempts (key_hash, created_at desc);
```

Ingen prompttext lagras — bara nyckelhash, workspace, utfall, tidsstämpel. Ingen retention-policy i v1.

## Reversibilitet / rollback

`promptbanken`-repot har ingen down-migration-konvention. Manuell rollback-SQL:

```sql
revoke execute on function app_private.save_prompt_for_key(text, text, text, text, text, boolean, uuid) from anon;
-- Nödbroms: stänger av write omedelbart utan att röra data.
-- Fullständig borttagning (separat, medvetet steg):
-- drop function if exists app_private.save_prompt_for_key(text, text, text, text, text, boolean, uuid);
-- drop table if exists app_private.mcp_write_attempts;
-- alter table public.content_items drop column if exists idempotency_key;
-- alter table public.content_items drop column if exists source;
```

I detta hostade repot: `revoke execute` räcker inte ensamt för att stänga av verktyget mot klienter — `hosted_guard.py`s allowlist måste också tömmas för `save_workspace_prompt` (ta bort ur `allowed_methods`/`allowed_tool_args`) och en ny image byggas/deployas. Snabbaste nödbromsen i praktiken: sätt `PROMPTBANKEN_MCP_HOSTED_GUARD=block` (finns redan som env-variabel, se `HOSTED_GUARD_MODE`) om guarden bara varnar idag — annars krävs en deploy för att ta bort verktyget helt.

## Skopning / permissions

Låst till egen personlig Pro-arbetsyta i v1. `visibility` hårdkodas till `'private'`. Delning till `shared_workspace_addons` är explicit utanför scope; kan läggas till senare med en `p_workspace_id`-parameter och samma medlemskapskontroll som `get_workspace_prompts_for_key` redan gör, utan att ändra kontraktet för v1-anrop.

## Kategorisering

`category` är fritext i databasen, ingen enum. Verktygsbeskrivningen för `save_workspace_prompt` innehåller en icke-bindande förslagslista: kommunikation, förändringsledning, processer, beslutsberedning, visuellt, ledarskap, arbetsbank (samma sju områden som `pro_prompt_templates` redan använder). Klientmodellen föreslår kategori utifrån denna lista eller egen fritext, användaren kan ändra fritt innan godkännande.

## Dubblettkontroll

Ingen exakt titel/kategori-varning i v1. Idempotensnyckeln löser den tekniska dubblett-risken vid timeout/retry. Semantisk likhetsdetektering utanför scope.

## Felrapportering vid missad GDPR-risk

Ingen separat rapporteringsväg i v1. Användaren äger raden och kan redigera/radera den direkt i `admin.html` (i `promptbanken`-repot, befintlig funktionalitet).

## Telemetri

`source` (`manual` | `chat_extraction`) på raden, ingen extra loggning av chattinnehåll. `mcp_write_attempts` (se Loggning) täcker anropsnivå-observability separat.

## Kodändringar

### `promptbanken/supabase/migrations/` (annat repo, delad databas)

Ny migration (t.ex. `20260712100000_save_prompt_for_key.sql`):
- Nya kolumner `source`/`idempotency_key` + unikt index på `content_items`.
- Ny tabell `app_private.mcp_write_attempts`.
- `create or replace function app_private.save_prompt_for_key(...)` enligt RPC-designen ovan.
- `grant execute on function app_private.save_prompt_for_key(text, text, text, text, text, boolean, uuid) to anon;`

### `mcp-server/server/mcp_server.py` — porta `check_input_risk` hit

Kopiera `RiskChecker`-klassen (`promptbanken/mcp-server/server/risk_checker.py`, ren regex, ingen extern dependency) till en ny fil `mcp-server/server/risk_checker.py` i **detta** repo, och registrera:

```python
from .risk_checker import RiskChecker

risk_checker = RiskChecker()


@mcp.tool()
def check_input_risk(text: str) -> dict[str, object]:
    """Check text for common personal-data patterns (personnummer, e-post,
    telefonnummer, ärendenummer) before saving it as a template. Never blocks,
    only warns — the calling model/user decides whether to edit or proceed."""
    logger.info("tool_call name=check_input_risk")
    return risk_checker.check(text).to_dict()
```

Lägg till i `_tool_definitions()` (inputSchema: `{"text": {"type": "string"}}`, required `["text"]`) och i `_handle_mcp_message`s `tools/call`-gren. Lägg till `"check_input_risk"` i `hosted_guard.py`s `allowed_methods` och `allowed_tool_args["check_input_risk"] = {"text"}` (måste tillåta argumentet — `HostedMetadataGuard.inspect_tool_args` har idag ingen gren för detta tool, se befintlig `elif`-kedja).

### `mcp-server/server/pro_templates.py` — write-klient

Ny funktion, samma mönster som `_call_context_rpc` men POST med fler payload-fält:

```python
def save_prompt(
    mcp_key: str,
    title: str,
    content: str,
    category: str,
    source: str = "manual",
    risk_check_passed: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Skriver en ny prompt i nyckelns personliga Pro-arbetsyta via
    save_prompt_for_key (samma anon-beviljade förtroendemodell som
    get_pro_templates_for_mcp_key/get_workspace_prompts_for_key, se
    promptbanken/supabase/migrations/20260712100000_save_prompt_for_key.sql).
    Kastar RuntimeError vid HTTP-fel (ogiltig nyckel, inte Pro, gräns nådd,
    rate limit, ogiltig indata, risk-check inte godkänd) -- mcp_server.py
    fångar och paketerar detta som ett strukturerat felsvar."""
    if not mcp_key or not is_configured():
        raise RuntimeError("MCP-nyckel saknas eller SUPABASE_URL/SUPABASE_ANON_KEY är inte konfigurerat.")

    url = f"{_SUPABASE_URL}/rest/v1/rpc/save_prompt_for_key"
    payload = {
        "p_key_hash": _hash_key(mcp_key),
        "p_title": title,
        "p_content": content,
        "p_category": category,
        "p_source": source,
        "p_risk_check_passed": risk_check_passed,
        "p_idempotency_key": idempotency_key,
    }
    response = httpx.post(
        url,
        headers={
            "apikey": _ANON_KEY,
            "Authorization": f"Bearer {_ANON_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=5,
    )
    response.raise_for_status()
    return response.json()
```

Notera: till skillnad från de befintliga `_call_context_rpc`-baserade funktionerna (som fångar alla fel och returnerar tom lista — rimligt för läsning), låter `save_prompt` undantaget propagera. En tyst tom lista vid ett write-fel skulle dölja för klientmodellen att skrivningen faktiskt misslyckades.

### `mcp-server/server/mcp_server.py` — verktyg, dispatch, REST, guard

Importera `save_prompt as _save_prompt` från `pro_templates.py`. Ny helper:

```python
def _save_workspace_prompt_payload(
    mcp_key: str,
    title: str,
    content: str,
    category: str,
    source: str,
    risk_check_passed: bool,
    idempotency_key: str | None,
) -> dict[str, Any]:
    try:
        row = _save_prompt(mcp_key, title, content, category, source, risk_check_passed, idempotency_key)
        return {"status": "success", "prompt": row}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.info("tool_call name=save_workspace_prompt status=error detail=%s", detail)
        return {"status": "error", "message": detail}
    except Exception as exc:
        logger.error("save_workspace_prompt_failed error=%s", exc)
        return {"status": "error", "message": "Kunde inte spara prompten."}
```

**Obs — samma mönster som redan gäller för alla andra workspace-tools i denna fil:** `@mcp.tool()`-dekorerade funktioner ser inte HTTP-request-kontexten direkt, så `list_my_private_prompts`, `list_shared_workspace_prompts` m.fl. har redan `mcp_key`-injektionen i `_handle_mcp_message`/REST-lagret istället för i själva den dekorerade funktionen (jämför `health_check()` — den odekorerade toolet anropar `_health_check_payload()` utan nyckel, medan `_handle_mcp_message`s `tools/call`-gren anropar `_health_check_payload(mcp_key)` med den faktiska headern). `save_workspace_prompt` följer exakt samma delning:

```python
@mcp.tool()
def save_workspace_prompt(
    title: str,
    content: str,
    category: str,
    source: str = "manual",
    risk_check_passed: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Spara en genererad, redan GDPR-granskad mall i användarens Pro-arbetsyta.
    VIKTIGT för anropande modell: generalisera innehållet (ta bort namn/personnummer/
    org-specifika detaljer) och kör check_input_risk på den genererade mallen INNAN
    detta verktyg anropas. Visa förslaget för användaren och invänta uttryckligt
    godkännande före anrop. Sätt risk_check_passed=true först efter godkänd check —
    anrop med risk_check_passed=false avvisas. Generera ett eget idempotency_key (UUID)
    per godkännande-tillfälle för att säkert kunna göra om anropet vid timeout utan att
    skapa en dubblett. Förslag på kategori (valfritt, ingen tvingad lista): kommunikation,
    förändringsledning, processer, beslutsberedning, visuellt, ledarskap, arbetsbank.
    Kräver en Pro-nyckel (X-MCP-Key/Authorization); free-nycklar avvisas."""
    logger.info("tool_call name=save_workspace_prompt")
    return _save_workspace_prompt_payload(
        "", title, content, category, source, risk_check_passed, idempotency_key
    )
```

Den dekorerade funktionen (körs bara i stdio/direktanropsläge, som saknar HTTP-header-kontext) skickar tom `mcp_key`, vilket ger ett tydligt `not_pro`/`invalid_key`-fel från RPC:n — korrekt, eftersom stdio-läge i detta repo ändå inte används i produktion (bara `tools/list`-schemat exponeras därifrån). Det faktiska produktionsanropet går genom `_handle_mcp_message` nedan, som har den riktiga `mcp_key` från `_mcp_key_from_request(request)`.

I `_tool_definitions()`, lägg till:

```python
{
    "name": "save_workspace_prompt",
    "description": (
        "Save a generalised, already GDPR-checked template into the caller's "
        "personal Pro workspace. Requires a Pro key. See tool description for "
        "the required approval + risk-check flow."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "category": {"type": "string"},
            "source": {"type": "string", "default": "manual"},
            "risk_check_passed": {"type": "boolean", "default": False},
            "idempotency_key": {"type": "string"},
        },
        "required": ["title", "content", "category"],
        "additionalProperties": False,
    },
},
```

I `_handle_mcp_message`s `tools/call`-gren, lägg till (efter `list_shared_workspace_prompts`-grenen):

```python
if tool_name == "save_workspace_prompt":
    title = arguments.get("title")
    content = arguments.get("content")
    category = arguments.get("category")
    source = arguments.get("source", "manual")
    risk_check_passed = arguments.get("risk_check_passed", False)
    idempotency_key = arguments.get("idempotency_key")
    if not all(isinstance(v, str) and v for v in (title, content, category)):
        return _json_rpc_error(request_id, -32602, "Invalid save_workspace_prompt arguments")
    if not isinstance(risk_check_passed, bool):
        return _json_rpc_error(request_id, -32602, "risk_check_passed must be a boolean")
    return _json_rpc_result(
        request_id,
        _mcp_content_result(
            _save_workspace_prompt_payload(
                mcp_key, title, content, category, source, risk_check_passed, idempotency_key
            )
        ),
    )
```

Ny REST-endpoint (första POST-endpointen i detta repo, alla `/api/v1/*` hittills är GET):

```python
async def _api_save_workspace_prompt(request: Request) -> JSONResponse:
    mcp_key = _mcp_key_from_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_error("INVALID_JSON", "Request body must be JSON"), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_error("INVALID_BODY", "Request body must be a JSON object"), status_code=400)
    title, content, category = body.get("title"), body.get("content"), body.get("category")
    if not all(isinstance(v, str) and v for v in (title, content, category)):
        return JSONResponse(_error("INVALID_ARGUMENTS", "title, content and category are required strings"), status_code=400)
    payload = _save_workspace_prompt_payload(
        mcp_key, title, content, category,
        body.get("source", "manual"),
        bool(body.get("risk_check_passed", False)),
        body.get("idempotency_key"),
    )
    status_code = 200 if payload.get("status") == "success" else 400
    logger.info("http_request path=/api/v1/my-prompts method=POST status=%s", status_code)
    return JSONResponse(payload, status_code=status_code)
```

Route (i `Starlette(routes=[...])`), återanvänder `/api/v1/my-prompts` som POST (GET redan finns för listning där — REST-konvention: samma path, olika metod för läs/skriv):

```python
Route("/api/v1/my-prompts", endpoint=_api_save_workspace_prompt, methods=["POST"]),
```

**Obs:** `Route("/api/v1/my-prompts", endpoint=_api_my_prompts)` (GET) finns redan i routes-listan — Starlette matchar på path **och** metod, så detta är en tillägg, inte en kollision, så länge `_api_my_prompts` inte redan har `methods=["GET"]` explicit satt (om den saknar `methods` matchar Starlette bara GET/HEAD som standard — verifiera vid implementation, lägg annars till `methods=["GET"]` på den befintliga raden för tydlighet).

I `hosted_guard.py`, lägg till i `allowed_methods`: `"save_workspace_prompt"`. I `allowed_tool_args`: `"save_workspace_prompt": {"title", "content", "category", "source", "risk_check_passed", "idempotency_key"}`. Lägg till en gren i `inspect_tool_args` som kräver att `title`/`content`/`category` är icke-tomma strängar (samma mönster som `get_skill`-grenen).

### Ej berört

- `promptbanken/mcp-server/` (lokala repot) — ingen write där i denna version.
- `enforce_content_access_model()`-triggern i Supabase — återanvänds helt oförändrad.
- `admin.html`/`admin.js` (i `promptbanken`-repot) — ingen UI-ändring krävs, raden dyker upp under befintliga "Mina prompts" som vilken annan prompt som helst (status `draft`).

## Testplan

Manuell verifiering (matchar befintligt mönster i båda repona, inga automatiserade tester):

1. `ast.parse` på ändrade Python-filer i detta repo.
2. Mot staging-Supabase: anropa `save_prompt_for_key` direkt via `curl`/SQL med en påhittad nyckel → tydligt fel, `invalid_key` loggat.
3. Skapa en riktig Pro-testnyckel, anropa `save_workspace_prompt` via `/mcp` JSON-RPC (med `risk_check_passed=true`) → raden dyker upp i `content_items` med rätt `workspace_id`/`owner_user_id`/`visibility='private'`/`status='draft'`/`source`/`slug`, `success` loggat.
4. Samma via `POST /api/v1/my-prompts` → identiskt resultat.
5. Free-nyckel → planfel, `not_pro` loggat.
6. `risk_check_passed=false`/utelämnad → avvisas, `risk_check_not_passed` loggat.
7. Tom `title`/extremt lång `content` → avvisas, `invalid_input` loggat.
8. Samma `idempotency_key` två gånger → andra gången returnerar samma rad, `idempotent_hit` loggat.
9. 11 anrop inom 60s → 11:e avvisas, `rate_limited` loggat.
10. Fyll test-arbetsyta till `max_prompts` → nästa anrop får gränsfel, `limit_reached` loggat.
11. `hosted_guard.py` avvisar `save_workspace_prompt` med extra/felaktiga argument (t.ex. saknad `category`).
12. `check_input_risk` (nyporterad) svarar identiskt mellan lokala och hostade repot för samma indata (t.ex. text med ett personnummer).
13. Bygg om Docker-image lokalt (`docker compose build`), rök-testa `/healthz` + `tools/list` innehåller `save_workspace_prompt` och `check_input_risk`.
14. Deploy till VPS, upprepa steg 3–4 mot `https://mcp.promptbanken.se`.
15. Rensa testnyckel/testdata efter verifiering.

## Uttryckligen utanför scope v1

- Delning till `shared_workspace_addons` via write-verktyget.
- Semantisk/dubblettdetektering.
- Versionshistorik på mallar.
- Separat "rapportera missad GDPR-risk"-väg.
- Confidence-tröskel eller låst kategorienum.
- Write-stöd i lokala `promptbanken/mcp-server/`.
- Retention/radering av `mcp_write_attempts`.
- `search_path`-uppstädning på befintliga läs-RPC:er (separat TODO).
