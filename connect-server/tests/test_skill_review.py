"""Milstolpe 1: inskick, status, återkallning, publicerade skills och loggning i Connect."""

import uuid

import pytest

from connect_service import skills as sk
from connect_service.data import ConnectWriteError
from connect_service.supports import SupportCatalog
from connect_service.work_layer import NotFound, ToolInputError, WorkLayer
from tests.test_skills import OTHER, MemorySkillLibrary, create, improve, rid
from tests.test_work_layer import TOKEN


class ReviewLibrary(MemorySkillLibrary):
    def __init__(self) -> None:
        super().__init__()
        self.submissions: list[dict] = []
        self.published: dict[str, dict] = {}

    def submit_my_skill(self, *, access_token, skill_id, consent_distribution, rights_attested, request_id):
        row = self._find(access_token, skill_id, None)
        assert row is not None
        if any(s["skill_id"] == skill_id and s["state"] == "review" for s in self.submissions):
            raise ConnectWriteError("Det finns redan en version under granskning.", kind="validation")
        sub = {
            "submission_id": str(uuid.uuid4()), "skill_id": skill_id, "slug": row["spec"]["slug"], "name": row["spec"]["name"],
            "version": row["version"], "revision": 1, "state": "review", "review_note": None, "owner": access_token,
            "catalog_slug": None, "catalog_status": None, "catalog_published_version": None,
        }
        self.submissions.append(sub)
        self.skill_writes.append("submit")
        return {"id": sub["submission_id"], "status": "review", "version": row["version"], "revision": 1}

    def list_my_skill_submissions(self, *, access_token, skill_id=None):
        return [dict(s) for s in self.submissions if s["owner"] == access_token and (skill_id is None or s["skill_id"] == skill_id)]

    def withdraw_my_skill_submission(self, *, access_token, submission_id, request_id):
        for s in self.submissions:
            if s["submission_id"] == submission_id and s["owner"] == access_token:
                s["state"] = "withdrawn"
                return {"id": submission_id, "status": "withdrawn"}
        raise ConnectWriteError("Inskicket hittades inte.", kind="validation")

    def list_published_skills(self, *, access_token):
        return [
            {"slug": slug, "name": p["name"], "description": "d", "use_when": "u", "not_when": "n", "version": p["version"],
             "distribution_allowed": p["distribution"], "creator_display_name": "Testskapare"}
            for slug, p in self.published.items()
        ]

    def get_published_skill(self, *, access_token, slug, version=None, file_path=None):
        p = self.published.get(slug)
        if p is None:
            return None
        if file_path is not None:
            if file_path != "references/checklista.md":
                return None
            return {"slug": slug, "version": p["version"], "path": file_path, "content": "- Pris"}
        return {
            "slug": slug, "name": p["name"], "version": p["version"], "skill_md": "---\nname: " + slug + "\n---\n# " + p["name"],
            "files": [{"path": "references/checklista.md", "content": "- Pris"}], "distribution_allowed": p["distribution"],
            "creator_display_name": "Testskapare",
        }


@pytest.fixture()
def library():
    return ReviewLibrary()


@pytest.fixture()
def layer(library):
    return WorkLayer(SupportCatalog(), library)


def test_submit_previews_then_submits_and_keeps_original_private(layer, library):
    create(layer)
    preview = layer.submit_skill(TOKEN, {"id": "skill:offertgranskaren", "consent_distribution": True, "rights_attested": True})
    assert preview["status"] == "preview" and "förblir privat" in preview["confirm_text"]
    assert "submit" not in library.skill_writes
    sent = layer.submit_skill(TOKEN, {"id": "skill:offertgranskaren", "consent_distribution": True, "rights_attested": True,
                                      "confirmed": True, "request_id": rid()})
    assert sent["status"] == "submitted" and sent["verified"] is True and sent["submission_id"]
    assert improve(layer)["version"] == 2  # originalet kan fortfarande ändras


