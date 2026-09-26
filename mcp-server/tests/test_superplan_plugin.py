"""Superplan-pluginet: struktur, versionsgrind och tunn dirigent."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import SERVICE_VERSION, _tool_definitions_for_profile

_PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
_SKILL = _PLUGIN / "skills" / "superplan"


class SuperplanPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        raw = (_SKILL / "SKILL.md").read_bytes().decode("utf-8")
        self.skill = raw.replace("\r\n", "\n")

    def test_plugin_version_follows_the_server(self) -> None:
        manifest = json.loads((_PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "promptbanken")
        self.assertEqual(manifest["version"], SERVICE_VERSION)

    def test_skill_has_name_and_description_frontmatter(self) -> None:
        match = re.match(r"^---\n(.*?)\n---\n", self.skill, flags=re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn("name: superplan", match.group(1))
        self.assertRegex(match.group(1), r"description: .{80,}")

    def test_skill_only_names_tools_the_server_publishes(self) -> None:
        public = {tool["name"] for tool in _tool_definitions_for_profile("public")}
        named = set(re.findall(r"`([a-z_]+)`", self.skill)) & {
            "list_package_prompts", "get_template", "search_templates", "list_packages",
            "get_package", "recommend_packages", "list_templates",
        }
        self.assertTrue(named)
        self.assertLessEqual(named, public)

    def test_skill_is_a_thin_conductor_without_catalog_prompt_text(self) -> None:
        # Fraser ur Superplans publicerade mallar får inte kopieras in i skillen.
        for phrase in ("Snabbfil", "Recommendation-first routing", "Frågeform", "Tolka fynd rätt"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.skill)

    def test_mcp_endpoint_is_the_same_in_both_manifests(self) -> None:
        mcp = json.loads((_PLUGIN / "mcp.json").read_text(encoding="utf-8"))
        url = mcp["mcpServers"]["promptbanken"]["url"]
        yaml_text = (_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn(f'url: "{url}"', yaml_text)
        self.assertTrue(url.endswith("/mcp"))


if __name__ == "__main__":
    unittest.main()
