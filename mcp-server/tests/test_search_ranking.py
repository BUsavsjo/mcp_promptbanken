"""Rankingen bakom search_templates. Uppgiften avgör ordningen; rollen får
lyfta inom jämna träffar men aldrig köra om en tydligt starkare textträff.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.search_ranking import rank


def _t(template_id: str, title: str, *, area: str = "omrade", tags: list[str] | None = None, syfte: str = "") -> dict[str, object]:
    return {
        "id": template_id,
        "title": title,
        "area": area,
        "area_label": area,
        "tags": tags or [],
        "syfte": syfte,
        "output_format": "text",
        "risk_level": "low",
        "tone_hint": None,
    }


def _filler(count: int, title: str = "Övrigt") -> list[dict[str, object]]:
    return [_t(f"filler-{i}", f"{title} {i}") for i in range(count)]


def _ids(templates: list[dict[str, object]]) -> list[str]:
    return [str(t["id"]) for t in templates]


class TextMatchTests(unittest.TestCase):
    def test_accents_are_folded_on_both_sides(self) -> None:
        templates = [_t("a", "Beskriv läget", tags=["malbild"]), *_filler(5)]

        self.assertEqual(_ids(rank(templates, "målbild")), ["a"])
        self.assertEqual(_ids(rank(templates, "LAGET")), ["a"])

    def test_function_words_do_not_count(self) -> None:
        templates = [_t("detta", "Gör detta visuellt"), _t("mejl", "Svar på mejl"), *_filler(5)]

        self.assertEqual(_ids(rank(templates, "skriv om detta mejl")), ["mejl"])

    def test_a_query_of_only_function_words_finds_nothing(self) -> None:
        self.assertEqual(rank([_t("a", "Detta och vad")], "detta vad"), [])

    def test_rare_words_outweigh_common_ones(self) -> None:
        templates = [
            _t("common", "Hitta rätt ton"),
            _t("rare", "Formulera hypotes"),
            *[_t(f"hitta-{i}", f"Hitta sak {i}") for i in range(12)],
        ]

        self.assertEqual(_ids(rank(templates, "hitta hypotes"))[0], "rare")

    def test_an_inflected_word_matches_its_stem(self) -> None:
        templates = [_t("a", "Välj målgrupp", tags=["produktutveckling"]), *_filler(5)]

        self.assertEqual(_ids(rank(templates, "produktutveckla")), ["a"])

    def test_an_exact_word_beats_a_stem_match(self) -> None:
        templates = [_t("stem", "Om produktutveckling"), _t("exact", "Produktutveckla snabbt"), *_filler(5)]

        self.assertEqual(_ids(rank(templates, "produktutveckla"))[0], "exact")

    def test_short_words_match_whole_words_only(self) -> None:
        templates = [_t("it", "IT-stöd"), _t("politik", "Politik och kvalitet"), *_filler(5)]

        self.assertEqual(_ids(rank(templates, "it")), ["it"])

    def test_filters_narrow_without_changing_the_rest(self) -> None:
        templates = [_t("a", "Planera", area="x"), _t("b", "Planera", area="y")]

        self.assertEqual(_ids(rank(templates, "planera", area="y")), ["b"])


class PackageContextTests(unittest.TestCase):
    def test_package_text_finds_a_step_whose_own_text_does_not(self) -> None:
        templates = [_t("step", "Välj målgrupp"), *_filler(5)]
        packages = {"step": [{"slug": "produkt", "package_type": "workflow", "title": "Produkt", "summary": "Arbetsflöde för produktutveckling"}]}

        self.assertEqual(_ids(rank(templates, "produktutveckling", template_packages=packages)), ["step"])

    def test_own_text_outranks_package_text(self) -> None:
        templates = [_t("step", "Välj målgrupp"), _t("own", "Produktutveckling i korthet"), *_filler(5)]
        packages = {"step": [{"slug": "produkt", "package_type": "workflow", "title": "Produkt", "summary": "produktutveckling"}]}

        self.assertEqual(_ids(rank(templates, "produktutveckling", template_packages=packages))[0], "own")


class WorkflowClusterTests(unittest.TestCase):
    def _catalog(self) -> tuple[list[dict[str, object]], dict[str, list[dict[str, str]]]]:
        workflow = {"slug": "wf", "package_type": "workflow", "title": "Arbetsflöde", "summary": ""}
        templates = [
            _t("single", "Förändring och effekt i en mall"),
            _t("wf-1", "Utforma förändringen"),
            _t("wf-2", "Gör förändringen genomförbar"),
            _t("wf-3", "Följ upp effekten"),
            *_filler(10),
        ]
        return templates, {"wf-1": [workflow], "wf-2": [workflow], "wf-3": [workflow]}

    def test_several_steps_of_one_workflow_are_lifted_together(self) -> None:
        templates, packages = self._catalog()

        top = _ids(rank(templates, "förändring effekt", template_packages=packages))[:3]

        self.assertEqual(set(top), {"wf-1", "wf-2", "wf-3"})

    def test_fewer_than_three_steps_are_not_a_workflow_signal(self) -> None:
        templates, packages = self._catalog()
        del packages["wf-3"]

        self.assertEqual(_ids(rank(templates, "förändring effekt", template_packages=packages))[0], "single")

    def test_a_collection_that_carries_the_answer_keeps_it(self) -> None:
        """Submissionens testfall 4: specialistcollectionen ska leda även när
        ett workflow har flera steg bland träffarna."""
        templates, packages = self._catalog()
        collection = {"slug": "krav", "package_type": "collection", "title": "Krav", "summary": ""}
        # Workflowet står för drygt 40 procent av träffvikten, collectionen för resten.
        templates.append(_t("c-1", "Förändring och effekt i kravet"))
        packages.update({"c-1": [collection], "single": [collection]})

        top = _ids(rank(templates, "förändring effekt", template_packages=packages))

        self.assertNotIn(top[0], {"wf-1", "wf-2", "wf-3"})

    def test_collections_do_not_cluster(self) -> None:
        templates, packages = self._catalog()
        for memberships in packages.values():
            memberships[0] = dict(memberships[0], package_type="collection")

        self.assertEqual(_ids(rank(templates, "förändring effekt", template_packages=packages))[0], "single")


class RoleRankingTests(unittest.TestCase):
    def test_role_lifts_its_area_among_equal_matches(self) -> None:
        templates = [_t("other", "Planera", area="x"), _t("mine", "Planera", area="y")]

        self.assertEqual(_ids(rank(templates, "planera", role_areas={"y"}, role_recognized=True))[0], "mine")

    def test_role_never_overtakes_a_clearly_stronger_match(self) -> None:
        templates = [
            _t("task", "Samla underlag och värdera källor", area="research"),
            _t("role", "Planera underlag", area="skola"),
            *_filler(5),
        ]

        ranked = rank(templates, "underlag källor", role_areas={"skola"}, role_recognized=True)

        self.assertEqual(_ids(ranked)[0], "task")

    def test_role_without_a_query_orders_by_role(self) -> None:
        templates = [_t("other", "A", area="x"), _t("mine", "B", area="y")]

        self.assertEqual(_ids(rank(templates, "", role_areas={"y"}, role_recognized=True)), ["mine", "other"])

    def test_role_never_removes_templates(self) -> None:
        templates = [_t("other", "Planera", area="x"), _t("mine", "Planera", area="y")]

        self.assertEqual(len(rank(templates, "planera", role_areas={"y"}, role_recognized=True)), 2)


if __name__ == "__main__":
    unittest.main()
