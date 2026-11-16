"""Egna skills i Connect: skapa, hitta, använda, förbättra och använda igen.

MemorySkillLibrary efterliknar skill-RPC:erna i Promptbanken
(20261115200100_creator_skills.sql): validering, atomisk version,
oföränderliga versioner, idempotens per request_id och ägarskap per token.
Databasens egna regler testas separat i
promptbanken/supabase/tests/verify_creator_skills_dev.sql.
"""

import json
import re
import uuid

import pytest

from connect_service import skills as sk
from connect_service import work_layer as wl
from connect_service.data import ConnectWriteError
from connect_service.supports import SupportCatalog
from connect_service.work_layer import NotFound, ToolInputError, WorkLayer
from tests.fakes import MemoryLibrary, rid
from tests.test_work_layer import TOKEN

OTHER = "other-user-token"

OFFERT = {
    "name": "Offertgranskaren",
    "description": "Granskar leverantörsofferter mot krav, pris, villkor och risker.",
    "use_when": "När användaren vill granska eller jämföra en leverantörsoffert.",
    "not_when": "Inte för avtalstvister eller juridisk rådgivning.",
    "instructions": "Läs offerten och jämför den med kraven. Använd references/checklista.md.",
    "steps": ["Sammanfatta offerten.", "Jämför mot kraven.", "Lista risker och frågor."],
    "quality_rules": ["Hitta inte på priser eller datum."],
    "files": [{"path": "references/checklista.md", "content": "# Checklista\n- Pris\n- Leveranstid"}],
}
MemorySkillLibrary = MemoryLibrary


@pytest.fixture()
def library():
    return MemorySkillLibrary()


@pytest.fixture()
def layer(library):
    return WorkLayer(SupportCatalog(), library)


def create(layer, spec=OFFERT, token=TOKEN):
    return layer.create_skill(token, {"skill": spec, "confirmed": True, "request_id": rid()})


# ------------------------------------------------------------ A. skapa


def test_create_previews_without_saving(layer, library):
    preview = layer.create_skill(TOKEN, {"skill": OFFERT})
    assert preview["status"] == "preview"
    assert preview["id"] == "skill:offertgranskaren"
    assert preview["confirm_text"].startswith("Ny privat skill: ”Offertgranskaren”. Används när:")
    assert preview["skill_md"].startswith("---\nname: offertgranskaren")
    assert library.skill_writes == []


def test_create_saves_verifies_and_is_idempotent(layer, library):
    request_id = rid()
    first = layer.create_skill(TOKEN, {"skill": OFFERT, "confirmed": True, "request_id": request_id})
    again = layer.create_skill(TOKEN, {"skill": OFFERT, "confirmed": True, "request_id": request_id})
    assert first["status"] == "saved" and first["verified"] is True and first["version"] == 1
    assert again["id"] == first["id"]
    assert library.skill_writes == ["create"]


def test_create_requires_request_id_when_confirmed(layer):
    with pytest.raises(ToolInputError):
        layer.create_skill(TOKEN, {"skill": OFFERT, "confirmed": True})


def test_invalid_skill_is_reported_not_saved(layer, library):
    bad = {**OFFERT, "not_when": "", "files": [{"path": "../hemligt.md", "content": "x"}]}
    result = layer.create_skill(TOKEN, {"skill": bad})
    assert result["status"] == "invalid"
    assert any("not_when" in error for error in result["errors"])
    assert any("Ogiltig sökväg" in error for error in result["errors"])
    # Även en bekräftad sparning nekas: databasen validerar igen.
    with pytest.raises(ConnectWriteError) as error:
        layer.create_skill(TOKEN, {"skill": bad, "confirmed": True, "request_id": rid()})
    assert error.value.kind == "validation" and "Ogiltig sökväg" in str(error.value)
    assert library.skill_writes == []


def test_personal_data_blocks_saving(layer, library):
    result = layer.create_skill(TOKEN, {"skill": {**OFFERT, "instructions": "Ring 070-123 45 67 vid frågor."}, "confirmed": True, "request_id": rid()})
    assert result["status"] == "blocked"
    assert library.skill_writes == []


def test_validate_shows_skill_md_without_saving(layer, library):
    result = layer.validate_skill(TOKEN, {"skill": OFFERT})
    assert result["valid"] is True and result["skill_md"].startswith("---")
    assert library.skill_writes == []


# ------------------------------------------------------------ B. hitta och använda


def test_context_lists_active_skills_briefly_without_skill_md(layer):
    create(layer)
    context = layer.context(TOKEN, "u")
    entry = context["my_skills"][0]
    assert entry == {
        "id": "skill:offertgranskaren",
        "name": "Offertgranskaren",
        "purpose": OFFERT["description"],
        "use_when": OFFERT["use_when"],
        "not_when": OFFERT["not_when"],
        "version": 1,
        "source": "creator_skill",
    }
    assert "SKILL.md" not in json.dumps(context, ensure_ascii=False)
    assert "Jämför mot kraven" not in json.dumps(context, ensure_ascii=False)
    assert context["how_to_manage_skills"]


