# OpenAI Publication Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicera Promptbanken Öppen som en stabil read-only MCP-integration hos OpenAI utan att exponera Valvet, och behåll Free-/Pro-nycklar på en separat kompatibilitetsyta tills OAuth 2.1 är klart.

**Architecture:** `https://mcp.promptbanken.se/mcp` blir det enda OpenAI-publicerade kontraktet och returnerar alltid den publika katalogens nio read-only-verktyg. Befintlig nyckelbaserad Valvet-åtkomst flyttas till `/mcp/key`, där en giltig Free- eller Pro-nyckel krävs innan privata verktyg listas eller anropas. OAuth och sammanslagning av Valvet på den universella `/mcp`-endpointen är en separat efterföljande plan.

**Tech Stack:** Python 3.12, Starlette, MCP 1.2.0, unittest, Supabase RPC, Docker Compose.

## Global Constraints

- `/mcp` ska vara anonym, read-only och den enda endpoint som skickas till OpenAI.
- `/mcp/key` är en tillfällig, icke publicerad kompatibilitetsendpoint.
- En statisk MCP-nyckel får aldrig låsa upp privata verktyg på `/mcp`.
- `/mcp/key` måste verifiera nyckeln innan privata verktyg listas eller anropas.
- Free och Pro har samma basverktyg i Valvet, inklusive paketaktivering.
- Free och Pro skiljs genom kvoter, usage och innehållsbehörighet.
- `tools/list` är inte ett säkerhetslager; varje `tools/call` auktoriseras separat.
- Service-role-nycklar, rå prompttext och personuppgifter får inte loggas.

---

## File Map

- Modify: `mcp-server/server/mcp_server.py` - endpointprofiler, verktygsmetadata, routing och auktorisering.
- Modify: `mcp-server/server/hosted_guard.py` - tillåt båda MCP-vägarna utan att släppa igenom okända argument.
- Create: `mcp-server/tests/test_openai_publication_contract.py` - kontraktstester för publicerad och nyckelbaserad verktygsyta.
- Modify: `mcp-server/README.md` - klientadresser, auth-gräns och avvecklingsmodell.
- Modify: `README.md` - drifts- och produktöversikt.
- Create: `docs/openai-submission-checklist.md` - konkreta submissionsfält, länkar och manuella verifieringar.

### Task 1: Lås den publicerade verktygsytan som ett testat kontrakt

**Files:**
- Create: `mcp-server/tests/test_openai_publication_contract.py`
- Modify: `mcp-server/server/mcp_server.py`

**Interfaces:**
- Consumes: `_PUBLIC_OPEN_TOOL_NAMES`, `_tool_definitions(mcp_key: str = "")`.
- Produces: `_tool_definitions_for_profile(profile: str) -> list[dict[str, Any]]`, där `profile` är `"public"` eller `"key_authenticated"`.

- [ ] **Step 1: Skriv kontraktstestet för exakt publik verktygslista**

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.mcp_server import _tool_definitions_for_profile


PUBLIC_TOOLS = {
    "health_check",
    "get_client_routing_instructions",
    "list_templates",
    "search_templates",
    "get_template",
    "list_packages",
    "get_package",
    "list_package_prompts",
    "recommend_packages",
}


class OpenAIPublicationContractTests(unittest.TestCase):
    def test_public_profile_exposes_exactly_public_read_only_tools(self) -> None:
        tools = _tool_definitions_for_profile("public")
        self.assertEqual({tool["name"] for tool in tools}, PUBLIC_TOOLS)
```

- [ ] **Step 2: Kör testet och verifiera att det fallerar**

Run: `python -m unittest mcp-server/tests/test_openai_publication_contract.py -v`

Expected: FAIL eftersom `_tool_definitions_for_profile` inte finns.

- [ ] **Step 3: Implementera explicit profilval**

Lägg till i `mcp-server/server/mcp_server.py` direkt efter `_tool_definitions`:

```python
def _tool_definitions_for_profile(profile: str) -> list[dict[str, Any]]:
    if profile == "public":
        return _tool_definitions("")
    if profile == "key_authenticated":
        return _tool_definitions("__verified_key__")
    raise ValueError(f"Unknown MCP tool profile: {profile}")
