# health_check: catalog/plan/message-fält

## Syfte

`health_check` (REST `GET /healthz` och MCP-verktyget/JSON-RPC-metoden) ska hjälpa en klient — och en människa som felsöker — att omedelbart se vilken katalog-nivå en given `X-MCP-Key`/`Authorization`-nyckel ger tillgång till, utan att behöva göra ett separat anrop mot `/api/v1/skills` eller `/api/v1/pro-templates` och tolka `workspace_status` där.

## Bakgrund

`health_check` returnerar idag bara `status`, `service`, `version`, `mode`, `skills_count` — statiskt, oavsett vilken nyckel (om någon) som skickas med. Det finns inget sätt att på en enda rad se om en nyckel är giltig, vilken plan den tillhör, eller vad som händer om ingen nyckel skickas alls.

Vi har redan motsvarande mönster för `list_skills_simple`/REST `GET /api/v1/skills`: fälten `workspace_status` (`"ok"`/`"invalid_key"`, utelämnat om ingen nyckel skickas) och `workspace_message` (läsbar svensk text). Den här designen bygger vidare på samma idé men för `health_check`, med en bredare uppsättning tillstånd (public/free/pro, inte bara giltig/ogiltig).

## Tillstånd och fält

Tre nya fält läggs till i `health_check`-svaret: `catalog`, `plan`, `message`.

| Tillstånd | `plan` | `catalog` | `message` |
|---|---|---|---|
| Ingen nyckel skickad | `public` | `open` | "Detta är den öppna katalogen. Autentisera med API/MCP-nyckel för användar- eller Pro-mallar på kommun.promptbanken.se." |
| Nyckel skickad men ogiltig/återkallad | `public` | `open` | Samma text som befintlig `workspace_message` för `invalid_key` i `mcp_server.py` (`_WORKSPACE_STATUS_MESSAGES["invalid_key"]`) — återanvänds som en sanningskälla, ingen dubblettsträng. |
| Giltig nyckel, `workspaces.plan = 'free'` | `free` | `workspace` | "Inloggad med en free-nyckel. Publika mallar och dina egna sparade prompts är tillgängliga. Uppgradera till Pro för premium-mallar." |
| Giltig nyckel, `workspaces.plan = 'pro'` | `pro` | `pro` | "Inloggad med en Pro-nyckel. Publika mallar, dina sparade prompts och premium-mallarna är tillgängliga." |

Dessa fält finns **alltid** i svaret (till skillnad från `workspace_status`/`workspace_message` på `/api/v1/skills`, som utelämnas helt utan nyckel) — `health_check` är tänkt att alltid ge en fullständig bild av katalogläget, inte bara flagga avvikelser.

`catalog` uttrycker tillgångsnivå (`open`/`workspace`/`pro`), `plan` uttrycker den råa plan-etiketten. De är avsiktligt separata fält trots att de idag är 1:1-mappade, så att framtida avvikelser (t.ex. en free-nyckel som ändå får ett tillfälligt pro-lyft) kan uttryckas utan att skriva om kontraktet.

## Kodändringar

### `supabase_repository.py`

`_resolve_workspace()` kastar idag bort `plan`/`workspace_type` från `verify_mcp_key`-RPC:ns svar och sparar bara `workspace_id`. Utöka till att spara `plan`/`workspace_type` också, och exponera `plan` via en ny publik property:

```python
@property
def plan(self) -> str | None:
    self._resolve_workspace()
    return self._plan
```

### `mcp_server.py`

Ny helper `_health_check_payload(mcp_key: str = "") -> dict[str, Any]`:

- Bygger på samma bas som dagens `health_check()` (`status`/`service`/`version`/`mode`/`skills_count`).
- Om `mcp_key` är tom: tillstånd `no_key` → `plan="public"`, `catalog="open"`.
- Om `mcp_key` finns men `SupabaseRepository.key_is_valid()` är `False`: tillstånd `invalid_key` → `plan="public"`, `catalog="open"`, meddelande återanvänder `_WORKSPACE_STATUS_MESSAGES["invalid_key"]`.
- Om giltig: läs `repo.plan`; `"pro"` → tillstånd `pro`, annat (inkl. `"free"` eller okänt) → tillstånd `free`. (Endast `free`/`pro` finns i denna version — `team`/organisationstyp är explicit uteslutet från denna design.)
- Slå upp `catalog`/`plan`/`message` ur en liten lookup-tabell per tillstånd (`no_key`, `invalid_key`, `free`, `pro`).

Anropsplatser som uppdateras till att skicka med `mcp_key`:
- REST `_healthz(request)` — idag `async def _healthz(_: Request)`, döps om parametern och läser `mcp_key = _mcp_key_from_request(request)`.
- `_handle_mcp_message`, grenen `tool_name == "health_check"` — skickar redan `mcp_key` in i funktionen, ändras till att anropa `_health_check_payload(mcp_key)` istället för `health_check()`.

Oförändrat:
- Den fristående `@mcp.tool() def health_check()` (stdio-läge, ingen HTTP-header-kontext) fortsätter anropa utan nyckel — samma asymmetri som redan finns för `list_skills`/`list_pro_templates` i stdio-läge.
- `hosted_guard.py` — inga ändringar. `health_check` har redan `set()` som tillåtna argument i guardens allowlist; vi ändrar bara svarets innehåll, inte anropets form/argument.
- Caddyfile/routes — inga ändringar, `/healthz` är redan en egen `handle`-sektion.

## Prestandaeffekt

En extra Supabase-nätverksanrop (`verify_mcp_key`-RPC) görs bara när en nyckel faktiskt skickas med — samma mönster som `list_skills_simple` redan använder. `/healthz` utan nyckel (t.ex. Dockers `HEALTHCHECK` eller uptime-monitorer som inte skickar någon `X-MCP-Key`) förblir lika snabb som idag, ingen extra nätverksväg.

## Testplan

Manuell verifiering (matchar hur `workspace_status`-arbetet verifierades tidigare i detta repo, inga automatiserade tester finns i repot):

1. `curl /healthz` utan nyckel → `plan="public"`, `catalog="open"`, no_key-meddelandet.
2. `curl /healthz -H "X-MCP-Key: <ogiltig>"` → `plan="public"`, `catalog="open"`, samma text som `workspace_message` för `invalid_key`.
3. `curl /healthz -H "X-MCP-Key: <giltig free-nyckel>"` → `plan="free"`, `catalog="workspace"`.
4. `curl /healthz -H "X-MCP-Key: <giltig pro-nyckel>"` → `plan="pro"`, `catalog="pro"`.
5. MCP JSON-RPC `tools/call` med `name="health_check"` över `/mcp` med samma fyra nyckel-varianter, verifiera att svaret matchar REST-varianten.
6. Bekräfta att `docker-compose ps`/`healthz` som infra-hälsokontroll (utan nyckel) fortfarande fungerar oförändrat efter deploy.

## Dokumentation

README.md och CLAUDE.md uppdateras med de nya fälten i `health_check`-avsnittet, i samma stil som `workspace_status`/`workspace_message`-dokumentationen som redan finns där. `TODO.md` får en ny post under "Klart" när arbetet är verifierat i produktion.
