import json
import uuid

import pytest
from starlette.testclient import TestClient

from connect_service import personal
from connect_service.app import create_app
from connect_service.supports import SupportCatalog
from connect_service.work_layer import NotFound, ToolInputError, WorkLayer

from tests.fakes import TOKEN  # noqa: E402
NINE = [
    "motessekreteraren",
    "utredaren",
    "processledaren",
    "forbattringsledaren",
    "forandringsledaren",
    "verksamhetsanalytikern",
    "workshopledaren",
    "produktutvecklaren",
    "superplan",
]


from tests.fakes import MemoryLibrary  # noqa: E402


def rid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def library():
    return MemoryLibrary()


@pytest.fixture()
def layer(library):
    return WorkLayer(SupportCatalog(), library)


# ------------------------------------------------------------ katalogen


def test_catalog_contains_all_nine_specialists_with_intact_sources():
    catalog = SupportCatalog()
    assert catalog.ids() == NINE
    for support_id in NINE:
        payload = catalog.support_payload(support_id)
        assert payload["instructions"].startswith("---\nname: " + support_id)
        assert payload["version"] != "okänd"
        for resource in catalog.resource_paths(support_id):
            assert catalog.read(support_id, resource)


def test_index_entries_have_use_when_and_not_when():
    for entry in SupportCatalog().index():
        assert entry["use_when"]
        if entry["id"] != "superplan":
            assert entry["not_when"].startswith("Använd inte")


def test_support_maps_open_tools_and_lists_dependencies(layer):
    payload = layer.support(TOKEN, "verksamhetsanalytikern", None)
    deps = payload["dependencies"]
    assert "get_template" in deps["tool_mapping"]
    assert {"path": "scripts/profilera.mjs"} .items() <= next(r for r in deps["resources"] if r["path"] == "scripts/profilera.mjs").items()
    assert any("Kodkörning" in item for item in deps["client_capabilities"])
    assert "precedence" in payload


def test_resource_is_readable_and_unknown_paths_are_refused(layer):
    evidence = layer.support(TOKEN, "utredaren", "assets/evidenslogg.md")
    assert evidence["content"]
    for bad in ("../app.py", "SKILL.md", "assets/finns-inte.md"):
        with pytest.raises(NotFound):
            layer.support(TOKEN, "utredaren", bad)
    with pytest.raises(NotFound):
        layer.support(TOKEN, "finns-inte", None)


def test_open_item_supports_superplan_package(layer):
    assert layer.open_item(TOKEN, "package", "superplanlage")["steps"][0]["prompt_text"] == "Fas 1"
    with pytest.raises(NotFound):
        layer.open_item(TOKEN, "prompt", "saknas")


# ------------------------------------------------------------ profil


def test_context_without_profile_lists_nine_supports_and_rules(layer):
    context = layer.context(TOKEN, "user-1")
    assert [entry["id"] for entry in context["supports"]] == NINE
    assert context["profile"]["exists"] is False
    assert context["my_ways_of_working"] == []
    assert context["routing_rules"] and context["how_to_personalize"]
    assert context["always_apply"] == [] and context["profile"]["note"]
    assert all(entry["in_short"] for entry in context["supports"])


def test_profile_preview_does_not_write(layer, library):
    result = layer.save_profile(TOKEN, {"profile": {"tone": "Saklig och vänlig"}})
    assert result["status"] == "preview"
    assert result["changes"] == [{"field": "profile.tone", "before": None, "after": "Saklig och vänlig"}]
    assert library.writes == []


def test_profile_save_requires_request_id(layer):
    with pytest.raises(ToolInputError):
        layer.save_profile(TOKEN, {"profile": {"tone": "Saklig"}, "confirmed": True})


def test_profile_rule_is_saved_and_applied_to_support(layer, library):
    saved = layer.save_profile(
        TOKEN,
        {"rules": {"add": [{"text": "Rekommendationen först i beslutsunderlag.", "applies_to": ["utredaren"]}]}, "confirmed": True, "request_id": rid()},
    )
    assert saved["status"] == "saved" and saved["version"] == 1
    assert library.writes == ["create"]
    payload = layer.support(TOKEN, "utredaren", None)
    assert payload["personal_rules"] == [{"id": "r1", "text": "Rekommendationen först i beslutsunderlag."}]
    assert layer.support(TOKEN, "workshopledaren", None)["personal_rules"] == []


def test_unknown_rule_target_is_rejected(layer):
    with pytest.raises(personal.PersonalError):
        layer.save_profile(TOKEN, {"rules": {"add": [{"text": "x", "applies_to": ["okänd"]}]}})


