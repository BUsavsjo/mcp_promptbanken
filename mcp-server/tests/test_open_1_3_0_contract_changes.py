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


if __name__ == "__main__":
    unittest.main()
