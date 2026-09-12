# Standalone Admin-MCP OAuth Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bygg en fristående OAuth-skyddad MCP-tjänst som exponerar exakt Promptbankens 20 befintliga adminverktyg plus `get_admin_context` och alltid agerar som den inloggade användaren.

**Architecture:** En liten Starlette-app validerar Supabase JWT lokalt mot JWKS, kräver `sub`, `aud=authenticated` och `client_id`, och hämtar databastvingad adminstatus med användarens egen bearer-token. Verktygsdefinitionerna ligger i en versionslåst snapshot; ett fokuserat repositorylager vidarebefordrar samma token till befintliga Supabase-RPC:er utan service role, statisk adminnyckel eller sparad refresh token.

**Tech Stack:** Python 3.12, Starlette 0.46.2, Uvicorn 0.34.0, HTTPX 0.28.1, PyJWT 2.10.1 med crypto, pytest, Ruff, Pyright, Docker Compose

**Spec:** `../specs/2026-09-11-admin-mcp-oauth-service-design.md`

## Global Constraints

- Skapa ett nytt syskonrepo `promptbanken-admin-mcp`; importera inte kod från den körande Connect-processen.
- Använd samma verifierade dependency-versioner som nuvarande Connect i första versionen; uppgradering är en separat ändring.
- Endpoint är `https://admin-mcp.promptbanken.se/mcp`; lokalt lyssnar containern på `127.0.0.1:8012`.
- OAuth issuer är Promptbankens Supabase Auth URL, audience är exakt `authenticated`, och OAuth-trafik måste ha ett icke-tomt `client_id`.
- Servern får endast använda `SUPABASE_URL` och `SUPABASE_PUBLISHABLE_KEY`; miljövariabler för service role, adminnyckel eller refresh token får inte finnas.
- Behörighetsdata hämtas från `public.get_admin_mcp_context()` för varje skyddad request och cachas inte.
- 401 använder `WWW-Authenticate: Bearer resource_metadata="https://admin-mcp.promptbanken.se/.well-known/oauth-protected-resource/mcp", scope="openid email profile"`; 403 används för giltig men otillåten identitet.
- OAuth-scopes styr identitetsfält, inte databasbehörighet; roll och `client_id` förblir den verkliga grinden.
- Token endpoint måste accepteras vid valfri 2xx-status; ingen kod får förutsätta historiska 201.
- Request body är högst 64 KiB i både app och Caddy.
- Loggar får aldrig innehålla bearer-token, refresh token, Authorization/Cookie-header, full e-postadress, Supabase response body eller stack trace i klientsvar.
- Exakt 21 verktyg exponeras; Open- och Connect-verktyg får inte förekomma.
- De 20 befintliga adminverktygens namn, argument, schemas och `confirm`-semantik porteras oförändrade innan gammal kod får tas bort.
- Dynamiska OAuth-klienter kräver explicit godkännande i databasens privata allowlist.

---

## File Structure

```text
promptbanken-admin-mcp/
  .env.example
  .gitignore
  README.md
  Dockerfile
  docker-compose.yml
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  mcp-contract.json
  contracts/
    admin-mcp-1.0.0.tools.json
  admin_mcp/
    __init__.py
    __main__.py
    app.py
    auth.py
    config.py
    contract.py
    repository.py
    tools.py
  scripts/
    test-live-contract.ps1
  tests/
    test_app.py
    test_auth.py
    test_config.py
    test_contract.py
    test_repository.py
    test_tools.py
```

Ansvar:

- `config.py`: fail-fast miljökonfiguration utan hemlighetsloggning.
- `auth.py`: JWT/JWKS-verifiering och typad identitet.
- `contract.py`: läser den versionslåsta verktygssnapshoten.
- `repository.py`: PostgREST-RPC med caller token, authkontext, audit och rate limit.
- `tools.py`: exakt dispatch och argumentöversättning för 21 verktyg.
- `app.py`: HTTP/MCP, 401/403 och sanerad felmodell.
- `__main__.py`: enda produktionsstartpunkt.

### Task 1: Skapa ett minimalt, låst Python-repo

**Files:**
- Create: `../promptbanken-admin-mcp/.gitignore`
- Create: `../promptbanken-admin-mcp/requirements.txt`
- Create: `../promptbanken-admin-mcp/requirements-dev.txt`
- Create: `../promptbanken-admin-mcp/pyproject.toml`
- Create: `../promptbanken-admin-mcp/admin_mcp/__init__.py`
- Create: `../promptbanken-admin-mcp/tests/test_config.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/config.py`

**Interfaces:**
- Consumes: fyra miljövärden — `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `OAUTH_ISSUER`, `OAUTH_JWKS_URL`.
- Produces: `Settings.from_env() -> Settings`.

- [ ] **Step 1: Skapa katalogen och Git-repot lokalt**

```powershell
New-Item -ItemType Directory -Path ..\promptbanken-admin-mcp
Set-Location ..\promptbanken-admin-mcp
git init
git branch -M main
New-Item -ItemType Directory -Path admin_mcp,contracts,scripts,tests
```

Skapa inte ett externt GitHub-repo i denna task; det är en separat extern åtgärd i rolloutplanen.

- [ ] **Step 2: Skriv konfigurationstestet först**

```python
import pytest

from admin_mcp.config import Settings