def test_get_support_returns_full_skill_with_rules_and_files(layer):
    create(layer)
    layer.save_profile(TOKEN, {"rules": {"add": [{"text": "Svara kort.", "applies_to": ["all"]}, {"text": "Börja med totalpriset.", "applies_to": ["skill:offertgranskaren"]}, {"text": "Börja med problemet.", "applies_to": ["utredaren"]}]}, "confirmed": True, "request_id": rid()})
    support = layer.support(TOKEN, "skill:offertgranskaren", None)
    assert support["source"] == "creator_skill" and support["version"] == 1
    assert support["instructions"].startswith("---\nname: offertgranskaren")
    assert support["files"] == [{"path": "references/checklista.md", "content": "# Checklista\n- Pris\n- Leveranstid"}]
    texts = {rule["text"] for rule in support["personal_rules"]}
    assert texts == {"Svara kort.", "Börja med totalpriset."}
    assert support["how_to_apply"] and support["precedence"]
    # Regeln för skillen läcker inte till specialisterna
    assert "Börja med totalpriset." not in {rule["text"] for rule in layer.support(TOKEN, "utredaren", None)["personal_rules"]}


def test_large_files_are_listed_and_fetched_separately(layer):
    big = {**OFFERT, "files": [{"path": "references/checklista.md", "content": "x" * 7000}]}
    create(layer, big)
    support = layer.support(TOKEN, "skill:offertgranskaren", None)
    assert support["files"] == [{"path": "references/checklista.md", "chars": 7000}]
    resource = layer.support(TOKEN, "skill:offertgranskaren", "references/checklista.md")
    assert resource["content"] == "x" * 7000 and resource["version"] == 1
    with pytest.raises(NotFound):
        layer.support(TOKEN, "skill:offertgranskaren", "../../etc/passwd")


def test_personal_rules_are_never_written_into_the_skill(layer, library):
    create(layer)
    layer.save_profile(TOKEN, {"rules": {"add": [{"text": "Börja med totalpriset.", "applies_to": ["skill:offertgranskaren"]}]}, "confirmed": True, "request_id": rid()})
    skill = layer.get_skill(TOKEN, {"id": "skill:offertgranskaren"})
    assert "totalpriset" not in skill["skill_md"] and skill["version"] == 1


def test_routing_rules_prefer_named_then_fitting_own_skill_but_not_irrelevant(layer):
    rules = " ".join(wl.ROUTING_RULES)
    assert "ber användaren om en skill, ett arbetssätt eller en specialist vid namn, använd det" in rules
    assert "Passar en aktiv egen skill (skill:)" in rules
    assert "Att den finns är inget skäl att använda den." in rules
    assert "Högst ett stöd åt gången." in rules


def test_server_instructions_route_everyday_tasks_but_not_simple_questions():
    text = wl.SERVER_INSTRUCTIONS
    assert "granska" in text and "egna skills" in text
    assert "1) Enkel fråga" in text and "använd inte Connect" in text
    assert "how_to_manage_skills" in text


def test_prompts_list_includes_active_skills(library):
    from tests.test_work_layer import http_client, call

    WorkLayer(SupportCatalog(), library).create_skill(TOKEN, {"skill": OFFERT, "confirmed": True, "request_id": rid()})
    client = http_client(library)
    names = [prompt["name"] for prompt in call(client, "prompts/list").json()["result"]["prompts"]]
    assert names[0] == "skill:offertgranskaren"


# ------------------------------------------------------------ C. förbättra


def improve(layer, version=1, confirmed=True, **extra):
    steps = [*OFFERT["steps"][:2], "Kontrollera betalningsvillkor.", OFFERT["steps"][2]]
    return layer.update_skill(TOKEN, {"id": "skill:offertgranskaren", "changes": {"steps": steps}, "expected_version": version,
                                      "note": "Betalningsvillkor", **({"confirmed": True, "request_id": rid()} if confirmed else {}), **extra})


def test_update_previews_changes_then_saves_new_version(layer, library):
    create(layer)
    preview = improve(layer, confirmed=False)
    assert preview["status"] == "preview" and preview["will_become_version"] == 2
    assert [change["field"] for change in preview["changes"]] == ["steps"]
    assert "Det blir en ny version; den tidigare finns kvar." in preview["confirm_text"]
    assert library.skill_writes == ["create"]
    saved = improve(layer)
    assert saved["status"] == "saved" and saved["version"] == 2 and saved["verified"] is True


