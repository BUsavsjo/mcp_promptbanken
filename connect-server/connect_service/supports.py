"""Promptbankens gemensamma metodstöd, levererade oförändrade från sin källa.

Innehållet genereras av `scripts/sync_supports.py` från `promptbanken/agent-skills`.
Connect ändrar aldrig metodtexten; anpassningar läggs i ett separat personligt
lager (se `personal.py`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

SUPPORTS_DIR = Path(__file__).resolve().parent / "supports"

# Skillsen är skrivna för Promptbanken Open. Connect har motsvarande verktyg
# under andra namn, så modellen får en översättning i stället för att källtexten
# skrivs om.
OPEN_TOOL_MAPPING = {
    "search_templates": "Connect söker inte i katalogen. Använd get_open_item (kind: prompt) med slug eller id ur metodens references/promptbanken.md; finns ingen passande mall, fortsätt med metoden utan.",
    "list_packages": "Connect söker inte i katalogen. Använd get_open_item (kind: package) med paketets slug ur metodens references/promptbanken.md.",
    "get_template": "get_open_item (kind: prompt, id eller slug)",
    "get_package": "get_open_item (kind: package, slug)",
    "list_package_prompts": "get_open_item (kind: package, slug) – svaret innehåller stegens prompt_text i ordning",
}


class SupportCatalogError(Exception):
    """Katalogen är skadad eller inte synkad."""


class SupportCatalog:
    def __init__(self, directory: Path = SUPPORTS_DIR) -> None:
        self._directory = directory
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            raise SupportCatalogError("Stödkatalogen saknas. Kör scripts/sync_supports.py.")
        self._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._supports = {entry["id"]: entry for entry in self._manifest["supports"]}
        self._verify()

    def _verify(self) -> None:
        for support in self._supports.values():
            for entry in support["files"]:
                data = (self._directory / support["id"] / entry["path"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise SupportCatalogError(f"{support['id']}/{entry['path']} avviker från manifestet.")

    @property
    def source_commit(self) -> str:
        return str(self._manifest["source_commit"])

    def ids(self) -> list[str]:
        return list(self._supports)

    def has(self, support_id: str) -> bool:
        return support_id in self._supports

    def name(self, support_id: str) -> str:
        return str(self._supports[support_id]["name"])

    def index(self) -> list[dict[str, object]]:
        return [
            {
                "id": support["id"],
                "name": support["name"],
                "use_when": support["use_when"],
                "not_when": support["not_when"],
                "version": support["version"],
            }
            for support in self._supports.values()
        ]

    def resource_paths(self, support_id: str) -> list[str]:
        return [entry["path"] for entry in self._supports[support_id]["files"] if entry["path"] != "SKILL.md"]

    def read(self, support_id: str, path: str = "SKILL.md") -> str | None:
        support = self._supports.get(support_id)
        if support is None or path not in {entry["path"] for entry in support["files"]}:
            return None
        return (self._directory / support_id / path).read_text(encoding="utf-8")

    def support_payload(self, support_id: str) -> Mapping[str, object] | None:
        support = self._supports.get(support_id)
        if support is None:
            return None
        requires = support["requires"]
        dependencies: dict[str, object] = {
            "resources": [
                {"path": entry["path"], "bytes": entry["bytes"]}
                for entry in support["files"]
                if entry["path"] != "SKILL.md"
            ],
            "how_to_read_resources": "Hämta en resurs med get_support(id, resource: \"<path>\") när arbetsgången hänvisar till den.",
        }
        if requires["open_catalog_tools"]:
            dependencies["tool_mapping"] = {
                name: OPEN_TOOL_MAPPING[name] for name in requires["open_catalog_tools"]
            }
        client_capabilities = []
        if requires["code_execution"]:
            client_capabilities.append(
                "Kodkörning behövs för skripten under scripts/. Saknas den: följ metodens manuella alternativ."
            )
        if requires["other_skills"]:
            client_capabilities.append(
                "Hänvisar till andra skills: " + ", ".join(requires["other_skills"])
                + ". Finns de inte i klienten: beskriv resultatet i text i stället."
            )
        dependencies["client_capabilities"] = client_capabilities
        return {
            "id": support["id"],
            "name": support["name"],
            "version": support["version"],
            "source": f"{self._manifest['source']}@{self.source_commit[:12]}",
            "instructions": self.read(support_id),
            "dependencies": dependencies,
        }