```

Ersätt inte auktorisering med denna helper. Den väljer endast verktygsmetadata.

- [ ] **Step 4: Kör kontraktstestet**

Run: `python -m unittest mcp-server/tests/test_openai_publication_contract.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp-server/server/mcp_server.py mcp-server/tests/test_openai_publication_contract.py
git commit -m "test: lock OpenAI public MCP tool contract"
```

### Task 2: Lägg korrekta OpenAI/MCP-annotations på publika verktyg

**Files:**
- Modify: `mcp-server/server/mcp_server.py`
- Modify: `mcp-server/tests/test_openai_publication_contract.py`

**Interfaces:**
- Consumes: `_tool_definitions_for_profile("public")`.
- Produces: `_public_tool_annotations(title: str) -> dict[str, Any]`.

- [ ] **Step 1: Lägg till ett fallerande metadatatest**

```python
    def test_public_tools_have_review_ready_annotations(self) -> None:
        for tool in _tool_definitions_for_profile("public"):
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["annotations"]["title"])
                self.assertIs(tool["annotations"]["readOnlyHint"], True)
                self.assertIs(tool["annotations"]["destructiveHint"], False)
                self.assertIs(tool["annotations"]["openWorldHint"], False)
                self.assertFalse(tool["inputSchema"].get("additionalProperties", True))
```

- [ ] **Step 2: Kör testet och verifiera att annotations saknas**

Run: `python -m unittest mcp-server/tests/test_openai_publication_contract.py -v`

Expected: FAIL med `KeyError: 'annotations'`.

- [ ] **Step 3: Lägg till metadatahelpern**

```python
def _public_tool_annotations(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    }
```

Lägg `annotations: _public_tool_annotations("<svensk titel>")` på exakt de nio
verktygen i `_PUBLIC_OPEN_TOOL_NAMES`. Använd titlarna:

```python
{
    "health_check": "Kontrollera tjänstens status",
    "get_client_routing_instructions": "Hämta routing- och integritetsregler",
    "list_templates": "Lista publicerade promptmallar",
    "search_templates": "Sök publicerade promptmallar",
    "get_template": "Hämta en publicerad promptmall",
    "list_packages": "Lista publicerade promptpaket",
    "get_package": "Hämta ett publicerat promptpaket",
    "list_package_prompts": "Lista mallar i ett promptpaket",
    "recommend_packages": "Rekommendera promptpaket för en roll",
}
```

- [ ] **Step 4: Kör hela unittest-sviten**

Run: `python -m unittest discover -s mcp-server/tests -v`

Expected: alla tester PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp-server/server/mcp_server.py mcp-server/tests/test_openai_publication_contract.py
git commit -m "feat: add review-ready public tool metadata"
```

### Task 3: Separera publicerad `/mcp` från nyckelbaserad `/mcp/key`

**Files:**
- Modify: `mcp-server/server/mcp_server.py`
- Modify: `mcp-server/server/hosted_guard.py`
- Modify: `mcp-server/tests/test_openai_publication_contract.py`

**Interfaces:**
- Consumes: `_mcp_key_from_request(request)`, `_supabase_repo_for_key(mcp_key)`, `SupabaseRepository.key_is_valid()`.
- Produces: `_handle_mcp_message(message, mcp_key="", tool_profile="public")` och `_mcp_key_streamable_http(request)`.

- [ ] **Step 1: Skriv tester för separerade profiler**

```python
from unittest.mock import patch

from server.mcp_server import _handle_mcp_message


    def test_public_profile_stays_public_even_when_key_is_present(self) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "valid-key",
            tool_profile="public",
        )
        self.assertEqual(
            {tool["name"] for tool in response["result"]["tools"]},
            PUBLIC_TOOLS,
        )

    @patch("server.mcp_server._mcp_key_is_valid", return_value=True)
    def test_key_profile_exposes_valvet_for_verified_free_or_pro_key(self, _) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "valid-key",
            tool_profile="key_authenticated",
        )
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("list_my_items", names)
        self.assertIn("activate_package", names)
        self.assertIn("deactivate_package", names)

    @patch("server.mcp_server._mcp_key_is_valid", return_value=False)
    def test_key_profile_rejects_invalid_key_before_listing_private_tools(self, _) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "invalid-key",
            tool_profile="key_authenticated",
        )
        self.assertEqual(response["error"]["code"], -32001)
```

- [ ] **Step 2: Kör testerna och verifiera signaturfelet**

Run: `python -m unittest mcp-server/tests/test_openai_publication_contract.py -v`

Expected: FAIL eftersom `tool_profile` och `_mcp_key_is_valid` saknas.

- [ ] **Step 3: Implementera nyckelverifiering och profilbaserad dispatch**

```python
def _mcp_key_is_valid(mcp_key: str) -> bool:
    if not mcp_key:
        return False
    repo = _supabase_repo_for_key(mcp_key)
    return repo is not None and repo.key_is_valid()
```

Ändra signaturen:

```python
def _handle_mcp_message(
    message: dict[str, Any],
    mcp_key: str = "",
    tool_profile: str = "public",
) -> dict[str, Any] | None:
```

Implementera `tools/list` så här:

```python
    if method == "tools/list":
        if tool_profile == "key_authenticated" and not _mcp_key_is_valid(mcp_key):
            return _json_rpc_error(request_id, -32001, "Ogiltig eller återkallad MCP-nyckel.")
        return _json_rpc_result(
            request_id,
            {"tools": _tool_definitions_for_profile(tool_profile)},
        )
```

Före `tools/call`, avvisa alla icke-publika verktyg när `tool_profile == "public"`
även om en header innehåller en nyckel. När profilen är `key_authenticated`,
verifiera nyckeln före privata anrop.

- [ ] **Step 4: Skapa den separata HTTP-handlern och routen**

Extrahera befintlig body-parsning till:

```python
async def _mcp_http_response(request: Request, tool_profile: str) -> Response:
    # Behåll befintlig GET/DELETE-, JSON-, batch- och 202-logik.
```

Låt handlerna vara:

```python
async def _mcp_streamable_http(request: Request) -> Response:
    return await _mcp_http_response(request, "public")


async def _mcp_key_streamable_http(request: Request) -> Response:
    return await _mcp_http_response(request, "key_authenticated")
```

Registrera:

```python
Route("/mcp", endpoint=_mcp_streamable_http, methods=["GET", "POST", "DELETE"]),
Route("/mcp/key", endpoint=_mcp_key_streamable_http, methods=["GET", "POST", "DELETE"]),
```

Utöka `OriginValidationMiddleware` och `HostedMetadataGuardMiddleware` från
bara `/mcp` till `{"/mcp", "/mcp/key"}`.

- [ ] **Step 5: Kör alla tester**

Run: `python -m unittest discover -s mcp-server/tests -v`

Expected: alla tester PASS, inklusive att paketaktivering listas för den
verifierade nyckelprofilen.

- [ ] **Step 6: Commit**

```powershell
git add mcp-server/server/mcp_server.py mcp-server/server/hosted_guard.py mcp-server/tests/test_openai_publication_contract.py
git commit -m "feat: separate public and key-authenticated MCP surfaces"
```

### Task 4: Dokumentera klientgränsen och submissionsmaterialet

**Files:**
- Modify: `mcp-server/README.md`
- Modify: `README.md`
- Create: `docs/openai-submission-checklist.md`

**Interfaces:**
- Consumes: public endpoint `/mcp`, compatibility endpoint `/mcp/key`.
- Produces: en granskningsbar checklista med endast verifierbara fält.

- [ ] **Step 1: Dokumentera endpointmatrisen**

Lägg följande tabell i båda README-filerna:

```markdown
| Yta | Endpoint | Auth | Verktyg | Publiceras hos OpenAI |
|---|---|---|---|---|
| Promptbanken Öppen | `/mcp` | Ingen | Publik katalog, read-only | Ja |
| Valvet kompatibilitet | `/mcp/key` | `X-MCP-Key` eller Bearer MCP-nyckel | Free/Pro Valvet | Nej |
| Valvet framtida | `/mcp` | OAuth 2.1 | Publik katalog + personligt Valv | Efter separat release |
```

Dokumentera uttryckligen att paketaktivering ingår för både Free och Pro och
att planerna skiljs genom kvoter.

- [ ] **Step 2: Skapa submissionschecklistan**

Skapa `docs/openai-submission-checklist.md` med följande avsnitt och
checkboxar:

```markdown
# OpenAI Submission Checklist

## Server
- [ ] Produktions-URL: `https://mcp.promptbanken.se/mcp`
- [ ] Anonym `initialize`, `tools/list` och samtliga nio publika `tools/call` fungerar
- [ ] Inga privata eller skrivande verktyg syns eller kan anropas
- [ ] Verktygsnamn, svenska titlar, beskrivningar, scheman och annotations är verifierade

## Listing
- [ ] Plugin-namn och kort beskrivning är slutgranskade
- [ ] Logotyp är kvadratisk och godkänd för publicering
- [ ] Privacy policy har publik HTTPS-URL
- [ ] Användarvillkor har publik HTTPS-URL
- [ ] Supportkontakt och support-URL fungerar

## Review Evidence
- [ ] Testprompt för att söka en mall är dokumenterad med förväntat svar
- [ ] Testprompt för att lista paket är dokumenterad med förväntat svar
- [ ] Testprompt för rollrekommendation är dokumenterad med förväntat svar
- [ ] Testprompt utan träff ger tom lista utan fel
- [ ] Test av privat verktygsnamn ger säkert MCP-fel utan sidoeffekt