def test_next_use_gets_new_version_and_old_version_is_kept(layer):
    create(layer)
    improve(layer)
    support = layer.support(TOKEN, "skill:offertgranskaren", None)
    assert support["version"] == 2 and "betalningsvillkor" in support["instructions"]
    old = layer.get_skill(TOKEN, {"id": "skill:offertgranskaren", "version": 1})
    assert "betalningsvillkor" not in old["skill_md"]
    assert layer.context(TOKEN, "u")["my_skills"][0]["version"] == 2
    assert [row["version"] for row in layer.history(TOKEN, "skill:offertgranskaren")["versions"]] == [2, 1]


def test_stale_update_is_refused_without_change(layer, library):
    create(layer)
    improve(layer)
    with pytest.raises(ConnectWriteError) as error:
        improve(layer, version=1)
    assert error.value.kind == "conflict"
    assert library.skill_writes == ["create", "update"]


def test_unchanged_update_and_slug_change_are_refused(layer):
    create(layer)
    with pytest.raises(ToolInputError):
        layer.update_skill(TOKEN, {"id": "skill:offertgranskaren", "changes": {"steps": OFFERT["steps"]}, "expected_version": 1})
    with pytest.raises(ToolInputError):
        layer.update_skill(TOKEN, {"id": "skill:offertgranskaren", "changes": {"slug": "annat"}, "expected_version": 1})


def test_restore_creates_new_version(layer):
    create(layer)
    improve(layer)
    preview = layer.restore(TOKEN, {"target": "skill:offertgranskaren", "version": 1})
    assert preview["status"] == "preview" and preview["confirm_text"].startswith("Går tillbaka till hur det var tidigare.")
    saved = layer.restore(TOKEN, {"target": "skill:offertgranskaren", "version": 1, "confirmed": True, "request_id": rid()})
    assert saved["version"] == 3
    assert "betalningsvillkor" not in layer.support(TOKEN, "skill:offertgranskaren", None)["instructions"]


# ------------------------------------------------------------ aktiv/inaktiv


def test_inactive_skill_is_not_offered_but_still_readable(layer):
    create(layer)
    preview = layer.set_skill_active(TOKEN, {"id": "skill:offertgranskaren", "active": False})
    assert preview["status"] == "preview"
    layer.set_skill_active(TOKEN, {"id": "skill:offertgranskaren", "active": False, "confirmed": True, "request_id": rid()})
    context = layer.context(TOKEN, "u")
    assert context["my_skills"] == []
    assert context["inactive_skills"] == [{"id": "skill:offertgranskaren", "name": "Offertgranskaren"}]
    support = layer.support(TOKEN, "skill:offertgranskaren", None)
    assert support["active"] is False and "inactive_note" in support


# ------------------------------------------------------------ behörighet


def test_other_user_cannot_see_or_change_the_skill(layer):
    create(layer)
    assert layer.list_skills(OTHER)["items"] == []
    with pytest.raises(NotFound):
        layer.support(OTHER, "skill:offertgranskaren", None)
    with pytest.raises(NotFound):
        layer.get_skill(OTHER, {"id": "skill:offertgranskaren"})
    with pytest.raises(NotFound):
        layer.update_skill(OTHER, {"id": "skill:offertgranskaren", "changes": {"name": "X"}, "expected_version": 1})


# ------------------------------------------------------------ kontextstorlek


def _big_skill(n):
    return {**OFFERT, "name": f"Testskill {n}", "description": "Beskrivning " * 80, "use_when": "När " * 140, "not_when": "Inte " * 110, "files": []}


def test_context_without_skills_has_room_to_spare(layer):
    size = len(json.dumps(layer.context(TOKEN, "u"), ensure_ascii=False))
    assert size < 11500


def test_context_with_many_long_skills_stays_within_budget(layer, library):
    for n in range(20):
        library.skills[str(n)] = {"id": str(n), "owner": TOKEN, "spec": {**_big_skill(n), "slug": f"testskill-{n}"}, "version": 1, "active": True}
    context = layer.context(TOKEN, "u")
    skills_part = len(json.dumps(context["my_skills"], ensure_ascii=False))
    assert skills_part <= sk.CONTEXT_BUDGET
    assert len(context["my_skills"]) + len(context["more_skills"]) == 20
    assert len(json.dumps(context, ensure_ascii=False)) < 15500


def test_context_survives_missing_skill_backend(library):
    class NoSkills(MemoryLibrary):
        pass

    context = WorkLayer(SupportCatalog(), NoSkills()).context(TOKEN, "u")
    assert context["my_skills"] == [] and len(context["supports"]) == 9


def test_specialist_index_keeps_trigger_sentence(layer):
    supports = {entry["id"]: entry for entry in layer.context(TOKEN, "u")["supports"]}
    for entry in supports.values():
        assert entry["use_when"] and entry["not_when"] and entry["in_short"]
    assert supports["utredaren"]["use_when"].startswith("Använd när")
    # Fullständig beskrivning finns kvar i metoden
    assert "Hjälper användaren genom en strukturerad utredning" in layer.support(TOKEN, "utredaren", None)["instructions"]
