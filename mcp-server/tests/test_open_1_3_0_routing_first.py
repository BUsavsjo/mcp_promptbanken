"""Routing-first UI: data fixes and instructions (spec 2026-09-27)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import mcp_server as server_mcp
from server.mcp_server import _tool_definitions_for_profile

MEMBERSHIPS = {
    "p1": [
        {"slug": "behov-till-verifierad-digital-losning", "title": "Från behov till verifierad digital lösning", "package_type": "workflow", "summary": ""},
        {"slug": "behov-till-effekt", "title": "Från behov till effekt", "package_type": "workflow", "summary": ""},
        {"slug": "processer", "title": "Verksamhetsutveckling och processer", "package_type": "collection", "summary": ""},
    ],
    "p2": [{"slug": "behov-till-effekt", "title": "Från behov till effekt", "package_type": "workflow", "summary": ""}],
}


def _tool(name):
    return next(t for t in _tool_definitions_for_profile("public") if t["name"] == name)


class TemplatePackagesTests(unittest.TestCase):
    def test_packages_lists_every_membership_workflows_first_then_title(self):
        with patch("server.mcp_server._catalog_template_packages", return_value=MEMBERSHIPS):
            packages = server_mcp._template_packages({"id": "p1", "slug": "s1"}, None)
        self.assertEqual(
            [p["slug"] for p in packages],
            ["behov-till-effekt", "behov-till-verifierad-digital-losning", "processer"],
        )
        self.assertEqual(set(packages[0]), {"slug", "title", "package_type"})

    def test_unknown_template_has_no_packages(self):
        with patch("server.mcp_server._catalog_template_packages", return_value=MEMBERSHIPS):
            self.assertEqual(server_mcp._template_packages({"id": "x"}, None), [])

    def test_summary_fields_and_schemas_declare_packages(self):
        self.assertIn("packages", server_mcp._TEMPLATE_SUMMARY_FIELDS)
        self.assertIn("packages", server_mcp._TEMPLATE_SUMMARY_SCHEMA["properties"])
        self.assertIn("packages", server_mcp._TEMPLATE_FULL_SCHEMA["properties"])


class TemplateCountTests(unittest.TestCase):
    def test_template_count_counts_real_members(self):
        base = {
            "role_recognized": True, "matched_role": "chef", "role_match_source": "exact",
            "recommended_areas": ["behov-till-effekt"],
            "packages": [{"area": "behov-till-effekt", "area_label": "x", "template_count": 1}],
        }
        prompts = [{"id": "p1", "slug": "s1"}, {"id": "p2", "slug": "s2"}]
        with (
            patch.object(server_mcp._catalog, "list_published_prompts", return_value=prompts),
            patch("server.mcp_server._catalog_area_index", return_value={}),
            patch("server.mcp_server._catalog_package_audiences", return_value={}),
            patch("server.mcp_server._recommend_packages", return_value=base),
            patch("server.mcp_server._catalog_package_cards", return_value={}),
            patch("server.mcp_server._catalog_template_packages", return_value=MEMBERSHIPS),
        ):
            result = server_mcp._recommend_packages_payload("chef")
        self.assertEqual(result["packages"][0]["template_count"], 2)


class RoutingFirstInstructionTests(unittest.TestCase):
    def test_client_flow_puts_routing_first_and_drops_the_stale_area_rule(self):
        flow = " ".join(server_mcp.get_client_routing_instructions()["client_flow"])
        self.assertIn("Routing först", flow)
        self.assertIn("första arbetsfråga", flow)
        self.assertIn("current_step", flow)
        self.assertNotIn("bara de värden schemat listar", flow)

    def test_descriptions_carry_the_routing_first_hints(self):
        self.assertIn("top 3", _tool("recommend_packages")["description"])
        self.assertIn("do not restate the template", _tool("get_template")["description"])


if __name__ == "__main__":
    unittest.main()
