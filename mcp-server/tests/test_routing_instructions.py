"""Bootstrapen i get_client_routing_instructions styr hur klienten routar.

Routingtestet 2026-09-14 visade att "börja med recommend_packages(role) om
rollen är känd" gav rollpaket i stället för researchworkflowet, trots att
uppgiften var tydlig. Uppgiften ska routas först; rollen är för utforskande.

client_flow är fri text i 1.2.2-schemat, så innehållet får ändras utan ny
granskning -- men bara innehållet, inte fältens form.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server.mcp_server as server_mcp


class RoutingInstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.flow = server_mcp.get_client_routing_instructions()["client_flow"]
        cls.text = "\n".join(cls.flow)

    def _first_step_naming(self, tool: str) -> int:
        return next(index for index, step in enumerate(self.flow) if tool in step)

    def test_a_clear_task_is_searched_before_any_role_recommendation(self) -> None:
        self.assertIn("search_templates", self.flow[0])
        self.assertNotIn("recommend_packages", self.flow[0])
        self.assertLess(self._first_step_naming("search_templates"), self._first_step_naming("recommend_packages"))

    def test_role_recommendation_is_for_an_unclear_task(self) -> None:
        step = self.flow[self._first_step_naming("recommend_packages")]
        self.assertIn("oklar", step)

    def test_role_is_not_sent_with_a_clear_task(self) -> None:
        self.assertIn("Skicka inte role", self.flow[0])

    def test_scope_choice_covers_prompt_collection_workflow_and_superplan(self) -> None:
        for term in ("enskild mall", "collection", "workflow", "Superplanläge"):
            with self.subTest(term=term):
                self.assertIn(term, self.text)

    def test_workflows_are_found_as_whole_packages(self) -> None:
        self.assertIn("package_type='workflow'", self.text)
        self.assertIn("list_package_prompts", self.text)
        self.assertIn("samma workflow", self.text)

    def test_area_filter_is_not_the_way_to_newer_packages(self) -> None:
        step = self.flow[self._first_step_naming("area")]
        self.assertIn("schemat", step)


if __name__ == "__main__":
    unittest.main()
