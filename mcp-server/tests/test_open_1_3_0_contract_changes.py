"""Kontraktsändringar och buggfixar i Promptbanken Open 1.3.0.

Buggfixarna kommer från ChatGPT:s MCP-test 2026-09-26: nonsenssökning gav
träff, okänt paket i list_package_prompts såg ut som ett tomt paket,
area_label blandades ihop med målgruppen och okänd roll gav hela katalogen.
"""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import mcp_server as server_mcp
from server.mcp_server import _search_templates_payload, _tool_definitions_for_profile
from server.search_ranking import query_terms, rank


def _public_tool(name: str) -> dict:
    return next(tool for tool in _tool_definitions_for_profile("public") if tool["name"] == name)


class SearchCoverageTests(unittest.TestCase):
    TEMPLATES = [
        {
            "id": "a",
            "title": "Planera verifiering, pilot och acceptanstest",
            "tags": ["go-no-go", "pilot"],
            "syfte": "Planerar verifiering före införande",
            "area": "x",
        },
        {
            "id": "b",
            "title": "Skriv ett tydligt vardagsmejl",
            "tags": ["mejl"],
            "syfte": "Skriv ett kort mejl",
            "area": "y",
        },
    ]

    def test_nonsense_query_with_one_accidental_word_gives_no_match(self) -> None:
        self.assertEqual(rank(self.TEMPLATES, "zzzz-no-such-template-987654321"), [])

    def test_digits_are_not_search_terms(self) -> None:
        self.assertEqual(query_terms("mejl 2026")[1], ["mejl"])

    def test_short_query_still_matches_on_one_word(self) -> None:
        self.assertEqual([t["id"] for t in rank(self.TEMPLATES, "mejl")], ["b"])

    def test_long_query_matches_when_two_words_hit(self) -> None:
        self.assertEqual([t["id"] for t in rank(self.TEMPLATES, "planera pilot för ny tjänst")], ["a"])

    def test_genuine_query_with_an_unknown_word_still_matches(self) -> None:
        # "kommun" finns inte i katalogen alls, men "pilot" och "införande"
        # gör -- frågan är inte mestadels okänd (2 av 3 termer finns i
        # katalogen), så täckningskravet ska aldrig slå till här.
        self.assertEqual([t["id"] for t in rank(self.TEMPLATES, "pilot införande kommun")], ["a"])


class SearchAreaTests(unittest.TestCase):
    CATALOG = {
        "templates": [
            {"id": "1", "title": "Skriv mejl", "tags": ["mejl"], "area": "kommunikation", "area_label": "Kommunikation"},
        ]
    }

    def _search(self, area: str) -> dict:
        with (
            patch("server.mcp_server._list_templates_payload", return_value=self.CATALOG),
            patch("server.mcp_server._catalog_template_packages", return_value={}),
        ):
            return _search_templates_payload(query="mejl", area=area)

    def test_area_is_an_open_string_in_the_tool_definition(self) -> None:
        area = _public_tool("search_templates")["inputSchema"]["properties"]["area"]
        self.assertEqual(area["type"], "string")
        self.assertNotIn("enum", area)

    def test_unknown_area_returns_no_matches_with_a_hint(self) -> None:
        payload = self._search("finns-inte")
        self.assertEqual(payload["total_matches"], 0)
        self.assertIn("list_packages", payload["hint"])

    def test_known_area_has_no_hint(self) -> None:
        payload = self._search("kommunikation")
        self.assertEqual(payload["total_matches"], 1)
        self.assertNotIn("hint", payload)

    def test_hint_is_declared_in_the_output_schema(self) -> None:
        self.assertIn("hint", _public_tool("search_templates")["outputSchema"]["properties"])


class RecommendPackagesTests(unittest.TestCase):
    BASE = {
        "role_recognized": True,
        "matched_role": "chef",
        "role_match_source": "exact",
        "recommended_areas": ["ledarskap"],
        "packages": [
            {"area": "ledarskap", "area_label": "Chefer, verksamhetsutvecklare", "template_count": 7},
        ],
    }
    CARDS = [
        {
            "slug": "ledarskap",
            "title": "Ledarskap och styrning",
            "summary": "Samlade mallar för ledning.",
            "package_type": "collection",
            "audience_label": "Chefer",
            "icon_key": None,
            "color_theme": None,
        }
    ]

    def _recommend(self, base: dict, cards=None, cards_error=None) -> dict:
        packages_patch = (
            patch.object(server_mcp._catalog, "list_published_packages", side_effect=cards_error)
            if cards_error
            else patch.object(server_mcp._catalog, "list_published_packages", return_value=cards or [])
        )
        with (
            patch.object(server_mcp._catalog, "list_published_prompts", return_value=[]),
            patch("server.mcp_server._catalog_area_index", return_value={}),
            patch("server.mcp_server._catalog_package_audiences", return_value={}),
            patch("server.mcp_server._recommend_packages", return_value=copy.deepcopy(base)),
            packages_patch,
        ):
            return server_mcp._recommend_packages_payload("chef")

    def test_packages_carry_card_fields_and_the_package_title_as_label(self) -> None:
        package = self._recommend(self.BASE, self.CARDS)["packages"][0]
        self.assertEqual(package["area_label"], "Ledarskap och styrning")
        self.assertEqual(package["title"], "Ledarskap och styrning")
        self.assertEqual(package["summary"], "Samlade mallar för ledning.")
        self.assertEqual(package["package_type"], "collection")
        self.assertEqual(package["audience_label"], "Chefer")
        self.assertIn("icon_key", package)
        self.assertIn("color_theme", package)

    def test_catalog_failure_keeps_the_recommendation(self) -> None:
        package = self._recommend(self.BASE, cards_error=RuntimeError("nere"))["packages"][0]
        self.assertEqual(package["area"], "ledarskap")
        self.assertIsNone(package["title"])

    def test_unknown_role_returns_no_packages_and_a_suggestion(self) -> None:
        base = copy.deepcopy(self.BASE) | {"role_recognized": False, "matched_role": None}
        result = self._recommend(base, self.CARDS)
        self.assertEqual(result["packages"], [])
        self.assertEqual(result["recommended_areas"], [])
        self.assertIn("list_packages", result["suggestion"])

    def test_area_label_fallback_never_uses_the_audience(self) -> None:
        meta = server_mcp._catalog_prompt_area_meta({"area": "processer", "audience_label": "Chefer"})
        self.assertEqual(meta["area_label"], "processer")

    def test_output_schema_declares_the_new_fields(self) -> None:
        schema = _public_tool("recommend_packages")["outputSchema"]
        items = schema["properties"]["packages"]["items"]["properties"]
        for field in ("title", "summary", "package_type", "audience_label", "icon_key", "color_theme"):
            self.assertIn(field, items)
        self.assertIn("suggestion", schema["properties"])


