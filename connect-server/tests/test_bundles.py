"""Bundles i Connect och egna arbetssätt i verktygslistan."""

import uuid

import pytest

from connect_service.supports import SupportCatalog
from connect_service.work_layer import NotFound, ToolInputError, WorkLayer
from tests.fakes import TOKEN, MemoryLibrary
from tests.test_skills import OFFERT, OTHER, create, rid

SKILL_ID = str(uuid.uuid4())
PROMPT_ID = str(uuid.uuid4())


class BundleLibrary(MemoryLibrary):
    def __init__(self) -> None:
        super().__init__()
        self.bundles: dict[str, dict] = {}
        self.products = {
            TOKEN: [
                {"product_kind": "skill", "id": SKILL_ID, "slug": "offertgranskaren", "name": "Offertgranskaren", "latest_version": 2, "published": True},
                {"product_kind": "prompt", "id": PROMPT_ID, "slug": None, "name": "Sammanfatta", "latest_version": None, "published": False},
            ]
        }
        self.bundle_writes: list[str] = []

    def list_my_bundleable_products(self, *, access_token):
        return [dict(p) for p in self.products.get(access_token, [])]

    def list_my_bundles(self, *, access_token):
        return [{"id": b["id"], "title": b["title"], "item_count": len(b["items"])} for b in self.bundles.values() if b["owner"] == access_token]

    def get_my_bundle(self, *, access_token, bundle_id):
        b = self.bundles.get(bundle_id)
        if b is None or b["owner"] != access_token:
            return None
        products = {p["id"]: p for p in self.products.get(access_token, [])}
        return {"id": b["id"], "title": b["title"], "summary": b["summary"], "items": [
            {"kind": i["kind"], "id": i["id"], "version": i.get("version"), "name": products[i["id"]]["name"],
             "latest_version": products[i["id"]]["latest_version"],
             "published": products[i["id"]]["published"] and i.get("version") in (None, products[i["id"]]["latest_version"])}
            for i in b["items"]]}

    def create_my_bundle(self, *, access_token, title, summary, request_id):
        bid = str(uuid.uuid4())
        self.bundles[bid] = {"id": bid, "owner": access_token, "title": title, "summary": summary, "items": []}
        self.bundle_writes.append("create")
        return {"id": bid}

    def update_my_bundle(self, *, access_token, bundle_id, title, summary, request_id):
        self.bundles[bundle_id].update(title=title, summary=summary)
        self.bundle_writes.append("update")
        return {"id": bundle_id}

    def set_my_bundle_items(self, *, access_token, bundle_id, items, request_id):
        own = {p["id"] for p in self.products.get(access_token, [])}
        if any(i["id"] not in own for i in items):
            from connect_service.data import ConnectWriteError

            raise ConnectWriteError("Post 1: produkten finns inte bland dina egna prompter och arbetssätt.", kind="validation")
        self.bundles[bundle_id]["items"] = [dict(i) for i in items]
        self.bundle_writes.append("items")
        return {"id": bundle_id, "item_count": len(items)}

    def get_published_bundle(self, *, access_token, slug, version=None):
        if slug != "upphandling":
            return None
        return {"slug": slug, "version": 1, "name": "Upphandling", "items": [
            {"kind": "skill", "catalog_id": str(uuid.uuid4()), "version": 1, "slug": "offertgranskaren", "name": "Offertgranskaren"},
            {"kind": "prompt", "catalog_id": str(uuid.uuid4()), "version": 1, "slug": "sammanfatta", "name": "Sammanfatta"}]}


@pytest.fixture()
def library():
    return BundleLibrary()


@pytest.fixture()
def layer(library):
    return WorkLayer(SupportCatalog(), library)


def test_bundle_listing_shows_own_products_published_or_not(layer):
    result = layer.list_bundles(TOKEN)
    assert result["items"] == []
    products = {p["id"]: p for p in result["addable_products"]}
    assert products["skill:offertgranskaren"]["published"] is True
    assert products[PROMPT_ID]["published"] is False
    assert "note" in layer.list_bundles(OTHER)


def test_save_bundle_previews_then_saves_with_pinned_latest_versions(layer, library):
    args = {"title": "Upphandling", "items": [{"kind": "skill", "id": "skill:offertgranskaren"}, {"kind": "prompt", "id": PROMPT_ID}]}
    preview = layer.save_bundle(TOKEN, args)
    assert preview["status"] == "preview" and "Offertgranskaren (version 2)" in preview["confirm_text"]
    assert "Inget innehåll kopieras" in preview["confirm_text"]
    assert library.bundle_writes == []
    saved = layer.save_bundle(TOKEN, {**args, "confirmed": True, "request_id": rid()})
    assert saved["status"] == "saved" and saved["items"] == 2
    bundle = layer.get_bundle(TOKEN, {"id": saved["id"]})
    assert [i["version"] for i in bundle["items"]] == [2, None]
    assert "Inte publicerade än: Sammanfatta" in bundle["note"]


