import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.hosted_guard import HostedMetadataGuard
from server.usage_events import _safe_metadata
from server import mcp_server as server_mcp
from server.mcp_server import (
    _tool_definitions_for_profile,
    _TEMPLATE_SUMMARY_FIELDS,
    _handle_mcp_message,
    _list_templates_with_usage,
    _catalog_prompt_to_template_summary,
    _get_package_payload,
    _get_template_payload,
    _list_package_prompts_payload,
    _list_templates_payload,
    _search_templates_payload,
    _search_templates_with_usage,
    _tool_definitions,
    repository,
)


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

        # list_templates now returns summary fields only, so the response is
        # the summary projection of the mocked payload rather than the mock
        # verbatim -- absent fields come back as null, same as
        # search_templates has always done. What this test is about is that
        # context_keys reaches the payload function.
        templates = json.loads(response["result"]["content"][0]["text"])["templates"]
        self.assertEqual(templates[0]["id"], "123")
        self.assertNotIn("prompt_text", templates[0])
        mocked_payload.assert_called_once_with(["kommun", "skola"])

    def _catalog_of(self, count: int) -> list[dict[str, object]]:
        return [
            {
                "id": f"prompt-{i}",
                "slug": f"mall-{i}",
                "title": f"Mall {i}",
                "summary": "Syfte",
                "prompt_text": "X" * 2000,
            }
            for i in range(count)
        ]

    def test_list_templates_omits_prompt_text_by_default(self) -> None:
        # 102 templates with full prompt_text was a 198 KB single response --
        # roughly 50k tokens, a third of a typical context window, from one
        # call. Summaries keep the tool usable; get_template fetches the text.
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog_area_index", return_value={}),
            patch("server.mcp_server.track_usage_event"),
        ):
            mocked_prompts.return_value = self._catalog_of(3)

            payload = _list_templates_with_usage(["generell"])

        self.assertEqual(len(payload["templates"]), 3)
        for template in payload["templates"]:
            self.assertNotIn("prompt_text", template)
            self.assertNotIn("parameter_schema", template)
            self.assertEqual(set(template), set(_TEMPLATE_SUMMARY_FIELDS))

    def test_list_templates_includes_prompt_text_when_asked(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog_area_index", return_value={}),
            patch("server.mcp_server.track_usage_event"),
        ):
            mocked_prompts.return_value = self._catalog_of(2)

            payload = _list_templates_with_usage(["generell"], include_prompt_text=True)

        self.assertEqual(payload["templates"][0]["prompt_text"], "X" * 2000)

    def test_list_templates_forwards_include_prompt_text_over_mcp(self) -> None:
        with patch("server.mcp_server._list_templates_with_usage") as mocked:
            mocked.return_value = {"templates": []}

            _handle_mcp_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "list_templates",
                        "arguments": {"include_prompt_text": True},
                    },
                },
                "",
            )

        self.assertTrue(mocked.call_args.kwargs["include_prompt_text"])

    def test_list_templates_rejects_non_boolean_include_prompt_text(self) -> None:
        response = _handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_templates",
                    "arguments": {"include_prompt_text": "yes"},
                },
            },
            "",
        )

        self.assertEqual(response["error"]["code"], -32602)

    def test_search_templates_still_sees_full_templates_internally(self) -> None:
        # The slimming happens at the tool boundary, not in
        # _list_templates_payload -- search filters on fields that only exist
        # on the full template, so it must keep receiving them.
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog_area_index", return_value={}),
        ):
            mocked_prompts.return_value = self._catalog_of(1)

            payload = _list_templates_payload(["generell"])

        self.assertIn("prompt_text", payload["templates"][0])

    def test_tool_definitions_expose_context_keys_and_package_tools(self) -> None:
        # spec 2026-07-27 v2, Beslut 1/1b: role/audience/tone/input_text are
        # removed from the get_template/get_package/list_package_prompts input
        # schemas -- rendering happens client-side, context_keys is the only
        # sanctioned server-side selection mechanism.
        definitions = {tool["name"]: tool for tool in _tool_definitions()}

        self.assertIn("context_keys", definitions["list_templates"]["inputSchema"]["properties"])
        self.assertIn("context_keys", definitions["search_templates"]["inputSchema"]["properties"])
        self.assertIn("context_keys", definitions["get_template"]["inputSchema"]["properties"])
        self.assertNotIn("role", definitions["get_template"]["inputSchema"]["properties"])
        self.assertNotIn("audience", definitions["get_template"]["inputSchema"]["properties"])
        self.assertNotIn("tone", definitions["get_template"]["inputSchema"]["properties"])
        self.assertNotIn("input_text", definitions["get_template"]["inputSchema"]["properties"])
        self.assertIn("list_packages", definitions)
        self.assertIn("get_package", definitions)
        self.assertIn("list_package_prompts", definitions)
        self.assertNotIn("role", definitions["list_package_prompts"]["inputSchema"]["properties"])
        self.assertNotIn("audience", definitions["list_package_prompts"]["inputSchema"]["properties"])
        self.assertNotIn("tone", definitions["list_package_prompts"]["inputSchema"]["properties"])
        self.assertNotIn("input_text", definitions["list_package_prompts"]["inputSchema"]["properties"])

    def test_open_tool_definitions_hide_private_and_write_tools(self) -> None:
        public_names = {tool["name"] for tool in _tool_definitions()}

        self.assertIn("search_templates", public_names)
        self.assertIn("get_template", public_names)
        self.assertIn("recommend_packages", public_names)
        self.assertNotIn("save_workspace_prompt", public_names)
        self.assertNotIn("save_my_item", public_names)
        self.assertNotIn("update_my_item", public_names)
        self.assertNotIn("archive_my_item", public_names)
        self.assertNotIn("list_my_items", public_names)
        self.assertNotIn("copy_template_to_valvet", public_names)

    def test_authenticated_tool_definitions_include_private_tools(self) -> None:
        authenticated_names = {tool["name"] for tool in _tool_definitions("mcp_key")}

        self.assertIn("save_workspace_prompt", authenticated_names)
        self.assertIn("list_my_items", authenticated_names)

    def test_open_connector_blocks_private_tool_calls(self) -> None:
        response = _handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "save_my_item", "arguments": {}},
            },
            "",
        )

        self.assertEqual(response["error"]["code"], -32601)

    def test_hosted_tools_list_stays_public_even_with_connector_token(self) -> None:
        response = _handle_mcp_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            "connector-token",
        )

        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("search_templates", names)
        self.assertNotIn("save_my_item", names)
        self.assertNotIn("list_my_items", names)

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

    # NOTE(spec 2026-07-27 v2, Beslut 1b): the old
    # test_hosted_guard_allows_render_arguments_for_catalog_tools test was
    # removed here rather than inverted -- it is now fully redundant with
    # test_open_catalog_read_only_contract.py::HostedGuardBlocksInputTextForCatalogToolsTests,
    # which asserts the same input_text-is-blocked behavior with a clearer,
    # more specific name and docstring. Keeping both would just assert the
    # same fact twice under different names.

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

    def _two_template_catalog(self) -> dict[str, object]:
        return {
            "templates": [
                {
                    "id": "1",
                    "title": "Förklara AI för medarbetare",
                    "tags": ["ai"],
                    "syfte": None,
                    "output_format": None,
                    "area_label": None,
                    "tone_hint": None,
                },
                {
                    "id": "2",
                    "title": "Kallelse till möte",
                    "tags": ["möte"],
                    "syfte": None,
                    "output_format": None,
                    "area_label": None,
                    "tone_hint": None,
                },
            ]
        }

    def test_short_acronym_query_filters_instead_of_matching_everything(self) -> None:
        """Verified against production 2026-08-23: query='AI' reported
        total_matches=102, the entire catalogue. The tokenizer dropped every
        token under three characters, left an empty token list, and the scoring
        loop treated "no tokens" as "no filter". AI, HR and IT are exactly the
        terms this catalogue is searched for."""
        with patch(
            "server.mcp_server._list_templates_payload",
            return_value=self._two_template_catalog(),
        ):
            payload = _search_templates_payload(query="AI")

        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["templates"][0]["id"], "1")

    def test_query_of_only_stopwords_does_not_return_whole_catalogue(self) -> None:
        """The same "empty token list means no filter" bug, reachable even
        after the length cut is lowered -- a query has to keep filtering, or
        report nothing, but never claim every template matched."""
        with patch(
            "server.mcp_server._list_templates_payload",
            return_value=self._two_template_catalog(),
        ):
            payload = _search_templates_payload(query="och")

        self.assertEqual(payload["total_matches"], 0)
        self.assertEqual(payload["templates"], [])

    def test_area_enum_follows_the_published_catalogue(self) -> None:
        """The hardcoded enum listed 7 areas while the live catalogue had 17,
        so ten areas could not be filtered on at all."""
        packages = [{"slug": "anti-slop"}, {"slug": "kommunikation"}, {"slug": "hall-traden"}]
        with patch("server.mcp_server._catalog.list_published_packages", return_value=packages):
            server_mcp._catalog_area_slug_cache = None
            definitions = {tool["name"]: tool for tool in _tool_definitions_for_profile("public")}
            server_mcp._catalog_area_slug_cache = None

        area_enum = definitions["search_templates"]["inputSchema"]["properties"]["area"]["enum"]
        self.assertEqual(area_enum, ["anti-slop", "hall-traden", "kommunikation"])

    def test_search_templates_propagates_catalog_error_payload(self) -> None:
        catalog_error = {
            "status": "error",
            "message": "Katalogen ar inte konfigurerad.",
            "templates": [],
        }
        with patch("server.mcp_server._list_templates_payload", return_value=catalog_error):
            payload = _search_templates_payload(query="medborgarmejl")

        self.assertEqual(payload, catalog_error)

    def test_usage_metadata_accepts_closed_prompt_list_alias(self) -> None:
        self.assertEqual(_safe_metadata({"tool": "list_prompts"}), {"tool": "list_prompts"})
        self.assertEqual(_safe_metadata({"tool": "search_prompts"}), {"tool": "search_prompts"})
        self.assertEqual(_safe_metadata({"tool": "list_templates"}), {})

    def test_json_rpc_search_templates_tracks_anonymous_usage(self) -> None:
        with (
            patch("server.mcp_server._search_templates_payload") as mocked_payload,
            patch("server.mcp_server.track_usage_event") as mocked_usage,
        ):
            mocked_payload.return_value = {
                "total_matches": 0,
                "returned": 0,
                "templates": [],
            }

            response = _handle_mcp_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "search_templates",
                        "arguments": {"query": "okand", "context_keys": ["kommun"]},
                    },
                },
                "",
            )

        self.assertIn("result", response)
        mocked_payload.assert_called_once_with("okand", "", "", "", 10, ["kommun"])
        mocked_usage.assert_called_once_with(
            event_type="search",
            outcome="empty",
            context_keys=["kommun"],
            result_count=0,
            metadata={"tool": "search_prompts"},
        )

    def test_search_templates_with_usage_tracks_catalog_errors(self) -> None:
        with (
            patch("server.mcp_server._search_templates_payload") as mocked_payload,
            patch("server.mcp_server.track_usage_event") as mocked_usage,
        ):
            mocked_payload.return_value = {
                "status": "error",
                "message": "Katalogen ar inte konfigurerad.",
                "templates": [],
            }

            payload = _search_templates_with_usage(query="mejl", context_keys=["skola"])

        self.assertEqual(payload["status"], "error")
        mocked_usage.assert_called_once_with(
            event_type="search",
            outcome="error",
            context_keys=["skola"],
            metadata={"tool": "search_prompts"},
        )

    def test_get_template_not_found_usage_keeps_attempted_slug(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts", return_value=[]),
            patch("server.mcp_server.track_usage_event") as mocked_usage,
        ):
            payload = _get_template_payload("okand-slug", ["kommun"], track_usage=True)

        self.assertEqual(payload["status"], "error")
        mocked_usage.assert_called_once_with(
            event_type="prompt_get",
            outcome="not_found",
            prompt_slug="okand-slug",
            context_keys=["kommun"],
            metadata={"tool": "get_prompt"},
        )

    def test_catalog_summary_uses_static_risk_and_output_metadata(self) -> None:
        with patch("server.mcp_server._static_skill_metadata") as mocked_metadata:
            mocked_metadata.return_value = {
                "beslutsunderlag": {
                    "risk_level": "high",
                    "output_type": "decision_brief",
                    "intents": ["decision_support"],
                }
            }

            payload = _catalog_prompt_to_template_summary(
                {"id": "prompt-1", "slug": "beslutsunderlag", "title": "Beslutsunderlag"}
            )

        self.assertEqual(payload["risk_level"], "high")
        self.assertEqual(payload["output_format"], "decision_brief")
        self.assertEqual(payload["tags"], ["decision_support"])

    def test_list_templates_derives_area_from_package_membership(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog.list_published_packages") as mocked_packages,
            patch("server.mcp_server._catalog.list_published_package_prompts") as mocked_package_prompts,
            patch("server.mcp_server._catalog_area_cache", {}),
        ):
            mocked_prompts.return_value = [
                {"id": "prompt-1", "slug": "mejl", "title": "Mejl", "summary": "Skriv mejl"}
            ]
            mocked_packages.return_value = [
                {"slug": "kommunikation", "title": "Kommunikation och publicering"}
            ]
            mocked_package_prompts.return_value = [{"prompt_slug": "mejl"}]

            payload = _list_templates_payload(["generell"])

        self.assertEqual(payload["templates"][0]["area"], "kommunikation")
        self.assertEqual(payload["templates"][0]["area_label"], "Kommunikation och publicering")

    def test_list_templates_renders_catalog_metadata_and_reports_selected_context(self) -> None:
        # spec 2026-07-27 v2, Beslut 1: server-side rendering is removed, so
        # rendered_prompt_text must be ABSENT; the context-match reporting
        # this test also covers (requested/matched context keys, variant
        # source) is unrelated, still-valid behavior and stays asserted.
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog_area_index", return_value={}),
        ):
            mocked_prompts.return_value = [
                {
                    "id": "prompt-1",
                    "slug": "rutin",
                    "title": "Rutiner",
                    "prompt_text": "Gör instruktioner tydliga för {{malgrupp}} i {{kontext}}.",
                    "audience_label": "medarbetare",
                    "context_key": "kommun",
                    "parameter_schema": {
                        "fields": [
                            {"key": "kontext", "source": "global"},
                            {"key": "malgrupp", "source": "global"},
                        ]
                    },
                    "default_bindings": {"malgrupp": "medarbetare"},
                }
            ]

            payload = _list_templates_payload(["kommun", "skola"])

        self.assertNotIn("rendered_prompt_text", payload["templates"][0])
        self.assertEqual(payload["templates"][0]["prompt_text"], "Gör instruktioner tydliga för {{malgrupp}} i {{kontext}}.")
        self.assertEqual(payload["requested_context_keys"], ["kommun", "skola"])
        self.assertEqual(payload["matched_context_keys"], ["kommun"])
        self.assertEqual(payload["variant_source"], "profile_variant")

    def test_list_templates_uses_audience_and_tone_metadata_when_bindings_are_missing(self) -> None:
        # spec 2026-07-27 v2, Beslut 1: rendered_prompt_text is gone (no more
        # server-side rendering), but audience_label/tone_hint are still
        # exposed as raw metadata for the client to use when it renders
        # locally -- that part of this test's coverage remains valid.
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog_area_index", return_value={}),
        ):
            mocked_prompts.return_value = [
                {
                    "id": "prompt-1",
                    "slug": "enkel_infografik",
                    "title": "Enkel infografik",
                    "prompt_text": "Skapa en {{ton}} stil för {{malgrupp}}.",
                    "audience_label": "medarbetare",
                    "tone_hint": "tydlig och vänlig",
                }
            ]

            payload = _list_templates_payload(["kommun"])

        template = payload["templates"][0]
        self.assertNotIn("rendered_prompt_text", template)
        self.assertEqual(template["audience_label"], "medarbetare")
        self.assertEqual(template["tone_hint"], "tydlig och vänlig")

    def test_list_package_prompts_fills_stable_identity_fields(self) -> None:
        with patch("server.mcp_server._catalog.list_published_package_prompts") as mocked_package_prompts:
            mocked_package_prompts.return_value = [
                {
                    "prompt_slug": "mejl",
                    "title": "Mejl",
                    "summary": "Skriv mejl",
                    "sort_order": 1,
                }
            ]

            payload = _list_package_prompts_payload("kommunikation", ["generell"])

        prompt = payload["prompts"][0]
        self.assertEqual(prompt["id"], "mejl")
        self.assertEqual(prompt["slug"], "mejl")
        self.assertEqual(prompt["area"], "kommunikation")

    def test_get_template_reports_the_selected_profile_variant(self) -> None:
        with (
            patch("server.mcp_server._catalog.list_published_prompts") as mocked_prompts,
            patch("server.mcp_server._catalog.get_published_prompt") as mocked_detail,
            patch("server.mcp_server._catalog_area_index", return_value={}),
        ):
            mocked_prompts.return_value = [
                {"id": "prompt-1", "slug": "mejl", "title": "Mejl"}
            ]
            mocked_detail.return_value = [
                {
                    "id": "prompt-1",
                    "slug": "mejl",
                    "title": "Mejl",
                    "context_key": "skola",
                    "prompt_text": "Skriv för {{malgrupp}}.",
                    "parameter_schema": {
                        "fields": [{"key": "malgrupp", "source": "global"}]
                    },
                    "default_bindings": {"malgrupp": "vårdnadshavare"},
                },
                {
                    "id": "prompt-1",
                    "slug": "mejl",
                    "title": "Mejl",
                    "context_key": "generell",
                    "prompt_text": "Skriv för {{malgrupp}}.",
                    "parameter_schema": {
                        "fields": [{"key": "malgrupp", "source": "global"}]
                    },
                    "default_bindings": {"malgrupp": "invånare"},
                },
            ]

            payload = _get_template_payload("prompt-1", ["kommun", "skola"])

        self.assertEqual(payload["requested_context_keys"], ["kommun", "skola"])
        self.assertEqual(payload["matched_context_keys"], ["skola"])
        self.assertEqual(payload["variant_source"], "profile_variant")
        self.assertEqual(payload["template"]["context_key"], "skola")

    def test_get_package_reports_fallback_when_no_profile_variant_matches(self) -> None:
        with patch("server.mcp_server._catalog.get_published_package") as mocked_package:
            mocked_package.return_value = [
                {
                    "id": "package-1",
                    "slug": "kommunikation",
                    "context_key": "generell",
                    "title": "Kommunikation",
                }
            ]

            payload = _get_package_payload("kommunikation", ["privat"])

        self.assertEqual(payload["requested_context_keys"], ["privat"])
        self.assertEqual(payload["matched_context_keys"], [])
        self.assertEqual(payload["variant_source"], "fallback_generell")

    def test_list_package_prompts_reports_context_matches(self) -> None:
        with patch("server.mcp_server._catalog.list_published_package_prompts") as mocked_prompts:
            mocked_prompts.return_value = [
                {
                    "prompt_id": "prompt-1",
                    "prompt_slug": "mejl",
                    "title": "Mejl",
                    "context_key": "skola",
                }
            ]

            payload = _list_package_prompts_payload(
                "kommunikation", ["kommun", "skola"]
            )

        self.assertEqual(payload["requested_context_keys"], ["kommun", "skola"])
        self.assertEqual(payload["matched_context_keys"], ["skola"])
        self.assertEqual(payload["variant_source"], "profile_variant")


if __name__ == "__main__":
    unittest.main()
