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


if __name__ == "__main__":
    unittest.main()
