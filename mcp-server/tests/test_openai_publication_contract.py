import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.mcp_server import _tool_definitions_for_profile


PUBLIC_TOOLS = {
    "health_check",
    "get_client_routing_instructions",
    "list_templates",
    "search_templates",
    "get_template",
    "list_packages",
    "get_package",
    "list_package_prompts",
    "recommend_packages",
}


class OpenAIPublicationContractTests(unittest.TestCase):
    def test_public_profile_exposes_exactly_public_read_only_tools(self) -> None:
        tools = _tool_definitions_for_profile("public")
        self.assertEqual({tool["name"] for tool in tools}, PUBLIC_TOOLS)

    def test_public_tools_have_review_ready_annotations(self) -> None:
        for tool in _tool_definitions_for_profile("public"):
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["annotations"]["title"])
                self.assertIs(tool["annotations"]["readOnlyHint"], True)
                self.assertIs(tool["annotations"]["destructiveHint"], False)
                self.assertIs(tool["annotations"]["openWorldHint"], False)
                self.assertFalse(tool["inputSchema"].get("additionalProperties", True))
