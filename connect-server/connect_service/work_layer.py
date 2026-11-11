"""Connects arbetslager: stödindex, metodstöd och personliga arbetssätt.

Ingen användartext används för routing. Modellen väljer stöd lokalt utifrån
indexet och hämtar sedan metoden med ett id.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

from connect_service import personal
from connect_service.supports import SupportCatalog

logger = logging.getLogger("connect.work_layer")

SERVER_INSTRUCTIONS = (
    "Promptbanken Connect ger användaren ett personligt AI-team med nio specialister och användarens egna "
    "arbetssätt. När en uppgift är mer än en enkel fråga (till exempel utreda, förbereda eller följa upp ett möte, "
    "kartlägga en process, driva ett förbättrings- eller förändringsarbete, analysera data, planera en workshop, "
    "utveckla en produktidé eller driva ett större uppdrag): anropa get_connect_context en gång, välj högst ett stöd "
    "vars use_when passar uppgiften och vars not_when inte utesluter den, och hämta det med get_support(id). Följ "
    "metoden och användarens personliga regler. Vid enkla frågor används inget stöd. Skicka aldrig användarens "
    "ärendetext, dokument eller personuppgifter till Connects verktyg."
)

ROUTING_RULES = [
    "Välj utifrån uppgiften, inte utifrån användarens yrkesroll eller enstaka sökord.",
    "Inget stöd vid enkla frågor: faktafrågor, korta omformuleringar, översättningar, enstaka mejl eller frågor som besvaras i ett svar.",
    "Högst ett stöd åt gången. Läs not_when; om två stöd passar lika bra, ställ en kort fråga om vad användaren vill uppnå.",
    "Ett aktivt eget arbetssätt (id som börjar med mitt:) går före ett gemensamt stöd när dess use_when passar uppgiften.",
    "Säg kort vilket arbetssätt du följer första gången, men visa inte verktygsnamn eller interna steg.",
    "get_support tar bara ett id. Skicka aldrig användarens text till verktygen för att välja stöd.",
]

IMPROVEMENT_RULES = [
    "En enstaka korrigering gäller bara den aktuella uppgiften och sparas inte.",
    "När användaren uttryckligen visar en återkommande preferens (till exempel 'alltid', 'varje gång', 'i fortsättningen') får du fråga om den ska sparas som personlig regel.",
    "Visa först en förhandsvisning (anropa sparverktyget utan confirmed) och spara bara efter användarens tydliga ja.",
    "Spara aldrig personuppgifter, sekretessbelagd information eller innehåll ur användarens arbetsdokument i regler eller arbetssätt.",
    "Föreslå att slå ihop regler som finns i possible_overlaps, men ändra inget utan godkännande.",
    "Säger användaren nej: ändra ingenting och fråga inte igen om samma regel i samtalet.",
]


class ToolInputError(ValueError):
    """Ogiltiga verktygsargument."""


class NotFound(LookupError):
    """Objektet finns inte eller är inte tillgängligt."""


class PersonalLibrary(Protocol):
    def list_connect_documents(self, *, access_token: str, categories: set[str]) -> list[Mapping[str, object]]: ...

    def create_my_prompt(self, *, access_token: str, title: str, content: str, summary: str | None, category: str | None, request_id: str) -> Mapping[str, object]: ...

    def update_my_prompt(self, *, access_token: str, prompt_id: str, title: str, content: str, summary: str | None, category: str | None, request_id: str) -> Mapping[str, object]: ...

    def archive_my_prompt(self, *, access_token: str, prompt_id: str, request_id: str) -> Mapping[str, object]: ...

    def get_open_item(self, *, access_token: str, kind: str, ref: str) -> Mapping[str, object] | None: ...


_REQUEST_ID = {"type": "string", "format": "uuid", "description": "Nytt UUID per ändring. Krävs när confirmed är true."}
_CONFIRMED = {"type": "boolean", "description": "Utelämna eller false för förhandsvisning. true sparar, och får bara sättas efter användarens uttryckliga godkännande av förhandsvisningen."}


def tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "name": "get_connect_context",
            "description": (
                "Hämta en gång i början när uppgiften är mer än en enkel fråga. Returnerar stödindex med Promptbankens nio "
                "specialister och användarens egna arbetssätt (use_when/not_when), användarens arbetsprofil och personliga "
                "regler samt regler för val av stöd. Tar inga argument och tar aldrig emot användarens text."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_support",
            "description": (
                "Hämtar den fullständiga arbetsmetoden för ett valt stöd (id från get_connect_context, till exempel "
                "utredaren eller mitt:leverantorssvar), kombinerad med användarens personliga regler. Ange resource för "
                "att läsa en mall eller referens som metoden hänvisar till."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Stödets id från indexet."},
                    "resource": {"type": "string", "description": "Sökväg till en resurs, till exempel assets/evidenslogg.md."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "get_open_item",
            "description": (
                "Läser publicerat innehåll ur Promptbankens öppna katalog med text: en prompt (id eller slug) eller ett "
                "paket med alla steg i ordning (slug eller id). Används när en metod hänvisar till Opens get_template, "
                "get_package eller list_package_prompts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["prompt", "package"]},
                    "ref": {"type": "string", "description": "Id eller slug."},
                },
                "required": ["kind", "ref"],
            },
        },
        {
            "name": "save_my_profile",
            "description": (
                "Visar en förhandsvisning av, eller sparar, ändringar i användarens arbetsprofil och personliga regler. "
                "Anropa först utan confirmed och visa exakt vad som ändras. Spara med confirmed: true först efter "
                "användarens uttryckliga ja. Varje sparning blir en ny version som kan återställas."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": "Fält att sätta. Tom sträng eller null tar bort fältet.",
                        "properties": {
                            "role": {"type": "string"},
                            "work_context": {"type": "string"},
                            "language": {"type": "string"},
                            "tone": {"type": "string"},
                            "writing_principles": {"type": "array", "items": {"type": "string"}},
                            "preferred_structure": {"type": "string"},
                            "quality_rules": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "rules": {
                        "type": "object",
                        "properties": {
                            "add": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "applies_to": {"type": "array", "items": {"type": "string"}, "description": "\"all\", stöd-id eller mitt:-id."}}, "required": ["text"]}},
                            "update": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "applies_to": {"type": "array", "items": {"type": "string"}}, "active": {"type": "boolean"}}, "required": ["id"]}},
                            "remove": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "note": {"type": "string", "description": "Kort beskrivning av ändringen, utan personuppgifter."},
                    "expected_version": {"type": "integer", "description": "Version från get_connect_context, skyddar mot att skriva över en nyare ändring."},
                    "confirmed": _CONFIRMED,
                    "request_id": _REQUEST_ID,
                },
            },
        },
        {
            "name": "save_my_way_of_working",
            "description": (
                "Visar en förhandsvisning av, eller sparar, ett eget arbetssätt: nytt från grunden, en anpassning av en "
                "gemensam specialist (extends) eller en ändring av ett befintligt (id). Kan också inaktivera (active: false) "
                "eller ta bort (delete: true). Spara med confirmed: true först efter användarens uttryckliga ja."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "mitt:-id för ett befintligt arbetssätt. Utelämna för nytt."},
                    "name": {"type": "string"},
                    "purpose": {"type": "string"},
                    "use_when": {"type": "string"},
                    "not_when": {"type": "string"},
                    "instructions": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "quality_rules": {"type": "array", "items": {"type": "string"}},
                    "extends": {"type": "string", "description": "Id för gemensam specialist som arbetssättet bygger på."},
                    "active": {"type": "boolean"},
                    "delete": {"type": "boolean"},
                    "note": {"type": "string"},
                    "expected_version": {"type": "integer"},
                    "confirmed": _CONFIRMED,
                    "request_id": _REQUEST_ID,
                },
            },
        },
        {
            "name": "get_my_history",
            "description": "Visar versionshistoriken för arbetsprofilen (target: profile) eller ett eget arbetssätt (target: mitt:-id).",
            "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
        },
        {
            "name": "restore_my_version",
            "description": (
                "Återställer en tidigare version av profilen eller ett eget arbetssätt. Återställningen blir en ny version, "
                "så inget går förlorat. Utan confirmed visas en förhandsvisning."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "version": {"type": "integer"},
                    "confirmed": _CONFIRMED,
                    "request_id": _REQUEST_ID,
                },
                "required": ["target", "version"],
            },
        },
    ]


TOOL_NAMES = {tool["name"] for tool in tool_definitions()}


class WorkLayer:
    def __init__(self, catalog: SupportCatalog, library: PersonalLibrary) -> None:
        self._catalog = catalog
        self._library = library

    # ------------------------------------------------------------ läsning

    def _load(self, token: str) -> tuple[tuple[str, dict[str, object]] | None, list[tuple[str, dict[str, object]]]]:
        rows = self._library.list_connect_documents(
            access_token=token, categories={personal.PROFILE_CATEGORY, personal.WAY_CATEGORY}
        )
        profile = None
        ways = []
        for row in sorted(rows, key=lambda row: str(row.get("updated_at", "")), reverse=True):
            doc = personal.parse_document(row.get("content"))
            if doc is None:
                continue
            if doc["connect_type"] == "profile" and row.get("category") == personal.PROFILE_CATEGORY and profile is None:
                profile = (str(row["id"]), doc)
            elif doc["connect_type"] == "way" and row.get("category") == personal.WAY_CATEGORY:
                ways.append((str(row["id"]), doc))
        return profile, ways

    def context(self, token: str, subject: str) -> dict[str, object]:
        profile, ways = self._load(token)
        profile_doc = profile[1] if profile else None
        return {
            "user_id": subject,
            "how_to_use": SERVER_INSTRUCTIONS,
            "routing_rules": ROUTING_RULES,
            "supports": self._catalog.index(),
            "my_ways_of_working": [personal.way_index_entry(doc) for _, doc in ways],
            "profile": {
                "exists": profile is not None,
                "prompt_id": profile[0] if profile else None,
                "version": profile_doc.get("version") if profile_doc else 0,
                "settings": profile_doc.get("profile", {}) if profile_doc else {},
                "rules": profile_doc.get("rules", []) if profile_doc else [],
                "possible_overlaps": personal.overlapping_rules(profile_doc.get("rules", [])) if profile_doc else [],
            },
            "improvement_rules": IMPROVEMENT_RULES,
            "catalog_version": self._catalog.source_commit[:12],
        }

    def support(self, token: str, support_id: str, resource: str | None) -> dict[str, object]:
        if support_id.startswith(personal.WAY_PREFIX):
            if resource:
                raise NotFound()
            profile, ways = self._load(token)
            match = next((doc for _, doc in ways if personal.way_id(doc) == support_id), None)
            if match is None:
                raise NotFound()
            logger.info("support_fetched kind=personal")
            extends = match.get("extends")
            payload: dict[str, object] = {
                "id": support_id,
                "name": match["name"],
                "version": match["version"],
                "active": match.get("active", True),
                "instructions": personal.way_instructions(match),
            }
            if extends and self._catalog.has(str(extends)):
                base = self._catalog.support_payload(str(extends))
                payload["base_method"] = base
                payload["how_to_combine"] = (
                    f"Följ grundmetoden {base['name']} och lägg det egna arbetssättet ovanpå. " + personal.PRECEDENCE
                )
            payload["personal_rules"] = personal.applicable_rules(profile[1] if profile else None, support_id, extends)
            payload["profile"] = profile[1].get("profile", {}) if profile else {}
            return payload

        if not self._catalog.has(support_id):
            raise NotFound()
        if resource:
            text = self._catalog.read(support_id, resource)
            if text is None or resource == "SKILL.md":
                raise NotFound()
            logger.info("support_resource_fetched id=%s", support_id)
            return {"id": support_id, "resource": resource, "content": text}

        logger.info("support_fetched id=%s", support_id)
        payload = dict(self._catalog.support_payload(support_id) or {})
        profile, ways = self._load(token)
        profile_doc = profile[1] if profile else None
        payload["personal_rules"] = personal.applicable_rules(profile_doc, support_id)
        payload["profile"] = profile_doc.get("profile", {}) if profile_doc else {}
        payload["my_adaptations"] = [
            personal.way_index_entry(doc) for _, doc in ways if doc.get("extends") == support_id and doc.get("active", True)
        ]
        payload["precedence"] = personal.PRECEDENCE
        return payload

    def open_item(self, token: str, kind: str, ref: str) -> Mapping[str, object]:
        item = self._library.get_open_item(access_token=token, kind=kind, ref=ref)
        if item is None:
            raise NotFound()
        return item

    # ------------------------------------------------------------ skrivning

    def save_profile(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        profile, ways = self._load(token)
        current = profile[1] if profile else None
        self._check_version(current, arguments.get("expected_version"))
        known = set(self._catalog.ids()) | {personal.way_id(doc) for _, doc in ways}
        changes = {key: arguments[key] for key in ("profile", "rules") if key in arguments}
        if not changes:
            raise ToolInputError("Ange profile eller rules.")
        new_doc = personal.apply_profile_changes(current, changes, note=_note(arguments), known_targets=known)
        findings = personal.privacy_findings([new_doc.get("profile"), new_doc.get("rules"), arguments.get("note")])
        changes_view = personal.diff(current, new_doc)
        if findings:
            return _blocked(findings, changes_view)
        if arguments.get("confirmed") is not True:
            return _preview(changes_view, new_doc["version"])
        request_id = _request_id(arguments)
        content = personal.render_profile(new_doc)
        if profile:
            saved = self._library.update_my_prompt(access_token=token, prompt_id=profile[0], title="Min arbetsprofil (Connect)", content=content, summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
        else:
            saved = self._library.create_my_prompt(access_token=token, title="Min arbetsprofil (Connect)", content=content, summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
        return {"status": "saved", "version": new_doc["version"], "changes": changes_view, "prompt_id": saved.get("id", profile[0] if profile else None)}

    def save_way(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        profile, ways = self._load(token)
        target_id = arguments.get("id")
        existing = None
        if target_id is not None:
            existing = next(((prompt_id, doc) for prompt_id, doc in ways if personal.way_id(doc) == target_id), None)
            if existing is None:
                raise NotFound()
        current = existing[1] if existing else None
        self._check_version(current, arguments.get("expected_version"))

        if arguments.get("delete") is True:
            if existing is None:
                raise ToolInputError("Ange id för arbetssättet som ska tas bort.")
            if arguments.get("confirmed") is not True:
                return {"status": "preview", "action": "delete", "id": target_id, "name": current["name"], "message": "Arbetssättet arkiveras och slutar användas. Bekräfta med confirmed: true."}
            self._library.archive_my_prompt(access_token=token, prompt_id=existing[0], request_id=_request_id(arguments))
            return {"status": "deleted", "id": target_id}

        fields = {key: arguments[key] for key in personal.WAY_FIELDS if key in arguments}
        if not fields:
            raise ToolInputError("Ange minst ett fält att spara.")
        new_doc = personal.apply_way_changes(current, fields, note=_note(arguments), support_ids=set(self._catalog.ids()))
        if existing is None and any(personal.way_id(doc) == personal.way_id(new_doc) for _, doc in ways):
            raise ToolInputError("Det finns redan ett arbetssätt med samma namn. Ange dess id för att ändra det, eller välj ett annat namn.")
        findings = personal.privacy_findings([{key: new_doc.get(key) for key in personal.WAY_FIELDS}, arguments.get("note")])
        changes_view = personal.diff(current, new_doc)
        if findings:
            return _blocked(findings, changes_view)
        if arguments.get("confirmed") is not True:
            return {**_preview(changes_view, new_doc["version"]), "id": personal.way_id(new_doc)}
        request_id = _request_id(arguments)
        title = f"{new_doc['name']} (mitt arbetssätt)"[:200]
        summary = str(new_doc["purpose"])[:500]
        content = personal.render_way(new_doc)
        if existing:
            self._library.update_my_prompt(access_token=token, prompt_id=existing[0], title=title, content=content, summary=summary, category=personal.WAY_CATEGORY, request_id=request_id)
        else:
            self._library.create_my_prompt(access_token=token, title=title, content=content, summary=summary, category=personal.WAY_CATEGORY, request_id=request_id)
        return {"status": "saved", "id": personal.way_id(new_doc), "version": new_doc["version"], "changes": changes_view}

    def history(self, token: str, target: str) -> dict[str, object]:
        _, doc = self._target(token, target)
        return {"target": target, "versions": personal.history_view(doc)}

    def restore(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        target = arguments.get("target")
        version = arguments.get("version")
        if not isinstance(target, str) or isinstance(version, bool) or not isinstance(version, int):
            raise ToolInputError("Ange target och version.")
        prompt_id, doc = self._target(token, target)
        new_doc = personal.restore(doc, version)
        changes_view = personal.diff(doc, new_doc)
        if arguments.get("confirmed") is not True:
            return _preview(changes_view, new_doc["version"])
        request_id = _request_id(arguments)
        if target == "profile":
            self._library.update_my_prompt(access_token=token, prompt_id=prompt_id, title="Min arbetsprofil (Connect)", content=personal.render_profile(new_doc), summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
        else:
            self._library.update_my_prompt(access_token=token, prompt_id=prompt_id, title=f"{new_doc['name']} (mitt arbetssätt)"[:200], content=personal.render_way(new_doc), summary=str(new_doc["purpose"])[:500], category=personal.WAY_CATEGORY, request_id=request_id)
        return {"status": "saved", "target": target, "version": new_doc["version"], "restored_from": version, "changes": changes_view}

    def _target(self, token: str, target: str) -> tuple[str, dict[str, object]]:
        profile, ways = self._load(token)
        if target == "profile":
            if profile is None:
                raise NotFound()
            return profile
        match = next(((prompt_id, doc) for prompt_id, doc in ways if personal.way_id(doc) == target), None)
        if match is None:
            raise NotFound()
        return match

    @staticmethod
    def _check_version(current: Mapping[str, object] | None, expected: object) -> None:
        if expected is None:
            return
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise ToolInputError("expected_version måste vara ett heltal.")
        actual = int(current.get("version", 0)) if current else 0
        if actual != expected:
            raise ToolInputError(f"Dokumentet har ändrats sedan du läste det (nu version {actual}). Hämta get_connect_context igen.")


def _note(arguments: Mapping[str, object]) -> str | None:
    note = arguments.get("note")
    if note is not None and not isinstance(note, str):
        raise ToolInputError("note måste vara en text.")
    return note


def _request_id(arguments: Mapping[str, object]) -> str:
    from uuid import UUID

    value = arguments.get("request_id")
    try:
        UUID(str(value))
    except ValueError as error:
        raise ToolInputError("request_id måste vara ett UUID när confirmed är true.") from error
    return str(value)


def _preview(changes: list[dict[str, object]], version: int) -> dict[str, object]:
    return {
        "status": "preview",
        "will_become_version": version,
        "changes": changes,
        "message": "Inget är sparat. Visa ändringarna för användaren och spara med confirmed: true och ett nytt request_id först efter ett uttryckligt ja.",
    }


def _blocked(findings: list[str], changes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "blocked",
        "privacy_findings": findings,
        "changes": changes,
        "message": "Förslaget verkar innehålla " + ", ".join(findings) + ". Sådant sparas inte. Ta bort uppgifterna och försök igen.",
    }
