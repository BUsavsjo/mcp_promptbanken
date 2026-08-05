import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.mcp_server import (
    SERVER_MODE,
    BearerAuthMiddleware,
    _handle_mcp_message,
    _save_my_item_payload,
    _tool_definitions_for_profile,
)
from server.mcp_server import mcp as _fastmcp_instance


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


def _make_challenge_request() -> "StarletteRequest":
    from starlette.requests import Request as StarletteRequest

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(
        {"type": "http", "method": "GET", "path": "/.well-known/openai-apps-challenge", "headers": []},
        receive,
    )


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

    def test_fastmcp_tool_registry_stays_within_public_tools_in_hosted_mode(self) -> None:
        """Regression test 3 (spec 2026-07-27-render-contract-parametric-
        templates-design.md v2, "Regressionstester som behövs" item 3 --
        "den viktigaste nya kontrollen"). FastMCP's own @mcp.tool() registry
        drives the /sse and /messages/ routes via a completely separate
        registration path from the hand-rolled _tool_definitions_for_profile
        JSON-RPC path tested above. FastMCP has no per-request auth
        filtering -- every @mcp.tool()-decorated function is registered
        unconditionally. Live verification against production (2026-07-27)
        found /sse exposing 28 tools, including write/vault/private tools
        such as save_workspace_prompt, list_my_items, activate_package,
        deactivate_package, copy_template_to_valvet -- with zero auth
        filtering at the registry level (calls without a key are still
        correctly rejected at the application layer, but the tool
        names/schemas themselves are visible to any client).

        This test is the regression lock spec Beslut 3 requires: in hosted
        mode, FastMCP's registered tool set must be a subset of the same
        9-tool PUBLIC_TOOLS list used by /mcp.

        EXPECTED TO FAIL today: this repo's mcp_server.py registers far more
        than 9 tools via @mcp.tool() with no SERVER_MODE-based gating (only
        route_skill/compile_skill_prompt are gated to local mode -- see
        mcp_server.py around line 1378). Would have caught the /sse exposure
        bug described in the spec.
        """
        self.assertEqual(
            SERVER_MODE,
            "hosted",
            "This test asserts the hosted-mode contract; expected default "
            "SERVER_MODE for the test environment is 'hosted' (no "
            "PROMPTBANKEN_MCP_MODE env var set).",
        )

        tools = asyncio.run(_fastmcp_instance.list_tools())
        tool_names = {tool.name for tool in tools}

        self.assertLessEqual(
            tool_names,
            PUBLIC_TOOLS,
            f"FastMCP registry exposes {len(tool_names)} tools in hosted mode, "
            f"including {sorted(tool_names - PUBLIC_TOOLS)} which are not in "
            "the public 9-tool set. This is the /sse over-exposure bug spec "
            "Beslut 3 must fix by gating the FastMCP registry to PUBLIC_TOOLS "
            "in hosted mode.",
        )


class OpenAIAppsChallengeTests(unittest.TestCase):
    def test_challenge_route_serves_configured_token_without_auth(self) -> None:
        from server.mcp_server import _openai_apps_challenge

        with patch.dict(
            "os.environ",
            {"PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN": "test-token-value"},
        ):
            response = asyncio.run(_openai_apps_challenge(_make_challenge_request()))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bytes(response.body).decode("utf-8"), "test-token-value")

    def test_challenge_route_404s_when_token_unset(self) -> None:
        from server.mcp_server import _openai_apps_challenge

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN", None)
            response = asyncio.run(_openai_apps_challenge(_make_challenge_request()))

        self.assertEqual(response.status_code, 404)

    @patch("server.mcp_server._api_key", return_value="global-key")
    def test_challenge_route_exempt_from_global_bearer_auth(self, _) -> None:
        from server.mcp_server import BearerAuthMiddleware

        app = BearerAuthMiddleware(_accept_asgi_request)

        self.assertEqual(
            _asgi_status(app, "/.well-known/openai-apps-challenge"),
            204,
        )
