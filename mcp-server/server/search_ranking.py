"""Rankingen bakom search_templates.

Uppgiften avgör ordningen. Ett ord väger mer ju färre mallar det finns i, så
"hitta" och "analysera" inte kör om "hypotes". Mallens eget innehåll väger
tyngst, paketens titel och sammanfattning lite. När flera steg ur samma
workflow tillsammans dominerar träffarna lyfts hela workflowet, eftersom det
då är ett bättre svar än ett enskilt steg. Rollen får lyfta inom jämna
träffar men aldrig köra om en tydligt starkare textträff.

Allt här ändrar bara ordningen och vilka mallar som räknas som träffar --
svaret har samma form som i den granskade 1.2.2-definitionen.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .skill_router import SkillRouter

# Funktionsord som folk skriver i en fråga men som inte säger något om
# uppgiften. "detta" gjorde att "Kan jag använda AI till detta HR-arbete?"
# toppade "skriv om detta mejl".
_SEARCH_STOPWORDS = SkillRouter.STOPWORDS | {
    "bor", "denna", "dessa", "detta", "din", "dina", "ditt", "min", "mina", "mitt",
    "oss", "sin", "sina", "sitt", "var", "vad", "vi", "vilka", "vilken", "vilket",
}

_STRONG = 2.0
_WEAK = 1.0
_PACKAGE = 0.5
# En stamträff ("produktutveckla" i "produktutveckling") är en gissning om
# böjning och väger mindre än det exakta ordet.
_STEM_FACTOR = 0.6
_MIN_STEM_TOKEN = 8
_MIN_STEM = 6
_STEM_TRIM = 3

# Kort nog att hela ordet krävs: "it" ska inte träffa "politik".
_MAX_WHOLE_WORD_TOKEN = 3

_CLUSTER_WINDOW = 10
_CLUSTER_MIN_STEPS = 3
_CLUSTER_MIN_SHARE = 0.4

_RECOGNIZED_ROLE_FACTOR = 1.25
_GUESSED_ROLE_FACTOR = 1.05


def _fold(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_fold(item) for item in value)
    if value is None:
        return ""
    return SkillRouter._normalize(str(value))


def query_terms(query: str) -> tuple[bool, list[str]]:
    """-> (frågan innehöll ord, de ord som bär betydelse)."""
    raw = re.findall(r"\w+", query.lower(), flags=re.UNICODE)
    terms: list[str] = []
    for word in raw:
        folded = SkillRouter._normalize(word)
        if len(folded) >= 2 and folded not in _SEARCH_STOPWORDS and folded not in terms:
            terms.append(folded)
    return bool(raw), terms


def _matcher(term: str) -> Any:
    if len(term) <= _MAX_WHOLE_WORD_TOKEN:
        pattern = re.compile(rf"\b{re.escape(term)}\b", flags=re.UNICODE)
        return lambda text: bool(pattern.search(text))
    return lambda text: term in text


def _stem(term: str) -> str | None:
    if len(term) < _MIN_STEM_TOKEN:
        return None
    return term[: max(_MIN_STEM, len(term) - _STEM_TRIM)]


def _fields(template: dict[str, Any], packages: list[dict[str, Any]]) -> tuple[str, str, str]:
    strong = f"{_fold(template.get('title'))} {_fold(template.get('tags'))}"
    weak = " ".join(
        _fold(template.get(key)) for key in ("syfte", "output_format", "area_label", "tone_hint")
    )
    package = " ".join(f"{_fold(p.get('title'))} {_fold(p.get('summary'))}" for p in packages)
    return strong, weak, package


def _level(term: str, fields: tuple[str, str, str]) -> float:
    exact = _matcher(term)
    stem = _stem(term)
    best = 0.0
    for text, weight in zip(fields, (_STRONG, _WEAK, _PACKAGE)):
        if exact(text):
            best = max(best, weight)
        elif stem and stem in text:
            best = max(best, weight * _STEM_FACTOR)
    return best


def _workflows(packages: list[dict[str, Any]]) -> set[str]:
    return {str(p.get("slug")) for p in packages if p.get("package_type") == "workflow"}


def _lift_dominant_workflow(
    scored: list[list[Any]], template_packages: dict[str, list[dict[str, Any]]]
) -> None:
    window = sorted(scored, key=lambda row: -row[0])[:_CLUSTER_WINDOW]
    total = sum(row[0] for row in window)
    if total <= 0:
        return

    mass: dict[str, float] = {}
    steps: dict[str, int] = {}
    workflows: set[str] = set()
    for score, template in window:
        packages = template_packages.get(str(template.get("id")), [])
        workflows |= _workflows(packages)
        for slug in {str(p.get("slug")) for p in packages}:
            mass[slug] = mass.get(slug, 0.0) + score
            steps[slug] = steps.get(slug, 0) + 1
    if not workflows:
        return

    # Bär en collection mer av svaret än workflowet ("Skarpare funktionskrav"
    # för kravfrågor) är specialistpaketet det bättre svaret.
    leader = max(workflows, key=lambda slug: mass[slug])
    if (
        steps[leader] < _CLUSTER_MIN_STEPS
        or mass[leader] < _CLUSTER_MIN_SHARE * total
        or mass[leader] < max(mass.values())
    ):
        return

    lift = window[0][0]
    for row in scored:
        if leader in _workflows(template_packages.get(str(row[1].get("id")), [])):
            row[0] += lift


def rank(
    templates: list[dict[str, Any]],
    query: str,
    *,
    area: str = "",
    risk_level: str = "",
    role_areas: set[str] | frozenset[str] = frozenset(),
    role_recognized: bool = False,
    template_packages: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Mallarna som matchar frågan, bäst först. Rollen filtrerar aldrig bort
    något; area och risk_level gör det."""
    had_words, terms = query_terms(query)
    if had_words and not terms:
        return []

    template_packages = template_packages or {}
    fields = {
        id(t): _fields(t, template_packages.get(str(t.get("id")), [])) for t in templates
    }

    weights: dict[str, float] = {}
    if terms:
        total = len(templates)
        for term in terms:
            found = sum(1 for t in templates if _level(term, fields[id(t)]) > 0)
            weights[term] = math.log((total + 1) / (found + 0.5))

    role_factor = _RECOGNIZED_ROLE_FACTOR if role_recognized else _GUESSED_ROLE_FACTOR

    scored: list[list[Any]] = []
    for template in templates:
        if area and template.get("area") != area:
            continue
        if risk_level and template.get("risk_level") != risk_level:
            continue
        if terms:
            score = sum(_level(term, fields[id(template)]) * weights[term] for term in terms)
            if score <= 0:
                continue
        else:
            score = 1.0 if template.get("area") in role_areas else 0.0
        scored.append([score, template])

    if terms:
        _lift_dominant_workflow(scored, template_packages)
        for row in scored:
            if row[1].get("area") in role_areas:
                row[0] *= role_factor

    return [template for _score, template in sorted(scored, key=lambda row: -row[0])]
