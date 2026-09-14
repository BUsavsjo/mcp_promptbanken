"""Routing-baseline mot en ögonblicksbild av den publika katalogen (2026-09-14).

Fixturen tests/fixtures/open_catalog_2026-09-14.json är hämtad från den öppna
connectorn: 147 mallar, 17 collections, 7 workflows, 4 fristående prompts.
Den innehåller bara publik metadata och paketmedlemskap -- ingen prompttext.

Frågorna är sådana en klient skickar efter anonymisering. "Routar till ett
workflow" betyder här att de tre översta träffarna är steg i workflowet och
att workflowet står för minst tre av de fem översta. Medlemskap räknas från
paketen, inte från mallens `area`: återanvända steg bär bara ett område, och
`behov-till-effekt` har bara två av sex steg med sin egen slug som area.

Fall markerade expectedFailure fungerar inte i dagens ranking. När rankingen
förbättras blir de "unexpected success" -- ta då bort markeringen.
"""
import json
import logging
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mcp_server import _search_templates_payload
from server.package_recommendations import _AREA_ROLES, recommend

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "open_catalog_2026-09-14.json"
_CATALOG = json.loads(_FIXTURE.read_text(encoding="utf-8"))
_WORKFLOWS = {p["slug"] for p in _CATALOG["packages"] if p["package_type"] == "workflow"}
_MEMBERSHIP: dict[str, set[str]] = {}
for _package in _CATALOG["packages"]:
    for _prompt_id in _package["prompt_ids"]:
        _MEMBERSHIP.setdefault(_prompt_id, set()).add(_package["slug"])


def _search(query: str, role: str = "") -> list[dict[str, object]]:
    with patch("server.mcp_server._list_templates_payload", return_value={"templates": _CATALOG["templates"]}):
        return _search_templates_payload(query=query, role=role, limit=8)["templates"]


def _workflow_counts(templates: list[dict[str, object]]) -> Counter[str]:
    return Counter(slug for t in templates for slug in _MEMBERSHIP.get(str(t["id"]), set()) if slug in _WORKFLOWS)


class RoutingBaselineCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls) -> None:
        logging.disable(logging.NOTSET)

    def assertRoutesToWorkflow(self, query: str, workflow: str, role: str = "") -> None:
        top = _search(query, role)
        titles = [t["title"] for t in top]
        for t in top[:3]:
            self.assertIn(workflow, _MEMBERSHIP.get(str(t["id"]), set()), f"topp 3 för {query!r}: {titles}")
        self.assertGreaterEqual(_workflow_counts(top[:5])[workflow], 3, f"topp 5 för {query!r}: {titles}")

    def assertRoutesToSinglePrompt(self, query: str, title_word: str) -> None:
        top = _search(query)
        titles = [t["title"] for t in top]
        self.assertTrue(top, f"inga träffar för {query!r}")
        self.assertIn(title_word, str(top[0]["title"]).lower(), f"topp för {query!r}: {titles}")
        self.assertFalse(_MEMBERSHIP.get(str(top[0]["id"]), set()) & _WORKFLOWS, f"topp för {query!r}: {titles}")
        self.assertLess(max(_workflow_counts(top[:5]).values(), default=0), 3, f"topp 5 för {query!r}: {titles}")


class FixtureTests(unittest.TestCase):
    def test_fixture_matches_the_tested_catalogue(self) -> None:
        member_ids = set(_MEMBERSHIP)
        all_ids = {t["id"] for t in _CATALOG["templates"]}
        types = Counter(p["package_type"] for p in _CATALOG["packages"])
        self.assertEqual(len(all_ids), 147)
        self.assertEqual(types, Counter({"collection": 17, "workflow": 7}))
        self.assertEqual(len(all_ids - member_ids), 4)


