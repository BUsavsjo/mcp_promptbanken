"""Regressionstester för de åtta scenarierna i användartestet 2026-11-11.

Allt körs mot ett syntetiskt bibliotek i minnet med en isolerad testanvändare.
Valet av stöd görs av AI-klientens modell. Testerna här verifierar kontraktet
som modellen får (MCP-svar, regler, prioritering), inte att ChatGPT faktiskt
anropar Connect. Det mäts manuellt, se docs/chatgpt-testprotokoll.md.
"""

import json
import uuid

import pytest

from connect_service import personal
from connect_service import work_layer as wl
from connect_service.data import ConnectWriteError
from connect_service.supports import SupportCatalog
from tests.test_work_layer import NINE, TOKEN, MemoryLibrary

GLOBAL = {"rules": {"add": [{"text": "Ge kortare sammanfattningar.", "applies_to": ["all"]}]}}
INVESTIGATION = {"rules": {"add": [{"text": "Börja alltid utredningar med en problembeskrivning.", "applies_to": ["utredaren"]}]}}
SUPPLIER = {
    "name": "Leverantörssvar",
    "purpose": "Svara leverantörer tydligt och vänligt.",
    "use_when": "Användaren vill formulera ett svar till en leverantör",
    "not_when": "Avtalstvister eller juridiska frågor",
    "instructions": "Tacka först, svara på frågan i högst tre stycken och avsluta med nästa steg.",
}


def rid() -> str:
    return str(uuid.uuid4())


def yes(arguments: dict) -> dict:
    return {**arguments, "confirmed": True, "request_id": rid()}


@pytest.fixture()
def library():
    return MemoryLibrary()


@pytest.fixture()
def layer(library):
    return wl.WorkLayer(SupportCatalog(), library)


def rule_texts(rules) -> set[str]:
    return {rule["text"] for rule in rules}


# ------------------------------------------------------------ 1. enkel fråga (negativ)


def test_scenario_1_simple_question_has_no_connect_path():
    assert "Enkel fråga" in wl.SERVER_INSTRUCTIONS and "använd inte Connect" in wl.SERVER_INSTRUCTIONS
    tools = {tool["name"]: tool for tool in wl.tool_definitions()}
    assert "Inte vid enkla frågor" in tools["get_connect_context"]["description"]
    # Kontexten tar inga argument, så användarens fråga kan aldrig skickas med.
    assert tools["get_connect_context"]["inputSchema"]["properties"] == {}


def test_scenario_1_no_tool_accepts_free_task_text():
    for tool in wl.tool_definitions():
        properties = set(tool["inputSchema"].get("properties", {}))
        assert not properties & {"query", "task", "prompt", "message", "text", "document"}, tool["name"]


# ------------------------------------------------------------ 2. utredning


def test_scenario_2_investigation_gets_utredaren_with_adaptive_guidance(layer):
    support = layer.support(TOKEN, "utredaren", None)
    assert support["instructions"].startswith("---\nname: utredaren")
    assert support["version"] == "1.0.3"
    joined = " ".join(support["how_to_apply"])
    assert "Skala efter uppgiften" in joined
    assert "hitta inte på fakta" in joined  # kvalitetskraven behålls


def test_scenario_2_method_text_is_unchanged_from_source():
    catalog = SupportCatalog()
    for support_id in NINE:
        assert catalog.support_payload(support_id)["instructions"].startswith("---\nname: " + support_id)


# ------------------------------------------------------------ 3. global regel


def test_scenario_3_global_rule_preview_then_save_reaches_every_specialist(layer, library):
    preview = layer.save_profile(TOKEN, GLOBAL)
    assert preview["status"] == "preview" and library.writes == []
    assert preview["confirm_text"] == "Ny regel: ”Ge kortare sammanfattningar” – gäller alla uppgifter. Vill du spara det?"

    saved = layer.save_profile(TOKEN, yes(GLOBAL))
    assert saved["verified"] is True
    for support_id in NINE:
        assert "Ge kortare sammanfattningar." in rule_texts(layer.support(TOKEN, support_id, None)["personal_rules"])
    assert rule_texts(layer.context(TOKEN, "u")["always_apply"]) == {"Ge kortare sammanfattningar."}


def test_scenario_3_global_rule_also_reaches_own_ways_of_working(layer):
    layer.save_profile(TOKEN, yes(GLOBAL))
    layer.save_way(TOKEN, yes(SUPPLIER))
    assert "Ge kortare sammanfattningar." in rule_texts(layer.support(TOKEN, "mitt:leverantorssvar", None)["personal_rules"])


# ------------------------------------------------------------ 4. specialistregel


def test_scenario_4_specialist_rule_is_scoped_and_does_not_leak(layer):
    preview = layer.save_profile(TOKEN, INVESTIGATION)
    assert preview["confirm_text"].endswith("– gäller Utredaren. Vill du spara det?")
    layer.save_profile(TOKEN, yes(INVESTIGATION))

    text = "Börja alltid utredningar med en problembeskrivning."
    assert text in rule_texts(layer.support(TOKEN, "utredaren", None)["personal_rules"])
    for support_id in set(NINE) - {"utredaren"}:
        assert text not in rule_texts(layer.support(TOKEN, support_id, None)["personal_rules"]), support_id
    assert layer.context(TOKEN, "u")["always_apply"] == []