class ListPackagePromptsTests(unittest.TestCase):
    PACKAGE = {
        "slug": "forbattring",
        "title": "Från förbättringsidé till synlig effekt",
        "package_type": "workflow",
        "summary": "Ett guidat förbättringsflöde.",
        "icon_key": None,
        "color_theme": None,
    }
    PROMPTS = [
        {"id": "p1", "slug": "avgransa", "title": "Avgränsa", "sort_order": 1, "step_title": "1. Avgränsa"},
        {"id": "p2", "slug": "mal", "title": "Mål", "sort_order": 2, "step_title": "2. Mål"},
    ]

    def _payload(self, slug: str = "forbattring", prompts=None, packages=None, **kwargs) -> dict:
        with (
            patch.object(server_mcp._catalog, "list_published_package_prompts", return_value=self.PROMPTS if prompts is None else prompts),
            patch.object(server_mcp._catalog, "list_published_packages", return_value=[self.PACKAGE] if packages is None else packages),
        ):
            return server_mcp._list_package_prompts_payload(slug, **kwargs)

    def _call(self, arguments: dict) -> dict:
        with (
            patch.object(server_mcp._catalog, "list_published_package_prompts", return_value=self.PROMPTS),
            patch.object(server_mcp._catalog, "list_published_packages", return_value=[self.PACKAGE]),
            patch("server.mcp_server.track_usage_event"),
        ):
            return server_mcp._handle_mcp_message(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "list_package_prompts", "arguments": arguments}},
                "",
            )

    def test_payload_carries_the_package_and_current_step(self) -> None:
        payload = self._payload(current_step=2)
        self.assertEqual(payload["package"]["package_type"], "workflow")
        self.assertEqual(payload["package"]["title"], "Från förbättringsidé till synlig effekt")
        self.assertEqual(payload["current_step"], 2)
        self.assertEqual(len(payload["prompts"]), 2)

    def test_current_step_defaults_to_none(self) -> None:
        self.assertIsNone(self._payload()["current_step"])

    def test_unknown_package_is_an_error_not_an_empty_package(self) -> None:
        payload = self._payload("finns-inte-xyz", prompts=[], packages=[])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], "package_not_found")
        self.assertEqual(payload["prompts"], [])

    def test_current_step_outside_the_steps_is_an_error(self) -> None:
        for step in (0, 3, -1):
            with self.subTest(step=step):
                payload = self._payload(current_step=step)
                self.assertEqual(payload["code"], "invalid_current_step")

    def test_dispatcher_rejects_non_integer_current_step(self) -> None:
        for bad in ("2", True, 1.5):
            with self.subTest(value=bad):
                response = self._call({"package_slug": "forbattring", "current_step": bad})
                self.assertEqual(response["error"]["code"], -32602)

    def test_dispatcher_passes_current_step_through(self) -> None:
        response = self._call({"package_slug": "forbattring", "current_step": 1})
        self.assertEqual(response["result"]["structuredContent"]["current_step"], 1)

    def test_get_package_not_found_has_the_same_code(self) -> None:
        with patch.object(server_mcp._catalog, "get_published_package", return_value=[]):
            payload = server_mcp._get_package_payload("finns-inte-xyz")
        self.assertEqual(payload["code"], "package_not_found")

    def test_definition_declares_current_step_and_package(self) -> None:
        tool = _public_tool("list_package_prompts")
        self.assertEqual(tool["inputSchema"]["properties"]["current_step"]["type"], "integer")
        for field in ("package", "current_step", "code", "message"):
            self.assertIn(field, tool["outputSchema"]["properties"])

    def test_guard_accepts_current_step_and_widget_resources(self) -> None:
        from server.hosted_guard import HostedMetadataGuard

        guard = HostedMetadataGuard(server_mcp.repository)
        self.assertIsNone(guard.inspect_json_rpc_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "list_package_prompts",
                        "arguments": {"package_slug": "x", "current_step": 1, "include_prompt_text": False}}}
        ))
        self.assertIsNone(guard.inspect_json_rpc_message(
            {"jsonrpc": "2.0", "id": 2, "method": "resources/read",
             "params": {"uri": "ui://promptbanken/package-cards.html"}}
        ))


if __name__ == "__main__":
    unittest.main()
