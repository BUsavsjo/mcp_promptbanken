"""MCP Apps-widgets: register, resurser, verktygskoppling och säkerhetsregler."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import widgets
from server.mcp_server import _handle_mcp_message, _tool_definitions_for_profile

_WIDGET_DIR = Path(__file__).resolve().parents[1] / "widgets"
_FORBIDDEN = (
    "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
    "eval(", "new Function", "http://", "https://",
)
_MAX_BYTES = 30 * 1024


def _rpc(method: str, params: dict | None = None, profile: str = "public") -> dict:
    return _handle_mcp_message(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, "", profile
    )


class WidgetResourceTests(unittest.TestCase):
    def test_initialize_announces_resources(self) -> None:
        self.assertIn("resources", _rpc("initialize")["result"]["capabilities"])

    def test_resources_list_has_every_widget_with_mcp_app_metadata(self) -> None:
        resources = _rpc("resources/list")["result"]["resources"]
        self.assertEqual({r["uri"] for r in resources}, {widgets.widget_uri(n) for n in widgets.WIDGETS})
        for resource in resources:
            with self.subTest(uri=resource["uri"]):
                self.assertEqual(resource["mimeType"], "text/html;profile=mcp-app")
                ui = resource["_meta"]["ui"]
                self.assertTrue(ui["prefersBorder"])
                self.assertEqual(ui["domain"], "https://mcp.promptbanken.se")
                self.assertEqual(ui["csp"], {"connectDomains": [], "resourceDomains": [], "frameDomains": []})

    def test_resources_read_returns_rendered_html(self) -> None:
        for name in widgets.WIDGETS:
            with self.subTest(widget=name):
                content = _rpc("resources/read", {"uri": widgets.widget_uri(name)})["result"]["contents"][0]
                self.assertEqual(content["mimeType"], "text/html;profile=mcp-app")
                self.assertIn("window.PB", content["text"])
                self.assertNotIn("/*PB_BRIDGE_JS*/", content["text"])
                self.assertNotIn("/*PB_BASE_CSS*/", content["text"])

    def test_resources_are_served_in_the_key_profile_too(self) -> None:
        with patch("server.mcp_server._mcp_key_is_valid", return_value=True):
            resources = _rpc("resources/list", profile="key_authenticated")["result"]["resources"]
        self.assertTrue(resources)

    def test_unknown_resource_is_an_error(self) -> None:
        self.assertEqual(_rpc("resources/read", {"uri": "ui://promptbanken/finns-inte.html"})["error"]["code"], -32002)

    def test_domain_follows_the_environment(self) -> None:
        with patch.dict(os.environ, {"PROMPTBANKEN_WIDGET_DOMAIN": "https://mcp-dev.promptbanken.se"}):
            resource = widgets.list_widget_resources()[0]
        self.assertEqual(resource["_meta"]["ui"]["domain"], "https://mcp-dev.promptbanken.se")

    def test_stepper_is_linked_to_list_package_prompts(self) -> None:
        self.assertEqual(widgets.TOOL_WIDGETS["list_package_prompts"], "workflow-stepper")
        self.assertIn("workflow-stepper", widgets.WIDGETS)

    def test_template_view_is_linked_to_get_template(self) -> None:
        self.assertEqual(widgets.TOOL_WIDGETS["get_template"], "template-view")
        self.assertEqual(len(widgets.WIDGETS), 3)

    def test_tools_point_to_their_widget_and_keep_status_texts(self) -> None:
        tools = {t["name"]: t for t in _tool_definitions_for_profile("public")}
        for tool_name, widget in widgets.TOOL_WIDGETS.items():
            with self.subTest(tool=tool_name):
                meta = tools[tool_name]["_meta"]
                self.assertEqual(meta["ui"], {"resourceUri": widgets.widget_uri(widget)})
                self.assertIn("openai/toolInvocation/invoking", meta)
        for tool_name in ("search_templates", "health_check", "get_package", "list_templates"):
            self.assertNotIn("ui", tools[tool_name]["_meta"])


class WidgetSafetyTests(unittest.TestCase):
    def test_widget_sources_use_no_html_injection_eval_or_external_urls(self) -> None:
        sources = [p for p in _WIDGET_DIR.glob("*") if p.suffix in {".html", ".js", ".css"} and p.name != "dev-harness.html"]
        self.assertTrue(sources)
        for path in sources:
            text = path.read_text(encoding="utf-8")
            for token in _FORBIDDEN:
                with self.subTest(file=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_rendered_widgets_stay_small(self) -> None:
        for name in widgets.WIDGETS:
            with self.subTest(widget=name):
                self.assertLessEqual(len(widgets.render_widget(name).encode("utf-8")), _MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
