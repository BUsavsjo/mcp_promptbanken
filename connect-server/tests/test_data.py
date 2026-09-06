import pytest

from connect_service.data import SupabaseConnectRepository


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class RecordingHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, path, *, headers, json):
        self.calls.append({"path": path, "headers": headers, "json": json})
        return Response(self.responses.pop(0))


def repository(client):
    return SupabaseConnectRepository(
        supabase_url="https://example.supabase.co",
        publishable_key="sb_publishable_test",
        http_client=client,
    )


def headers():
    return {
        "apikey": "sb_publishable_test",
        "Authorization": "Bearer oauth-access-token",
        "Content-Type": "application/json",
    }


def test_list_library_uses_creator_rpcs_and_hides_prompt_body():
    client = RecordingHttpClient([
        [{"id": "00000000-0000-0000-0000-000000000001", "title": "Creator", "summary": "Egen", "content": "hemlig text", "status": "draft", "updated_at": "2026-09-05T10:00:00Z"}],
        [{"id": "00000000-0000-0000-0000-000000000002", "title": "Valvet", "summary": "Sparad", "status": "draft", "is_library_reference": True, "updated_at": "2026-09-05T11:00:00Z"}],
        [{"id": "00000000-0000-0000-0000-000000000003", "title": "Paket", "summary": "Tre steg", "status": "draft", "is_library_reference": False, "updated_at": "2026-09-05T12:00:00Z"}],
    ])

    result = repository(client).list_library(access_token="oauth-access-token", kind="all", limit=2)

    assert [item["id"] for item in result] == [
        "00000000-0000-0000-0000-000000000003",
        "00000000-0000-0000-0000-000000000002",
    ]
    assert result[0]["kind"] == "package"
    assert "content" not in result[1]
    assert client.calls == [
        {"path": "/rest/v1/rpc/list_my_creator_prompts", "headers": headers(), "json": {}},
        {"path": "/rest/v1/rpc/list_my_library_prompts", "headers": headers(), "json": {}},
        {"path": "/rest/v1/rpc/list_my_creator_package_drafts", "headers": headers(), "json": {}},
    ]


def test_get_library_prompt_resolves_live_reference_content():
    prompt_id = "00000000-0000-0000-0000-000000000001"
    client = RecordingHttpClient([
        [{"id": prompt_id, "title": "Gammal", "summary": "Gammal", "content": "", "module": "valvet", "status": "draft", "is_library_reference": True, "source_prompt_id": "00000000-0000-0000-0000-000000000099"}],
        [{"title": "Levande", "summary": "Aktuell", "prompt_text": "Live text", "area": "Test", "risk_level": "low", "security_examples": []}],
    ])

    result = repository(client).get_library_prompt(access_token="oauth-access-token", prompt_id=prompt_id)

    assert result["content"] == "Live text"
    assert result["title"] == "Levande"
    assert client.calls[0] == {"path": "/rest/v1/rpc/get_my_connect_library_prompt", "headers": headers(), "json": {"p_content_item_id": prompt_id}}
    assert client.calls[1] == {"path": "/rest/v1/rpc/get_referenced_library_prompt", "headers": headers(), "json": {"p_content_item_id": prompt_id, "p_context_keys": ["generell"]}}


def test_get_library_prompt_rejects_invalid_uuid_without_http_call():
    client = RecordingHttpClient([])

    assert repository(client).get_library_prompt(access_token="oauth-access-token", prompt_id="inte-ett-uuid") is None
    assert client.calls == []


def test_get_package_sorts_own_items_before_loading_their_prompt_bodies():
    package_id = "00000000-0000-0000-0000-000000000010"
    first_id = "00000000-0000-0000-0000-000000000011"
    second_id = "00000000-0000-0000-0000-000000000012"
    client = RecordingHttpClient([
        [{"id": package_id, "title": "Paket", "summary": "S", "status": "draft", "package_type": "workflow", "is_library_reference": False}],
        [{"content_item_id": second_id, "position": 1}, {"content_item_id": first_id, "position": 0}],
        [{"id": first_id, "title": "Första", "summary": "", "content": "Första text", "module": "kommun", "status": "draft", "is_library_reference": False}],
        [{"id": second_id, "title": "Andra", "summary": "", "content": "Andra text", "module": "valvet", "status": "draft", "is_library_reference": False}],
    ])

    result = repository(client).get_package(access_token="oauth-access-token", package_id=package_id)

    assert [(item["id"], item["content"]) for item in result["items"]] == [
        (first_id, "Första text"),
        (second_id, "Andra text"),
    ]


