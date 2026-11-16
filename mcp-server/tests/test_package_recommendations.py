import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.package_recommendations import _AREA_ROLES, recommend, role_focus_areas


def _live_templates() -> list[dict[str, str]]:
    """Alla 20 publicerade paketslugs, som prod returnerar dem."""
    return [
        {"area": area, "area_label": label}
        for area, label in (
            ("anti-slop", "Anti-slop"),
            ("arbetsbank", "Egen AI-arbetsbank"),
            ("behov-till-effekt", "Från behov till effekt"),
            ("bemot-argument", "Bemöt argument"),
            ("beslutsberedning", "Tjänstemannastöd och beslutsberedning"),
            ("forandringsledning", "Förändringsledning och införande"),
            ("fran-ide-till-artikel", "Från idé till artikel"),
            ("hall-traden", "Håll tråden"),
            ("hr", "HR – tryggt AI-stöd i arbetsvardagen"),
            ("kommunikation", "Kommunikation och publicering"),
            ("ledarskap", "Ledarskap och styrning"),
            ("processer", "Verksamhetsutveckling och processer"),
            ("sag-emot-mig", "Säg emot mig"),
            ("skarpare-funktionskrav", "Skarpare funktionskrav – kravställning i upphandling"),
            ("skola-undervisning-larare", "Skola och undervisning – för lärare"),
            ("superplanlage", "Superplanläge"),
            ("supportarenden", "Supportärenden"),
            ("vardagspaket", "Vardagspaket"),
            ("visuellt", "Visuellt stöd och informationsbilder"),
            ("workshop-och-facilitering", "Workshop och facilitering"),
        )
    ]


def _templates() -> list[dict[str, str]]:
    return [
        {"area": area, "area_label": area}
        for area in (
            "kommunikation",
            "forandringsledning",
            "processer",
            "beslutsberedning",
            "visuellt",
            "ledarskap",
            "arbetsbank",
            "behov-till-effekt",
        )
    ]


class PackageRecommendationTests(unittest.TestCase):
    def test_rektor_is_recognized_as_a_school_leadership_role(self) -> None:
        payload = recommend("rektor", _templates())

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["matched_role"], "rektor")
        self.assertEqual(
            payload["recommended_areas"],
            [
                "ledarskap",
                "kommunikation",
                "processer",
                "forandringsledning",
                "beslutsberedning",
                "arbetsbank",
            ],
        )

    def test_verksamhetsutvecklare_leads_with_the_behov_till_effekt_workflow(self) -> None:
        payload = recommend("verksamhetsutvecklare", _templates())

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["matched_role"], "verksamhetsutvecklare")
        self.assertEqual(
            payload["recommended_areas"],
            [
                "behov-till-effekt",
                "processer",
                "forandringsledning",
                "arbetsbank",
            ],
        )

    def test_compound_it_samordnare_includes_communication(self) -> None:
        payload = recommend("IT-samordnare barn och utbildning", _templates())

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["matched_role"], "samordnare")
        self.assertEqual(payload["role_match_source"], "compound")
        self.assertEqual(
            payload["recommended_areas"],
            [
                "forandringsledning",
                "processer",
                "behov-till-effekt",
                "ledarskap",
                "kommunikation",
                "arbetsbank",
            ],
        )


