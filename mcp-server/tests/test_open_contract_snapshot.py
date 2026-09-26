"""Release-gate: den publika tool-ytan måste vara identisk med kontraktsfilen
för den version servern annonserar.

Under arbetet med en ny version genereras contracts/promptbanken-open-<version>
.tools.json om med scripts/export_open_contract.py och diffen granskas i varje
commit. När versionen är inskickad till OpenAI är filen fryst: ett rött test
betyder då att ändringen kräver ett nytt versionsbeslut, inte en ny snapshot.

contracts/promptbanken-open-1.2.2.tools.json behålls som historik över den
granskade 1.2.2-ytan.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import SERVICE_VERSION, _tool_definitions_for_profile

_CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


class OpenContractSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = _CONTRACTS / f"promptbanken-open-{SERVICE_VERSION}.tools.json"
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        cls.version = snapshot["version"]
        cls.reviewed = {tool["name"]: tool for tool in snapshot["tools"]}
        cls.served = {tool["name"]: tool for tool in _tool_definitions_for_profile("public")}

    def test_served_version_is_1_3_0(self) -> None:
        self.assertEqual(SERVICE_VERSION, "1.3.0")

    def test_snapshot_is_the_served_version(self) -> None:
        self.assertEqual(self.version, SERVICE_VERSION)

    def test_public_tool_names_match_the_contract(self) -> None:
        self.assertEqual(set(self.served), set(self.reviewed))

    def test_every_public_tool_is_identical_to_the_contract(self) -> None:
        for name, reviewed in self.reviewed.items():
            served = self.served.get(name, {})
            for key in sorted(set(reviewed) | set(served)):
                with self.subTest(tool=name, field=key):
                    self.assertEqual(
                        served.get(key),
                        reviewed.get(key),
                        f"{name}.{key} avviker från {self.version}-kontraktet",
                    )

    def test_reviewed_1_2_2_contract_is_kept_as_history(self) -> None:
        snapshot = json.loads(
            (_CONTRACTS / "promptbanken-open-1.2.2.tools.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["version"], "1.2.2")


if __name__ == "__main__":
    unittest.main()
