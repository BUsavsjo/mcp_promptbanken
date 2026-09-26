"""Skriv den publika verktygsytan till contracts/promptbanken-open-<version>.tools.json.

Kör efter varje avsiktlig kontraktsändring och granska diffen innan commit:
    .venv/Scripts/python.exe scripts/export_open_contract.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.mcp_server import SERVICE_VERSION, _tool_definitions_for_profile  # noqa: E402


def main() -> None:
    target = ROOT / "contracts" / f"promptbanken-open-{SERVICE_VERSION}.tools.json"
    payload = {
        "version": SERVICE_VERSION,
        "source": f"Promptbanken Open {SERVICE_VERSION} (utkast före OpenAI-inskickning)",
        "tools": _tool_definitions_for_profile("public"),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
