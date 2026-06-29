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
    display_name: str
    description: str
    category: str
    file: str
    intents: list[str]
    roles: list[str]
    audiences: list[str]
    risk_level: str
    risk_message: str
    requires_anonymization: bool
    anonymization_level: str
    example_phrases: list[str]
    output_type: str
    language: str
    version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        return cls(
            id=data["id"],
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            description=data["description"],
            category=data.get("category", "Övrigt"),
            file=data["file"],
            intents=list(data.get("intents", [])),
            roles=list(data.get("roles", [])),
            audiences=list(data.get("audiences", [])),
            risk_level=data.get("risk_level", "medium"),
            risk_message=data.get("risk_message", cls._default_risk_message(data.get("risk_level", "medium"))),
            requires_anonymization=bool(data.get("requires_anonymization", True)),
            anonymization_level=data.get(
                "anonymization_level",
                "required" if bool(data.get("requires_anonymization", True)) else "recommended",
            ),
            example_phrases=list(data.get("example_phrases", [])),
            output_type=data.get("output_type", "text"),
            language=data.get("language", "sv-SE"),
            version=data.get("version", "1.0.0"),
        )

    @staticmethod
    def _default_risk_message(risk_level: str) -> str:
        return {
            "low": "Låg risk: kontrollera att texten passar målgruppen innan den används.",
            "medium": "Medelrisk: kontrollera fakta, personuppgifter och eventuell sekretess innan texten används.",
            "high": "Hög risk: kontrollera fakta, juridik, ekonomi och beslutsformulering innan texten används.",
        }.get(risk_level, "Kontrollera innehållet innan texten används.")

    def to_dict(self, include_prompt: bool = False, prompt: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "intents": self.intents,
            "roles": self.roles,
            "audiences": self.audiences,
            "risk_level": self.risk_level,
            "risk_message": self.risk_message,
            "requires_anonymization": self.requires_anonymization,
            "anonymization_level": self.anonymization_level,
            "example_phrases": self.example_phrases,
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
                "required_sections": ["Kort sammanfattning", "Omskriven text", "Nästa steg"],
            },
            "email_draft": {
                "format": "markdown",
                "required_sections": ["Ämne", "Hälsning", "Svar", "Avslutning"],
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
                    "Analys/Förslag",
                    "Konsekvenser",
                    "Ekonomi",
                    "Juridik",
                    "Beslut",
                ],
            },
            "procedure": {
                "format": "markdown",
                "required_sections": ["Syfte", "Omfattning", "Ansvar", "Steg-för-steg", "Uppföljning"],
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
                "required_sections": ["Syfte", "Agenda", "Frågor", "Nästa steg"],
            },
            "summary": {
                "format": "markdown",
                "required_sections": ["Vad handlar det om?", "Huvudbudskap", "Konsekvens/nästa steg"],
                "max_words": 100,
            },
            "structured_notes": {
                "format": "markdown",
                "required_sections": ["Sammanfattning", "Beslut", "Att göra", "Öppna frågor"],
            },
            "keyword_list": {
                "format": "markdown",
                "item_schema": {"keyword": "string", "category": "optional_string", "reason": "optional_string"},
            },
            "announcement": {
                "format": "markdown",
                "required_sections": ["Rubrik", "Kort sammanfattning", "Vad som händer", "Vad mottagaren behöver göra"],
            },
            "image_prompt": {
                "format": "markdown",
                "required_sections": ["Bildprompt", "Alt-text", "Kontroll innan användning"],
            },
            "accessibility_text": {
                "format": "markdown",
                "required_sections": [
                    "Kort alt-text",
                    "Längre bildbeskrivning",
                    "När bilden kan markeras som dekorativ",
                    "Kontroll innan publicering",
                ],
            },
            "clarity_review": {
                "format": "markdown",
                "required_sections": [
                    "Snabb bedömning",
                    "Otydligheter",
                    "Ansvar och beslut",
                    "Nästa steg",
                    "Risk för missförstånd",
                    "Förslag på preciseringar",
                ],
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
