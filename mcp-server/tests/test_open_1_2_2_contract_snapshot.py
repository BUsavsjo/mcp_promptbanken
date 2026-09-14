"""Release-gate: den publika tool-ytan måste vara identisk med den granskade
Promptbanken Open 1.2.2-submissionen.

Snapshoten i contracts/promptbanken-open-1.2.2.tools.json är det som skickades
till OpenAI. Varje avvikelse i namn, beskrivning, input-/output-schema, enum,
annotations eller _meta gör submissionen materiellt annorlunda och kan trigga
en ny review. Ett rött test här betyder: ändringen kräver ett uttryckligt
versionsbeslut, inte en uppdaterad snapshot.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import _tool_definitions_for_profile

_SNAPSHOT = Path(__file__).resolve().parents[1] / "contracts" / "promptbanken-open-1.2.2.tools.json"


class Open122ContractSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
        cls.version = snapshot["version"]
        cls.reviewed = {tool["name"]: tool for tool in snapshot["tools"]}
        cls.served = {tool["name"]: tool for tool in _tool_definitions_for_profile("public")}

    def test_snapshot_is_the_reviewed_version(self) -> None:
        self.assertEqual(self.version, "1.2.2")

    def test_public_tool_names_match_the_review(self) -> None:
        self.assertEqual(set(self.served), set(self.reviewed))

    def test_every_public_tool_is_identical_to_the_review(self) -> None:
        for name, reviewed in self.reviewed.items():
            served = self.served.get(name, {})
            for key in sorted(set(reviewed) | set(served)):
                with self.subTest(tool=name, field=key):
                    self.assertEqual(
                        served.get(key),
                        reviewed.get(key),
                        f"{name}.{key} avviker från 1.2.2-submissionen",
                    )


if __name__ == "__main__":
    unittest.main()
