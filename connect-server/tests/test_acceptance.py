"""Acceptansscenarier för förenklingen av Connect DEV (2026-11-11).

Valet av stöd görs av AI-klientens modell, inte av Connect. Scenario 1–3 kan
därför bara testas här som att kontraktet ger modellen rätt underlag. Hur
ChatGPT eller Claude faktiskt väljer mäts i klienten, se
docs/forenkling-2026-11-11.md.
"""

import uuid

import httpx
import pytest

from connect_service import work_layer as wl
from connect_service.data import ConnectWriteError, SupabaseConnectRepository
from connect_service.supports import SupportCatalog
from tests.test_work_layer import TOKEN, MemoryLibrary


def rid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def library():
    return MemoryLibrary()


@pytest.fixture()
def layer(library):
    return wl.WorkLayer(SupportCatalog(), library)


# ------------------------------------------------------------ 1–3. rätt stöd


def test_1_simple_question_is_answered_without_connect(layer):
    text = wl.SERVER_INSTRUCTIONS
    assert "Enkel fråga" in text and "använd inte Connect" in text
    assert any("Inget stöd vid enkla frågor" in rule for rule in wl.ROUTING_RULES)
    # get_connect_context ska inte anropas för enkla frågor enligt sin egen beskrivning.
    description = next(tool for tool in wl.tool_definitions() if tool["name"] == "get_connect_context")["description"]
    assert "Inte vid enkla frågor" in description


def test_2_and_3_index_points_investigation_and_workshop_to_the_right_specialist(layer):
    supports = {entry["id"]: entry for entry in layer.context(TOKEN, "u")["supports"]}
    assert "Utreda" in supports["utredaren"]["in_short"]
    assert "för- och nackdelar" in supports["utredaren"]["use_when"]
    assert "workshop" in supports["workshopledaren"]["in_short"]
    assert "workshop" in supports["workshopledaren"]["use_when"].casefold()
    # Mötessekreteraren pekar uttryckligen bort workshopar.
    assert "Workshopledaren" in supports["motessekreteraren"]["not_when"]


def test_explicit_specialist_choice_is_honoured(layer):
    assert any("vid namn" in rule for rule in layer.context(TOKEN, "u")["routing_rules"])


def test_context_never_claims_automatic_activation():
    text = (wl.SERVER_INSTRUCTIONS + " ".join(wl.ROUTING_RULES)).casefold()
    assert "automatiskt" not in text
    assert any("Connect väljer inget åt dig" in rule for rule in wl.ROUTING_RULES)


# ------------------------------------------------------------ 4–5. anpassning genom samtal


SHORTER = {"rules": {"add": [{"text": "Kortare sammanfattningar.", "applies_to": ["all"]}]}}


def test_4_next_time_shorter_summaries_gives_a_readable_preview_and_no_write(layer, library):
    preview = layer.save_profile(TOKEN, SHORTER)
    assert preview["status"] == "preview"
    assert preview["confirm_text"] == "Ny regel: ”Kortare sammanfattningar” – gäller alla uppgifter. Vill du spara det?"
    assert library.writes == []


def test_4_investigation_rule_is_scoped_to_utredaren_with_its_name(layer):
    preview = layer.save_profile(
        TOKEN, {"rules": {"add": [{"text": "Börja med att beskriva problemet.", "applies_to": ["utredaren"]}]}}
    )
    assert "gäller Utredaren." in preview["confirm_text"]


def test_5_saved_rule_is_verified_and_used_in_a_new_conversation(layer, library):
    saved = layer.save_profile(TOKEN, {**SHORTER, "confirmed": True, "request_id": rid()})
    assert saved["status"] == "saved" and saved["verified"] is True
    assert saved["saved_text"].startswith("Sparat. Ny regel")

    fresh = wl.WorkLayer(SupportCatalog(), library)  # ny konversation, samma bibliotek
    context = fresh.context(TOKEN, "u")
    assert context["always_apply"] == [{"id": "r1", "text": "Kortare sammanfattningar."}]
    rules = fresh.support(TOKEN, "workshopledaren", None)["personal_rules"]
    assert {"id": "r1", "text": "Kortare sammanfattningar."} in rules


