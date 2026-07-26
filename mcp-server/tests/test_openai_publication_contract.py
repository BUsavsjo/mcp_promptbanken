import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.mcp_server import (
    BearerAuthMiddleware,
    _handle_mcp_message,
    _save_my_item_payload,
    _tool_definitions_for_profile,
)


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


async def _accept_asgi_request(scope, receive, send) -> None:
    await Response(status_code=204)(scope, receive, send)


def _asgi_status(app, path: str, authorization: str = "") -> int:
    messages = []
    headers = [(b"authorization", authorization.encode("utf-8"))] if authorization else []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "method": "POST",
                "path": path,
                "headers": headers,
            },
            receive,
            send,
        )
    )
    return next(message["status"] for message in messages if message["type"] == "http.response.start")


def _http_status_error(status_code: int, code: str, secret: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/vault/items")
    response = httpx.Response(
        status_code,
        json={"code": code, "message": secret},
        request=request,
    )
    return httpx.HTTPStatusError("write failed", request=request, response=response)


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

    @patch("server.mcp_server._api_key", return_value="global-key")
    def test_global_bearer_auth_keeps_public_mcp_anonymous(self, _) -> None:
        app = BearerAuthMiddleware(_accept_asgi_request)

        self.assertEqual(_asgi_status(app, "/mcp"), 204)
        self.assertEqual(_asgi_status(app, "/mcp/key"), 401)
        self.assertEqual(_asgi_status(app, "/mcp/key", "Bearer global-key"), 204)

    def test_public_profile_ignores_key_for_health_check(self) -> None:
        with patch(
            "server.mcp_server._health_check_payload",
            side_effect=lambda mcp_key: {"plan": "pro" if mcp_key else "free"},
        ):
            response = _handle_mcp_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "health_check", "arguments": {}},
                },
                "pro-key",
                tool_profile="public",
            )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["plan"], "free")

    def test_unknown_profile_rejects_tools_list(self) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            tool_profile="unknown",
        )

        self.assertEqual(response["error"]["code"], -32602)

    def test_unknown_profile_rejects_tools_call(self) -> None:
        response = _handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "health_check", "arguments": {}},
            },
            tool_profile="unknown",
        )

        self.assertEqual(response["error"]["code"], -32602)

    def test_private_write_error_log_omits_response_body(self) -> None:
        secret = "RA_PROMPT_OCH_RADDATA"
        error = _http_status_error(422, "invalid_input", secret)
        with (
            patch("server.mcp_server._vault_save_item", side_effect=error),
            patch("server.mcp_server._vault_log_write_attempt"),
            self.assertLogs("promptbanken_mcp", level="INFO") as logs,
        ):
            payload = _save_my_item_payload(
                "valid-key",
                "idempotency-key",
                "prompt",
                "Titel",
                "Innehall",
                None,
            )

        log_output = "\n".join(logs.output)
        self.assertEqual(payload["status"], "error")
        self.assertIn("http_status=422", log_output)
        self.assertIn("error_code=invalid_input", log_output)
        self.assertNotIn(secret, log_output)
