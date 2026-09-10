import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.package_recommendations import recommend, role_focus_areas


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

    def test_universal_packages_come_after_the_role_specific_ones(self) -> None:
        areas = recommend("lärare", _live_templates())["recommended_areas"]

        self.assertLess(areas.index("skola-undervisning-larare"), areas.index("vardagspaket"))
        self.assertLess(areas.index("visuellt"), areas.index("arbetsbank"))

    def test_every_published_area_is_accounted_for(self) -> None:
        """Ett nytt paket utan rollmappning ska synas här, inte i produktion."""
        from server.package_recommendations import _AREA_ROLES

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
