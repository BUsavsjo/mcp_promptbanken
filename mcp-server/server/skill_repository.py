from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKILL_ID_PATTERN = re.compile(r"^[a-z0-9_-]{2,50}$")


class InvalidSkillIdError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    file: str
    intents: list[str]
    roles: list[str]
    audiences: list[str]
    risk_level: str
    requires_anonymization: bool
    output_type: str
    language: str
    version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            file=data["file"],
            intents=list(data.get("intents", [])),
            roles=list(data.get("roles", [])),
            audiences=list(data.get("audiences", [])),
            risk_level=data.get("risk_level", "medium"),
            requires_anonymization=bool(data.get("requires_anonymization", True)),
            output_type=data.get("output_type", "text"),
            language=data.get("language", "sv-SE"),
            version=data.get("version", "1.0.0"),
        )

    def to_dict(self, include_prompt: bool = False, prompt: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "intents": self.intents,
            "roles": self.roles,
            "audiences": self.audiences,
            "risk_level": self.risk_level,
            "requires_anonymization": self.requires_anonymization,
            "output_type": self.output_type,
            "output_schema": self.output_schema(),
            "language": self.language,
            "version": self.version,
        }
        if include_prompt:
            result["prompt"] = prompt or ""
        return result

    def output_schema(self) -> dict[str, Any]:
        schemas: dict[str, dict[str, Any]] = {
            "rewritten_text": {
                "format": "markdown",
                "required_sections": ["Kort sammanfattning", "Omskriven text", "Nasta steg"],
            },
            "email_draft": {
                "format": "markdown",
                "required_sections": ["Amne", "Halsning", "Svar", "Avslutning"],
            },
            "faq": {
                "format": "markdown",
                "item_schema": {"question": "string", "answer": "string"},
                "min_items": 8,
                "max_items": 12,
            },
            "checklist": {
                "format": "markdown",
                "item_schema": {"label": "string", "done": "unchecked_checkbox"},
            },
            "notice": {
                "format": "markdown",
                "required_sections": ["Rubrik", "Tid och plats", "Syfte", "Praktisk information"],
            },
            "decision_brief": {
                "format": "markdown",
                "required_sections": [
                    "Rubrik",
                    "Sammanfattning",
                    "Bakgrund",
                    "Analys/Forslag",
                    "Konsekvenser",
                    "Ekonomi",
                    "Juridik",
                    "Beslut",
                ],
            },
            "procedure": {
                "format": "markdown",
                "required_sections": ["Syfte", "Omfattning", "Ansvar", "Steg-for-steg", "Uppfoljning"],
            },
            "text_variants": {
                "format": "markdown",
                "required_sections": ["Formell version", "Vardaglig version"],
            },
            "questions": {
                "format": "markdown",
                "item_schema": {"question": "string", "purpose": "optional_string"},
            },
            "meeting_structure": {
                "format": "markdown",
                "required_sections": ["Syfte", "Agenda", "Fragor", "Nasta steg"],
            },
            "summary": {
                "format": "markdown",
                "required_sections": ["Vad handlar det om?", "Huvudbudskap", "Konsekvens/nasta steg"],
                "max_words": 100,
            },
            "structured_notes": {
                "format": "markdown",
                "required_sections": ["Sammanfattning", "Beslut", "Att gora", "Oppna fragor"],
            },
            "keyword_list": {
                "format": "markdown",
                "item_schema": {"keyword": "string", "category": "optional_string", "reason": "optional_string"},
            },
            "announcement": {
                "format": "markdown",
                "required_sections": ["Rubrik", "Kort sammanfattning", "Vad som hander", "Vad mottagaren behover gora"],
            },
        }
        return schemas.get(
            self.output_type,
            {
                "format": "markdown",
                "required_sections": ["Resultat"],
            },
        )


class SkillRepository:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.config_path = repo_root / "skills.json"

    def list_skills(self) -> list[Skill]:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return [Skill.from_dict(skill) for skill in data.get("skills", [])]

    @staticmethod
    def is_valid_skill_id(skill_id: str) -> bool:
        return bool(SKILL_ID_PATTERN.fullmatch(skill_id))

    def get_skill(self, skill_id: str) -> Skill:
        if not self.is_valid_skill_id(skill_id):
            raise InvalidSkillIdError("Skill id contains invalid characters")
        match = next((skill for skill in self.list_skills() if skill.id == skill_id), None)
        if not match:
            raise KeyError("Skill not found")
        return match

    def get_prompt(self, skill_id: str) -> str:
        skill = self.get_skill(skill_id)
        prompt_path = self.repo_root / skill.file
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file '{skill.file}' was not found")
        return prompt_path.read_text(encoding="utf-8").strip()