## Security
- [ ] Loggar innehåller inte rå prompttext, MCP-nycklar eller personuppgifter
- [ ] Rate limiting och timeout-beteende är verifierat
- [ ] Privacy- och routinginstruktionen förbjuder rå persondata till den öppna MCP:n
```

- [ ] **Step 3: Kontrollera dokumentens interna länkar och adresser**

Run: `rg -n "/mcp/key|OpenAI|OAuth 2.1|activate_package" README.md mcp-server/README.md docs/openai-submission-checklist.md`

Expected: båda endpointadresserna, OAuth-gränsen och paketaktivering för
Free/Pro framgår utan motstridiga formuleringar.

- [ ] **Step 4: Commit**

```powershell
git add README.md mcp-server/README.md docs/openai-submission-checklist.md
git commit -m "docs: define OpenAI submission boundary"
```

### Task 5: Lokal releaseverifiering och VPS-röktest

**Files:**
- Modify: `docs/openai-submission-checklist.md`

**Interfaces:**
- Consumes: färdig Docker-image och båda MCP-endpoints.
- Produces: dokumenterade testresultat inför submission.

- [ ] **Step 1: Kör Python- och Docker-verifiering lokalt**

```powershell
python -m unittest discover -s mcp-server/tests -v
docker compose build
```

Expected: alla tester PASS och image byggs utan fel.

- [ ] **Step 2: Röktesta publik profil lokalt**

```powershell
$body = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
$public = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp -ContentType application/json -Body $body
$public.result.tools.name
```

Expected: exakt de nio namnen i `PUBLIC_TOOLS`; inga Valvet- eller
skrivverktyg.

- [ ] **Step 3: Röktesta ogiltig och giltig nyckelprofil lokalt**

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp/key -Headers @{"X-MCP-Key"="invalid"} -ContentType application/json -Body $body
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp/key -Headers @{"X-MCP-Key"=$env:PROMPTBANKEN_FREE_TEST_KEY} -ContentType application/json -Body $body
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp/key -Headers @{"X-MCP-Key"=$env:PROMPTBANKEN_PRO_TEST_KEY} -ContentType application/json -Body $body
```

Expected: ogiltig nyckel ger MCP-fel `-32001`; både Free och Pro listar
`list_active_packages`, `activate_package` och `deactivate_package`.

- [ ] **Step 4: Verifiera paketaktivering med både Free och Pro**

```powershell
$activate = '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"activate_package","arguments":{"area":"kommunikation"}}}'
$deactivate = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"deactivate_package","arguments":{"area":"kommunikation"}}}'
foreach ($key in @($env:PROMPTBANKEN_FREE_TEST_KEY, $env:PROMPTBANKEN_PRO_TEST_KEY)) {
    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp/key -Headers @{"X-MCP-Key"=$key} -ContentType application/json -Body $activate
    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp/key -Headers @{"X-MCP-Key"=$key} -ContentType application/json -Body $deactivate
}
```

Expected: alla fyra anrop lyckas. Deaktiveringen återställer testets
utgångsläge.

- [ ] **Step 5: Deploya enligt VPS-runbook och verifiera produktion**

Kör från VPS i `~/mcp_promptbanken`:

```bash
git pull --ff-only
docker-compose build promptbanken-mcp
docker-compose up -d --force-recreate promptbanken-mcp
docker-compose ps
curl -fsS https://mcp.promptbanken.se/healthz
```

Röktesta därefter `https://mcp.promptbanken.se/mcp` med samma anonyma
`tools/list`-body och bekräfta exakt nio publika verktyg.

- [ ] **Step 6: Fyll endast verifierade checkboxar i submissionchecklistan**

Markera en checkbox som klar först när kommandot eller den publika URL:en
faktiskt har kontrollerats. Privacy policy, villkor och support får inte
markeras klara utifrån antagande.

- [ ] **Step 7: Commit**

```powershell
git add docs/openai-submission-checklist.md
git commit -m "docs: record OpenAI publication verification"
```

## Separat efterföljande plan

OAuth 2.1 för Valvet ska planeras och implementeras separat. Den planen ska
omfatta authorization-server metadata, PKCE, dynamisk klientregistrering eller
godkänd klientkonfiguration, tokenvalidering, scope-till-capability-mappning,
workspaceval, återkallelse och migration från `/mcp/key` till `/mcp`.

Den får inte påbörjas genom att tolka en statisk MCP-nyckel som OAuth-token.