def test_get_package_resolves_live_reference_package():
    package_id = "00000000-0000-0000-0000-000000000010"
    client = RecordingHttpClient([
        [{"id": package_id, "title": "Gammal", "summary": "Gammal", "status": "draft", "package_type": "collection", "is_library_reference": True}],
        [{"title": "Levande paket", "summary": "Aktuell", "intro_text": "Intro", "package_type": "collection", "item_title": "Steg", "item_summary": "Beskrivning", "item_prompt_text": "Text", "item_sort_order": 0}],
    ])

    result = repository(client).get_package(access_token="oauth-access-token", package_id=package_id)

    assert result["title"] == "Levande paket"
    assert result["items"] == [{"position": 0, "title": "Steg", "summary": "Beskrivning", "content": "Text"}]


def test_list_shares_excludes_inactive_rows_by_default():
    client = RecordingHttpClient([[{"id": "active", "is_active": True}, {"id": "inactive", "is_active": False}]])

    assert repository(client).list_shares(access_token="oauth-access-token") == [{"id": "active", "is_active": True}]


def test_create_my_prompt_sends_the_oauth_token_and_idempotency_key_to_connect_rpc():
    request_id = "00000000-0000-0000-0000-000000000030"
    client = RecordingHttpClient(
        [{"id": "00000000-0000-0000-0000-000000000031", "title": "Informationsbrev", "status": "draft"}]
    )

    result = repository(client).create_my_prompt(
        access_token="oauth-access-token",
        title="Informationsbrev",
        content="Skriv ett kort informationsbrev.",
        summary="Ett kort brev",
        category="Kommunikation",
        request_id=request_id,
    )

    assert result == {
        "id": "00000000-0000-0000-0000-000000000031",
        "title": "Informationsbrev",
        "status": "draft",
    }
    assert client.calls == [
        {
            "path": "/rest/v1/rpc/connect_create_my_prompt",
            "headers": headers(),
            "json": {
                "p_title": "Informationsbrev",
                "p_content": "Skriv ett kort informationsbrev.",
                "p_summary": "Ett kort brev",
                "p_category": "Kommunikation",
                "p_confirmed": True,
                "p_request_id": request_id,
            },
        }
    ]


