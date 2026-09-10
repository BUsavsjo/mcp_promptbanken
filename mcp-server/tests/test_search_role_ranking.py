"""search_templates(role=...) ska ranka mot rollen -- även när rollordet
inte står i den statiska vokabulären. Rollen får aldrig filtrera bort mallar,
bara flytta dem uppåt, precis som verktygsbeskrivningen i 1.2.2 lovar.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import _search_templates_payload


def _template(area: str, area_label: str, title: str) -> dict[str, object]:
    return {
        "id": f"{area}-1",
        "title": title,
        "area": area,
        "area_label": area_label,
        "tags": [],
        "syfte": "Planera arbetet.",
        "output_format": "text",
        "risk_level": "low",
        "tone_hint": None,
    }


def _catalog() -> dict[str, object]:
    return {
        "templates": [
            _template("kommunikation", "Kommunikation och publicering", "Planera ett utskick"),
            _template("skola-undervisning-larare", "Skola och undervisning – för lärare", "Planera en lektion"),
            _template("skarpare-funktionskrav", "Skarpare funktionskrav – kravställning i upphandling", "Planera kravarbetet"),
        ]
    }


class SearchRoleRankingTests(unittest.TestCase):
    def _search(self, role: str) -> list[str]:
        with patch("server.mcp_server._list_templates_payload", return_value=_catalog()):
            payload = _search_templates_payload(query="planera", role=role, limit=10)
        return [t["area"] for t in payload["templates"]]

    def test_recognized_role_lifts_its_own_area(self) -> None:
        self.assertEqual(self._search("lärare")[0], "skola-undervisning-larare")

    def test_unrecognized_role_is_ranked_by_lexical_overlap(self) -> None:
        self.assertEqual(self._search("upphandlingsjurist")[0], "skarpare-funktionskrav")

    def test_role_never_removes_templates_from_other_areas(self) -> None:
        self.assertEqual(len(self._search("lärare")), 3)

    def test_role_without_signal_leaves_the_ranking_alone(self) -> None:
        self.assertEqual(self._search("bibliotekarie"), self._search(""))

    def test_a_real_title_match_beats_a_guessed_role(self) -> None:
        """Gissningen får bryta lika, inte köra om en stark textträff."""
        catalog = {
            "templates": [
                _template("kommunikation", "Kommunikation och publicering", "Skriv kravarbete tydligt"),
                dict(
                    _template("skarpare-funktionskrav", "Skarpare funktionskrav", "Planera arbetet"),
                    syfte="Stöd i kravarbete inför upphandling.",
                ),
            ]
        }
        with patch("server.mcp_server._list_templates_payload", return_value=catalog):
            payload = _search_templates_payload(query="kravarbete", role="upphandlingsjurist", limit=10)

        self.assertEqual(payload["templates"][0]["area"], "kommunikation")

    def test_payload_still_reports_the_role_fields(self) -> None:
        with patch("server.mcp_server._list_templates_payload", return_value=_catalog()):
            payload = _search_templates_payload(query="planera", role="lärare", limit=10)

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["matched_role"], "larare")
        self.assertIn("recommended_areas", payload)


if __name__ == "__main__":
    unittest.main()
