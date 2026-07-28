# mcp-server/tests/test_admin_route.py
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import (
    AdminBearerAuthMiddleware,
    _admin_tool_definitions,
    _handle_admin_message,
    _tool_definitions_for_profile,
)


class AdminRouteTests(unittest.TestCase):
    def test_admin_tool_definitions_are_exactly_the_twelve_admin_tools(self):
        names = {tool["name"] for tool in _admin_tool_definitions()}
        self.assertEqual(
            names,
            {
                "admin_create_prompt",
                "admin_upsert_prompt_variant",
                "admin_list_draft_prompts",
                "admin_get_prompt",
                "admin_publish_prompt",
                "admin_unpublish_prompt",
                "admin_delete_draft_prompt",
                "admin_create_package",
                "admin_add_prompt_to_package",
                "admin_publish_package",
                "admin_unpublish_package",
                "admin_delete_draft_package",
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

    def test_admin_tools_are_absent_from_public_and_key_authenticated_profiles(self):
        admin_names = {tool["name"] for tool in _admin_tool_definitions()}
        for profile in ("public", "key_authenticated"):
            names = {tool["name"] for tool in _tool_definitions_for_profile(profile)}
            self.assertTrue(
                names.isdisjoint(admin_names),
                f"admin tools leaked into profile={profile!r}: {names & admin_names}",
            )


class AdminBearerAuthMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    @patch("server.mcp_server._admin_api_key", return_value="")
    async def test_returns_401_when_admin_key_unset_regardless_of_authorization_header(self, _mock_key):
        app_called = []

        async def inner_app(scope, receive, send):
            app_called.append(True)

        scope = {
            "type": "http",
            "path": "/admin",
            "headers": [(b"authorization", b"Bearer whatever")],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent = []

        async def send(message):
            sent.append(message)

        middleware = AdminBearerAuthMiddleware(inner_app)
        await middleware(scope, receive, send)

        self.assertEqual(app_called, [])
        start_messages = [m for m in sent if m.get("type") == "http.response.start"]
        self.assertEqual(len(start_messages), 1)
        self.assertEqual(start_messages[0]["status"], 401)


if __name__ == "__main__":
    unittest.main()
