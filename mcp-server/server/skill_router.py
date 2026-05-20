from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .skill_repository import Skill, SkillRepository


@dataclass(frozen=True)
class SkillMatch:
    skill: Skill
    score: int
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "skill": self.skill.to_dict(),
            "score": self.score,
            "reasons": self.reasons,
        }


class SkillRouter:
    STOPWORDS = {
        "att",
        "av",
        "de",
        "den",
        "det",
        "du",
        "en",
        "ett",
        "for",
        "fran",
        "gor",
        "har",
        "hur",
        "i",
        "jag",
        "kan",
        "med",
        "och",
        "om",
        "pa",
        "ska",
        "skriv",
        "skriva",
        "som",
        "till",
        "var",
        "vara",
        "vi",
    }

    def __init__(self, repository: SkillRepository) -> None:
        self.repository = repository

    def route(self, task: str, role: str | None = None, audience: str | None = None, limit: int = 3) -> list[SkillMatch]:
        terms = self._terms(task)
        normalized_task = self._normalize(task)
        matches = [self._score(skill, terms, normalized_task, role, audience) for skill in self.repository.list_skills()]
        ranked = sorted(
            (match for match in matches if match.score > 0),
            key=lambda match: (match.score, self._specificity(match.skill, terms)),
            reverse=True,
        )
        return ranked[:limit] if ranked else self._fallback(limit)

    def _score(
        self,
        skill: Skill,
        terms: set[str],
        normalized_task: str,
        role: str | None,
        audience: str | None,
    ) -> SkillMatch:
        score = 0
        reasons: list[str] = []
        normalized_skill_id = self._normalize(skill.id)
        normalized_name = self._normalize(skill.name)

        if normalized_skill_id in terms:
            score += 30
            reasons.append(f"Matchar skill-id: {skill.id}")

        name_terms = self._terms(skill.name)
        name_overlap = terms & name_terms
        if name_overlap:
            name_score = len(name_overlap) * 6
            if name_terms and len(name_overlap) / len(name_terms) >= 0.5:
                name_score += 20
                reasons.append(f"Matchar skillnamn: {skill.name}")
            else:
                reasons.append(f"Matchar ord i skillnamn: {', '.join(sorted(name_overlap)[:5])}")
            score += name_score

        if normalized_name and normalized_name in normalized_task:
            score += 20
            reasons.append(f"Matchar skillnamn som fras: {skill.name}")

        intent_terms = self._terms(" ".join(skill.intents))
        intent_overlap = terms & intent_terms
        if intent_overlap:
            score += len(intent_overlap) * 12
            reasons.append(f"Matchar intents: {', '.join(sorted(intent_overlap)[:5])}")

        description_overlap = terms & self._terms(skill.description)
        if description_overlap:
            score += len(description_overlap) * 4
            reasons.append(f"Matchar beskrivning: {', '.join(sorted(description_overlap)[:5])}")

        if role and self._normalize(role) in {self._normalize(item) for item in skill.roles}:
            score += 3
            reasons.append(f"Matchar roll: {role}")

        if audience and self._normalize(audience) in {self._normalize(item) for item in skill.audiences}:
            score += 2
            reasons.append(f"Matchar malgrupp: {audience}")

        return SkillMatch(skill=skill, score=score, reasons=reasons)

    @classmethod
    def _specificity(cls, skill: Skill, terms: set[str]) -> int:
        specific_terms = cls._terms(" ".join([skill.id, skill.name, *skill.intents]))
        return len(terms & specific_terms)

    def _fallback(self, limit: int) -> list[SkillMatch]:
        defaults = ["klarsprak", "sammanfattning", "mejl"]
        skills = []
        for skill_id in defaults[:limit]:
            try:
                skill = self.repository.get_skill(skill_id)
            except KeyError:
                continue
            skills.append(SkillMatch(skill=skill, score=0, reasons=["Fallback nar ingen tydlig match hittades."]))
        return skills

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            normalized
            for term in re.findall(r"\w+", text.lower(), flags=re.UNICODE)
            if len((normalized := SkillRouter._normalize(term))) > 2 and normalized not in SkillRouter.STOPWORDS
        }

    @staticmethod
    def _normalize(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text.strip().lower())
        return "".join(char for char in decomposed if not unicodedata.combining(char))