def test_5_scoped_rule_only_reaches_its_specialist(layer):
    layer.save_profile(
        TOKEN,
        {"rules": {"add": [{"text": "Börja med att beskriva problemet.", "applies_to": ["utredaren"]}]}, "confirmed": True, "request_id": rid()},
    )
    assert layer.support(TOKEN, "utredaren", None)["personal_rules"]
    assert layer.support(TOKEN, "workshopledaren", None)["personal_rules"] == []
    assert layer.context(TOKEN, "u")["always_apply"] == []


def test_reused_request_id_is_not_reported_as_saved(layer):
    request_id = rid()
    layer.save_profile(TOKEN, {**SHORTER, "confirmed": True, "request_id": request_id})
    other = {"rules": {"add": [{"text": "Använd punktlistor.", "applies_to": ["all"]}]}}
    with pytest.raises(wl.ToolInputError, match="inte sparad"):
        layer.save_profile(TOKEN, {**other, "confirmed": True, "request_id": request_id})


# ------------------------------------------------------------ 6. kvot


class QuotaLibrary(MemoryLibrary):
    def create_my_prompt(self, **kwargs):
        raise ConnectWriteError("Du har nått gränsen för privata prompts i Free-läget.", kind="quota")


def test_6_free_account_at_quota_gets_an_understandable_message_and_nothing_changes():
    library = QuotaLibrary()
    layer = wl.WorkLayer(SupportCatalog(), library)
    with pytest.raises(ConnectWriteError) as raised:
        layer.save_profile(TOKEN, {**SHORTER, "confirmed": True, "request_id": rid()})
    assert raised.value.kind == "quota"
    message = str(raised.value)
    assert "inget har ändrats" in message and "Arkivera en prompt" in message and "det här samtalet" in message
    assert library.rows == {}


def _rejecting(status, payload):
    class Rejected:
        def raise_for_status(self):
            httpx.Response(status, request=httpx.Request("POST", "https://x/rest/v1/rpc/f"), json=payload).raise_for_status()

        def json(self):
            return payload

    class Client:
        def post(self, *args, **kwargs):
            return Rejected()

    return SupabaseConnectRepository(supabase_url="https://x", publishable_key="k", http_client=Client())


@pytest.mark.parametrize(
    ("status", "payload", "kind", "fragment"),
    [
        (400, {"code": "P0001", "message": "Du har nått gränsen på 3 prompts för free-planen."}, "quota", "Free-läget"),
        (401, {"message": "JWT expired"}, "permission", "Logga in på nytt"),
        (403, {"code": "42501", "message": "permission denied for table content_items"}, "permission", "behörighet"),
        (500, {"message": "connection reset"}, "technical", "Inget har ändrats"),
        (400, {"code": "P0001", "message": "Prompttext krävs (max 20000 tecken)."}, "validation", "Prompttext krävs"),
        (400, {"code": "23505", "message": "duplicate key value violates unique constraint \"x_pkey\""}, "validation", "Kontrollera uppgifterna"),
    ],
)
def test_6_errors_separate_quota_permission_validation_and_technical(status, payload, kind, fragment):
    with pytest.raises(ConnectWriteError) as raised:
        _rejecting(status, payload).archive_my_prompt(access_token="t", prompt_id=str(uuid.uuid4()), request_id=rid())
    assert raised.value.kind == kind
    assert fragment in str(raised.value)
    assert "content_items" not in str(raised.value) and "pkey" not in str(raised.value)


# ------------------------------------------------------------ 7–8. nej och avaktivering


def test_7_saying_no_leaves_nothing_behind(layer, library):
    layer.save_profile(TOKEN, SHORTER)  # förhandsvisning, användaren säger nej
    layer.save_way(
        TOKEN,
        {"name": "Leverantörssvar", "purpose": "Svara leverantörer.", "use_when": "Leverantörsfrågor.", "instructions": "Kort och vänligt."},
    )
    assert library.writes == [] and library.rows == {}
    assert layer.context(TOKEN, "u")["profile"]["exists"] is False