def test_settings_require_every_public_configuration_value(monkeypatch):
    for key in (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "OAUTH_ISSUER",
        "OAUTH_JWKS_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="Saknad konfiguration"):
        Settings.from_env()


def test_settings_build_canonical_resource_urls(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable")
    monkeypatch.setenv("OAUTH_ISSUER", "https://project.supabase.co/auth/v1")
    monkeypatch.setenv(
        "OAUTH_JWKS_URL",
        "https://project.supabase.co/auth/v1/.well-known/jwks.json",
    )

    settings = Settings.from_env()

    assert settings.resource_url == "https://admin-mcp.promptbanken.se/mcp"
    assert settings.audience == "authenticated"
```

- [ ] **Step 3: Kör testet och verifiera rött läge**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
```

Förväntat: FAIL eftersom `admin_mcp.config` saknas.

- [ ] **Step 4: Lägg in låsta beroenden och minimal konfiguration**

`requirements.txt`:

```text
PyJWT[crypto]==2.10.1
httpx==0.28.1
starlette==0.46.2
uvicorn==0.34.0
jsonschema==4.23.0
```

`requirements-dev.txt`:

```text
-r requirements.txt
pytest==8.3.5
ruff==0.11.2
pyright==1.1.398
```

`config.py` ska använda:

```python
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    publishable_key: str
    issuer: str
    jwks_url: str
    audience: str = "authenticated"
    resource_url: str = "https://admin-mcp.promptbanken.se/mcp"
    max_body_bytes: int = 65_536

    @classmethod
    def from_env(cls) -> "Settings":
        values = {
            "supabase_url": os.getenv("SUPABASE_URL", "").rstrip("/"),
            "publishable_key": os.getenv("SUPABASE_PUBLISHABLE_KEY", ""),
            "issuer": os.getenv("OAUTH_ISSUER", "").rstrip("/"),
            "jwks_url": os.getenv("OAUTH_JWKS_URL", ""),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(f"Saknad konfiguration: {', '.join(missing)}")
        return cls(**values)
```

- [ ] **Step 5: Lägg in lint/typecheck-konfiguration**

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
include = ["admin_mcp"]
```

`.gitignore` ska minst innehålla `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `*.pyc`, `.ruff_cache/` och `.pyright/`.

- [ ] **Step 6: Kör grönt och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
.\.venv\Scripts\python.exe -m ruff check .
git add .gitignore requirements.txt requirements-dev.txt pyproject.toml admin_mcp tests/test_config.py
git commit -m "chore: scaffold standalone Admin MCP service"
```

Förväntat: tester och Ruff exit code 0.

### Task 2: Verifiera Supabase JWT fail-closed

**Files:**
- Create: `../promptbanken-admin-mcp/tests/test_auth.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/auth.py`

**Interfaces:**
- Consumes: compact bearer JWT, issuer, audience och JWKS URL.
- Produces: `VerifiedIdentity(user_id: str, client_id: str, email: str | None)` och `SupabaseJwtVerifier.verify(token: str) -> VerifiedIdentity`.

- [ ] **Step 1: Skriv positiva och negativa JWT-tester**

Använd en lokalt genererad RSA-testnyckel och monkeypatcha `PyJWKClient`.
Testerna ska omfatta:

```python
def test_verify_requires_subject_and_oauth_client(verifier, signed_token):
    identity = verifier.verify(
        signed_token(
            sub="00000000-0000-0000-0000-000000000001",
            client_id="00000000-0000-0000-0000-00000000a001",
            aud="authenticated",
        )
    )
    assert identity.user_id == "00000000-0000-0000-0000-000000000001"
    assert identity.client_id == "00000000-0000-0000-0000-00000000a001"


@pytest.mark.parametrize(
    "override",
    [
        {"aud": "another-service"},
        {"iss": "https://attacker.example/auth/v1"},
        {"sub": ""},
        {"client_id": ""},
    ],
)
def test_verify_rejects_wrong_or_missing_required_claim(verifier, signed_token, override):
    with pytest.raises(InvalidAccessToken):
        verifier.verify(signed_token(**override))
```

Lägg separata tester för utgången token, HS256, trasig signatur och
`PyJWKClientError`. Ingen assertion får förvänta rå token i felmeddelandet.

- [ ] **Step 2: Kör och verifiera rött läge**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py -v
```

Förväntat: FAIL eftersom verifieraren saknas.

- [ ] **Step 3: Implementera den minsta verifieraren**

```python
from dataclasses import dataclass

import jwt
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError


class InvalidAccessToken(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedIdentity:
    user_id: str
    client_id: str
    email: str | None


class SupabaseJwtVerifier:
    def __init__(self, *, issuer: str, audience: str, jwks_url: str) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "iss", "aud", "client_id"]},
            )
        except (InvalidTokenError, PyJWKClientError) as error:
            raise InvalidAccessToken("Ogiltig åtkomsttoken.") from error

        user_id = claims.get("sub")
        client_id = claims.get("client_id")
        email = claims.get("email")
        if not isinstance(user_id, str) or not user_id:
            raise InvalidAccessToken("Åtkomsttoken saknar användaridentitet.")
        if not isinstance(client_id, str) or not client_id:
            raise InvalidAccessToken("Åtkomsttoken saknar OAuth-klient.")
        return VerifiedIdentity(
            user_id=user_id,
            client_id=client_id,
            email=email if isinstance(email, str) and email else None,
        )
```

`PyJWKClient` ska behålla sin inbyggda JWKS-cache och göra högst sin
dokumenterade refresh vid okänd `kid`; lägg ingen egen oändlig retryloop runt
`verify`.

- [ ] **Step 4: Kör tester, lint och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py -v
.\.venv\Scripts\python.exe -m ruff check admin_mcp tests
.\.venv\Scripts\pyright.exe
git add admin_mcp/auth.py tests/test_auth.py
git commit -m "feat: validate Supabase OAuth access tokens"
```

Förväntat: samtliga kommandon exit code 0.

### Task 3: Bygg ett caller-token-bundet Supabase-repository

**Files:**
- Create: `../promptbanken-admin-mcp/tests/test_repository.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/repository.py`

**Interfaces:**
- Consumes: Supabase URL, publishable key och caller access token.
- Produces: `AdminContext`, `SupabaseAdminRepository.get_context(access_token)`, `call_rpc(access_token, function_name, payload)` och `audit(access_token, tool, target_id, outcome, detail)`.

- [ ] **Step 1: Skriv repositorytester med en inspelande HTTP-klient**

Testerna ska bevisa:

```python
def test_get_context_forwards_the_callers_token(repository, http_client):
    http_client.response_json = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email": "owner@example.test",
        "role": "platform_owner",
        "client_id": "00000000-0000-0000-0000-00000000a001",
        "client_approved": True,
        "allowed": True,
    }

    context = repository.get_context("caller-token")

    assert context.allowed is True
    assert http_client.last_headers["Authorization"] == "Bearer caller-token"
    assert http_client.last_path.endswith("/rpc/get_admin_mcp_context")


def test_repository_never_uses_a_service_role_header(repository, http_client):
    repository.call_rpc("caller-token", "list_draft_catalog_prompts", {})
    assert http_client.last_headers["apikey"] == "publishable-test-key"
    assert "service_role" not in str(http_client.last_headers).lower()
```

Lägg även tester för 204, JSON-objekt, JSON-lista, timeout, 401/403/5xx från
Supabase och oväntad JSON-typ. Klientfelet ska vara en typad
`RepositoryUnavailable` eller `RepositoryRejected` utan response body.

- [ ] **Step 2: Kör rött läge**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py -v
```

Förväntat: FAIL eftersom repositorylagret saknas.

- [ ] **Step 3: Implementera typer och den enda HTTP-vägen**

```python
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class HttpClient(Protocol):
    def post(
        self,
        path: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class AdminContext:
    user_id: str
    email: str | None
    role: str
    client_id: str
    client_approved: bool
    allowed: bool


class RepositoryRejected(RuntimeError):
    pass


class RepositoryUnavailable(RuntimeError):
    pass


class SupabaseAdminRepository:
    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        http_client: HttpClient | None = None,
    ) -> None:
        self._client = http_client or httpx.Client(
            base_url=supabase_url.rstrip("/"),
            timeout=httpx.Timeout(15.0),
        )
        self._publishable_key = publishable_key

    def _rpc(self, access_token: str, function_name: str, payload: dict[str, Any]):
        try:
            response = self._client.post(
                f"/rest/v1/rpc/{function_name}",
                headers={
                    "apikey": self._publishable_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise RepositoryRejected("Supabase avvisade anropet.") from error
            raise RepositoryUnavailable("Supabase kunde inte slutföra anropet.") from error
        except httpx.HTTPError as error:
            raise RepositoryUnavailable("Supabase kunde inte nås.") from error

        if response.status_code == 204:
            return None
        return response.json()
```

Lägg därefter in dessa publika metoder på `SupabaseAdminRepository`.
`get_context` kräver ett JSON-objekt med sex fält och verifierar att
`user_id` och `client_id` är icke-tomma strängar. Ingen response body hamnar
i ett undantagsmeddelande:

```python
    def get_context(self, access_token: str) -> AdminContext:
        value = self._rpc(access_token, "get_admin_mcp_context", {})
        if not isinstance(value, dict):
            raise RepositoryUnavailable("Supabase returnerade ogiltig adminkontext.")

        required = {
            "user_id",
            "email",
            "role",
            "client_id",
            "client_approved",
            "allowed",
        }
        if set(value) != required:
            raise RepositoryUnavailable("Supabase returnerade ofullständig adminkontext.")
        if not isinstance(value["user_id"], str) or not value["user_id"]:
            raise RepositoryRejected("Adminanvändaren saknar identitet.")
        if not isinstance(value["client_id"], str) or not value["client_id"]:
            raise RepositoryRejected("OAuth-klienten saknar identitet.")
        if value["email"] is not None and not isinstance(value["email"], str):
            raise RepositoryUnavailable("Supabase returnerade ogiltig adminkontext.")
        if not isinstance(value["role"], str):
            raise RepositoryUnavailable("Supabase returnerade ogiltig adminkontext.")
        if not isinstance(value["client_approved"], bool) or not isinstance(value["allowed"], bool):
            raise RepositoryUnavailable("Supabase returnerade ogiltig adminkontext.")

        return AdminContext(
            user_id=value["user_id"],
            email=value["email"],
            role=value["role"],
            client_id=value["client_id"],
            client_approved=value["client_approved"],
            allowed=value["allowed"],
        )

    def call_rpc(
        self,
        access_token: str,
        function_name: str,
        payload: dict[str, Any],
    ) -> Any:
        return self._rpc(access_token, function_name, payload)

    def audit(
        self,
        access_token: str,
        tool: str,
        target_id: str | None,
        outcome: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._rpc(
            access_token,
            "log_admin_write_attempt",
            {
                "p_tool": tool,
                "p_target_id": target_id,
                "p_outcome": outcome,
                "p_detail": detail,
            },
        )
```

Aktör och `client_id` skickas inte som argument; databasen läser dem ur
JWT-kontexten. Testet för `audit` ska låsa exakt denna payload:

```python
{
    "p_tool": tool,
    "p_target_id": target_id,
    "p_outcome": outcome,
    "p_detail": detail,
}
```

- [ ] **Step 4: Kör grönt och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repository.py -v
.\.venv\Scripts\python.exe -m ruff check admin_mcp tests
.\.venv\Scripts\pyright.exe
git add admin_mcp/repository.py tests/test_repository.py
git commit -m "feat: forward caller identity to Supabase admin RPCs"
```

### Task 4: Lås den exakta verktygssnapshoten

**Files:**
- Create: `../promptbanken-admin-mcp/contracts/admin-mcp-1.0.0.tools.json`
- Create: `../promptbanken-admin-mcp/mcp-contract.json`
- Create: `../promptbanken-admin-mcp/tests/test_contract.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/contract.py`

**Interfaces:**
- Consumes: den granskade `_admin_tool_definitions()` i gamla Open-repot.
- Produces: `load_tool_definitions() -> list[dict[str, object]]` med exakt 21 poster.

- [ ] **Step 1: Skriv det röda kontraktstestet**

```python
from admin_mcp.contract import load_tool_definitions


EXPECTED_NAMES = [
    "get_admin_context",
    "admin_create_prompt",
    "admin_upsert_prompt_variant",
    "admin_list_draft_prompts",
    "admin_get_prompt",
    "admin_publish_prompt",
    "admin_unpublish_prompt",
    "admin_delete_draft_prompt",
    "admin_create_package",
    "admin_upsert_package_variant",
    "admin_upsert_package_metadata",
    "admin_add_prompt_to_package",
    "admin_update_package_item",
    "admin_remove_prompt_from_package",
    "admin_publish_package",
    "admin_unpublish_package",
    "admin_delete_draft_package",
    "admin_list_prompt_history",
    "admin_restore_prompt_version",
    "admin_list_package_history",
    "admin_restore_package_version",
]


def test_tool_snapshot_has_exact_admin_surface():
    definitions = load_tool_definitions()
    assert [tool["name"] for tool in definitions] == EXPECTED_NAMES
    assert len({tool["name"] for tool in definitions}) == 21
```

Lägg detta andra test som jämför hela snapshotfilen via den sökväg som
kontraktet anger, inte bara namnen:

```python
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_contract_points_to_the_loaded_full_snapshot():
    contract = json.loads((ROOT / "mcp-contract.json").read_text(encoding="utf-8"))
    relative = contract["toolGroups"]["admin"]["definitionSnapshot"]
    snapshot = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert load_tool_definitions() == snapshot
```

- [ ] **Step 2: Kör rött läge**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contract.py -v
```

Förväntat: FAIL eftersom snapshot/loader saknas.

- [ ] **Step 3: Exportera den gamla koddefinitionen, inte live-servern**

Från `mcp_promptbanken`-repot:

```powershell
Set-Location ..\mcp_promptbanken\mcp-server
.\.venv\Scripts\python.exe -c "import json; from server.mcp_server import _admin_tool_definitions; print(json.dumps(_admin_tool_definitions(), ensure_ascii=False, indent=2))"
```

Detta skriver den versionsstyrda källan till terminalen för granskning utan
att redigera någon fil. Skapa sedan snapshotfilen med `apply_patch` från det
granskade resultatet. Det är inte en regenerering från live `tools/list`.
Granska alla 20 definitioner mot gamla tester och
`mcp-server/mcp-contract.json`.

- [ ] **Step 4: Lägg `get_admin_context` först i snapshoten**

```json
{
  "name": "get_admin_context",
  "description": "Bekräftar vilken Promptbanken-användare och OAuth-klient Admin-MCP är kopplad till.",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  },
  "annotations": {
    "title": "Visa Admin-MCP-kontext",
    "readOnlyHint": true,
    "destructiveHint": false,
    "openWorldHint": false
  }
}
```

Sätt `additionalProperties: false` på den nya definitionen men ändra inte de
20 porterade schemana i samma commit.

- [ ] **Step 5: Lägg kontrakt och loader**

`mcp-contract.json`:

```json
{
  "version": 1,
  "baseUrl": "https://admin-mcp.promptbanken.se",
  "toolGroups": {
    "admin": {
      "definitionSnapshot": "contracts/admin-mcp-1.0.0.tools.json",
      "tools": [
        "get_admin_context",
        "admin_create_prompt",
        "admin_upsert_prompt_variant",
        "admin_list_draft_prompts",
        "admin_get_prompt",
        "admin_publish_prompt",
        "admin_unpublish_prompt",
        "admin_delete_draft_prompt",
        "admin_create_package",
        "admin_upsert_package_variant",
        "admin_upsert_package_metadata",
        "admin_add_prompt_to_package",
        "admin_update_package_item",
        "admin_remove_prompt_from_package",
        "admin_publish_package",
        "admin_unpublish_package",
        "admin_delete_draft_package",
        "admin_list_prompt_history",
        "admin_restore_prompt_version",
        "admin_list_package_history",
        "admin_restore_package_version"
      ]
    }
  },
  "profiles": {
    "admin_oauth": {
      "endpoint": "/mcp",
      "groups": ["admin"],
      "auth": {
        "type": "oauth_bearer",
        "tokenEnv": "PROMPTBANKEN_ADMIN_OAUTH_TEST_TOKEN"
      },
      "expectUnauthorizedWithoutAuth": true
    }
  }
}
```

`contract.py` ska läsa snapshoten relativt repo-roten, validera att den är en
lista med unika strängnamn och returnera en djup kopia så anropskod inte kan
mutera källan:

```python
from copy import deepcopy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "contracts" / "admin-mcp-1.0.0.tools.json"


def load_tool_definitions() -> list[dict[str, Any]]:
    value = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise RuntimeError("Admin MCP tool snapshot must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise RuntimeError("Every Admin MCP tool definition must be an object")

    names = [item.get("name") for item in value]
    if not all(isinstance(name, str) and name for name in names):
        raise RuntimeError("Every Admin MCP tool must have a non-empty name")
    if len(names) != len(set(names)):
        raise RuntimeError("Admin MCP tool names must be unique")
    if len(names) != 21:
        raise RuntimeError("Admin MCP 1.0.0 must expose exactly 21 tools")
    return deepcopy(value)
```

- [ ] **Step 6: Kör grönt och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contract.py -v
git add contracts mcp-contract.json admin_mcp/contract.py tests/test_contract.py
git commit -m "test: lock Admin MCP 1.0.0 tool contract"
```

### Task 5: Portera exakt dispatch och confirm-skydd

**Files:**
- Create: `../promptbanken-admin-mcp/tests/test_tools.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/tools.py`

**Interfaces:**
- Consumes: `AdminContext`, `SupabaseAdminRepository.call_rpc`, `audit` och kontraktets input schemas.
- Produces: `AdminToolDispatcher.call(name, arguments, access_token, context) -> object`.

- [ ] **Step 1: Skriv tabellstyrda tester för samtliga mappings**

Lås denna mapping i testet:

| MCP-verktyg | Supabase-RPC | Mål-id |
| --- | --- | --- |
| `admin_create_prompt` | `create_catalog_prompt` | resultatets id |
| `admin_upsert_prompt_variant` | `upsert_catalog_prompt_variant` | `prompt_id` |
| `admin_list_draft_prompts` | `list_draft_catalog_prompts` | inget |
| `admin_get_prompt` | `get_catalog_prompt_by_id` | `prompt_id` |
| `admin_publish_prompt` | `publish_catalog_prompt` | `prompt_id` |
| `admin_unpublish_prompt` | `unpublish_catalog_prompt` | `prompt_id` |
| `admin_delete_draft_prompt` | `delete_draft_catalog_prompt` | `prompt_id` |
| `admin_create_package` | `create_catalog_package` | resultatets id |
| `admin_upsert_package_variant` | `upsert_catalog_package_variant` | `package_id` |
| `admin_upsert_package_metadata` | `upsert_catalog_package_metadata` | `package_id` |
| `admin_add_prompt_to_package` | `add_prompt_to_catalog_package` | `package_id` |
| `admin_update_package_item` | `update_catalog_package_item` | `package_id` |
| `admin_remove_prompt_from_package` | `remove_prompt_from_catalog_package` | `package_id` |
| `admin_publish_package` | `publish_catalog_package` | `package_id` |
| `admin_unpublish_package` | `unpublish_catalog_package` | `package_id` |
| `admin_delete_draft_package` | `delete_draft_catalog_package` | `package_id` |
| `admin_list_prompt_history` | `admin_list_prompt_history` | inget |
| `admin_restore_prompt_version` | `admin_restore_prompt_version` | inget |
| `admin_list_package_history` | `admin_list_package_history` | inget |
| `admin_restore_package_version` | `admin_restore_package_version` | inget |

Testa dessutom att `get_admin_context` returnerar det redan verifierade
kontextobjektet utan ett andra RPC-anrop.

- [ ] **Step 2: Skriv negativa confirm- och schemafall**

Alla följande ska ge `InvalidToolArguments` före Supabase-anrop:

- saknad/falsk `confirm` för publish, delete, remove och restore,
- bool som `history_id`,
- saknat obligatoriskt id,
- okänt verktyg,
- Open-verktyget `list_templates`,
- oväntad argumenttyp enligt snapshotens schema.

- [ ] **Step 3: Kör rött läge**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py -v
```

Förväntat: FAIL eftersom dispatchern saknas.

- [ ] **Step 4: Implementera kontraktsvaliderad dispatch**

```python
from dataclasses import asdict, dataclass
import time
from typing import Any

from jsonschema import Draft202012Validator

from admin_mcp.repository import (
    AdminContext,
    RepositoryRejected,
    RepositoryUnavailable,
    SupabaseAdminRepository,
)


class InvalidToolArguments(ValueError):
    pass


class UnknownTool(LookupError):
    pass


CONFIRM_TOOLS = {
    "admin_publish_prompt",
    "admin_delete_draft_prompt",
    "admin_remove_prompt_from_package",
    "admin_publish_package",
    "admin_delete_draft_package",
    "admin_restore_prompt_version",
    "admin_restore_package_version",
}


@dataclass(frozen=True)
class ToolRoute:
    rpc: str
    write: bool
    target_key: str | None = None
    keep_confirm: bool = False
    result_mode: str = "rpc"


ROUTES = {
    "admin_create_prompt": ToolRoute("create_catalog_prompt", True, result_mode="created"),
    "admin_upsert_prompt_variant": ToolRoute("upsert_catalog_prompt_variant", True, "prompt_id"),
    "admin_list_draft_prompts": ToolRoute("list_draft_catalog_prompts", False),
    "admin_get_prompt": ToolRoute("get_catalog_prompt_by_id", False, "prompt_id"),
    "admin_publish_prompt": ToolRoute("publish_catalog_prompt", True, "prompt_id"),
    "admin_unpublish_prompt": ToolRoute("unpublish_catalog_prompt", True, "prompt_id"),
    "admin_delete_draft_prompt": ToolRoute(
        "delete_draft_catalog_prompt", True, "prompt_id", result_mode="deleted_prompt"
    ),
    "admin_create_package": ToolRoute("create_catalog_package", True, result_mode="created"),
    "admin_upsert_package_variant": ToolRoute("upsert_catalog_package_variant", True, "package_id"),
    "admin_upsert_package_metadata": ToolRoute("upsert_catalog_package_metadata", True, "package_id"),
    "admin_add_prompt_to_package": ToolRoute("add_prompt_to_catalog_package", True, "package_id"),
    "admin_update_package_item": ToolRoute("update_catalog_package_item", True, "package_id"),
    "admin_remove_prompt_from_package": ToolRoute(
        "remove_prompt_from_catalog_package", True, "package_id", result_mode="removed"
    ),
    "admin_publish_package": ToolRoute("publish_catalog_package", True, "package_id"),
    "admin_unpublish_package": ToolRoute("unpublish_catalog_package", True, "package_id"),
    "admin_delete_draft_package": ToolRoute(
        "delete_draft_catalog_package", True, "package_id", result_mode="deleted_package"
    ),
    "admin_list_prompt_history": ToolRoute("admin_list_prompt_history", False, "prompt_id"),
    "admin_restore_prompt_version": ToolRoute(
        "admin_restore_prompt_version", True, keep_confirm=True
    ),
    "admin_list_package_history": ToolRoute("admin_list_package_history", False, "package_id"),
    "admin_restore_package_version": ToolRoute(
        "admin_restore_package_version", True, keep_confirm=True
    ),
}


def _validate_arguments(definition, arguments):
    errors = sorted(
        Draft202012Validator(definition["inputSchema"]).iter_errors(arguments),
        key=lambda error: list(error.path),
    )
    if errors:
        raise InvalidToolArguments("Ogiltiga verktygsargument.")
    if definition["name"] in CONFIRM_TOOLS and arguments.get("confirm") is not True:
        raise InvalidToolArguments("Verktyget kräver confirm=true.")
```

Lägg till dispatchern nedan. Den generiska `p_*`-översättningen är exakt
för samtliga 20 porterade scheman. `confirm` skickas bara till
restore-RPC:erna; för övriga verktyg är den en lokal spärr:

```python
class AdminToolDispatcher:
    def __init__(
        self,
        *,
        repository: SupabaseAdminRepository,
        definitions: list[dict[str, Any]],
        limiter: "SlidingWindowRateLimiter",
    ) -> None:
        self._repository = repository
        self._definitions = {item["name"]: item for item in definitions}
        self._limiter = limiter

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        access_token: str,
        context: AdminContext,
    ) -> object:
        definition = self._definitions.get(name)
        if definition is None:
            raise UnknownTool("Okänt Admin-MCP-verktyg.")
        _validate_arguments(definition, arguments)

        if name == "get_admin_context":
            return asdict(context)

        route = ROUTES.get(name)
        if route is None:
            raise UnknownTool("Verktyget saknar godkänd RPC-route.")

        payload = {
            f"p_{key}": value
            for key, value in arguments.items()
            if key != "confirm" or route.keep_confirm
        }
        target_id = arguments.get(route.target_key) if route.target_key else None

        if route.write:
            self._limiter.check(
                f"{context.user_id}:{context.client_id}",
                time.monotonic(),
            )

        try:
            result = self._repository.call_rpc(
                access_token,
                route.rpc,
                payload,
            )
        except RepositoryRejected:
            if route.write:
                try:
                    self._repository.audit(
                        access_token,
                        name,
                        target_id if isinstance(target_id, str) else None,
                        "rejected",
                        {"error_code": "supabase_rejected"},
                    )
                except (RepositoryRejected, RepositoryUnavailable):
                    pass
            raise

        if route.write:
            if route.result_mode == "created" and isinstance(result, dict):
                returned_id = result.get("id")
                if isinstance(returned_id, str):
                    target_id = returned_id
            self._repository.audit(
                access_token,
                name,
                target_id if isinstance(target_id, str) else None,
                "success",
            )

        if route.result_mode == "deleted_prompt":
            return {"status": "deleted", "prompt_id": arguments["prompt_id"]}
        if route.result_mode == "deleted_package":
            return {"status": "deleted", "package_id": arguments["package_id"]}
        if route.result_mode == "removed":
            return {
                "status": "removed",
                "package_id": arguments["package_id"],
                "prompt_id": arguments["prompt_id"],
            }
        return result
```

`RepositoryUnavailable` ska passera vidare utan ett försök att auditlogga;
det undviker att dölja det ursprungliga tillgänglighetsfelet bakom ett andra
misslyckat HTTP-anrop. Inga exceptiontexter eller response bodies skrivs till
audit eller logg.

- [ ] **Step 5: Lägg ett per-identitet rate limit**

```python
import threading


class RateLimitExceeded(RuntimeError):
    pass


class SlidingWindowRateLimiter:
    def __init__(self, max_calls: int = 30, window_seconds: int = 60) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._calls: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, identity_key: str, now: float) -> None:
        with self._lock:
            calls = self._calls.setdefault(identity_key, [])
            calls[:] = [
                value
                for value in calls
                if now - value <= self._window_seconds
            ]
            if len(calls) >= self._max_calls:
                raise RateLimitExceeded(
                    "För många adminskrivningar. Vänta och försök igen."
                )
            calls.append(now)
```

Nyckeln är `f"{context.user_id}:{context.client_id}"`.

- [ ] **Step 6: Kör grönt och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py -v
.\.venv\Scripts\python.exe -m ruff check admin_mcp tests
.\.venv\Scripts\pyright.exe
git add admin_mcp/tools.py tests/test_tools.py
git commit -m "feat: port the exact Admin MCP tool surface"
```

### Task 6: Bygg MCP- och OAuth HTTP-gränsen

**Files:**
- Create: `../promptbanken-admin-mcp/tests/test_app.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/app.py`
- Create: `../promptbanken-admin-mcp/admin_mcp/__main__.py`

**Interfaces:**
- Consumes: `SupabaseJwtVerifier`, `SupabaseAdminRepository`, `AdminToolDispatcher`, `Settings`.
- Produces: `create_app(...) -> Starlette` och körbar `python -m admin_mcp`.

- [ ] **Step 1: Skriv HTTP-tester för discovery och authstatus**

Lås:

```python
def test_metadata_describes_the_exact_admin_resource(client):
    response = client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    assert response.json() == {
        "resource": "https://admin-mcp.promptbanken.se/mcp",
        "authorization_servers": ["https://project.supabase.co/auth/v1"],
        "scopes_supported": ["openid", "email", "profile"],
        "bearer_methods_supported": ["header"],
    }


def test_missing_token_returns_rfc9728_challenge(client):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 401
    assert 'resource_metadata="https://admin-mcp.promptbanken.se/.well-known/oauth-protected-resource/mcp"' in response.headers["www-authenticate"]


def test_valid_but_unapproved_identity_returns_403(client, repository):
    repository.context_allowed = False
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer valid-test-token"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert response.status_code == 403
```

Lägg tester för invalid/expired token → 401, Supabase context-timeout → 503,
body på 65 537 bytes → 413, okänd route → 404, och att `/healthz` aldrig
returnerar konfiguration eller identitet.

- [ ] **Step 2: Skriv MCP-protokolltesterna**

Verifiera:

- `initialize` returnerar protocol `2025-06-18`, servernamn
  `promptbanken-admin-mcp`, version `1.0.0` och tools-capability,
- `notifications/initialized` returnerar 202 utan JSON-RPC body,
- `tools/list` returnerar exakt snapshoten,
- `tools/call` returnerar både `content` och `structuredContent`,
- okänd metod/verktyg → `-32601`,
- schemafel → `-32602`,
- Supabase-avvisning → sanerat `-32003`,
- oväntat fel → `-32603` med korrelations-id men utan stack trace.

- [ ] **Step 3: Kör rött läge**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app.py -v
```

Förväntat: FAIL eftersom appen saknas.

- [ ] **Step 4: Implementera bearer-, body- och authkedjan**

Kedjan i `POST /mcp` ska vara exakt:

```python
token = bearer_token(request)
if token is None:
    return unauthorized(resource_metadata_url)

try:
    identity = verifier.verify(token)
except InvalidAccessToken:
    return unauthorized(resource_metadata_url)

try:
    context = repository.get_context(token)
except RepositoryRejected:
    return forbidden()
except RepositoryUnavailable:
    return service_unavailable()

if (
    not context.allowed
    or context.role != "platform_owner"
    or not context.client_approved
    or context.user_id != identity.user_id
    or context.client_id != identity.client_id
):
    return forbidden()
```

Läs body först efter body-size-kontroll. Fånga JSON-dekodningsfel som
`-32700 Parse error`. Authorization-headern får inte läggas i request state,
loggkontext eller feltext; token ska bara skickas direkt till verifierare och
repository.

Appens ASGI-middleware ska räkna verkliga body-bytes även när
`Content-Length` saknas. Den får buffra högst 65 536 bytes och ska svara direkt
med 413 när nästa chunk passerar gränsen:

```python
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self._app(scope, receive, send)
            return

        messages: list[Message] = []
        total = 0
        more = True
        while more:
            message = await receive()
            body = message.get("body", b"")
            total += len(body)
            if total > self._max_bytes:
                await send({"type": "http.response.start", "status": 413, "headers": []})
                await send({"type": "http.response.body", "body": b"Request too large"})
                return
            messages.append(message)
            more = bool(message.get("more_body", False))

        async def replay_receive() -> Message:
            return messages.pop(0)

        await self._app(scope, replay_receive, send)
```

- [ ] **Step 5: Implementera MCP-svar och startpunkt**

`app.py` ska ha denna konkreta factory och protokollgren. Hjälpfunktionerna
`result`, `error` och `mcp_payload` bygger vanliga JSON-serialiserbara dictar;
de ska testas genom de publika HTTP-testerna, inte som en separat abstraktion:

```python
import json
import logging
from uuid import uuid4

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from admin_mcp.auth import InvalidAccessToken, SupabaseJwtVerifier
from admin_mcp.config import Settings
from admin_mcp.contract import load_tool_definitions
from admin_mcp.repository import (
    RepositoryRejected,
    RepositoryUnavailable,
    SupabaseAdminRepository,
)
from admin_mcp.tools import (
    AdminToolDispatcher,
    InvalidToolArguments,
    RateLimitExceeded,
    SlidingWindowRateLimiter,
    UnknownTool,
)

logger = logging.getLogger("promptbanken_admin_mcp")


def result(request_id: object, value: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def error(
    request_id: object,
    code: int,
    message: str,
    data: dict[str, object] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": body}


def mcp_payload(value: object) -> dict[str, object]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, default=str),
            }
        ],
        "structuredContent": value,
    }


def bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    scheme, separator, token = value.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def unauthorized(metadata_url: str) -> JSONResponse:
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401,
        headers={
            "WWW-Authenticate": (
                'Bearer resource_metadata="' + metadata_url + '"'
            )
        },
    )


def forbidden() -> JSONResponse:
    return JSONResponse({"error": "forbidden"}, status_code=403)


def service_unavailable() -> JSONResponse:
    return JSONResponse({"error": "service_unavailable"}, status_code=503)


def create_app(
    *,
    settings: Settings,
    verifier: SupabaseJwtVerifier,
    repository: SupabaseAdminRepository,
    dispatcher: AdminToolDispatcher,
    definitions: list[dict[str, object]],
) -> Starlette:
    metadata_url = (
        "https://admin-mcp.promptbanken.se/"
        ".well-known/oauth-protected-resource/mcp"
    )

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "promptbanken-admin-mcp",
                "version": "1.0.0",
            }
        )

    async def protected_resource(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "resource": settings.resource_url,
                "authorization_servers": [settings.issuer],
                "scopes_supported": ["openid", "email", "profile"],
                "bearer_methods_supported": ["header"],
            }
        )

    async def mcp(request: Request) -> Response:
        token = bearer_token(request)
        if token is None:
            return unauthorized(metadata_url)
        try:
            identity = verifier.verify(token)
        except InvalidAccessToken:
            return unauthorized(metadata_url)
        try:
            context = repository.get_context(token)
        except RepositoryRejected:
            logger.warning(
                "oauth_client_denied client_id=%s correlation_id=%s outcome=forbidden",
                identity.client_id,
                str(uuid4()),
            )
            return forbidden()
        except RepositoryUnavailable:
            return service_unavailable()
        if (
            not context.allowed
            or context.role != "platform_owner"
            or not context.client_approved
            or context.user_id != identity.user_id
            or context.client_id != identity.client_id
        ):
            logger.warning(
                "oauth_client_denied client_id=%s correlation_id=%s outcome=forbidden",
                identity.client_id,
                str(uuid4()),
            )
            return forbidden()

        try:
            message = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(error(None, -32700, "Parse error"))
        if not isinstance(message, dict):
            return JSONResponse(error(None, -32600, "Invalid Request"))

        request_id = message.get("id")
        method = message.get("method")
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return Response(status_code=202)
        if method == "initialize":
            return JSONResponse(
                result(
                    request_id,
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "promptbanken-admin-mcp",
                            "version": "1.0.0",
                        },
                    },
                )
            )
        if method == "ping":
            return JSONResponse(result(request_id, {}))
        if method == "tools/list":
            return JSONResponse(result(request_id, {"tools": definitions}))
        if method != "tools/call":
            return JSONResponse(error(request_id, -32601, "Method not found"))

        params = message.get("params")
        if not isinstance(params, dict):
            return JSONResponse(error(request_id, -32602, "Invalid params"))
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return JSONResponse(error(request_id, -32602, "Invalid params"))

        try:
            value = dispatcher.call(name, arguments, token, context)
            return JSONResponse(result(request_id, mcp_payload(value)))
        except UnknownTool:
            return JSONResponse(error(request_id, -32601, "Tool not found"))
        except InvalidToolArguments:
            return JSONResponse(error(request_id, -32602, "Invalid tool arguments"))
        except RepositoryRejected:
            return JSONResponse(error(request_id, -32003, "Admin request rejected"))
        except RateLimitExceeded:
            return JSONResponse(error(request_id, -32029, "Rate limit exceeded"))
        except RepositoryUnavailable:
            return JSONResponse(error(request_id, -32003, "Admin backend unavailable"))
        except Exception as exc:
            correlation_id = str(uuid4())
            logger.error(
                "admin_mcp_internal_error type=%s correlation_id=%s",
                type(exc).__name__,
                correlation_id,
            )
            return JSONResponse(
                error(
                    request_id,
                    -32603,
                    "Internal error",
                    {"correlation_id": correlation_id},
                )
            )

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route(
                "/.well-known/oauth-protected-resource/mcp",
                protected_resource,
                methods=["GET"],
            ),
            Route("/mcp", mcp, methods=["POST"]),
        ]
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    return app


def build_app_from_settings(settings: Settings) -> Starlette:
    definitions = load_tool_definitions()
    repository = SupabaseAdminRepository(
        supabase_url=settings.supabase_url,
        publishable_key=settings.publishable_key,
    )
    return create_app(
        settings=settings,
        verifier=SupabaseJwtVerifier(
            issuer=settings.issuer,
            audience=settings.audience,
            jwks_url=settings.jwks_url,
        ),
        repository=repository,
        dispatcher=AdminToolDispatcher(
            repository=repository,
            definitions=definitions,
            limiter=SlidingWindowRateLimiter(),
        ),
        definitions=definitions,
    )
```

Testet ska uttryckligen kräva att exceptiontexten inte finns i loggen.

`__main__.py`:

```python
import uvicorn

from admin_mcp.app import build_app_from_settings
from admin_mcp.config import Settings


def main() -> None:
    app = build_app_from_settings(Settings.from_env())
    uvicorn.run(app, host="0.0.0.0", port=8012, log_level="info")


if __name__ == "__main__":
    main()
```

Använd denna rekursiva filterfunktion innan en struktur skickas till loggern:

```python
_SENSITIVE_LOG_KEYS = {"authorization", "cookie", "token", "email", "claims"}


def redact_for_log(value: object) -> object:
    if isinstance(value, dict):
        filtered: dict[str, object] = {}
        for key, item in value.items():
            name = str(key)
            filtered[name] = (
                "[redacted]"
                if name.lower() in _SENSITIVE_LOG_KEYS
                else redact_for_log(item)
            )
        return filtered
    if isinstance(value, list):
        return [redact_for_log(item) for item in value]
    return value
```

Logga aldrig hela request-/responseobjekt eller exceptionsträngar från HTTPX.
E-post får returneras till den autentiserade användaren via
`get_admin_context`, men aldrig loggas.

- [ ] **Step 6: Kör grönt och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app.py -v
.\.venv\Scripts\python.exe -m ruff check admin_mcp tests
.\.venv\Scripts\pyright.exe
git add admin_mcp/app.py admin_mcp/__main__.py tests/test_app.py
git commit -m "feat: expose the OAuth-protected Admin MCP endpoint"
```

### Task 7: Lägg live-kontraktstest och sekretessregressioner

**Files:**
- Create: `../promptbanken-admin-mcp/scripts/test-live-contract.ps1`
- Modify: `../promptbanken-admin-mcp/tests/test_contract.py`
- Modify: `../promptbanken-admin-mcp/tests/test_app.py`

**Interfaces:**
- Consumes: `PROMPTBANKEN_ADMIN_OAUTH_TEST_TOKEN`, `mcp-contract.json` och en base URL.
- Produces: exit code 0 endast när exakt verktygsyta, fulla definitioner och authgräns passerar.

- [ ] **Step 1: Skriv först ett test för loggredigering**

Skicka en medvetet trasig bearer-token, en e-postadress och ett Supabase-fel
genom appens felvägar med `caplog`. Assert:

```python
combined = "\n".join(record.getMessage() for record in caplog.records)
assert "valid-test-token" not in combined
assert "owner@example.test" not in combined
assert "Authorization" not in combined
assert "PGRST" not in combined
```

- [ ] **Step 2: Implementera live-runnern mot statiskt kontrakt**

Skriptet ska:

1. läsa `mcp-contract.json` och dess `definitionSnapshot`,
2. POST:a utan token och kräva 401 + `resource_metadata`,
3. om testtoken saknas: avsluta med kod 2 och texten `SKIP: PROMPTBANKEN_ADMIN_OAUTH_TEST_TOKEN saknas`,
4. med token: `initialize`, `tools/list`, jämför hela definitionerna som JSON,
5. anropa `list_templates` och kräva JSON-RPC `-32601`,
6. anropa `get_admin_context` och kräva `role=platform_owner`,
   `client_approved=true` och icke-tomma `user_id`/`client_id`,
7. aldrig skriva token eller full e-post till output.

Parameterkontrakt:

```powershell
param(
  [string]$BaseUrl = "http://127.0.0.1:8012",
  [string]$Contract = ".\mcp-contract.json",
  [string]$Token = $env:PROMPTBANKEN_ADMIN_OAUTH_TEST_TOKEN
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-True([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw $Message }
}

function Invoke-Mcp([hashtable]$Message) {
  $response = Invoke-WebRequest `
    -Method Post `
    -Uri "$BaseUrl/mcp" `
    -Headers @{ Authorization = "Bearer $Token" } `
    -ContentType "application/json" `
    -Body ($Message | ConvertTo-Json -Depth 100 -Compress)
  Assert-True ($response.StatusCode -eq 200) "MCP returned HTTP $($response.StatusCode)"
  return $response.Content | ConvertFrom-Json -Depth 100
}

$contractObject = Get-Content -Raw -LiteralPath $Contract | ConvertFrom-Json -Depth 100
$contractDirectory = Split-Path -Parent (Resolve-Path -LiteralPath $Contract)
$snapshotRelative = $contractObject.toolGroups.admin.definitionSnapshot
$snapshotPath = Join-Path $contractDirectory $snapshotRelative
$expected = Get-Content -Raw -LiteralPath $snapshotPath | ConvertFrom-Json -Depth 100

$unauthorized = Invoke-WebRequest `
  -Method Post `
  -Uri "$BaseUrl/mcp" `
  -ContentType "application/json" `
  -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' `
  -SkipHttpErrorCheck
Assert-True ($unauthorized.StatusCode -eq 401) "Missing token did not return 401"
Assert-True `
  ($unauthorized.Headers.WwwAuthenticate -match 'resource_metadata=') `
  "401 lacked OAuth protected-resource metadata"

if ([string]::IsNullOrWhiteSpace($Token)) {
  Write-Output "SKIP: PROMPTBANKEN_ADMIN_OAUTH_TEST_TOKEN saknas"
  exit 2
}

$initialize = Invoke-Mcp @{
  jsonrpc = "2.0"; id = 2; method = "initialize"; params = @{}
}
Assert-True `
  ($initialize.result.serverInfo.name -eq "promptbanken-admin-mcp") `
  "Wrong MCP server identity"

$listed = Invoke-Mcp @{ jsonrpc = "2.0"; id = 3; method = "tools/list" }
$actualJson = $listed.result.tools | ConvertTo-Json -Depth 100 -Compress
$expectedJson = $expected | ConvertTo-Json -Depth 100 -Compress
Assert-True ($actualJson -ceq $expectedJson) "Full tool definition snapshot mismatch"
Assert-True (@($listed.result.tools).Count -eq 21) "Expected exactly 21 tools"

$blocked = Invoke-Mcp @{
  jsonrpc = "2.0"
  id = 4
  method = "tools/call"
  params = @{ name = "list_templates"; arguments = @{} }
}
Assert-True ($blocked.error.code -eq -32601) "Open tool was not blocked"

$context = Invoke-Mcp @{
  jsonrpc = "2.0"
  id = 5
  method = "tools/call"
  params = @{ name = "get_admin_context"; arguments = @{} }
}
$value = $context.result.structuredContent
Assert-True ($value.role -eq "platform_owner") "Caller is not platform_owner"
Assert-True ($value.client_approved -eq $true) "OAuth client is not approved"
Assert-True (-not [string]::IsNullOrWhiteSpace($value.user_id)) "Missing user id"
Assert-True (-not [string]::IsNullOrWhiteSpace($value.client_id)) "Missing client id"

Write-Output "PASS: Admin MCP contract 21/21, auth boundary and context verified"
```

Skriptet får endast skriva de två fasta `SKIP`/`PASS`-raderna eller ett
sanerat assertionsfel. Det får inte skriva response body, headers, token eller
e-postadress.

- [ ] **Step 3: Kör mot lokal app med testdubblerad auth**

Enhetstestsviten ska testa runnerns jämförelselogik utan riktig token. Starta
därefter appen med ett lokalt testharness där verifierare/repository injiceras
och kör skriptet mot `http://127.0.0.1:8012`.

Förväntat: 21/21 definitioner matchar; blockerat Open-verktyg nekas.

- [ ] **Step 4: Kör full verifiering och commit**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\pyright.exe
git diff --check
git add scripts/test-live-contract.ps1 tests/test_contract.py tests/test_app.py
git commit -m "test: add live Admin MCP OAuth contract gate"
```

### Task 8: Paketera en härdad container och dokumentera drift

**Files:**
- Create: `../promptbanken-admin-mcp/Dockerfile`
- Create: `../promptbanken-admin-mcp/docker-compose.yml`
- Create: `../promptbanken-admin-mcp/.env.example`
- Create: `../promptbanken-admin-mcp/README.md`

**Interfaces:**
- Consumes: fyra publika konfigurationsvärden från Task 1.
- Produces: service `admin-mcp`, image `promptbanken-admin-mcp:latest`, localhostport 8012 och healthcheck.

- [ ] **Step 1: Skriv container-smoketestets förväntningar**

Dokumentera och kör följande efter build:

```powershell
docker build -t promptbanken-admin-mcp:test .
docker run --rm promptbanken-admin-mcp:test python -c "import admin_mcp; print('import-ok')"
docker inspect promptbanken-admin-mcp:test
```

Förväntat: import ger `import-ok`; imagen har en icke-root `User` och inga
hemligheter i `Config.Env`.

- [ ] **Step 2: Skapa en flerstegs-Dockerfile**

Använd den verifierade multi-arch-digesten
`python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`
(Python 3.12.14 slim, verifierad 2026-09-11). Kontrollera före implementation
att digesten fortfarande kan hämtas men ändra den bara genom en granskad
dependency-commit. Installera bara `requirements.txt`, kopiera
`admin_mcp/` och `contracts/`, skapa användaren `app` utan shell:

```dockerfile
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS builder
WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
RUN groupadd --system app && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app admin_mcp ./admin_mcp
COPY --chown=app:app contracts ./contracts
USER app
EXPOSE 8012
CMD ["python", "-m", "admin_mcp"]
```

Ingen compiler, package manager-cache, testkod eller `.env` får finnas i
slutimagen.

- [ ] **Step 3: Skapa compose med exakt härdning**

```yaml
services:
  admin-mcp:
    image: promptbanken-admin-mcp:latest
    build: .
    environment:
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_PUBLISHABLE_KEY: ${SUPABASE_PUBLISHABLE_KEY}
      OAUTH_ISSUER: ${OAUTH_ISSUER}
      OAUTH_JWKS_URL: ${OAUTH_JWKS_URL}
    ports:
      - "127.0.0.1:8012:8012"
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    mem_limit: 128m
    cpus: 0.50
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8012/healthz', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

Mät idle- och testlast och dokumentera resultatet i README. Gränserna 128 MiB
och 0,50 CPU är releasekravet; om E2E når 80 procent av minnesgränsen ska
utrullningen stoppas och gränsen omprövas genom en specändring, inte höjas
tyst i compose.

- [ ] **Step 4: Skapa en säker `.env.example`**

Filen innehåller bara namn och publika exempelvärden:

```dotenv
SUPABASE_URL=https://project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_example
OAUTH_ISSUER=https://project-ref.supabase.co/auth/v1
OAUTH_JWKS_URL=https://project-ref.supabase.co/auth/v1/.well-known/jwks.json
```

Inga `SERVICE_ROLE`, `ADMIN_KEY` eller `REFRESH_TOKEN`-namn får finnas.

- [ ] **Step 5: Dokumentera lokal körning, OAuth-flöde och säkerhetsgräns**

README ska innehålla:

- de tre publika routes,
- exakt 21 verktyg,
- varför scopes inte ger DB-behörighet,
- hur `platform_owner + client_id allowlist` fungerar,
- lokala test/lint/typecheck/contract-kommandon,
- att Supabase OAuth token endpoint ska behandlas som valfri 2xx,
- hur en klient spärras utan omdeploy,
- att verkliga tokens aldrig ska sparas i shellhistorik eller Git.

- [ ] **Step 6: Verifiera image, compose och hela sviten**

```powershell
docker-compose config
docker-compose build admin-mcp
docker-compose up -d admin-mcp
Invoke-RestMethod http://127.0.0.1:8012/healthz
docker-compose ps
docker-compose logs --tail=80 admin-mcp
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\pyright.exe
```

Förväntat: health JSON är exakt
`{"status":"ok","service":"promptbanken-admin-mcp","version":"1.0.0"}`;
loggar saknar tokens/e-post; inga omstarter.

- [ ] **Step 7: Commit**

```powershell
git add Dockerfile docker-compose.yml .env.example README.md
git commit -m "build: package hardened Admin MCP container"
```

### Task 9: Slutgranska tjänsten före extern repo/deploy

**Files:**
- Modify only if verification finds a defect: files already listed above.

**Interfaces:**
- Consumes: färdig lokal service.
- Produces: ett verifierat commit-id som rolloutplanen kan deploya.

- [ ] **Step 1: Kör full ren verifiering**

```powershell
git status --short
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\pyright.exe
git diff --check
docker-compose config
docker-compose build admin-mcp
```

Förväntat: Git är rent; tester, lint, typer, diffcheck, compose och build har
exit code 0.

- [ ] **Step 2: Kör säkerhetssökningar**

```powershell
rg -n "service[_-]?role|SUPABASE_ADMIN_REFRESH_TOKEN|PROMPTBANKEN_ADMIN_KEY|refresh[_-]?token" .
rg -n "Authorization|Cookie|email|claims|response\.text" admin_mcp
```

Förväntat: första sökningen träffar endast README:s uttryckliga förbud och
tester som bevisar frånvaro; andra sökningen granskas rad för rad och visar
ingen loggning av känsliga värden.

- [ ] **Step 3: Jämför verktygsytorna**

Kör ett litet granskningsskript som läser gamla
`mcp_promptbanken/mcp-server/server/mcp_server.py` och nya snapshoten.
Förväntat:

- `missing_from_new=[]`,
- `unexpected_admin=[]`,
- enda nya namn är `get_admin_context`,
- exakt 21 unika verktyg.

- [ ] **Step 4: Kontrollera Supabase/MCP discoverykontraktet**

Hämta aktuell Supabase OAuth discovery och MCP protected-resource metadata.
Bekräfta `code_challenge_methods_supported` innehåller `S256`,
`registration_endpoint` finns om dynamisk registrering ska användas, och
att authorization/token/JWKS URLs matchar `OAUTH_ISSUER`.

Om den verkliga Admin-tokenens `aud` inte är `authenticated`, stoppa före
deploy och revidera spec/konfiguration; bredda inte verifieraren för att få
testet grönt.

- [ ] **Step 5: Commit eventuella verifieringsfixar separat**

```powershell
git add admin_mcp tests contracts scripts README.md Dockerfile docker-compose.yml
git commit -m "fix: address Admin MCP pre-deploy review findings"
```

Hoppa över commit om inga filer ändrats.

## Service Plan Completion Gate

Tjänsten är redo för rollout först när:

- Git är rent och alla tester/lint/typer/build passerar färskt,
- full snapshot matchar exakt 21 verktyg,
- 401/403/413/503 och JSON-RPC-fel är verifierade,
- vanlig Connect-/Open-tool call blockeras,
- caller-token är den enda Supabase-identiteten,
- inga förbjudna hemligheter eller hemlighetsvariabler finns,
- container kör icke-root, read-only och utan capabilities,
- Supabase discovery, S256 och den verkliga tokenens audience är verifierade.
