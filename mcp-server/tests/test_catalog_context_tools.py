import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.hosted_guard import HostedMetadataGuard
from server.mcp_server import _handle_mcp_message, _search_templates_payload, _tool_definitions, repository


class CatalogContextToolsTests(unittest.TestCase):
    def test_list_templates_accepts_context_keys_and_uses_catalog_prompts(self) -> None:
        with patch("server.mcp_server._list_templates_payload") as mocked_payload:
            mocked_payload.return_value = {"templates": [{"id": "123"}]}

            response = _handle_mcp_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "list_templates",
                        "arguments": {"context_keys": ["kommun", "skola"]},
                    },
                },
                "",
            )

        self.assertEqual(response["result"]["content"][0]["text"], '{"templates": [{"id": "123"}]}')
        mocked_payload.assert_called_once_with(["kommun", "skola"])

    def test_tool_definitions_expose_context_keys_and_package_tools(self) -> None:
        definitions = {tool["name"]: tool for tool in _tool_definitions()}

        self.assertIn("context_keys", definitions["list_templates"]["inputSchema"]["properties"])
        self.assertIn("context_keys", definitions["search_templates"]["inputSchema"]["properties"])
        self.assertIn("context_keys", definitions["get_template"]["inputSchema"]["properties"])
        self.assertIn("role", definitions["get_template"]["inputSchema"]["properties"])
        self.assertIn("audience", definitions["get_template"]["inputSchema"]["properties"])
        self.assertIn("tone", definitions["get_template"]["inputSchema"]["properties"])
        self.assertIn("input_text", definitions["get_template"]["inputSchema"]["properties"])
        self.assertIn("list_packages", definitions)
        self.assertIn("get_package", definitions)
        self.assertIn("list_package_prompts", definitions)
        self.assertIn("role", definitions["list_package_prompts"]["inputSchema"]["properties"])
        self.assertIn("audience", definitions["list_package_prompts"]["inputSchema"]["properties"])
        self.assertIn("tone", definitions["list_package_prompts"]["inputSchema"]["properties"])
        self.assertIn("input_text", definitions["list_package_prompts"]["inputSchema"]["properties"])

    def test_hosted_guard_allows_context_keys_for_catalog_tools(self) -> None:
        guard = HostedMetadataGuard(repository)

        warning = guard.inspect_json_rpc_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_templates",
                    "arguments": {"context_keys": ["kommun", "skola"]},
                },
            }
        )

        self.assertIsNone(warning)

    def test_search_templates_tolerates_nullable_catalog_fields(self) -> None:
        with patch("server.mcp_server._list_templates_payload") as mocked_payload:
            mocked_payload.return_value = {
                "templates": [
                    {
                        "id": "123",
                        "title": "Svar på medborgarmejl",
                        "tags": None,
                        "syfte": None,
                        "output_format": None,
                        "area_label": None,
                        "tone_hint": None,
                    }
                ]
            }

            payload = _search_templates_payload(query="medborgarmejl", context_keys=["företag"])

        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["templates"][0]["id"], "123")


if __name__ == "__main__":
    unittest.main()
