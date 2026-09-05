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