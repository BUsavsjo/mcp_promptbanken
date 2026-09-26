"""MCP Apps-widgets för den öppna katalogen (Promptbanken Open 1.3.0).

Widgetarna är självständiga HTML-filer i mcp-server/widgets/. Bryggan och
bas-CSS:en bakas in vid läsning så att varje resurs är en enda fil utan
externa laddningar -- CSP:n kan då vara tom.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
_WIDGET_DIR = Path(__file__).resolve().parents[1] / "widgets"
_URI_PREFIX = "ui://promptbanken/"

WIDGETS: dict[str, dict[str, str]] = {
    "package-cards": {
        "file": "package-cards.html",
        "name": "Promptbanken – paketkort",
        "description": "Kort för rekommenderade eller listade promptpaket med filter för arbetsflöden och samlingar.",
    },
}

TOOL_WIDGETS: dict[str, str] = {
    "recommend_packages": "package-cards",
    "list_packages": "package-cards",
}


def widget_uri(name: str) -> str:
    return f"{_URI_PREFIX}{name}.html"


def _widget_domain() -> str:
    return os.getenv("PROMPTBANKEN_WIDGET_DOMAIN", "https://mcp.promptbanken.se")


@lru_cache(maxsize=None)
def render_widget(name: str) -> str:
    html = (_WIDGET_DIR / WIDGETS[name]["file"]).read_text(encoding="utf-8")
    base_css = (_WIDGET_DIR / "base.css").read_text(encoding="utf-8")
    bridge = (_WIDGET_DIR / "bridge.js").read_text(encoding="utf-8")
    return html.replace("/*PB_BASE_CSS*/", base_css).replace("/*PB_BRIDGE_JS*/", bridge)


def _resource_meta() -> dict[str, Any]:
    return {
        "ui": {
            "prefersBorder": True,
            "domain": _widget_domain(),
            "csp": {"connectDomains": [], "resourceDomains": [], "frameDomains": []},
        }
    }


def list_widget_resources() -> list[dict[str, Any]]:
    return [
        {
            "uri": widget_uri(name),
            "name": widget["name"],
            "description": widget["description"],
            "mimeType": WIDGET_MIME_TYPE,
            "_meta": _resource_meta(),
        }
        for name, widget in WIDGETS.items()
    ]


def read_widget_resource(uri: str) -> dict[str, Any] | None:
    for name in WIDGETS:
        if widget_uri(name) == uri:
            return {
                "contents": [
                    {"uri": uri, "mimeType": WIDGET_MIME_TYPE, "text": render_widget(name), "_meta": _resource_meta()}
                ]
            }
    return None


def tool_ui_meta(tool_name: str) -> dict[str, Any]:
    name = TOOL_WIDGETS.get(tool_name)
    return {"ui": {"resourceUri": widget_uri(name)}} if name else {}
