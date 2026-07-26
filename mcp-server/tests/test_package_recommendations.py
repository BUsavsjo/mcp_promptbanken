import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.package_recommendations import recommend


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


if __name__ == "__main__":
    unittest.main()
