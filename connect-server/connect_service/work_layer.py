"""Connects arbetslager: stödindex, metodstöd och personliga arbetssätt.

Ingen användartext används för routing. Modellen väljer stöd lokalt utifrån
indexet och hämtar sedan metoden med ett id.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Protocol

from connect_service import personal
from connect_service.data import ConnectWriteError
from connect_service.supports import SupportCatalog

logger = logging.getLogger("connect.work_layer")

PERSONAL_QUOTA_MESSAGE = (
    "Önskemålet kunde inte sparas, och inget har ändrats. Dina personliga anpassningar sparas som privata prompter i "
    "ditt Promptbanken-bibliotek, och Free-kontot har redan nått sin gräns för privata prompter. Arkivera en prompt "
    "du inte behöver på app.promptbanken.se, eller uppgradera kontot, och försök igen. Fram till dess kan jag följa "
    "önskemålet i det här samtalet."
)


@contextmanager
def _personal_write() -> Iterator[None]:
    """Översätter kvotfel vid personliga anpassningar till ett begripligt besked."""
    try:
        yield
    except ConnectWriteError as error:
        if error.kind == "quota":
            raise ConnectWriteError(PERSONAL_QUOTA_MESSAGE, kind="quota") from error
        raise

SERVER_INSTRUCTIONS = (
    "Promptbanken Connect: användarens AI, användarens sätt att arbeta. Tre lägen. "
    "1) Enkel fråga (fakta, förklaring, omformulering, översättning, ett enstaka mejl): svara direkt, använd inte Connect. "
    "2) Arbete i flera steg (utreda, möte, process, förbättring, förändring, data, workshop, produktidé, större uppdrag) "
    "eller användaren ber om en specialist vid namn: anropa get_connect_context en gång, välj själv högst ett stöd och "
    "hämta det med get_support(id). Följ metoden och användarens regler. "
    "3) Användaren uttrycker en återkommande önskan ('alltid', 'varje gång', 'nästa gång', 'i fortsättningen', "
    "'så här vill jag'): följ how_to_personalize i get_connect_context. "
    "Använd alltid användarens aktiva regler (always_apply) när Connect används. Prata vanlig svenska: nämn aldrig "
    "verktyg, MCP, prompter eller id. Skicka aldrig användarens ärendetext, dokument eller personuppgifter till Connect."
)

ROUTING_RULES = [
    "Du väljer stöd själv utifrån uppgiften. Connect väljer inget åt dig och får aldrig användarens text.",
    "Inget stöd vid enkla frågor som besvaras i ett svar, även om ämnet låter som en specialist (\"vad är en konsekvensanalys?\" är en fråga, inte en utredning).",
    "Ber användaren om en specialist vid namn (\"använd Utredaren\", \"som workshopledare\"): använd den, även om du hade valt en annan.",
    "Högst ett stöd åt gången. Läs not_when. Passar två lika bra: ställ en kort fråga om vad användaren vill uppnå.",
    "Ett aktivt eget arbetssätt (mitt:) går före en gemensam specialist när det passar uppgiften.",
    "Superplan bara när användaren vill ha hjälp hela vägen med ett större uppdrag utan tydlig väg, inte för att ett ord förekommer.",
    "Säg en gång, kort och på svenska, vilket arbetssätt du följer (\"Jag tar det här som en utredning.\"). Visa inga interna steg.",
]

HOW_TO_PERSONALIZE = [
    "1. Tolka: vad vill användaren ska gälla framöver? En enstaka rättelse i stunden sparas inte.",
    "2. Välj: önskemål om svar eller arbetssätt (längd, ton, ordning, struktur, vad som ska ingå) blir en personlig regel via "
    "save_my_profile med rules.add. applies_to = [\"all\"] om det gäller allt, annars stödets id (t.ex. [\"utredaren\"] för "
    "'mina utredningar'). Ett helt eget återkommande arbetsflöde blir ett arbetssätt via save_my_way_of_working.",
    "3. Visa: anropa utan confirmed. Visa användaren confirm_text ordagrant, inget annat tekniskt.",
    "4. Fråga: be om ett tydligt ja. Säger användaren nej eller tvekar: spara inget och fråga inte igen om samma sak.",
    "5. Spara: samma anrop med confirmed: true och ett nytt request_id. Säg bara att det är sparat när svaret har verified: true.",
    "6. Använd: regeln gäller direkt i samtalet och kommer tillbaka i always_apply eller personal_rules nästa gång.",
    "Ändra eller stänga av: hitta regeln i profile.rules och använd rules.update (active: false stänger av, text ändrar), "
    "eller active: false på ett arbetssätt. Samma förhandsvisning och ja gäller.",
    "Spara aldrig personuppgifter, sekretess eller innehåll ur användarens dokument. Föreslå sammanslagning av regler i possible_overlaps, men ändra inget utan ja.",
]

# Kort, Connect-ägd beskrivning per specialist. Metodtexten och use_when synkas
# oförändrade från agent-skills; det här är bara en snabb orientering för valet.
IN_SHORT = {
    "motessekreteraren": "Före och efter möten: agenda, beslut, uppdrag, uppföljning.",
    "utredaren": "Utreda en fråga och väga alternativ till ett beslutsunderlag med källor.",
    "processledaren": "Kartlägga hur ett arbetsflöde går till och var det fastnar.",
    "forbattringsledaren": "Lösa ett återkommande problem med ett litet test och mätning.",
    "forandringsledaren": "Planera och förankra ett införande på en eller flera arbetsplatser.",
    "verksamhetsanalytikern": "Analysera siffror, tabeller eller kostnader och dra hållbara slutsatser.",
    "workshopledaren": "Planera, leda och följa upp en workshop eller planeringsdag med övningar.",
    "produktutvecklaren": "Pröva en produkt- eller tjänsteidé fram till en validerad MVP.",
    "superplan": "Driva ett större uppdrag hela vägen när vägen dit är oklar.",
}


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
                "Hämta en gång när uppgiften är ett arbete i flera steg, när användaren ber om en specialist vid namn, "
                "eller när användaren vill att något ska gälla framöver ('alltid', 'nästa gång'). Inte vid enkla frågor. "
                "Returnerar de nio specialisterna och användarens egna arbetssätt att välja bland, användarens regler "
                "(always_apply gäller alltid) och how_to_personalize. Tar inga argument och aldrig användarens text."
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
                "Sparar hur användaren vill att du ska arbeta framöver, till exempel 'börja alltid utredningar med "
                "problembeskrivningen' (rules.add, applies_to [\"utredaren\"]) eller 'kortare sammanfattningar' "
                "(rules.add, applies_to [\"all\"]). Stänger av eller ändrar en regel med rules.update. "
                "Utan confirmed: förhandsvisning med confirm_text som visas för användaren. Med confirmed: true "
                "(efter ett uttryckligt ja) och nytt request_id: sparar och verifierar. Varje sparning blir en ny version."
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
                "Sparar ett helt eget, återkommande arbetsflöde ('så här vill jag göra leverantörssvar'): nytt (name, "
                "purpose, use_when, instructions), som anpassning av en specialist (extends) eller ändring av ett "
                "befintligt (id). active: false stänger av, delete: true tar bort. För en enstaka önskan om svar eller "
                "format: använd save_my_profile i stället. Utan confirmed: förhandsvisning med confirm_text. Med "
                "confirmed: true efter ett uttryckligt ja: sparar och verifierar."
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
        rules = profile_doc.get("rules", []) if profile_doc else []
        supports = [{**entry, "in_short": IN_SHORT.get(str(entry["id"]), "")} for entry in self._catalog.index()]
        return {
            "user_id": subject,
            "how_to_use": SERVER_INSTRUCTIONS,
            "routing_rules": ROUTING_RULES,
            "supports": supports,
            "my_ways_of_working": [personal.way_index_entry(doc) for _, doc in ways if doc.get("active", True)],
            "inactive_ways_of_working": [
                {"id": personal.way_id(doc), "name": doc.get("name"), "version": doc.get("version")}
                for _, doc in ways
                if not doc.get("active", True)
            ],
            "always_apply": [
                {"id": rule["id"], "text": rule["text"]}
                for rule in rules
                if rule.get("active", True) and "all" in rule.get("applies_to", [])
            ],
            "profile": {
                "exists": profile is not None,
                "note": None if profile else "Ingen profil ännu. Den skapas automatiskt första gången användaren sparar ett önskemål.",
                "prompt_id": profile[0] if profile else None,
                "version": profile_doc.get("version") if profile_doc else 0,
                "settings": profile_doc.get("profile", {}) if profile_doc else {},
                "rules": rules,
                "possible_overlaps": personal.overlapping_rules(rules) if profile_doc else [],
            },
            "how_to_personalize": HOW_TO_PERSONALIZE,
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
        confirm_text = self._profile_confirm_text(current, new_doc, ways)
        if arguments.get("confirmed") is not True:
            return {**_preview(changes_view, new_doc["version"]), "confirm_text": confirm_text}
        request_id = _request_id(arguments)
        content = personal.render_profile(new_doc)
        with _personal_write():
            if profile:
                saved = self._library.update_my_prompt(access_token=token, prompt_id=profile[0], title="Min arbetsprofil (Connect)", content=content, summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
            else:
                saved = self._library.create_my_prompt(access_token=token, title="Min arbetsprofil (Connect)", content=content, summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
        self._verify(token, "profile", new_doc["version"])
        return {
            "status": "saved",
            "verified": True,
            "version": new_doc["version"],
            "changes": changes_view,
            "saved_text": "Sparat. " + confirm_text.removesuffix(" Vill du spara det?"),
            "prompt_id": saved.get("id", profile[0] if profile else None),
        }

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
                return {
                    "status": "preview",
                    "action": "delete",
                    "id": target_id,
                    "name": current["name"],
                    "confirm_text": f"Jag tar bort ditt arbetssätt ”{current['name']}”. Vill du det?",
                    "message": "Arbetssättet arkiveras och slutar användas. Bekräfta med confirmed: true.",
                }
            with _personal_write():
                self._library.archive_my_prompt(access_token=token, prompt_id=existing[0], request_id=_request_id(arguments))
            self._verify(token, str(target_id), None)
            return {"status": "deleted", "verified": True, "id": target_id, "saved_text": f"Borttaget: ”{current['name']}”."}

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
        confirm_text = self._way_confirm_text(current, new_doc)
        if arguments.get("confirmed") is not True:
            return {**_preview(changes_view, new_doc["version"]), "id": personal.way_id(new_doc), "confirm_text": confirm_text}
        request_id = _request_id(arguments)
        title = f"{new_doc['name']} (mitt arbetssätt)"[:200]
        summary = str(new_doc["purpose"])[:500]
        content = personal.render_way(new_doc)
        with _personal_write():
            if existing:
                self._library.update_my_prompt(access_token=token, prompt_id=existing[0], title=title, content=content, summary=summary, category=personal.WAY_CATEGORY, request_id=request_id)
            else:
                self._library.create_my_prompt(access_token=token, title=title, content=content, summary=summary, category=personal.WAY_CATEGORY, request_id=request_id)
        self._verify(token, personal.way_id(new_doc), new_doc["version"])
        return {
            "status": "saved",
            "verified": True,
            "id": personal.way_id(new_doc),
            "version": new_doc["version"],
            "changes": changes_view,
            "saved_text": "Sparat. " + confirm_text.removesuffix(" Vill du spara det?"),
        }

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
        with _personal_write():
            if target == "profile":
                self._library.update_my_prompt(access_token=token, prompt_id=prompt_id, title="Min arbetsprofil (Connect)", content=personal.render_profile(new_doc), summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
            else:
                self._library.update_my_prompt(access_token=token, prompt_id=prompt_id, title=f"{new_doc['name']} (mitt arbetssätt)"[:200], content=personal.render_way(new_doc), summary=str(new_doc["purpose"])[:500], category=personal.WAY_CATEGORY, request_id=request_id)
        self._verify(token, target, new_doc["version"])
        return {"status": "saved", "verified": True, "target": target, "version": new_doc["version"], "restored_from": version, "changes": changes_view}

    # ------------------------------------------------------------ hjälp

    def _verify(self, token: str, target: str, version: int | None) -> None:
        """Läser tillbaka efter skrivning. version None betyder att målet ska vara borta."""
        profile, ways = self._load(token)
        if target == "profile":
            actual = profile[1].get("version") if profile else None
        else:
            actual = next((doc.get("version") for _, doc in ways if personal.way_id(doc) == target), None)
        if actual != version:
            raise ToolInputError(
                "Ändringen gick inte att bekräfta och är troligen inte sparad. Hämta get_connect_context och försök "
                "igen med ett nytt request_id. Säg inte till användaren att den är sparad."
            )

    def _target_names(self, targets: list[str], ways: list[tuple[str, dict[str, object]]]) -> str:
        if "all" in targets:
            return "alla uppgifter"
        names = {entry["id"]: entry["name"] for entry in self._catalog.index()}
        names.update({personal.way_id(doc): doc.get("name") for _, doc in ways})
        return ", ".join(str(names.get(target, target)) for target in targets)

    def _profile_confirm_text(self, current: Mapping[str, object] | None, new_doc: Mapping[str, object], ways: list[tuple[str, dict[str, object]]]) -> str:
        old_rules = {rule["id"]: rule for rule in (current or {}).get("rules", [])}
        new_rules = {rule["id"]: rule for rule in new_doc.get("rules", [])}
        parts: list[str] = []
        for rule_id, rule in new_rules.items():
            where = self._target_names(list(rule.get("applies_to", [])), ways)
            old = old_rules.get(rule_id)
            if old is None:
                parts.append(f"Ny regel: {_q(rule['text'])} – gäller {where}.")
                continue
            if old.get("text") != rule.get("text"):
                parts.append(f"Ändrar regeln {_q(old['text'])} till {_q(rule['text'])}.")
            if old.get("applies_to") != rule.get("applies_to"):
                parts.append(f"Regeln {_q(rule['text'])} gäller nu {where}.")
            if old.get("active", True) and not rule.get("active", True):
                parts.append(f"Stänger av regeln {_q(rule['text'])}.")
            elif not old.get("active", True) and rule.get("active", True):
                parts.append(f"Slår på regeln {_q(rule['text'])} igen.")
        for rule_id, rule in old_rules.items():
            if rule_id not in new_rules:
                parts.append(f"Tar bort regeln {_q(rule['text'])}.")
        old_profile = dict((current or {}).get("profile", {}))
        new_profile = dict(new_doc.get("profile", {}))
        for key, label in personal.PROFILE_FIELDS.items():
            if old_profile.get(key) != new_profile.get(key):
                value = new_profile.get(key)
                shown = "; ".join(value) if isinstance(value, list) else value
                parts.append(f"{label}: {shown}." if shown else f"{label} tas bort.")
        return " ".join(parts) + " Vill du spara det?"

    def _way_confirm_text(self, current: Mapping[str, object] | None, new_doc: Mapping[str, object]) -> str:
        name = new_doc["name"]
        if current is None:
            base = f" Bygger på {self._catalog.support_payload(str(new_doc['extends']))['name']}." if new_doc.get("extends") and self._catalog.has(str(new_doc["extends"])) else ""
            use_when = str(new_doc.get("use_when") or "").strip().rstrip(".")
            return f"Nytt arbetssätt: ”{name}”. Används när: {use_when}.{base} Vill du spara det?"
        if current.get("active", True) and not new_doc.get("active", True):
            return f"Stänger av ditt arbetssätt ”{name}”. Det finns kvar och kan slås på igen. Vill du spara det?"
        if not current.get("active", True) and new_doc.get("active", True):
            return f"Slår på ditt arbetssätt ”{name}” igen. Vill du spara det?"
        changed = [personal.WAY_FIELDS[key].lower() for key in personal.WAY_FIELDS if current.get(key) != new_doc.get(key)]
        return f"Ändrar ditt arbetssätt ”{name}”: {', '.join(changed)}. Vill du spara det?"

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


def _q(text: object) -> str:
    """Citerar en regeltext utan dubbel punkt: ”Kortare sammanfattningar”."""
    return "”" + str(text).strip().rstrip(".") + "”"


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