@pytest.mark.parametrize(
    ("method_name", "arguments", "rpc_name", "rpc_arguments"),
    [
        ("update_my_prompt", {"prompt_id": "00000000-0000-0000-0000-000000000040", "title": "Ny titel", "content": "Ny text", "summary": None, "category": None, "request_id": "00000000-0000-0000-0000-000000000041"}, "connect_update_my_prompt", {"p_content_item_id": "00000000-0000-0000-0000-000000000040", "p_title": "Ny titel", "p_content": "Ny text", "p_summary": None, "p_category": None, "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000041"}),
        ("archive_my_prompt", {"prompt_id": "00000000-0000-0000-0000-000000000042", "request_id": "00000000-0000-0000-0000-000000000043"}, "connect_archive_my_prompt", {"p_content_item_id": "00000000-0000-0000-0000-000000000042", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000043"}),
        ("save_my_package", {"package_id": None, "title": "Mitt paket", "summary": None, "package_type": "workflow", "request_id": "00000000-0000-0000-0000-000000000044"}, "connect_save_my_package", {"p_draft_id": None, "p_title": "Mitt paket", "p_summary": None, "p_package_type": "workflow", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000044"}),
        ("set_package_prompts", {"package_id": "00000000-0000-0000-0000-000000000045", "prompt_ids": ["00000000-0000-0000-0000-000000000046"], "request_id": "00000000-0000-0000-0000-000000000047"}, "connect_set_package_prompts", {"p_draft_id": "00000000-0000-0000-0000-000000000045", "p_prompt_ids": ["00000000-0000-0000-0000-000000000046"], "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000047"}),
        ("archive_my_package", {"package_id": "00000000-0000-0000-0000-000000000048", "request_id": "00000000-0000-0000-0000-000000000049"}, "connect_archive_my_package", {"p_draft_id": "00000000-0000-0000-0000-000000000048", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000049"}),
        ("add_open_prompt_to_library", {"prompt_id": "00000000-0000-0000-0000-000000000050", "request_id": "00000000-0000-0000-0000-000000000051"}, "connect_add_catalog_prompt_to_library", {"p_prompt_id": "00000000-0000-0000-0000-000000000050", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000051"}),
        ("add_open_package_to_library", {"package_id": "00000000-0000-0000-0000-000000000052", "request_id": "00000000-0000-0000-0000-000000000053"}, "connect_add_catalog_package_to_library", {"p_package_id": "00000000-0000-0000-0000-000000000052", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000053"}),
        ("create_my_share", {"subject_type": "prompt", "subject_id": "00000000-0000-0000-0000-000000000054", "pin_version": False, "expires_at": None, "label": None, "request_id": "00000000-0000-0000-0000-000000000055"}, "connect_create_my_share", {"p_subject_type": "prompt", "p_subject_id": "00000000-0000-0000-0000-000000000054", "p_pin_version": False, "p_expires_at": None, "p_label": None, "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000055"}),
        ("revoke_my_share", {"share_id": "00000000-0000-0000-0000-000000000056", "request_id": "00000000-0000-0000-0000-000000000057"}, "connect_revoke_my_share", {"p_share_id": "00000000-0000-0000-0000-000000000056", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000057"}),
        ("extend_my_share", {"share_id": "00000000-0000-0000-0000-000000000058", "expires_at": "2026-12-31T23:59:59Z", "request_id": "00000000-0000-0000-0000-000000000059"}, "connect_extend_my_share", {"p_share_id": "00000000-0000-0000-0000-000000000058", "p_expires_at": "2026-12-31T23:59:59Z", "p_confirmed": True, "p_request_id": "00000000-0000-0000-0000-000000000059"}),
    ],
)
def test_write_methods_use_the_matching_idempotent_connect_rpc(method_name, arguments, rpc_name, rpc_arguments):
    client = RecordingHttpClient([{"id": "00000000-0000-0000-0000-000000000060", "status": "draft"}])

    result = getattr(repository(client), method_name)(access_token="oauth-access-token", **arguments)

    assert result == {"id": "00000000-0000-0000-0000-000000000060", "status": "draft"}
    assert client.calls == [{"path": f"/rest/v1/rpc/{rpc_name}", "headers": headers(), "json": rpc_arguments}]


def test_search_open_catalog_filters_published_prompt_metadata_without_returning_prompt_text():
    client = RecordingHttpClient([
        [
            {"id": "00000000-0000-0000-0000-000000000080", "title": "Beslutsunderlag", "summary": "Gör ett underlag", "area": "Ledning", "prompt_text": "hemlig malltext"},
            {"id": "00000000-0000-0000-0000-000000000081", "title": "Pressmeddelande", "summary": "Kommunikation", "area": "Kommunikation", "prompt_text": "annan text"},
        ],
    ])

    result = repository(client).search_open_catalog(
        access_token="oauth-access-token", query="beslut", kind="prompt", category=None, limit=10, cursor=0
    )

    assert result == {
        "items": [{"id": "00000000-0000-0000-0000-000000000080", "kind": "prompt", "title": "Beslutsunderlag", "summary": "Gör ett underlag", "category": "Ledning"}],
        "next_cursor": None,
    }
    assert client.calls == [
        {"path": "/rest/v1/rpc/list_published_prompts", "headers": headers(), "json": {"p_context_keys": ["generell"]}},
    ]


def test_create_my_prompt_translates_the_free_prompt_limit_without_leaking_the_database_error():
    import httpx

    class RejectedResponse:
        def raise_for_status(self):
            response = httpx.Response(
                400,
                request=httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/connect_create_my_prompt"),
                json={"message": "Du har nått gränsen på 3 prompts för free-planen."},
            )
            response.raise_for_status()

        def json(self):
            return {"message": "Du har nått gränsen på 3 prompts för free-planen."}

    class RejectedClient:
        def post(self, *args, **kwargs):
            return RejectedResponse()

    from connect_service.data import ConnectWriteError

    with pytest.raises(ConnectWriteError, match="Arkivera en prompt eller uppgradera kontot"):
        repository(RejectedClient()).create_my_prompt(
            access_token="oauth-access-token",
            title="Informationsbrev",
            content="Skriv ett kort informationsbrev.",
            summary=None,
            category=None,
            request_id="00000000-0000-0000-0000-000000000090",
        )
