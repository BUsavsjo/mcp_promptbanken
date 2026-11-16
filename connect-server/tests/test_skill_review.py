"""Milstolpe 1: inskick, status, återkallning, publicerade skills och loggning i Connect."""

import uuid

import pytest

from connect_service import skills as sk
from connect_service.data import ConnectWriteError
from connect_service.supports import SupportCatalog
from connect_service.work_layer import NotFound, ToolInputError, WorkLayer
from tests.fakes import MemoryLibrary
from tests.test_skills import OTHER, create, improve, rid
from tests.test_work_layer import TOKEN


ReviewLibrary = MemoryLibrary


@pytest.fixture()
def library():
    return ReviewLibrary()


@pytest.fixture()
def layer(library):
    return WorkLayer(SupportCatalog(), library)


def test_submit_previews_then_submits_and_keeps_original_private(layer, library):
    create(layer)
    preview = layer.submit(TOKEN, {"kind": "skill", "id": "skill:offertgranskaren", "consent_distribution": True, "rights_attested": True})
    assert preview["status"] == "preview" and "förblir privat" in preview["confirm_text"]
    assert "submit" not in library.skill_writes
    sent = layer.submit(TOKEN, {"kind": "skill", "id": "skill:offertgranskaren", "consent_distribution": True, "rights_attested": True,
                                      "confirmed": True, "request_id": rid()})
    assert sent["status"] == "submitted" and sent["verified"] is True and sent["submission_id"]
    assert improve(layer)["version"] == 2  # originalet kan fortfarande ändras


def test_distribution_requires_rights(layer):
    create(layer)
    with pytest.raises(ToolInputError):
        layer.submit(TOKEN, {"kind": "skill", "id": "skill:offertgranskaren", "consent_distribution": True, "rights_attested": False})


def test_submission_status_is_readable_and_withdrawable(layer, library):
    create(layer)
    sent = layer.submit(TOKEN, {"kind": "skill", "id": "skill:offertgranskaren", "confirmed": True, "request_id": rid()})
    assert layer.submission_status(TOKEN, {"id": "skill:offertgranskaren"})["items"][0]["status"] == "Väntar på granskning"
    library.submissions[0].update(state="changes_requested", review_note="Lägg till betalningsvillkor.")
    status = layer.submission_status(TOKEN, {})["items"][0]
    assert status["status"] == "Ändringar begärda" and status["feedback"] == "Lägg till betalningsvillkor."
    with pytest.raises(ToolInputError):
        layer.withdraw(TOKEN, {"submission_id": sent["submission_id"], "confirmed": True, "request_id": rid()})
    library.submissions[0]["state"] = "review"
    assert layer.withdraw(TOKEN, {"submission_id": sent["submission_id"]})["status"] == "preview"
    done = layer.withdraw(TOKEN, {"submission_id": sent["submission_id"], "confirmed": True, "request_id": rid()})
    assert done["status"] == "withdrawn"


def test_other_user_cannot_withdraw_or_see_submissions(layer):
    create(layer)
    sent = layer.submit(TOKEN, {"kind": "skill", "id": "skill:offertgranskaren", "confirmed": True, "request_id": rid()})
    assert layer.submission_status(OTHER, {})["items"] == []
    with pytest.raises(NotFound):
        layer.withdraw(OTHER, {"submission_id": sent["submission_id"], "confirmed": True, "request_id": rid()})


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