class RoleVocabularyTests(unittest.TestCase):
    """Rollerna användarna faktiskt skriver, mot hela den publicerade katalogen."""

    def test_larare_is_recognized_and_leads_with_the_school_package(self) -> None:
        payload = recommend("lärare", _live_templates())

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["matched_role"], "larare")
        self.assertEqual(payload["role_match_source"], "exact")
        self.assertEqual(payload["recommended_areas"][0], "skola-undervisning-larare")

    def test_hr_is_recognized_and_leads_with_the_hr_package(self) -> None:
        payload = recommend("HR", _live_templates())

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["matched_role"], "hr")
        self.assertEqual(payload["recommended_areas"][0], "hr")

    def test_single_word_compounds_match_their_head_noun(self) -> None:
        for role, expected in (
            ("personalchef", "hr"),
            ("förskollärare", "larare"),
            ("enhetschef", "chef"),
            ("biståndshandläggare", "handlaggare"),
        ):
            with self.subTest(role=role):
                payload = recommend(role, _live_templates())
                self.assertTrue(payload["role_recognized"])
                self.assertEqual(payload["matched_role"], expected)
                self.assertEqual(payload["role_match_source"], "compound")

    def test_socialsekreterare_is_a_caseworker_not_a_minute_taker(self) -> None:
        payload = recommend("socialsekreterare", _live_templates())

        self.assertEqual(payload["matched_role"], "handlaggare")

    def test_a_recognized_role_gets_a_short_list_not_half_the_catalog(self) -> None:
        for role in ("HR", "lärare", "rektor", "chef"):
            with self.subTest(role=role):
                areas = recommend(role, _live_templates())["recommended_areas"]
                universal = [a for a in areas if _AREA_ROLES.get(a) is None]
                self.assertLessEqual(len(universal), 2, "universella paket ska inte dränka rollens egna")

    def test_the_universal_packages_offered_are_the_two_broadest(self) -> None:
        areas = recommend("HR", _live_templates())["recommended_areas"]

        self.assertEqual(areas, ["hr", "vardagspaket", "arbetsbank"])

    def test_universal_packages_come_after_the_role_specific_ones(self) -> None:
        areas = recommend("lärare", _live_templates())["recommended_areas"]

        self.assertLess(areas.index("skola-undervisning-larare"), areas.index("vardagspaket"))
        self.assertLess(areas.index("visuellt"), areas.index("arbetsbank"))

    def test_every_published_area_is_accounted_for(self) -> None:
        """Ett nytt paket utan rollmappning ska synas här, inte i produktion."""
        published = {t["area"] for t in _live_templates()}
        self.assertEqual(published - set(_AREA_ROLES), set())


class UnknownRoleRankingTests(unittest.TestCase):
    """Okända roller behåller alla paket -- men i vettig ordning."""

    def test_unknown_role_still_returns_every_package(self) -> None:
        payload = recommend("bibliotekarie", _live_templates())

        self.assertFalse(payload["role_recognized"])
        self.assertIsNone(payload["matched_role"])
        self.assertEqual(len(payload["packages"]), 20)

    def test_unknown_role_is_ranked_by_lexical_overlap(self) -> None:
        payload = recommend("upphandlingsjurist", _live_templates())

        self.assertFalse(payload["role_recognized"])
        self.assertEqual(payload["recommended_areas"][0], "skarpare-funktionskrav")

    def test_unknown_role_without_any_overlap_keeps_catalog_order(self) -> None:
        live = _live_templates()
        payload = recommend("bibliotekarie", live)

        self.assertEqual(payload["recommended_areas"], [t["area"] for t in live])


class NewlyPublishedPackageTests(unittest.TestCase):
    """Kartan är handskriven. Ett paket som publiceras i morgon får inte
    försvinna ur rekommendationerna bara för att ingen hunnit koda om den."""

    def _live_plus(self, area: str, label: str) -> list[dict[str, str]]:
        return _live_templates() + [{"area": area, "area_label": label}]

    def test_unmapped_package_reaches_the_role_its_name_points_at(self) -> None:
        templates = self._live_plus("socialtjanst-handlaggning", "Socialtjänst – handläggning")

        areas = recommend("handläggare", templates)["recommended_areas"]

        self.assertIn("socialtjanst-handlaggning", areas)

    def test_unmapped_package_is_logged_so_the_gap_can_be_closed(self) -> None:
        import server.package_recommendations as module

        module._UNMAPPED_AREAS_LOGGED.clear()
        templates = self._live_plus("nytt-paket", "Ett alldeles nytt paket")

        with self.assertLogs("server.package_recommendations", level="WARNING") as captured:
            recommend("chef", templates)

        self.assertIn("nytt-paket", " ".join(captured.output))

    def test_unmapped_package_still_reaches_unknown_roles(self) -> None:
        templates = self._live_plus("nytt-paket", "Ett alldeles nytt paket")

        areas = recommend("bibliotekarie", templates)["recommended_areas"]

        self.assertIn("nytt-paket", areas)


