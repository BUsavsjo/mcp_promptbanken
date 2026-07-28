# mcp-server/tests/test_admin_route.py
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import _handle_admin_message, _admin_tool_definitions


class AdminRouteTests(unittest.TestCase):
    def test_admin_tool_definitions_are_exactly_the_eight_admin_tools(self):
        names = {tool["name"] for tool in _admin_tool_definitions()}
        self.assertEqual(
            names,
            {
                "admin_create_prompt",
                "admin_upsert_prompt_variant",
                "admin_list_draft_prompts",
                "admin_get_prompt",
                "admin_publish_prompt",
                "admin_create_package",
                "admin_add_prompt_to_package",
                "admin_publish_package",
            },
        )

    def test_tools_list_returns_admin_tools(self):
        response = _handle_admin_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("admin_create_prompt", names)

    def test_unknown_tool_returns_json_rpc_error(self):
        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_templates", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], -32601)

    @patch("server.mcp_server.admin_catalog.create_prompt")
    def test_admin_create_prompt_dispatches_to_admin_catalog(self, create_prompt):
        create_prompt.return_value = {"id": "prompt-1"}

        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "admin_create_prompt",
                    "arguments": {
                        "slug": "test-slug",
                        "title": "Title",
                        "summary": "Summary",
                        "prompt_text": "Prompt text",
                    },
                },
            }
        )

        create_prompt.assert_called_once_with("test-slug", "Title", "Summary", "Prompt text")
        self.assertNotIn("error", response)

    def test_admin_publish_prompt_requires_confirm_argument(self):
        response = _handle_admin_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "admin_publish_prompt", "arguments": {"prompt_id": "prompt-1"}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