def test_distribution_requires_rights(layer):
    create(layer)
    with pytest.raises(ToolInputError):
        layer.submit_skill(TOKEN, {"id": "skill:offertgranskaren", "consent_distribution": True, "rights_attested": False})


def test_submission_status_is_readable_and_withdrawable(layer, library):
    create(layer)
    sent = layer.submit_skill(TOKEN, {"id": "skill:offertgranskaren", "confirmed": True, "request_id": rid()})
    assert layer.skill_submissions(TOKEN, {"id": "skill:offertgranskaren"})["items"][0]["status"] == "Väntar på granskning"
    library.submissions[0].update(state="changes_requested", review_note="Lägg till betalningsvillkor.")
    status = layer.skill_submissions(TOKEN, {})["items"][0]
    assert status["status"] == "Ändringar begärda" and status["feedback"] == "Lägg till betalningsvillkor."
    with pytest.raises(ToolInputError):
        layer.withdraw_submission(TOKEN, {"submission_id": sent["submission_id"], "confirmed": True, "request_id": rid()})
    library.submissions[0]["state"] = "review"
    assert layer.withdraw_submission(TOKEN, {"submission_id": sent["submission_id"]})["status"] == "preview"
    done = layer.withdraw_submission(TOKEN, {"submission_id": sent["submission_id"], "confirmed": True, "request_id": rid()})
    assert done["status"] == "withdrawn"


def test_other_user_cannot_withdraw_or_see_submissions(layer):
    create(layer)
    sent = layer.submit_skill(TOKEN, {"id": "skill:offertgranskaren", "confirmed": True, "request_id": rid()})
    assert layer.skill_submissions(OTHER, {})["items"] == []
    with pytest.raises(NotFound):
        layer.withdraw_submission(OTHER, {"submission_id": sent["submission_id"], "confirmed": True, "request_id": rid()})


def test_published_status_labels():
    assert sk.submission_status_label({"state": "published", "catalog_status": "draft"}) == "Godkänd, inte publicerad ännu"
    assert sk.submission_status_label({"state": "published", "catalog_status": "published", "catalog_published_version": 1}) == "Godkänd och publicerad i katalogen"
    assert sk.submission_status_label({"state": "rejected"}) == "Avslagen"


def test_published_catalog_respects_distribution_consent(layer, library):
    library.published["offertgranskaren-pb"] = {"name": "Offertgranskaren", "version": 2, "distribution": True}
    library.published["bara-webben"] = {"name": "Bara webben", "version": 1, "distribution": False}
    listing = layer.published_skills(OTHER)
    assert [item["id"] for item in listing["items"]] == ["katalog:offertgranskaren-pb"]
    assert "1 publicerade skills finns bara på promptbanken.se" in listing["note"]
    support = layer.support(TOKEN, "katalog:offertgranskaren-pb", None)
    assert support["version"] == 2 and support["source"] == "promptbanken_catalog" and support["instructions"].startswith("---")
    assert layer.support(TOKEN, "katalog:offertgranskaren-pb", "references/checklista.md")["content"] == "- Pris"
    with pytest.raises(NotFound):
        layer.support(TOKEN, "katalog:bara-webben", None)
    with pytest.raises(NotFound):
        layer.support(TOKEN, "katalog:bara-webben", "references/checklista.md")
    assert layer.open_item(TOKEN, "skill", "offertgranskaren-pb")["version"] == 2


def test_tool_logging_never_includes_free_text():
    from connect_service.app import _log_target

    assert _log_target({"id": "skill:offertgranskaren"}) == "skill:offertgranskaren"
    assert _log_target({"id": "katalog:offertgranskaren-pb"}) == "katalog:offertgranskaren-pb"
    assert _log_target({"target": "profile"}) == "profile"
    assert _log_target({"ref": "Granska offerten från Städbolaget AB, 38 000 kr"}) == "-"
    assert _log_target({"skill": {"name": "x"}}) == "-"