def _catalog_with_workflows() -> list[dict[str, str]]:
    """Katalogen 2026-09-14: de 20 ovan plus de fyra nyaste workflowen."""
    return _live_templates() + [
        {"area": area, "area_label": label}
        for area, label in (
            ("behov-till-verifierad-digital-losning", "Från behov till verifierad digital lösning"),
            ("data-till-forbattring", "Från data till förbättring"),
            ("fran-behov-till-validerad-produkt", "Från behov till validerad produkt"),
            ("fran-fraga-till-researchunderlag", "Från fråga till researchunderlag"),
        )
    ]


class WorkflowRoleTests(unittest.TestCase):
    """Banken är bred: varje workflow ska nå de yrkesroller som har nytta av det."""

    def _areas(self, role: str) -> list[str]:
        return recommend(role, _catalog_with_workflows())["recommended_areas"]

    def test_every_workflow_reaches_several_roles(self) -> None:
        for workflow, roles in (
            ("fran-fraga-till-researchunderlag", ("utredare", "analytiker", "samordnare", "handläggare", "kommunikatör")),
            ("data-till-forbattring", ("analytiker", "verksamhetsutvecklare", "utredare", "chef")),
            ("behov-till-verifierad-digital-losning", ("verksamhetsutvecklare", "upphandlare", "systemförvaltare")),
            ("fran-behov-till-validerad-produkt", ("verksamhetsutvecklare", "produktägare", "entreprenör")),
            ("behov-till-effekt", ("verksamhetsutvecklare", "utredare", "samordnare", "chef", "projektledare")),
        ):
            for role in roles:
                with self.subTest(workflow=workflow, role=role):
                    self.assertIn(workflow, self._areas(role))

    def test_new_professional_roles_are_recognized(self) -> None:
        for role, expected in (
            ("projektledare", "projektledare"),
            ("systemförvaltare", "systemforvaltare"),
            ("produktägare", "produktagare"),
            ("entreprenör", "entreprenor"),
            ("statistiker", "analytiker"),
            ("controller", "analytiker"),
            ("forskare", "utredare"),
            ("kvalitetsutvecklare", "verksamhetsutvecklare"),
            ("produktchef", "produktagare"),
            ("företagare", "entreprenor"),
            ("projektchef", "projektledare"),
        ):
            with self.subTest(role=role):
                payload = recommend(role, _catalog_with_workflows())
                self.assertTrue(payload["role_recognized"])
                self.assertEqual(payload["matched_role"], expected)

    def test_chef_still_leads_with_the_packages_in_the_reviewed_test_case(self) -> None:
        """chatgpt-app-submission.json, testfall 1: förändringsledning,
        beslutsberedning och ledarskap för rollen chef."""
        self.assertEqual(self._areas("chef")[:3], ["forandringsledning", "beslutsberedning", "ledarskap"])

    def test_kommunikator_still_leads_with_kommunikation(self) -> None:
        self.assertEqual(self._areas("kommunikatör")[0], "kommunikation")

    def test_investigators_and_analysts_meet_research_and_data_early(self) -> None:
        self.assertEqual(self._areas("utredare")[:2], ["beslutsberedning", "fran-fraga-till-researchunderlag"])
        self.assertEqual(self._areas("analytiker")[:2], ["data-till-forbattring", "fran-fraga-till-researchunderlag"])

    def test_projektledare_leads_with_the_change_workflow(self) -> None:
        self.assertEqual(self._areas("projektledare")[0], "behov-till-effekt")

    def test_samordnare_gets_research(self) -> None:
        self.assertIn("fran-fraga-till-researchunderlag", self._areas("samordnare"))