def test_bundle_tool_descriptions_allow_own_private_products():
    from connect_service import work_layer as wl

    tools = {t["name"]: t["description"] for t in wl.tool_definitions()}
    save = tools["save_my_bundle"]
    assert "egna publicerade prompter" not in save  # den gamla, motsägelsefulla formuleringen
    assert "både privata och publicerade" in save
    assert "Bara användarens egna" in save
    assert "Bundlen förblir privat" in save and "submit_to_promptbanken" in save
    assert "både privata och publicerade" in tools["list_my_bundles"]


def test_bundle_preview_says_it_stays_private(layer):
    preview = layer.save_bundle(TOKEN, {"title": "P", "items": [{"kind": "prompt", "id": PROMPT_ID}]})
    assert "Bundlen är privat och publiceras inte" in preview["confirm_text"]


def test_bundle_notes_newer_versions_without_changing(layer, library):
    saved = layer.save_bundle(TOKEN, {"title": "B", "items": [{"kind": "skill", "id": SKILL_ID, "version": 1}], "confirmed": True, "request_id": rid()})
    bundle = layer.get_bundle(TOKEN, {"id": saved["id"]})
    assert bundle["items"][0]["version"] == 1 and "Nyare version finns för: Offertgranskaren" in bundle["note"]


def test_bundle_rejects_foreign_products_and_other_users(layer):
    with pytest.raises(ToolInputError):
        layer.save_bundle(TOKEN, {"title": "X", "items": [{"kind": "skill", "id": str(uuid.uuid4())}]})
    saved = layer.save_bundle(TOKEN, {"title": "Min", "confirmed": True, "request_id": rid()})
    with pytest.raises(NotFound):
        layer.get_bundle(OTHER, {"id": saved["id"]})
    with pytest.raises(NotFound):
        layer.save_bundle(OTHER, {"id": saved["id"], "title": "Kapad", "confirmed": True, "request_id": rid()})


def test_empty_bundle_cannot_be_submitted(layer):
    saved = layer.save_bundle(TOKEN, {"title": "Tom", "confirmed": True, "request_id": rid()})
    with pytest.raises(ToolInputError):
        layer.submit(TOKEN, {"kind": "bundle", "id": saved["id"]})


def test_published_bundle_points_to_catalog_skills(layer):
    bundle = layer.open_item(TOKEN, "bundle", "upphandling")
    assert bundle["items"][0]["use_with"] == "katalog:offertgranskaren"
    assert bundle["items"][1]["use_with"] is None
    with pytest.raises(NotFound):
        layer.open_item(TOKEN, "bundle", "saknas")


def test_locked_paid_bundle_returns_only_metadata(layer, library):
    library.get_published_bundle = lambda **kw: {"slug": "betald", "name": "Betald", "summary": "s", "version": 1, "item_count": 3,
                                                 "offer": {"access_model": "paid", "price_amount_ore": 9900, "fictive": True}, "access": "locked"}
    result = layer.open_item(TOKEN, "bundle", "betald")
    assert result["access"] == "paid" and result["price_sek"] == 99.0 and "items" not in result
    assert "kan inte användas" in result["note"]


def test_locked_paid_skill_never_returns_instructions(layer, library):
    library.get_published_skill = lambda **kw: {"slug": "betald", "name": "Betald", "description": "d", "version": 1,
                                                "distribution_allowed": True, "offer": {"access_model": "paid", "price_amount_ore": 100, "fictive": True}, "access": "locked"}
    result = layer.support(TOKEN, "katalog:betald", None)
    assert result["access"] == "paid" and "instructions" not in result and "files" not in result


def test_tools_list_names_own_active_ways_of_working(library):
    from tests.test_work_layer import call, http_client

    WorkLayer(SupportCatalog(), library).create_skill(TOKEN, {"skill": OFFERT, "confirmed": True, "request_id": rid()})
    client = http_client(library)
    tools = {t["name"]: t for t in call(client, "tools/list").json()["result"]["tools"]}
    description = tools["get_connect_context"]["description"]
    assert "Användarens egna arbetssätt: Offertgranskaren (När användaren vill granska" in description
    assert "references/checklista.md" not in description  # inga instruktioner i listan
    assert "Användarens egna arbetssätt" not in tools["get_support"]["description"]


def test_tools_list_without_skills_is_unchanged(library):
    from connect_service import work_layer as wl
    from tests.test_work_layer import call, http_client

    tools = {t["name"]: t for t in call(http_client(library), "tools/list").json()["result"]["tools"]}
    base = {t["name"]: t for t in wl.tool_definitions()}
    assert tools["get_connect_context"]["description"] == base["get_connect_context"]["description"]
