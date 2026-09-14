"""Routing-baseline mot en ögonblicksbild av den publika katalogen (2026-09-14).

Fixturen tests/fixtures/open_catalog_2026-09-14.json är hämtad från den öppna
connectorn: 147 mallar, 17 collections, 7 workflows, 4 fristående prompts.
Den innehåller bara publik metadata och paketmedlemskap -- ingen prompttext.

Frågorna är sådana en klient skickar efter anonymisering. "Routar till ett
workflow" betyder här att de tre översta träffarna är steg i workflowet och
att workflowet står för minst tre av de fem översta. Medlemskap räknas från
paketen, inte från mallens `area`: återanvända steg bär bara ett område, och
`behov-till-effekt` har bara två av sex steg med sin egen slug som area.

Fall markerade expectedFailure fungerar inte ännu. Blir de "unexpected
success" -- ta då bort markeringen. Sökningen ser samma paketmedlemskap som
servern i produktion.
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
_TEMPLATE_PACKAGES: dict[str, list[dict[str, object]]] = {}
for _package in _CATALOG["packages"]:
    for _prompt_id in _package["prompt_ids"]:
        _MEMBERSHIP.setdefault(_prompt_id, set()).add(_package["slug"])
        _TEMPLATE_PACKAGES.setdefault(_prompt_id, []).append(
            {k: _package[k] for k in ("slug", "package_type", "title", "summary")}
        )


def _search(query: str, role: str = "", limit: int = 8) -> list[dict[str, object]]:
    """Som servern i produktion: katalogen plus paketmedlemskapet."""
    with (
        patch("server.mcp_server._list_templates_payload", return_value={"templates": _CATALOG["templates"]}),
        patch("server.mcp_server._catalog_template_packages", return_value=_TEMPLATE_PACKAGES),
        patch("server.mcp_server._catalog_package_audiences", return_value={}),
    ):
        return _search_templates_payload(query=query, role=role, limit=limit)["templates"]


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
        self.assertEqual(len(all_ids), 159)
        self.assertEqual(types, Counter({"collection": 18, "workflow": 8}))
        self.assertEqual(len(all_ids - member_ids), 7)


class KeywordQueryRoutingTests(RoutingBaselineCase):
    """Nyckelordstäta frågor, som testrapportens input-intents."""

    def test_research(self) -> None:
        self.assertRoutesToWorkflow("research omvärldsanalys flera aktuella källor jämförelse", "fran-fraga-till-researchunderlag")

    def test_research_with_a_role_that_uses_research(self) -> None:
        self.assertRoutesToWorkflow(
            "research omvärldsanalys flera aktuella källor jämförelse", "fran-fraga-till-researchunderlag", role="samordnare"
        )

    def test_research_is_not_overtaken_by_an_unrelated_role(self) -> None:
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

    def test_business_development(self) -> None:
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

    def test_product(self) -> None:
        self.assertRoutesToWorkflow("produktutveckla SaaS", "fran-behov-till-validerad-produkt")

    def test_data(self) -> None:
        self.assertRoutesToWorkflow("analysera verksamhetsdata hitta vad vi bör testa", "data-till-forbattring")

    def test_digital_solution(self) -> None:
        self.assertRoutesToWorkflow("verksamhetsbehov till krav leverantörsvisning test införande", "behov-till-verifierad-digital-losning")

    def test_business_development(self) -> None:
        # Hittas via paketets sammanfattning ("förbättra arbetssätt och lösa
        # återkommande problem"), ändrad i katalogen 2026-09-14. Stegen delas med
        # andra workflows och saknar orden.
        self.assertRoutesToWorkflow("återkommande supportproblem förbättra arbetssättet", "behov-till-effekt")

    def test_article(self) -> None:
        self.assertRoutesToWorkflow("skriva artikel från idé", "fran-ide-till-artikel")

    def test_simple_email(self) -> None:
        self.assertRoutesToSinglePrompt("skriv om detta mejl", "mejl")


class SubmissionSearchCaseTests(RoutingBaselineCase):
    """Sökfallen i chatgpt-app-submission.json är publicerat beteende och får
    inte försämras av rankingändringar."""

    def test_case_0_information_mailing_about_a_school_change(self) -> None:
        top = _search("informationsutskick förändring skola")
        self.assertIn("📣 Skapa informationsutskick", [t["title"] for t in top[:5]])

    def test_case_4_system_requirements_to_functional_requirements(self) -> None:
        top = _search("göra om systemkrav till funktionskrav inför upphandling", limit=10)
        titles = [t["title"] for t in top]
        self.assertEqual(titles[0], "Gör om till funktionskrav", titles)
        for title in ("Slå ihop och förenkla krav", "SKA, mervärde eller användningsfall?", "Utmana våra krav"):
            with self.subTest(title=title):
                self.assertIn(title, titles)


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