def test_privacy_findings_block_saving(layer, library):
    result = layer.save_profile(TOKEN, {"profile": {"work_context": "Kontakta anna.svensson@kommun.se"}, "confirmed": True, "request_id": rid()})
    assert result["status"] == "blocked"
    assert "e-postadress" in result["privacy_findings"]
    assert library.writes == []


def test_expected_version_protects_against_overwrite(layer):
    layer.save_profile(TOKEN, {"profile": {"tone": "Saklig"}, "confirmed": True, "request_id": rid()})
    with pytest.raises(ToolInputError):
        layer.save_profile(TOKEN, {"profile": {"tone": "Ledig"}, "expected_version": 0, "confirmed": True, "request_id": rid()})


def test_disable_and_remove_rule(layer):
    layer.save_profile(TOKEN, {"rules": {"add": [{"text": "Korta meningar."}, {"text": "Inga förkortningar."}]}, "confirmed": True, "request_id": rid()})
    layer.save_profile(TOKEN, {"rules": {"update": [{"id": "r1", "active": False}], "remove": ["r2"]}, "confirmed": True, "request_id": rid()})
    rules = layer.context(TOKEN, "u")["profile"]["rules"]
    assert rules == [{"id": "r1", "text": "Korta meningar.", "applies_to": ["all"], "active": False}]
    assert layer.support(TOKEN, "utredaren", None)["personal_rules"] == []


def test_overlapping_rules_are_suggested_not_merged(layer):
    layer.save_profile(
        TOKEN,
        {"rules": {"add": [{"text": "Skriv alltid rekommendationen först i underlaget."}, {"text": "Rekommendationen ska alltid stå först i underlaget."}]}, "confirmed": True, "request_id": rid()},
    )
    context = layer.context(TOKEN, "u")
    assert context["profile"]["possible_overlaps"] == [{"rules": ["r1", "r2"], "reason": "Reglerna säger nästan samma sak."}]
    assert len(context["profile"]["rules"]) == 2


# ------------------------------------------------------------ egna arbetssätt

SUPPLIER_WAY = {
    "name": "Leverantörssvar",
    "purpose": "Skriva tydliga och vänliga svar till leverantörer.",
    "use_when": "När användaren ska svara en leverantör på frågor i en upphandling eller avtalsdialog.",
    "not_when": "Inte för interna mejl eller beslutsunderlag.",
    "instructions": "Skriv tydligt och vänligt. Skilj alltid krav från önskemål.",
    "quality_rules": ["Krav och önskemål står under egna rubriker."],
}


def test_create_way_from_scratch_and_reuse_in_new_conversation(layer, library):
    # Nya arbetssätt sparas som skills (Creator 2.0).
    preview = layer.save_way(TOKEN, dict(SUPPLIER_WAY))
    assert preview["status"] == "preview" and preview["id"] == "skill:leverantorssvar"
    assert preview["confirm_text"].startswith("Nytt arbetssätt: ”Leverantörssvar”.")
    assert library.writes == [] and library.skill_writes == []
    saved = layer.save_way(TOKEN, {**SUPPLIER_WAY, "confirmed": True, "request_id": rid()})
    assert saved["status"] == "saved" and saved["id"] == "skill:leverantorssvar"

    fresh = WorkLayer(SupportCatalog(), library)
    context = fresh.context(TOKEN, "u")
    assert context["my_skills"][0]["id"] == "skill:leverantorssvar"
    assert context["my_ways_of_working"] == []
    support = fresh.support(TOKEN, "skill:leverantorssvar", None)
    assert "Skilj alltid krav från önskemål." in support["instructions"]
    assert "Krav och önskemål står under egna rubriker." in support["instructions"]


def test_way_extending_specialist_combines_with_base_and_rules(layer):
    layer.save_profile(TOKEN, {"rules": {"add": [{"text": "Rekommendationen först."}]}, "confirmed": True, "request_id": rid()})
    layer.save_way(
        TOKEN,
        {
            "name": "Mina korta utredningar",
            "purpose": "Korta beslutsunderlag.",
            "use_when": "När jag utreder en fråga och behöver ett kort beslutsunderlag.",
            "not_when": "Inte för långa utredningar med många källor.",
            "instructions": "Max två sidor. Sammanfattning först.",
            "extends": "utredaren",
            "confirmed": True,
            "request_id": rid(),
        },
    )
    support = layer.support(TOKEN, "skill:mina-korta-utredningar", None)
    assert support["base_method"]["id"] == "utredaren"
    assert support["base_method"]["instructions"].startswith("---\nname: utredaren")
    assert "säkerhets- och integritetsregler" in support["how_to_combine"]
    assert support["personal_rules"] == [{"id": "r1", "text": "Rekommendationen först."}]
    assert layer.support(TOKEN, "utredaren", None)["my_adaptations"][0]["id"] == "skill:mina-korta-utredningar"