def test_scenario_4_specialist_rule_does_not_leak_into_unrelated_own_way(layer):
    layer.save_profile(TOKEN, yes(INVESTIGATION))
    layer.save_way(TOKEN, yes(SUPPLIER))
    assert layer.support(TOKEN, "mitt:leverantorssvar", None)["personal_rules"] == []


# ------------------------------------------------------------ 5. byte av specialist


def test_scenario_5_switching_specialist_keeps_global_and_drops_specific(layer):
    layer.save_profile(TOKEN, yes(GLOBAL))
    layer.save_profile(TOKEN, yes(INVESTIGATION))
    investigation = rule_texts(layer.support(TOKEN, "utredaren", None)["personal_rules"])
    workshop = rule_texts(layer.support(TOKEN, "workshopledaren", None)["personal_rules"])
    assert investigation == {"Ge kortare sammanfattningar.", "Börja alltid utredningar med en problembeskrivning."}
    assert workshop == {"Ge kortare sammanfattningar."}


# ------------------------------------------------------------ 6. eget arbetssätt och prioritering


def test_scenario_6_own_way_preview_save_and_listing(layer, library):
    preview = layer.save_way(TOKEN, SUPPLIER)
    assert preview["confirm_text"].startswith("Nytt arbetssätt: ”Leverantörssvar”. Används när: Användaren vill formulera")
    assert ".." not in preview["confirm_text"]
    assert library.writes == []
    layer.save_way(TOKEN, yes(SUPPLIER))
    ways = layer.context(TOKEN, "u")["my_ways_of_working"]
    assert ways[0]["id"] == "mitt:leverantorssvar" and ways[0]["use_when"] == SUPPLIER["use_when"]


def test_scenario_6_own_way_takes_precedence_over_specialist(layer):
    rules = " ".join(wl.ROUTING_RULES)
    assert "Passar ett aktivt eget arbetssätt (mitt:) uppgiften, använd det, även om en specialist också passar" in rules
    adapted = {**SUPPLIER, "name": "Mina utredningar", "use_when": "Utredningar i min förvaltning", "extends": "utredaren"}
    layer.save_way(TOKEN, yes(adapted))
    support = layer.support(TOKEN, "utredaren", None)
    assert support["my_adaptations"][0]["id"] == "mitt:mina-utredningar"
    assert "följ det i stället" in support["adaptation_hint"]
    own = layer.support(TOKEN, "mitt:mina-utredningar", None)
    assert own["base_method"]["id"] == "utredaren" and own["how_to_apply"]


def test_scenario_6_inactive_own_way_is_not_offered(layer):
    adapted = {**SUPPLIER, "name": "Mina utredningar", "use_when": "Utredningar", "extends": "utredaren"}
    layer.save_way(TOKEN, yes(adapted))
    layer.save_way(TOKEN, yes({"id": "mitt:mina-utredningar", "active": False}))
    assert layer.context(TOKEN, "u")["my_ways_of_working"] == []
    support = layer.support(TOKEN, "utredaren", None)
    assert support["my_adaptations"] == [] and "adaptation_hint" not in support


# ------------------------------------------------------------ 7. ändra, inaktivera och återställa


def test_scenario_7_full_lifecycle_deactivate_history_restore(layer):
    layer.save_profile(TOKEN, yes(GLOBAL))  # version 1
    off = {"rules": {"update": [{"id": "r1", "active": False}]}}
    assert layer.save_profile(TOKEN, off)["confirm_text"] == "Stänger av regeln ”Ge kortare sammanfattningar”. Vill du spara det?"
    layer.save_profile(TOKEN, yes({**off, "expected_version": 1}))  # version 2
    assert layer.context(TOKEN, "u")["always_apply"] == []
    assert layer.support(TOKEN, "utredaren", None)["personal_rules"] == []

    history = layer.history(TOKEN, "profile")
    assert [entry["version"] for entry in history["versions"]] == [2, 1]
    preview = layer.restore(TOKEN, {"target": "profile", "version": 1})
    assert preview["status"] == "preview"
    assert preview["confirm_text"] == "Går tillbaka till version 1. Slår på regeln ”Ge kortare sammanfattningar” igen. Vill du spara det?"
    restored = layer.restore(TOKEN, {"target": "profile", "version": 1, "confirmed": True, "request_id": rid()})
    assert restored["version"] == 3 and restored["verified"] is True
    assert rule_texts(layer.context(TOKEN, "u")["always_apply"]) == {"Ge kortare sammanfattningar."}


def test_scenario_7_missing_rule_id_lists_existing_rules(layer):
    layer.save_profile(TOKEN, yes(GLOBAL))
    with pytest.raises(personal.PersonalError, match=r"Hittar ingen regel med id r9\. Användarens regler: r1 ”Ge kortare"):
        layer.save_profile(TOKEN, {"rules": {"update": [{"id": "r9", "active": False}]}})


