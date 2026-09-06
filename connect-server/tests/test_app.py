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

    def search_open_catalog(self, *, access_token: str, query: str, kind: str, category: str | None, limit: int, cursor: int):
        assert access_token == "test-access-token"
        assert (query, kind, category, limit, cursor) == ("beslut", "prompt", None, 10, 0)
        return {"items": [{"id": "open-item", "kind": "prompt", "title": "Beslutsunderlag"}], "next_cursor": None}

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

    def create_my_prompt(self, *, access_token: str, title: str, content: str, summary: str | None, category: str | None, request_id: str):
        assert access_token == "test-access-token"
        assert content == "Skriv ett kort informationsbrev."
        assert summary is None
        assert category is None
        assert request_id == "00000000-0000-0000-0000-000000000030"
        return {"id": "00000000-0000-0000-0000-000000000031", "title": title, "status": "draft"}

    def archive_my_prompt(self, *, access_token: str, prompt_id: str, request_id: str):
        assert access_token == "test-access-token"
        assert prompt_id == "00000000-0000-0000-0000-000000000070"
        assert request_id == "00000000-0000-0000-0000-000000000071"
        return {"id": prompt_id, "status": "archived"}


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
        "search_open_catalog",
        "list_my_library",
        "get_my_library_prompt",
        "list_my_packages",
        "get_my_package",
        "list_my_shares",
        "create_my_prompt",
            "update_my_prompt",
            "archive_my_prompt",
            "unfollow_open_prompt",
            "save_my_package",
            "set_package_prompts",
            "archive_my_package",
            "unfollow_open_package",
        "add_open_prompt_to_library",
        "add_open_package_to_library",
        "create_my_share",
        "revoke_my_share",
        "extend_my_share",
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


def test_create_my_prompt_requires_explicit_confirmation_before_any_write():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "create_my_prompt",
                "arguments": {
                    "title": "Informationsbrev",
                    "content": "Skriv ett kort informationsbrev.",
                    "confirmed": False,
                    "request_id": "00000000-0000-0000-0000-000000000030",
                },
            },
        }
    )

    assert response.json()["error"] == {
        "code": -32010,
        "message": "Bekräfta ändringen med confirmed: true.",
    }


def test_create_my_prompt_returns_the_created_creator_draft():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "create_my_prompt",
                "arguments": {
                    "title": "Informationsbrev",
                    "content": "Skriv ett kort informationsbrev.",
                    "confirmed": True,
                    "request_id": "00000000-0000-0000-0000-000000000030",
                },
            },
        }
    )

    assert response.json()["result"]["structuredContent"] == {
        "prompt": {
            "id": "00000000-0000-0000-0000-000000000031",
            "title": "Informationsbrev",
            "status": "draft",
        }
    }


def test_search_open_catalog_returns_public_metadata():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {"name": "search_open_catalog", "arguments": {"query": "beslut", "kind": "prompt", "limit": 10}},
        }
    )

    assert response.json()["result"]["structuredContent"] == {
        "items": [{"id": "open-item", "kind": "prompt", "title": "Beslutsunderlag"}],
        "next_cursor": None,
    }


def test_archive_my_prompt_returns_archived_status_after_confirmation():
    response = authenticated_post(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "archive_my_prompt",
                "arguments": {
                    "prompt_id": "00000000-0000-0000-0000-000000000070",
                    "confirmed": True,
                    "request_id": "00000000-0000-0000-0000-000000000071",
                },
            },
        }
    )

    assert response.json()["result"]["structuredContent"] == {
        "prompt": {"id": "00000000-0000-0000-0000-000000000070", "status": "archived"}
    }

class PromptQuotaLibrary(Library):
    def create_my_prompt(self, **kwargs):
        from connect_service.data import ConnectWriteError

        raise ConnectWriteError("Du har nått gränsen för privata prompts i Free-läget. Arkivera en prompt eller uppgradera kontot.")


def test_write_limit_returns_a_structured_mcp_error_instead_of_an_upstream_failure():
    quota_client = TestClient(
        create_app(
            resource_url="https://connect.promptbanken.se/mcp",
            authorization_server="https://example.supabase.co/auth/v1",
            token_verifier=AcceptingVerifier(),
            library=PromptQuotaLibrary(),
        )
    )

    response = quota_client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-access-token"},
        json={
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": "create_my_prompt",
                "arguments": {
                    "title": "Ny prompt",
                    "content": "Kort innehåll.",
                    "confirmed": True,
                    "request_id": "00000000-0000-0000-0000-000000000090",
                },
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["error"] == {
        "code": -32020,
        "message": "Du har nått gränsen för privata prompts i Free-läget. Arkivera en prompt eller uppgradera kontot.",
    }