def test_way_rejects_unknown_base_and_missing_fields(layer):
    with pytest.raises(ToolInputError):
        layer.save_way(TOKEN, {**SUPPLIER_WAY, "extends": "okänd"})
    with pytest.raises(ToolInputError):
        layer.save_way(TOKEN, {"name": "Halvfärdig"})
    with pytest.raises(ToolInputError):
        layer.save_way(TOKEN, {key: value for key, value in SUPPLIER_WAY.items() if key != "not_when"})


def test_duplicate_way_name_is_refused(layer):
    from connect_service.data import ConnectWriteError

    layer.save_way(TOKEN, {**SUPPLIER_WAY, "confirmed": True, "request_id": rid()})
    with pytest.raises((ToolInputError, ConnectWriteError)):
        layer.save_way(TOKEN, {**SUPPLIER_WAY, "confirmed": True, "request_id": rid()})


def legacy_way(layer, fields):
    """Ett äldre mitt:-arbetssätt, skapat som före Creator 2.0 (bakåtkompatibilitet)."""
    return layer._save_legacy_way(TOKEN, {**fields, "confirmed": True, "request_id": rid()})


def test_deactivate_and_delete_way(layer, library):
    legacy_way(layer, SUPPLIER_WAY)
    layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "active": False, "confirmed": True, "request_id": rid()})
    context = layer.context(TOKEN, "u")
    assert context["my_ways_of_working"] == []
    assert context["inactive_ways_of_working"][0]["id"] == "mitt:leverantorssvar"
    preview = layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "delete": True})
    assert preview["status"] == "preview"
    layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "delete": True, "confirmed": True, "request_id": rid()})
    assert layer.context(TOKEN, "u")["my_ways_of_working"] == []
    assert library.writes[-1] == "archive"


def test_new_way_as_skill_can_be_turned_off_and_on(layer, library):
    layer.save_way(TOKEN, {**SUPPLIER_WAY, "confirmed": True, "request_id": rid()})
    assert layer.save_way(TOKEN, {"id": "skill:leverantorssvar", "active": False})["status"] == "preview"
    layer.save_way(TOKEN, {"id": "skill:leverantorssvar", "active": False, "confirmed": True, "request_id": rid()})
    context = layer.context(TOKEN, "u")
    assert context["my_skills"] == [] and context["inactive_skills"][0]["id"] == "skill:leverantorssvar"
    layer.save_way(TOKEN, {"id": "skill:leverantorssvar", "instructions": "Ny instruktion.", "confirmed": True, "request_id": rid()})
    assert layer.get_skill(TOKEN, {"id": "skill:leverantorssvar"})["version"] == 2


def test_legacy_way_can_be_converted_to_skill_without_losing_it(layer, library):
    legacy_way(layer, SUPPLIER_WAY)
    preview = layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "convert_to_skill": True})
    assert preview["status"] == "preview" and "gör om" in preview["confirm_text"]
    assert library.skill_writes == []
    done = layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "convert_to_skill": True, "confirmed": True, "request_id": rid()})
    assert done["id"] == "skill:leverantorssvar" and done["replaced"] == "mitt:leverantorssvar"
    context = layer.context(TOKEN, "u")
    assert context["my_ways_of_working"] == []
    assert context["inactive_ways_of_working"][0]["id"] == "mitt:leverantorssvar"
    assert context["my_skills"][0]["id"] == "skill:leverantorssvar"


# ------------------------------------------------------------ versioner