def test_8_user_can_turn_off_a_rule_and_a_way_of_working(layer):
    layer.save_profile(TOKEN, {**SHORTER, "confirmed": True, "request_id": rid()})
    off = {"rules": {"update": [{"id": "r1", "active": False}]}}
    preview = layer.save_profile(TOKEN, off)
    assert preview["confirm_text"] == "Stänger av regeln ”Kortare sammanfattningar”. Vill du spara det?"
    layer.save_profile(TOKEN, {**off, "confirmed": True, "request_id": rid()})
    assert layer.context(TOKEN, "u")["always_apply"] == []

    way = {"name": "Leverantörssvar", "purpose": "Svara leverantörer.", "use_when": "Leverantörsfrågor.", "instructions": "Kort och vänligt."}
    layer.save_way(TOKEN, {**way, "confirmed": True, "request_id": rid()})
    preview = layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "active": False})
    assert "kan slås på igen" in preview["confirm_text"]
    layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "active": False, "confirmed": True, "request_id": rid()})
    context = layer.context(TOKEN, "u")
    assert context["my_ways_of_working"] == []
    assert context["inactive_ways_of_working"] == [{"id": "mitt:leverantorssvar", "name": "Leverantörssvar", "version": 2}]


# ------------------------------------------------------------ friktion i katalogen


def test_multi_word_catalog_search_finds_and_ranks_items():
    rows = [
        {"id": "1", "title": "Sortera råa mötesanteckningar", "summary": "Gör anteckningar tydliga.", "area": "möten"},
        {"id": "2", "title": "Verifiera beslut och uppdrag", "summary": "Efter mötet: mötesanteckningar till beslut.", "area": "möten"},
        {"id": "3", "title": "Budgetkommentar", "summary": "Ekonomi.", "area": "ekonomi"},
    ]

    class Client:
        def post(self, path, **kwargs):
            class R:
                def raise_for_status(self):
                    return None

                def json(self):
                    return rows if "prompts" in path else []

            return R()

    repo = SupabaseConnectRepository(supabase_url="https://x", publishable_key="k", http_client=Client())
    result = repo.search_open_catalog(access_token="t", query="mötesanteckningar beslut", kind="prompt", category=None, limit=10, cursor=0)
    assert [item["id"] for item in result["items"]] == ["2", "1"]


# ------------------------------------------------------------ sju kärnverktyg


CORE = {
    "get_connect_context",
    "get_support",
    "get_open_item",
    "save_my_profile",
    "save_my_way_of_working",
    "get_my_history",
    "restore_my_version",
}


def _core_client(library, profile="core"):
    from starlette.testclient import TestClient

    from connect_service.app import create_app
    from tests.test_work_layer import Verifier

    return TestClient(
        create_app(
            resource_url="https://connect-dev.promptbanken.se/mcp",
            authorization_server="https://example.supabase.co/auth/v1",
            token_verifier=Verifier(),
            library=library,
            tool_profile=profile,
        )
    )


def _rpc(client, method, params=None):
    return client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    ).json()


def test_core_profile_lists_exactly_the_seven_tools(library):
    tools = _rpc(_core_client(library), "tools/list")["result"]["tools"]
    assert {tool["name"] for tool in tools} == CORE


def test_core_profile_refuses_library_tools(library):
    response = _rpc(_core_client(library), "tools/call", {"name": "list_my_library", "arguments": {}})
    assert response["error"]["code"] == -32601
    assert "finns inte" in response["error"]["message"]


def test_core_profile_still_saves_and_uses_a_new_way_of_working(library):
    client = _core_client(library)
    way = {"name": "Leverantörssvar", "purpose": "Svara leverantörer.", "use_when": "Jag ska svara en leverantör.", "instructions": "Tacka, svara kort, avsluta med nästa steg."}
    preview = _rpc(client, "tools/call", {"name": "save_my_way_of_working", "arguments": way})
    assert "Nytt arbetssätt: ”Leverantörssvar”" in preview["result"]["structuredContent"]["confirm_text"]
    saved = _rpc(client, "tools/call", {"name": "save_my_way_of_working", "arguments": {**way, "confirmed": True, "request_id": rid()}})
    assert saved["result"]["structuredContent"]["verified"] is True
    context = _rpc(client, "tools/call", {"name": "get_connect_context", "arguments": {}})["result"]["structuredContent"]
    assert context["my_ways_of_working"][0]["id"] == "mitt:leverantorssvar"


def test_full_profile_keeps_the_library_tools(library):
    tools = _rpc(_core_client(library, "full"), "tools/list")["result"]["tools"]
    assert len(tools) == 26


def test_catalog_search_mapping_points_to_get_open_item():
    from connect_service.supports import OPEN_TOOL_MAPPING

    assert all("search_open_catalog" not in target for target in OPEN_TOOL_MAPPING.values())