def test_scenario_7_missing_rule_id_without_profile(layer):
    with pytest.raises(personal.PersonalError, match="inga regler ännu"):
        layer.save_profile(TOKEN, {"rules": {"remove": ["r1"]}})


def test_scenario_7_version_conflict_saves_nothing_and_explains(layer, library):
    layer.save_profile(TOKEN, yes(GLOBAL))
    writes = len(library.writes)
    with pytest.raises(wl.ToolInputError, match=r"Inget sparades.*nu version 1, angiven 0"):
        layer.save_profile(TOKEN, yes({**INVESTIGATION, "expected_version": 0}))
    assert len(library.writes) == writes


def test_scenario_7_empty_history_is_friendly(layer):
    assert layer.history(TOKEN, "profile")["message"].startswith("Du har inga sparade versioner ännu")


def test_scenario_7_turning_off_an_already_off_rule_is_explained(layer):
    layer.save_profile(TOKEN, yes(GLOBAL))
    off = {"rules": {"update": [{"id": "r1", "active": False}]}}
    layer.save_profile(TOKEN, yes(off))
    with pytest.raises(personal.PersonalError, match="Det gäller redan"):
        layer.save_profile(TOKEN, off)


# ------------------------------------------------------------ 8. ny konversation


def test_scenario_8_new_conversation_sees_saved_rules_and_ways(layer, library):
    layer.save_profile(TOKEN, yes(GLOBAL))
    layer.save_profile(TOKEN, yes(INVESTIGATION))
    layer.save_way(TOKEN, yes(SUPPLIER))

    fresh = wl.WorkLayer(SupportCatalog(), library)  # ingen delad minnesbild utöver lagringen
    context = fresh.context(TOKEN, "u")
    assert rule_texts(context["always_apply"]) == {"Ge kortare sammanfattningar."}
    assert [way["id"] for way in context["my_ways_of_working"]] == ["mitt:leverantorssvar"]
    assert "Börja alltid utredningar med en problembeskrivning." in rule_texts(fresh.support(TOKEN, "utredaren", None)["personal_rules"])


# ------------------------------------------------------------ negativa fall: inga ändringar utan ja


@pytest.mark.parametrize(
    "call",
    [
        lambda layer: layer.save_profile(TOKEN, GLOBAL),
        lambda layer: layer.save_way(TOKEN, SUPPLIER),
        lambda layer: layer.save_profile(TOKEN, {**GLOBAL, "confirmed": False}),
    ],
)
def test_nothing_is_written_without_explicit_confirmation(layer, library, call):
    call(layer)
    assert library.writes == [] and library.rows == {}


def test_personal_data_is_blocked_before_saving(layer, library):
    blocked = layer.save_profile(TOKEN, {"rules": {"add": [{"text": "Skicka alltid kopia till anna.svensson@example.se"}]}, "confirmed": True, "request_id": rid()})
    assert blocked["status"] == "blocked" and library.writes == []


def test_quota_failure_changes_nothing(library):
    class Full(MemoryLibrary):
        def create_my_prompt(self, **kwargs):
            raise ConnectWriteError("gräns", kind="quota")

    full = Full()
    with pytest.raises(ConnectWriteError) as raised:
        wl.WorkLayer(SupportCatalog(), full).save_profile(TOKEN, yes(GLOBAL))
    assert raised.value.kind == "quota" and full.rows == {}


# ------------------------------------------------------------ bakåtkompatibilitet


LEGACY_PROFILE = """# Min arbetsprofil (Connect)

```connect-data
{"connect_type": "profile", "schema": 1, "version": 2, "profile": {"tone": "Saklig"},
 "rules": [{"id": "r1", "text": "Använd punktlistor.", "applies_to": ["all"], "active": true}],
 "history": [{"version": 1, "saved_at": null, "note": null, "snapshot": {"profile": {}, "rules": []}}]}
```
"""


def test_profiles_saved_by_earlier_versions_still_load_and_apply(library):
    library.rows["legacy"] = {"id": "legacy", "title": "Min arbetsprofil (Connect)", "content": LEGACY_PROFILE, "summary": None, "category": personal.PROFILE_CATEGORY, "status": "draft", "updated_at": "0001"}
    layer = wl.WorkLayer(SupportCatalog(), library)
    context = layer.context(TOKEN, "u")
    assert context["profile"]["version"] == 2
    assert rule_texts(context["always_apply"]) == {"Använd punktlistor."}
    assert [entry["version"] for entry in layer.history(TOKEN, "profile")["versions"]] == [2, 1]
    saved = layer.save_profile(TOKEN, yes({**INVESTIGATION, "expected_version": 2}))
    assert saved["version"] == 3


def test_storage_schema_is_unchanged():
    assert personal.SCHEMA == 1
    assert json.loads(json.dumps(personal.empty_profile()))["connect_type"] == "profile"
