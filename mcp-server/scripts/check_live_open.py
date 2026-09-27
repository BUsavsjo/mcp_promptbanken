"""Livekontroll av Promptbanken Open mot en körande server.

    .venv/Scripts/python.exe scripts/check_live_open.py https://mcp-dev.promptbanken.se/mcp
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.mcp_server import SERVICE_VERSION  # noqa: E402

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _call(client: httpx.Client, url: str, method: str, params: dict | None = None) -> dict:
    response = client.post(url, headers=_HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    response.raise_for_status()
    body = response.text.strip()
    if not body.startswith("{"):
        body = next(line[5:].strip() for line in body.splitlines() if line.startswith("data:"))
    return json.loads(body)


def main(url: str) -> None:
    failures: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(("OK   " if ok else "FAIL ") + label)
        if not ok:
            failures.append(label)

    def safe(label: str, fn) -> object:
        """Run fn(); on any exception, record FAIL for label and return None."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - a failing check must never crash the script
            check(label, False)
            print(f"     ({exc!r})")
            return None

    contract = json.loads((ROOT / "contracts" / f"promptbanken-open-{SERVICE_VERSION}.tools.json").read_text(encoding="utf-8"))
    with httpx.Client(timeout=30) as client:
        def tool(name: str, arguments: dict) -> dict:
            return _call(client, url, "tools/call", {"name": name, "arguments": arguments})["result"]["structuredContent"]

        init = safe("initialize svarar", lambda: _call(client, url, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "check_live_open", "version": "1"}})["result"])
        if init is not None:
            check(f"serverversion {SERVICE_VERSION}", init.get("serverInfo", {}).get("version") == SERVICE_VERSION)
            check("resources annonseras", "resources" in init.get("capabilities", {}))

        tools_list = safe("tools/list svarar", lambda: _call(client, url, "tools/list")["result"]["tools"])
        served = {t["name"]: t for t in tools_list} if tools_list is not None else {}
        expected = {t["name"]: t for t in contract["tools"]}
        if tools_list is not None:
            check("verktygsnamn = kontrakt", set(served) == set(expected))
            for name, definition in expected.items():
                check(f"{name} = kontrakt", served.get(name) == definition)

        resources = safe("resources/list svarar", lambda: _call(client, url, "resources/list")["result"]["resources"])
        if resources is not None:
            check("tre widgetresurser", len(resources) == 3)
            for resource in resources:
                content = safe(f"{resource['uri']} läsbar", lambda resource=resource: _call(client, url, "resources/read", {"uri": resource["uri"]})["result"]["contents"][0])
                if content is not None:
                    check(f"{resource['uri']} läsbar", content.get("mimeType") == "text/html;profile=mcp-app" and "window.PB" in content.get("text", ""))

        packages = safe("list_packages svarar", lambda: tool("list_packages", {})["packages"])
        if packages is not None:
            check("katalogen har paket", len(packages) > 0)
        else:
            packages = []

        search_result = safe("search_templates svarar", lambda: tool("search_templates", {"query": "zzzz-no-such-template-987654321"}))
        if search_result is not None:
            check("nonsenssökning ger 0 träffar", search_result.get("total_matches") == 0)

        unknown_pkg = safe("list_package_prompts (okänt paket) svarar", lambda: tool("list_package_prompts", {"package_slug": "finns-inte-xyz"}))
        if unknown_pkg is not None:
            check("okänt paket ger package_not_found", unknown_pkg.get("code") == "package_not_found")

        chef = safe("recommend_packages (chef) svarar", lambda: tool("recommend_packages", {"role": "chef"}))
        if chef is not None:
            check("chef ger paket med titel som etikett", bool(chef.get("packages")) and all(p.get("title") and p.get("area_label") == p.get("title") for p in chef.get("packages", [])))

        unknown = safe("recommend_packages (okänd roll) svarar", lambda: tool("recommend_packages", {"role": "xyzzy-roll"}))
        if unknown is not None:
            check("okänd roll ger tom lista och förslag", unknown.get("packages") == [] and bool(unknown.get("suggestion")))

        workflow = next((p["slug"] for p in packages if p.get("package_type") == "workflow"), None)
        check("katalogen har ett arbetsflöde", workflow is not None)
        if workflow:
            steps = safe("list_package_prompts (arbetsflöde) svarar", lambda: tool("list_package_prompts", {"package_slug": workflow, "current_step": 1}))
            if steps is not None:
                check("stegsvaret har package och current_step", (steps.get("package") or {}).get("slug") == workflow and steps.get("current_step") == 1)

        if chef is not None:
            for package in chef.get("packages", [])[:3]:
                area = package.get("area")
                label = f"template_count stämmer för {area}"
                prompts = safe(label, lambda area=area: tool("list_package_prompts", {"package_slug": area})["prompts"])
                if prompts is not None:
                    check(label, package.get("template_count") == len(prompts))

        search_hit = safe("search_templates (mejl till invånare) svarar", lambda: tool("search_templates", {"query": "svara på mejl från invånare"}))
        if search_hit is not None:
            found = search_hit.get("templates") or []
            if found:
                template_id = found[0].get("id")
                template_result = safe("get_template (mejlträff) svarar", lambda: tool("get_template", {"template_id": template_id}))
                if template_result is not None:
                    package_list = (template_result.get("template") or {}).get("packages")
                    check(
                        "mallens packages är en icke-tom lista med slug",
                        isinstance(package_list, list) and bool(package_list) and all("slug" in p for p in package_list),
                    )
            else:
                check("mejlsökningen ger minst en träff", False)

        routing = safe("get_client_routing_instructions svarar", lambda: tool("get_client_routing_instructions", {}))
        if routing is not None:
            client_flow = routing.get("client_flow") or []
            check(
                "client_flow[0] börjar med 'Routing först'",
                bool(client_flow) and str(client_flow[0]).startswith("Routing först"),
            )

    print(f"\n{len(failures)} fel")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://mcp-dev.promptbanken.se/mcp")
