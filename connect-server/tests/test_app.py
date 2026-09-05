from starlette.testclient import TestClient

from connect_service.app import create_app


class AcceptingVerifier:
    def verify(self, token: str) -> dict[str, str]:
        if token != "test-access-token":
            raise ValueError("Ogiltig åtkomsttoken.")
        return {"sub": "00000000-0000-0000-0000-000000000001"}


class Library:
    def list_library(self, *, access_token: str, user_id: str):
        assert access_token == "test-access-token"
        assert user_id == "00000000-0000-0000-0000-000000000001"
        return [{"id": "library-item", "title": "Min privata prompt"}]

    def list_shared_items(self, *, access_token: str):
        assert access_token == "test-access-token"
        return [{"id": "shared-item", "title": "Delad prompt"}]

    def get_item(self, *, access_token: str, item_id: str):
        assert access_token == "test-access-token"
        if item_id == "library-item":
            return {"id": "library-item", "title": "Min privata prompt", "content": "Min text"}
        return None


def _client() -> TestClient:
    return TestClient(
        create_app(
            resource_url="https://connect.promptbanken.se/mcp",
            authorization_server="https://example.supabase.co/auth/v1",
            token_verifier=AcceptingVerifier(),
            library=Library(),
        )
    )


def test_protected_resource_metadata_describes_connect_resource() -> None:
    response = _client().get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    assert response.json() == {
        "resource": "https://connect.promptbanken.se/mcp",
        "authorization_servers": ["https://example.supabase.co/auth/v1"],
    }


def test_health_check_is_available_without_an_access_token() -> None:
    response = _client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "promptbanken-connect"}


def test_mcp_rejects_request_without_access_token() -> None:
    response = _client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        'Bearer resource="https://connect.promptbanken.se/mcp"'
    )


def test_authenticated_client_can_discover_connect_tool() -> None:
    response = _client().post(
        "/mcp",
        headers={"Authorization": "Bearer test-access-token"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["tools"] == [
        {
            "name": "get_connect_context",
            "description": "Bekräftar vem Connect är kopplad till.",
            "inputSchema": {"type": "object", "properties": {}},
        }
        ,
        {
            "name": "list_my_library",
            "description": "Listar dina egna aktiva prompts i Valvet.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_shared_workspace_prompts",
            "description": "Listar prompts i arbetsytor du är medlem i.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_connect_item",
            "description": "Hämtar en prompt du har behörighet att läsa.",
            "inputSchema": {
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        },
    ]


def test_mcp_returns_identity_bound_connect_context_for_valid_token() -> None:
    response = _client().post(
        "/mcp",
        headers={"Authorization": "Bearer test-access-token"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_connect_context", "arguments": {}},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": '{"user_id": "00000000-0000-0000-0000-000000000001"}',
                }
            ],
            "structuredContent": {"user_id": "00000000-0000-0000-0000-000000000001"},
        },
    }


def test_authenticated_client_can_list_its_private_library() -> None:
    response = _client().post(
        "/mcp",
        headers={"Authorization": "Bearer test-access-token"},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_my_library", "arguments": {}},
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"] == {
        "items": [{"id": "library-item", "title": "Min privata prompt"}]
    }


def test_authenticated_client_can_only_get_an_item_the_library_returns() -> None:
    response = _client().post(
        "/mcp",
        headers={"Authorization": "Bearer test-access-token"},
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_connect_item", "arguments": {"item_id": "library-item"}},
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"] == {
        "item": {"id": "library-item", "title": "Min privata prompt", "content": "Min text"}
    }
