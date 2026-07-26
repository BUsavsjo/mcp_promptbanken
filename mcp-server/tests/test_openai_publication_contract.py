import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.mcp_server import _handle_mcp_message, _tool_definitions_for_profile


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

    def test_public_profile_stays_public_even_when_key_is_present(self) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "valid-key",
            tool_profile="public",
        )

        self.assertEqual(
            {tool["name"] for tool in response["result"]["tools"]},
            PUBLIC_TOOLS,
        )

    @patch("server.mcp_server._mcp_key_is_valid", return_value=True)
    def test_key_profile_exposes_valvet_for_verified_free_or_pro_key(self, _) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "valid-key",
            tool_profile="key_authenticated",
        )

        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("list_my_items", names)
        self.assertIn("activate_package", names)
        self.assertIn("deactivate_package", names)

    @patch("server.mcp_server._mcp_key_is_valid", return_value=False)
    def test_key_profile_rejects_invalid_key_before_listing_private_tools(self, _) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "invalid-key",
            tool_profile="key_authenticated",
        )

        self.assertEqual(response["error"]["code"], -32001)

    def test_public_profile_rejects_private_calls_even_when_key_is_present(self) -> None:
        response = _handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "save_my_item", "arguments": {}},
            },
            "static-key",
            tool_profile="public",
        )

        self.assertEqual(response["error"]["code"], -32601)

    @patch("server.mcp_server._mcp_key_is_valid", return_value=False)
    def test_key_profile_rejects_invalid_key_before_private_calls(self, _) -> None:
        response = _handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "save_my_item", "arguments": {}},
            },
            "invalid-key",
            tool_profile="key_authenticated",
        )

        self.assertEqual(response["error"]["code"], -32001)
