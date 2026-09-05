from connect_service.data import SupabaseConnectRepository


class RecordingHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, *, headers, params):
        self.calls.append({"path": path, "headers": headers, "params": params})
        return self.responses.pop(0)


class Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("Supabase-fel")


def _repository(http_client):
    return SupabaseConnectRepository(
        supabase_url="https://example.supabase.co",
        publishable_key="sb_publishable_test",
        http_client=http_client,
    )


def test_list_library_uses_callers_token_and_limits_to_private_valvet_items():
    http_client = RecordingHttpClient(
        [Response([{"id": "item-1", "title": "Min prompt", "module": "valvet"}])]
    )

    result = _repository(http_client).list_library(
        access_token="oauth-access-token",
        user_id="00000000-0000-0000-0000-000000000001",
    )

    assert result == [{"id": "item-1", "title": "Min prompt", "module": "valvet"}]
    assert http_client.calls == [
        {
            "path": "/rest/v1/content_items",
            "headers": {
                "apikey": "sb_publishable_test",
                "Authorization": "Bearer oauth-access-token",
            },
            "params": {
                "select": "id,title,summary,updated_at,status,visibility,workspace_id,type,module",
                "module": "eq.valvet",
                "owner_user_id": "eq.00000000-0000-0000-0000-000000000001",
                "visibility": "eq.private",
                "status": "neq.archived",
                "order": "updated_at.desc",
            },
        }
    ]


def test_get_item_uses_the_callers_token_and_returns_only_one_rls_visible_item():
    http_client = RecordingHttpClient([Response([{"id": "item-1", "content": "Privat text"}])])

    result = _repository(http_client).get_item(
        access_token="oauth-access-token",
        item_id="00000000-0000-0000-0000-000000000099",
    )

    assert result == {"id": "item-1", "content": "Privat text"}
    assert http_client.calls[0]["params"] == {
        "select": "id,title,summary,content,updated_at,status,visibility,workspace_id,type,module",
        "id": "eq.00000000-0000-0000-0000-000000000099",
        "limit": "1",
    }


def test_get_item_rejects_an_invalid_identifier_before_calling_supabase():
    http_client = RecordingHttpClient([])

    result = _repository(http_client).get_item(access_token="oauth-access-token", item_id="not-a-uuid")

    assert result is None
    assert http_client.calls == []
