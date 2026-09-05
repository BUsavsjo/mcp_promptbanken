from starlette.testclient import TestClient

from connect_service.app import create_app


class AcceptingVerifier:
    def verify(self, token: str) -> dict[str, str]:
        if token != "test-access-token":
            raise ValueError("Ogiltig åtkomsttoken.")
        return {"sub": "00000000-0000-0000-0000-000000000001"}


class Library:
    def list_library(self, *, access_token: str, kind: str, limit: int):
        assert access_token == "test-access-token"
        return [{"id": "library-item", "kind": kind, "title": "Min Creator-prompt"}]

    def get_library_prompt(self, *, access_token: str, prompt_id: str):
        assert access_token == "test-access-token"
        if prompt_id == "00000000-0000-0000-0000-000000000010":
            return {"id": prompt_id, "title": "Min Creator-prompt", "content": "Min text"}
        return None

    def list_packages(self, *, access_token: str, limit: int):
        assert access_token == "test-access-token"
        return [{"id": "package-item", "title": "Mitt paket"}]

    def get_package(self, *, access_token: str, package_id: str):
        assert access_token == "test-access-token"
        if package_id == "00000000-0000-0000-0000-000000000020":
            return {"id": package_id, "title": "Mitt paket", "items": []}
        return None

    def list_shares(self, *, access_token: str, include_inactive: bool):
        assert access_token == "test-access-token"
        return [{"id": "share-item", "is_active": not include_inactive}]


def client() -> TestClient:
    return TestClient(
        create_app(
            resource_url="https://connect.promptbanken.se/mcp",
            authorization_server="https://example.supabase.co/auth/v1",
            token_verifier=AcceptingVerifier(),
            library=Library(),
        )
    )


def authenticated_post(payload):
    return client().post("/mcp", headers={"Authorization": "Bearer test-access-token"}, json=payload)


def test_protected_resource_metadata_describes_connect_resource():
    response = client().get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    assert response.json() == {
        "resource": "https://connect.promptbanken.se/mcp",
        "authorization_servers": ["https://example.supabase.co/auth/v1"],
    }


def test_mcp_rejects_request_without_access_token():
    response = client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer resource="https://connect.promptbanken.se/mcp"'


def test_authenticated_client_discovers_creator_library_tools():
    response = authenticated_post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert response.status_code == 200
    assert [tool["name"] for tool in response.json()["result"]["tools"]] == [
        "get_connect_context",
        "list_my_library",
        "get_my_library_prompt",
        "list_my_packages",
        "get_my_package",
        "list_my_shares",
    ]


def test_list_my_library_returns_the_repository_result():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_my_library", "arguments": {"kind": "prompt", "limit": 10}},
        }
    )

    assert response.json()["result"]["structuredContent"] == {
        "items": [{"id": "library-item", "kind": "prompt", "title": "Min Creator-prompt"}]
    }


def test_get_my_library_prompt_returns_not_found_without_leaking_ownership():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_my_library_prompt", "arguments": {"prompt_id": "00000000-0000-0000-0000-000000000099"}},
        }
    )

    assert response.json()["error"] == {"code": -32004, "message": "Objektet finns inte eller är inte tillgängligt."}


def test_get_my_package_returns_ordered_package():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "get_my_package", "arguments": {"package_id": "00000000-0000-0000-0000-000000000020"}},
        }
    )

    assert response.json()["result"]["structuredContent"] == {
        "package": {"id": "00000000-0000-0000-0000-000000000020", "title": "Mitt paket", "items": []}
    }


def test_list_my_shares_allows_inactive_filter():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "list_my_shares", "arguments": {"include_inactive": True}},
        }
    )

    assert response.json()["result"]["structuredContent"] == {
        "shares": [{"id": "share-item", "is_active": False}]
    }


def test_invalid_creator_tool_arguments_return_invalid_params():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "list_my_library", "arguments": {"kind": "annat", "limit": 0}},
        }
    )

    assert response.json()["error"] == {"code": -32602, "message": "Ogiltiga verktygsargument."}