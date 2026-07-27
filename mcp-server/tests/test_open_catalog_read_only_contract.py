"""Regression suite for the read-only open-catalog contract.

Spec: docs/superpowers/specs/2026-07-27-render-contract-parametric-templates-design.md
(v2, "Regressionstester som behövs" section). Peter's decision: the open MCP
catalog must become strictly read-only -- the server never renders a finished
prompt, `context_keys` only selects a profile variant. These tests are written
BEFORE the implementation change (TDD). Tests that assert the DESIRED
(not-yet-implemented) behavior are expected to fail until Beslut 1, 1b and 3
from the spec land. Do not weaken these assertions to make them pass against
today's code.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.hosted_guard import HostedMetadataGuard
from server.mcp_server import (
    _get_package_payload,
    _get_template_payload,
    _handle_mcp_message,
    _list_package_prompts_payload,
    _list_templates_payload,
    repository,
)


class ReadOnlyCatalogPayloadContractTests(unittest.TestCase):
    """Regression test 1 (spec item 1): rendered_* fields must be gone from
    every catalog payload function, while the raw ingredients the client
    needs to render locally (prompt_text/intro_text, parameter_schema,
    default_bindings, binding_overrides) must remain.

    EXPECTED TO FAIL today: `_catalog_prompt_to_template` and
    `_catalog_package_to_payload` still call `render_template_variant` and
    attach `rendered_prompt_text`/`rendered_intro_text` (mcp_server.py:410,
    :432). That is correct -- this test is the red half of the TDD cycle for
    spec Beslut 1.
    """

    def test_list_templates_payload_has_no_rendered_fields(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog_area_index", return_value={}),
        ):
            mocked_prompts.return_value = [
                {
                    "id": "prompt-1",
                    "slug": "mejl",
                    "title": "Mejl",
                    "prompt_text": "Skriv ett {{ton}} svar till {{malgrupp}}.",
                    "parameter_schema": {
                        "fields": [
                            {"key": "malgrupp", "source": "global"},
                            {"key": "ton", "source": "global"},
                        ]
                    },
                    "default_bindings": {"malgrupp": "invanare", "ton": "formellt"},
                    "binding_overrides": [
                        {"when": {"kontext": "foretag"}, "set": {"malgrupp": "foretagare"}}
                    ],
                }
            ]

            payload = _list_templates_payload(["generell"])

        template = payload["templates"][0]
        self.assertNotIn("rendered_prompt_text", template)
        self.assertIn("prompt_text", template)
        self.assertIn("parameter_schema", template)
        self.assertIn("default_bindings", template)
        self.assertIn("binding_overrides", template)

    def test_get_template_payload_has_no_rendered_fields(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog.get_published_prompt") as mocked_detail,
            patch("server.mcp_server._catalog_area_index", return_value={}),
        ):
            mocked_prompts.return_value = [{"id": "prompt-1", "slug": "mejl", "title": "Mejl"}]
            mocked_detail.return_value = [
                {
                    "id": "prompt-1",
                    "slug": "mejl",
                    "title": "Mejl",
                    "context_key": "generell",
                    "prompt_text": "Skriv for {{malgrupp}}.",
                    "parameter_schema": {"fields": [{"key": "malgrupp", "source": "global"}]},
                    "default_bindings": {"malgrupp": "invanare"},
                    "binding_overrides": [
                        {"when": {"kontext": "foretag"}, "set": {"malgrupp": "foretagare"}}
                    ],
                }
            ]

            payload = _get_template_payload("prompt-1", ["generell"])

        template = payload["template"]
        self.assertNotIn("rendered_prompt_text", template)
        self.assertIn("prompt_text", template)
        self.assertIn("parameter_schema", template)
        self.assertIn("default_bindings", template)
        self.assertIn("binding_overrides", template)

    def test_get_package_payload_has_no_rendered_fields(self) -> None:
        with patch("server.mcp_server._catalog.get_published_package") as mocked_package:
            mocked_package.return_value = [
                {
                    "id": "package-1",
                    "slug": "kommunikation",
                    "context_key": "generell",
                    "title": "Kommunikation",
                    "intro_text": "Valkommen till {{malgrupp}}.",
                    "parameter_schema": {"fields": [{"key": "malgrupp", "source": "global"}]},
                    "default_bindings": {"malgrupp": "invanare"},
                    "binding_overrides": [
                        {"when": {"kontext": "foretag"}, "set": {"malgrupp": "foretagare"}}
                    ],
                }
            ]

            payload = _get_package_payload("kommunikation", ["generell"])

        package = payload["package"]
        self.assertNotIn("rendered_intro_text", package)
        self.assertIn("intro_text", package)
        self.assertIn("parameter_schema", package)
        self.assertIn("default_bindings", package)
        self.assertIn("binding_overrides", package)

    def test_list_package_prompts_payload_has_no_rendered_fields(self) -> None:
        with patch("server.mcp_server._catalog.list_published_package_prompts") as mocked_prompts:
            mocked_prompts.return_value = [
                {
                    "prompt_id": "prompt-1",
                    "prompt_slug": "mejl",
                    "title": "Mejl",
                    "prompt_text": "Skriv for {{malgrupp}}.",
                    "parameter_schema": {"fields": [{"key": "malgrupp", "source": "global"}]},
                    "default_bindings": {"malgrupp": "invanare"},
                    "binding_overrides": [
                        {"when": {"kontext": "foretag"}, "set": {"malgrupp": "foretagare"}}
                    ],
                }
            ]

            payload = _list_package_prompts_payload("kommunikation", ["generell"])

        prompt = payload["prompts"][0]
        self.assertNotIn("rendered_prompt_text", prompt)
        self.assertIn("prompt_text", prompt)
        self.assertIn("parameter_schema", prompt)
        self.assertIn("default_bindings", prompt)
        self.assertIn("binding_overrides", prompt)


class CatalogResponseIdenticalRegardlessOfAuthTests(unittest.TestCase):
    """Regression test 2 (spec item 2): the same catalog tool call must
    produce a byte-identical payload whether it comes through the public
    profile (no key) or the key-authenticated profile (valid key) -- the
    catalog is public read data, not user/plan-specific. Underlying Supabase
    catalog access is mocked so this doesn't hit the network; the auth check
    itself (`_mcp_key_is_valid`) is patched to always succeed for the
    key-authenticated call so we're isolating the catalog-payload behavior,
    not re-testing key validation (already covered elsewhere).

    No field is expected to legitimately differ: `_get_template_payload`
    takes no mcp_key/profile argument at all today, so profile cannot leak
    into the catalog response even before spec Beslut 1 lands.
    """

    def _fixed_prompts(self):
        return [
            {
                "id": "prompt-1",
                "slug": "mejl",
                "title": "Mejl",
                "prompt_text": "Skriv for {{malgrupp}}.",
                "parameter_schema": {"fields": [{"key": "malgrupp", "source": "global"}]},
                "default_bindings": {"malgrupp": "invanare"},
            }
        ]

    def test_get_template_response_identical_for_public_and_key_authenticated(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog.get_published_prompt") as mocked_detail,
            patch("server.mcp_server._catalog_area_index", return_value={}),
            patch("server.mcp_server._mcp_key_is_valid", return_value=True),
        ):
            mocked_prompts.return_value = [{"id": "prompt-1", "slug": "mejl", "title": "Mejl"}]
            mocked_detail.return_value = self._fixed_prompts()

            message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "get_template",
                    "arguments": {"template_id": "prompt-1", "context_keys": ["generell"]},
                },
            }

            public_response = _handle_mcp_message(dict(message), "", tool_profile="public")
            authenticated_response = _handle_mcp_message(
                dict(message), "valid-key", tool_profile="key_authenticated"
            )

        self.assertEqual(
            public_response["result"]["content"][0]["text"],
            authenticated_response["result"]["content"][0]["text"],
        )


class HostedGuardBlocksInputTextForCatalogToolsTests(unittest.TestCase):
    """Regression test 4 (spec item 4): `get_template`/`get_package`/
    `list_package_prompts` calls carrying an `input_text` argument must be
    blocked (a warning from HostedMetadataGuard), not silently allowed.
    `input_text` is a GDPR risk on the open catalog surface (spec section C,
    Beslut 1b) and becomes meaningless once server-side rendering is removed
    (spec Beslut 1).

    EXPECTED TO FAIL today: `hosted_guard.py`'s `allowed_tool_args` for these
    three tools explicitly includes "input_text" (hosted_guard.py:56, 58,
    59), so `inspect_json_rpc_message` returns None (no warning) for these
    calls right now. That is correct -- this is the red test that spec
    Beslut 1b turns green.
    """

    def test_input_text_argument_is_blocked_for_catalog_render_tools(self) -> None:
        guard = HostedMetadataGuard(repository)

        for tool_name, id_key in (
            ("get_template", "template_id"),
            ("get_package", "package_slug"),
            ("list_package_prompts", "package_slug"),
        ):
            with self.subTest(tool_name=tool_name):
                warning = guard.inspect_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": {
                                id_key: "abc",
                                "input_text": "Ansokan saknar bilaga (personnummer 19800101-1234).",
                            },
                        },
                    }
                )

                self.assertIsNotNone(
                    warning,
                    f"{tool_name}: input_text should be blocked by HostedMetadataGuard "
                    "once spec Beslut 1b lands; today it is still in allowed_tool_args "
                    "and passes through unwarned.",
                )
                if warning is not None:
                    self.assertIn("reason", warning)


if __name__ == "__main__":
    unittest.main()