def test_history_and_restore_create_new_version(layer):
    legacy_way(layer, SUPPLIER_WAY)
    layer.save_way(TOKEN, {"id": "mitt:leverantorssvar", "instructions": "Ny instruktion.", "note": "Kortare", "confirmed": True, "request_id": rid()})
    history = layer.history(TOKEN, "mitt:leverantorssvar")["versions"]
    assert [entry["version"] for entry in history] == [2, 1]

    preview = layer.restore(TOKEN, {"target": "mitt:leverantorssvar", "version": 1})
    assert preview["status"] == "preview"
    assert preview["changes"] == [{"field": "instructions", "before": "Ny instruktion.", "after": SUPPLIER_WAY["instructions"]}]
    restored = layer.restore(TOKEN, {"target": "mitt:leverantorssvar", "version": 1, "confirmed": True, "request_id": rid()})
    assert restored["version"] == 3
    assert SUPPLIER_WAY["instructions"] in layer.support(TOKEN, "mitt:leverantorssvar", None)["instructions"]
    assert [entry["version"] for entry in layer.history(TOKEN, "mitt:leverantorssvar")["versions"]] == [3, 2, 1]


def test_restore_unknown_version_explains_available(layer):
    layer.save_profile(TOKEN, {"profile": {"tone": "A"}, "confirmed": True, "request_id": rid()})
    layer.save_profile(TOKEN, {"profile": {"tone": "B"}, "confirmed": True, "request_id": rid()})
    with pytest.raises(personal.PersonalError, match="Tillgängliga"):
        layer.restore(TOKEN, {"target": "profile", "version": 7})


def test_no_change_is_not_a_new_version(layer):
    layer.save_profile(TOKEN, {"profile": {"tone": "A"}, "confirmed": True, "request_id": rid()})
    with pytest.raises(personal.PersonalError):
        layer.save_profile(TOKEN, {"profile": {"tone": "A"}})


def test_history_is_capped_and_document_stays_within_limit():
    doc = None
    for number in range(15):
        doc = personal.apply_profile_changes(doc, {"profile": {"tone": f"Ton {number}"}}, note=None, known_targets=set())
    assert len(doc["history"]) == personal.MAX_HISTORY
    content = personal.render_profile(doc)
    assert len(content) <= personal.MAX_CONTENT
    assert personal.parse_document(content)["version"] == 15


def test_unrelated_creator_prompts_are_ignored(layer, library):
    library.rows["x"] = {"id": "x", "title": "Vanlig prompt", "content": "```connect-data\n{\"connect_type\": \"way\"}\n```", "category": "annat", "status": "draft", "updated_at": "1"}
    assert layer.context(TOKEN, "u")["my_ways_of_working"] == []


# ------------------------------------------------------------ MCP-ytan


class Verifier:
    def verify(self, token):
        if token != TOKEN:
            raise ValueError("fel")
        return {"sub": "00000000-0000-0000-0000-000000000001"}


def http_client(library):
    return TestClient(create_app(resource_url="https://connect-dev.promptbanken.se/mcp", authorization_server="https://example.supabase.co/auth/v1", token_verifier=Verifier(), library=library))


def call(client, method, params=None):
    return client.post("/mcp", headers={"Authorization": f"Bearer {TOKEN}"}, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def test_initialize_announces_instructions_and_negotiates_version(library):
    client = http_client(library)
    result = call(client, "initialize", {"protocolVersion": "2025-03-26"}).json()["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert "get_connect_context" in result["instructions"]
    assert result["capabilities"] == {"tools": {}, "prompts": {}}
    assert call(client, "initialize", {"protocolVersion": "1999-01-01"}).json()["result"]["protocolVersion"] == "2025-06-18"


def test_notifications_are_accepted_without_body(library):
    response = call(http_client(library), "notifications/initialized")
    assert response.status_code == 202


def test_prompts_offer_manual_selection(library):
    client = http_client(library)
    prompts = call(client, "prompts/list").json()["result"]["prompts"]
    assert [prompt["name"] for prompt in prompts] == NINE
    message = call(client, "prompts/get", {"name": "workshopledaren"}).json()["result"]["messages"][0]["content"]["text"]
    assert "name: workshopledaren" in message


def test_tools_call_routes_to_work_layer_and_maps_errors(library):
    client = http_client(library)
    context = call(client, "tools/call", {"name": "get_connect_context", "arguments": {}}).json()["result"]["structuredContent"]
    assert context["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert len(context["supports"]) == 9
    missing = call(client, "tools/call", {"name": "get_support", "arguments": {"id": "saknas"}}).json()
    assert missing["error"]["code"] == -32004
    invalid = call(client, "tools/call", {"name": "save_my_profile", "arguments": {"rules": {"add": [{"text": "x", "applies_to": ["okänd"]}]}}}).json()
    assert invalid["error"]["code"] == -32602
    assert "okänd" in invalid["error"]["message"]


def test_context_payload_stays_compact(layer):
    size = len(json.dumps(layer.context(TOKEN, "u"), ensure_ascii=False))
    assert size < 12000