class AudienceRoleTests(unittest.TestCase):
    """Roller från paketets målgrupp ("Vem det är för"), som sätts med
    admin-MCP. Nya paket och nya yrkesroller ska nå rätt person utan kodändring."""

    def _new_package(self, area: str = "arkiv-och-diarium", label: str = "Arkiv och diarium") -> list[dict[str, str]]:
        return _catalog_with_workflows() + [{"area": area, "area_label": label}]

    def test_a_role_only_named_in_the_audience_is_recognized(self) -> None:
        payload = recommend(
            "bibliotekarie", self._new_package(), audiences={"arkiv-och-diarium": "För bibliotekarier och arkivarier"}
        )

        self.assertTrue(payload["role_recognized"])
        self.assertEqual(payload["recommended_areas"][0], "arkiv-och-diarium")

    def test_plural_audience_words_reach_the_singular_role(self) -> None:
        audiences = {"arkiv-och-diarium": "För chefer, HR-specialister och registratorer"}
        for role in ("chef", "HR", "registrator"):
            with self.subTest(role=role):
                self.assertIn("arkiv-och-diarium", recommend(role, self._new_package(), audiences=audiences)["recommended_areas"])

    def test_audience_adds_roles_and_never_removes_mapped_ones(self) -> None:
        audiences = {"fran-fraga-till-researchunderlag": "För bibliotekarier"}

        self.assertIn("fran-fraga-till-researchunderlag", recommend("bibliotekarie", _catalog_with_workflows(), audiences=audiences)["recommended_areas"])
        self.assertIn("fran-fraga-till-researchunderlag", recommend("utredare", _catalog_with_workflows(), audiences=audiences)["recommended_areas"])

    def test_universal_packages_stay_universal(self) -> None:
        audiences = {"vardagspaket": "För bibliotekarier"}

        payload = recommend("bibliotekarie", _catalog_with_workflows(), audiences=audiences)

        self.assertFalse(payload["role_recognized"])

    def test_filler_words_in_the_audience_are_not_roles(self) -> None:
        audiences = {"arkiv-och-diarium": "För alla som arbetar med dokument i verksamheten"}
        for role in ("alla", "arbetar"):
            with self.subTest(role=role):
                self.assertFalse(recommend(role, self._new_package(), audiences=audiences)["role_recognized"])

    def test_package_with_an_audience_is_not_reported_as_unmapped(self) -> None:
        import server.package_recommendations as module

        module._UNMAPPED_AREAS_LOGGED.clear()
        with self.assertNoLogs("server.package_recommendations", level="WARNING"):
            recommend("chef", self._new_package(), audiences={"arkiv-och-diarium": "För chefer"})

    def test_role_focus_areas_follow_the_audience(self) -> None:
        recognized, areas = role_focus_areas(
            "bibliotekarie", self._new_package(), audiences={"arkiv-och-diarium": "För bibliotekarier"}
        )

        self.assertTrue(recognized)
        self.assertEqual(areas, ["arkiv-och-diarium"])


class RoleFocusAreaTests(unittest.TestCase):
    """Det search_templates rankar på."""

    def test_recognized_role_focuses_on_its_own_areas(self) -> None:
        recognized, areas = role_focus_areas("lärare", _live_templates())

        self.assertTrue(recognized)
        self.assertIn("skola-undervisning-larare", areas)
        self.assertNotIn("vardagspaket", areas)

    def test_unrecognized_role_focuses_on_lexical_hits_only(self) -> None:
        recognized, areas = role_focus_areas("upphandlingsjurist", _live_templates())

        self.assertFalse(recognized)
        self.assertEqual(areas, ["skarpare-funktionskrav"])

    def test_role_without_signal_gets_no_focus_at_all(self) -> None:
        recognized, areas = role_focus_areas("bibliotekarie", _live_templates())

        self.assertFalse(recognized)
        self.assertEqual(areas, [])


if __name__ == "__main__":
    unittest.main()