class KeywordQueryRoutingTests(RoutingBaselineCase):
    """Nyckelordstäta frågor, som testrapportens input-intents."""

    def test_research(self) -> None:
        self.assertRoutesToWorkflow("research omvärldsanalys flera aktuella källor jämförelse", "fran-fraga-till-researchunderlag")

    def test_research_with_a_role_that_uses_research(self) -> None:
        self.assertRoutesToWorkflow(
            "research omvärldsanalys flera aktuella källor jämförelse", "fran-fraga-till-researchunderlag", role="samordnare"
        )

    @unittest.expectedFailure
    def test_research_is_not_overtaken_by_an_unrelated_role(self) -> None:
        # Baseline: rollbonusen (+5) lyfter rektorns paket förbi researchstegen.
        self.assertRoutesToWorkflow(
            "research omvärldsanalys flera aktuella källor jämförelse", "fran-fraga-till-researchunderlag", role="rektor"
        )

    def test_product(self) -> None:
        self.assertRoutesToWorkflow("produktutveckling målgrupp produktlöfte MVP affärsmodell validering", "fran-behov-till-validerad-produkt")

    def test_data(self) -> None:
        self.assertRoutesToWorkflow("verksamhetsdata mönster avvikelser hypotes förbättringstest", "data-till-forbattring")

    def test_digital_solution(self) -> None:
        self.assertRoutesToWorkflow(
            "verksamhetsbehov digital lösning funktionskrav verifiering acceptanstest införande", "behov-till-verifierad-digital-losning"
        )

    @unittest.expectedFailure
    def test_business_development(self) -> None:
        # Baseline: plats 2 är ett krav-steg från digital lösning.
        self.assertRoutesToWorkflow("problem i arbetssättet nuläge målbild förändring effekt", "behov-till-effekt")

    def test_article(self) -> None:
        self.assertRoutesToWorkflow("artikelidé till publiceringsklar artikel", "fran-ide-till-artikel")

    def test_simple_email(self) -> None:
        self.assertRoutesToSinglePrompt("skriv om mejl tydligare", "mejl")


class NaturalQueryRoutingTests(RoutingBaselineCase):
    """Kortare, naturliga formuleringar från rapportens exempel."""

    def test_research(self) -> None:
        self.assertRoutesToWorkflow("research kommuner systemstöd skolval", "fran-fraga-till-researchunderlag")

    def test_research_with_role(self) -> None:
        self.assertRoutesToWorkflow("research kommuner systemstöd skolval", "fran-fraga-till-researchunderlag", role="samordnare")

    @unittest.expectedFailure
    def test_product(self) -> None:
        # Baseline: en enda träff -- "produktutveckla" matchar inga stegtitlar.
        self.assertRoutesToWorkflow("produktutveckla SaaS", "fran-behov-till-validerad-produkt")

    @unittest.expectedFailure
    def test_data(self) -> None:
        # Baseline: "Analysera argumentet" på plats 2 -- vanliga ord väger lika tungt som ovanliga.
        self.assertRoutesToWorkflow("analysera verksamhetsdata hitta vad vi bör testa", "data-till-forbattring")

    def test_digital_solution(self) -> None:
        self.assertRoutesToWorkflow("verksamhetsbehov till krav leverantörsvisning test införande", "behov-till-verifierad-digital-losning")

    @unittest.expectedFailure
    def test_business_development(self) -> None:
        # Baseline: tre träffar, inget steg ur behov-till-effekt.
        self.assertRoutesToWorkflow("återkommande supportproblem förbättra arbetssättet", "behov-till-effekt")

    def test_article(self) -> None:
        self.assertRoutesToWorkflow("skriva artikel från idé", "fran-ide-till-artikel")

    @unittest.expectedFailure
    def test_simple_email(self) -> None:
        # Baseline: "Kan jag använda AI till detta HR-arbete?" på plats 1 -- "detta" räknas som titelträff.
        self.assertRoutesToSinglePrompt("skriv om detta mejl", "mejl")


class RoleExplorationTests(unittest.TestCase):
    def test_exploratory_role_question_gets_role_packages(self) -> None:
        """'Vad finns för en samordnare?' -- här är rollrouting rätt beteende."""
        logging.disable(logging.CRITICAL)
        try:
            result = recommend("samordnare", _CATALOG["templates"])
        finally:
            logging.disable(logging.NOTSET)
        self.assertTrue(result["role_recognized"])
        self.assertTrue(result["packages"])

    def test_every_published_package_has_a_role_mapping(self) -> None:
        published = {p["slug"] for p in _CATALOG["packages"]}
        self.assertEqual(published - set(_AREA_ROLES), set())


if __name__ == "__main__":
    unittest.main()
