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
from tests.test_work_layer import TOKEN, MemoryLibrary

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
REQUIRED = ("name", "description", "use_when", "not_when", "instructions")
PATH = re.compile(r"^(references|assets)/[a-z0-9][a-z0-9._-]{0,79}\.(md|txt|csv|json)$")


def rid() -> str:
    return str(uuid.uuid4())


def _slug(name: str) -> str:
    table = str.maketrans("åäöÅÄÖ", "aaoaao")
    return re.sub(r"[^a-z0-9]+", "-", name.translate(table).lower()).strip("-")[:64]


def _render(spec, version):
    return f"---\nname: {spec['slug']}\nmetadata:\n  version: \"1.{version - 1}.0\"\n---\n\n# {spec['name']}\n\n{spec['instructions']}\n" + "".join(
        f"{n}. {step}\n" for n, step in enumerate(spec.get("steps", []), 1)
    )


class MemorySkillLibrary(MemoryLibrary):
    def __init__(self) -> None:
        super().__init__()
        self.skills: dict[str, dict] = {}
        self.versions: dict[tuple[str, int], dict] = {}
        self.skill_requests: dict[tuple[str, str, str], dict] = {}
        self.skill_writes: list[str] = []

    # --- läsning

    def list_my_skills(self, *, access_token):
        return [
            {
                "id": row["id"],
                "slug": row["spec"]["slug"],
                "name": row["spec"]["name"],
                "description": row["spec"]["description"],
                "use_when": row["spec"]["use_when"],
                "not_when": row["spec"]["not_when"],
                "language": "sv",
                "version": row["version"],
                "is_active": row["active"],
                "status": "draft",
                "file_count": len(row["spec"].get("files", [])),
                "updated_at": f"{row['version']:04d}",
            }
            for row in self.skills.values()
            if row["owner"] == access_token
        ]

    def _find(self, token, skill_id, slug):
        for row in self.skills.values():
            if row["owner"] == token and (row["id"] == skill_id or (skill_id is None and row["spec"]["slug"] == slug)):
                return row
        return None

    def get_my_skill(self, *, access_token, skill_id=None, slug=None, version=None, file_path=None, include_files=True):
        row = self._find(access_token, skill_id, slug)
        if row is None:
            return None
        v = version or row["version"]
        snap = self.versions.get((row["id"], v))
        if snap is None:
            return None
        spec = snap["spec"]
        if file_path is not None:
            match = next((f for f in spec.get("files", []) if f["path"] == file_path), None)
            return None if match is None else {"id": row["id"], "slug": spec["slug"], "version": v, "path": match["path"], "content": match["content"]}
        files = [{"path": f["path"], "chars": len(f["content"]), **({"content": f["content"]} if include_files else {})} for f in spec.get("files", [])]
        return {
            "id": row["id"], **{k: spec.get(k) for k in ("slug", "name", "description", "use_when", "not_when", "instructions", "language")},
            "steps": spec.get("steps", []), "quality_rules": spec.get("quality_rules", []), "dependencies": spec.get("dependencies", []),
            "version": v, "current_version": row["version"], "is_active": row["active"], "status": "draft",
            "skill_md": snap["skill_md"], "files": files,
        }

    def list_my_skill_versions(self, *, access_token, skill_id):
        row = self._find(access_token, skill_id, None)
        assert row is not None
        return [{"version": v, "note": s["note"], "is_current": v == row["version"]} for (sid, v), s in sorted(self.versions.items(), reverse=True) if sid == skill_id]

    def validate_my_skill(self, *, access_token, spec, skill_id=None):
        errors = [f"{key} krävs." for key in REQUIRED if not str(spec.get(key) or "").strip()]
        errors += [f"Okänt fält: {key}." for key in spec if key not in sk.SPEC_FIELDS]
        paths = []
        for item in spec.get("files", []) or []:
            if not PATH.match(item.get("path", "")) or ".." in item.get("path", ""):
                errors.append(f"Ogiltig sökväg: {item.get('path')}.")
            paths.append(item.get("path"))
        for ref in re.findall(r"(?:references|assets)/[A-Za-z0-9._/-]+[A-Za-z0-9]", str(spec.get("instructions", ""))):
            if ref not in paths:
                errors.append(f"Instruktionen hänvisar till {ref}, som inte finns bland filerna.")
        version = 1
        fixed = None
        if skill_id is not None:
            row = self._find(access_token, skill_id, None)
            if row is None:
                raise ConnectWriteError("Skillen hittades inte eller tillhör inte dig.", kind="validation")
            fixed, version = row["spec"]["slug"], row["version"] + 1
        normalized = {k: v for k, v in spec.items() if v not in (None, [], "")}
        normalized["slug"] = fixed or _slug(str(spec.get("slug") or spec.get("name") or ""))
        normalized.setdefault("language", "sv")
        if skill_id is None and any(r["owner"] == access_token and r["spec"]["slug"] == normalized["slug"] for r in self.skills.values()):
            errors.append("Du har redan en skill med samma id.")
        return {"valid": not errors, "errors": errors, "slug": normalized["slug"], "version": version, "spec": normalized,
                "skill_md": None if errors else _render(normalized, version)}

    # --- skrivning

    def _replay(self, token, tool, request_id):
        return self.skill_requests.get((token, tool, request_id))

    def create_my_skill(self, *, access_token, spec, request_id):
        if (prev := self._replay(access_token, "create", request_id)) is not None:
            return prev
        check = self.validate_my_skill(access_token=access_token, spec=spec)
        if not check["valid"]:
            raise ConnectWriteError(" ".join(check["errors"]), kind="validation")
        if sum(1 for r in self.skills.values() if r["owner"] == access_token) >= 5:
            raise ConnectWriteError("Du har nått gränsen på 5 egna skills för free-planen.", kind="quota")
        skill_id = str(uuid.uuid4())
        self.skills[skill_id] = {"id": skill_id, "owner": access_token, "spec": check["spec"], "version": 1, "active": True}
        self.versions[(skill_id, 1)] = {"spec": check["spec"], "skill_md": check["skill_md"], "note": None}
        result = {"id": skill_id, "slug": check["slug"], "version": 1}
        self.skill_requests[(access_token, "create", request_id)] = result
        self.skill_writes.append("create")
        return result

    def update_my_skill(self, *, access_token, skill_id, spec, expected_version, note, request_id):
        if (prev := self._replay(access_token, "update", request_id)) is not None:
            return prev
        row = self._find(access_token, skill_id, None)
        if row is None:
            raise ConnectWriteError("Skillen hittades inte eller tillhör inte dig.", kind="validation")
        if row["version"] != expected_version:
            raise ConnectWriteError(f"Versionskonflikt: skillen är nu version {row['version']}.", kind="conflict")
        check = self.validate_my_skill(access_token=access_token, spec=spec, skill_id=skill_id)
        new = row["version"] + 1
        row.update(spec=check["spec"], version=new)
        self.versions[(skill_id, new)] = {"spec": check["spec"], "skill_md": check["skill_md"], "note": note}
        result = {"id": skill_id, "version": new}
        self.skill_requests[(access_token, "update", request_id)] = result
        self.skill_writes.append("update")
        return result

    def set_my_skill_active(self, *, access_token, skill_id, active, request_id):
        row = self._find(access_token, skill_id, None)
        assert row is not None
        row["active"] = active
        self.skill_writes.append("active")
        return {"id": skill_id, "is_active": active}


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
