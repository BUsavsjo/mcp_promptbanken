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
from connect_service import skills as sk
from connect_service.data import ConnectWriteError
from connect_service.supports import SupportCatalog

logger = logging.getLogger("connect.work_layer")

PERSONAL_QUOTA_MESSAGE = (
    "Önskemålet kunde inte sparas, och inget har ändrats. Dina personliga anpassningar sparas som privata prompter i "
    "ditt Promptbanken-bibliotek, och Free-kontot har redan nått sin gräns för privata prompter. Arkivera en prompt "
    "du inte behöver på app.promptbanken.se, eller uppgradera kontot, och försök igen. Fram till dess kan jag följa "
    "önskemålet i det här samtalet."
)


NO_HISTORY_MESSAGE = (
    "Du har inga sparade versioner ännu. Profilen skapas första gången du sparar ett önskemål, "
    "till exempel 'kortare sammanfattningar framöver'."
)


@contextmanager
def _personal_write() -> Iterator[None]:
    """Översätter kvotfel vid personliga anpassningar till ett begripligt besked."""
    try:
        yield
    except ConnectWriteError as error:
        if error.kind == "quota" and "arbetssätt" in str(error):
            raise ConnectWriteError("Inget har ändrats. " + str(error), kind="quota") from error
        if error.kind == "quota":
            raise ConnectWriteError(PERSONAL_QUOTA_MESSAGE, kind="quota") from error
        raise

SERVER_INSTRUCTIONS = (
    "Promptbanken Connect: användarens AI, användarens sätt att arbeta. Fyra lägen. "
    "1) Enkel fråga (fakta, förklaring, omformulering, översättning): svara direkt, använd inte Connect. "
    "2) Användaren vill ha hjälp att göra en uppgift (granska, skriva, planera, analysera, utreda, möte, process, "
    "förbättring, förändring, workshop, produktidé, större uppdrag), eller ber om en skill, ett arbetssätt eller en "
    "specialist vid namn: anropa get_connect_context en gång. Användaren kan ha egna skills för just sådana uppgifter. "
    "Välj själv högst ett stöd som passar enligt use_when och not_when och hämta det med get_support(id). Passar inget: "
    "hjälp utan stöd. Följ metoden och användarens regler. "
    "3) Användaren uttrycker en återkommande önskan ('alltid', 'varje gång', 'nästa gång', 'i fortsättningen', "
    "'så här vill jag'): följ how_to_personalize i get_connect_context. "
    "4) Användaren vill skapa, förbättra, visa eller slå av/på en egen skill: följ how_to_manage_skills i "
    "get_connect_context. "
    "Använd alltid användarens aktiva regler (always_apply) när Connect används. Prata vanlig svenska: nämn aldrig "
    "verktyg, MCP, prompter eller id. Skicka aldrig användarens ärendetext, dokument eller personuppgifter till Connect."
)

ROUTING_RULES = [
    "Du väljer stöd själv utifrån uppgiften. Connect väljer inget åt dig och får aldrig användarens text.",
    "Inget stöd vid enkla frågor som besvaras i ett svar, även om ämnet låter som en specialist (\"vad är en konsekvensanalys?\" är en fråga, inte en utredning).",
    "Vid konkurrens gäller denna ordning: 1) ber användaren om en skill, ett arbetssätt eller en specialist vid namn, använd det. "
    "2) Passar en aktiv egen skill (skill:) eller ett aktivt eget arbetssätt (mitt:) uppgiften enligt use_when, och säger "
    "not_when inte emot, använd det, även om en specialist också passar. "
    "3) Annars den specialist som passar bäst. 4) Passar två lika bra: ställ en kort fråga om vad användaren vill uppnå.",
    "En egen skill används bara när den passar uppgiften. Att den finns är inget skäl att använda den.",
    "Publika metoder ur Open hämtas bara när en metod hänvisar till dem (get_open_item).",
    "Ett eget arbetssätt som bygger på en specialist (extends) ersätter den specialisten när det passar. Hämta då arbetssättet, inte specialisten.",
    "Högst ett stöd åt gången. Läs not_when.",
    "Superplan bara när användaren vill ha hjälp hela vägen med ett större uppdrag utan tydlig väg, inte för att ett ord förekommer.",
    "Säg en gång, kort och på svenska, vilket arbetssätt du följer (\"Jag tar det här som en utredning.\"). Visa inga interna steg.",
]

HOW_TO_PERSONALIZE = [
    "1. Tolka: vad vill användaren ska gälla framöver? En enstaka rättelse i stunden sparas inte.",
    "2. Välj: Gäller önskemålet en viss typ av uppgift som ingen specialist täcker (t.ex. 'leverantörssvar', 'veckobrev', "
    "'så här vill jag göra X') blir det ett eget arbetssätt via save_my_way_of_working, med use_when för just den uppgiften. "
    "Gäller det hur du svarar i allmänhet (längd, ton, struktur) blir det en personlig regel via save_my_profile rules.add "
    "med applies_to [\"all\"]. Gäller det en specialists uppgifter ('mina utredningar') blir det en regel med stödets id "
    "(t.ex. [\"utredaren\"]). Lägg aldrig en uppgiftsspecifik instruktion som regel med [\"all\"].",
    "3. Visa: anropa utan confirmed. Visa användaren confirm_text ordagrant, inget annat tekniskt.",
    "4. Fråga: be om ett tydligt ja. Säger användaren nej eller tvekar: spara inget och fråga inte igen om samma sak.",
    "5. Spara: samma anrop med confirmed: true och ett nytt request_id. Säg bara att det är sparat när svaret har verified: true.",
    "6. Använd: regeln gäller direkt i samtalet och kommer tillbaka i always_apply eller personal_rules nästa gång.",
    "Ändra eller stänga av: hitta regeln i profile.rules och använd rules.update (active: false stänger av, text ändrar), "
    "eller active: false på ett arbetssätt. Samma förhandsvisning och ja gäller.",
    "Ångra ('gå tillbaka till hur det var'): get_my_history visar versionerna, restore_my_version återställer som en ny "
    "version efter förhandsvisning (confirm_text) och ja. Finns ingen historik får användaren ett vänligt besked.",
    "Spara aldrig personuppgifter, sekretess eller innehåll ur användarens dokument. Föreslå sammanslagning av regler i possible_overlaps, men ändra inget utan ja.",
]

HOW_TO_MANAGE_SKILLS = [
    "Skapa ('skapa en skill som …'): ta fram name, description, use_when, not_when, instructions och vid behov steps, "
    "quality_rules och files (textfiler under references/ eller assets/). Fråga högst en sak i taget. create_my_skill utan "
    "confirmed, visa confirm_text och en kort sammanfattning, spara med confirmed: true och nytt request_id efter ett tydligt ja.",
    "Förbättra: get_my_skill, föreslå ändringen, update_my_skill med changes (bara ändrade fält, hela nya värdet) och "
    "expected_version utan confirmed, visa confirm_text, spara efter ja. Tidigare versioner finns kvar.",
    "Slå av eller på: set_my_skill_active med samma förhandsvisning och ja.",
    "Säg 'sparat' bara vid verified: true. Personliga regler skrivs aldrig in i skillen. Inga personuppgifter, inget ur "
    "användarens dokument, ingen kod.",
]

# Hur en metod tillämpas i samtalet. Metodtexten synkas oförändrad; det här
# styr bara omfånget, aldrig kvalitetskraven.
HOW_TO_APPLY = [
    "Skala efter uppgiften. En liten eller tydlig uppgift: gå direkt till nästa användbara steg i metodens anda och svara kort. En stor eller oklar uppgift: följ fler av metodens faser.",
    "Använd metodens faser, mallar och kontrollpunkter i bakgrunden. Visa dem inte som rubriker eller listor om användaren inte ber om det.",
    "Beskriv inte hur du arbetar eller vilka principer metoden har (\"Så här arbetar jag …\"). Visa det genom svaret. En mening om vad du tar sikte på räcker.",
    "Kvalitetskraven gäller alltid, oavsett längd: hitta inte på fakta, källor, siffror, ansvariga eller beslut; skilj fakta från antaganden; säg vad som är osäkert.",
    "Fråga högst en sak i taget och bara sådant som ändrar resultatet. Gissa rimligt och säg vad du antagit i stället för att fråga om allt.",
    "Fördjupa (fler faser, evidenslogg, mallar) när användaren ber om det eller när uppgiften är ett beslutsunderlag.",
    "Användarens personliga regler styr form, längd och ordning. De går före metodens förvalda format men aldrig före dess kvalitets- och säkerhetsregler.",
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

    def list_my_skills(self, *, access_token: str) -> list[Mapping[str, object]]: ...

    def get_my_skill(self, *, access_token: str, skill_id: str | None = None, slug: str | None = None, version: int | None = None, file_path: str | None = None, include_files: bool = True) -> Mapping[str, object] | None: ...

    def list_my_skill_versions(self, *, access_token: str, skill_id: str) -> list[Mapping[str, object]]: ...

    def validate_my_skill(self, *, access_token: str, spec: Mapping[str, object], skill_id: str | None = None) -> Mapping[str, object]: ...

    def create_my_skill(self, *, access_token: str, spec: Mapping[str, object], request_id: str) -> Mapping[str, object]: ...

    def update_my_skill(self, *, access_token: str, skill_id: str, spec: Mapping[str, object], expected_version: int, note: str | None, request_id: str) -> Mapping[str, object]: ...

    def set_my_skill_active(self, *, access_token: str, skill_id: str, active: bool, request_id: str) -> Mapping[str, object]: ...


_REQUEST_ID = {"type": "string", "format": "uuid", "description": "Nytt UUID per ändring. Krävs när confirmed är true."}
_CONFIRMED = {"type": "boolean", "description": "Utelämna eller false för förhandsvisning. true sparar, och får bara sättas efter användarens uttryckliga godkännande av förhandsvisningen."}


def tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "name": "get_connect_context",
            "description": (
                "Hämta en gång när användaren vill ha hjälp att göra en uppgift (granska, skriva, planera, analysera, "
                "utreda m.m.), ber om en skill, ett arbetssätt eller en specialist vid namn, vill skapa eller ändra en egen "
                "skill, eller vill att något ska gälla framöver ('alltid', 'nästa gång'). Inte vid enkla frågor (fakta, "
                "förklaringar, omformuleringar, översättningar). Returnerar användarens egna skills, de nio "
                "specialisterna och egna arbetssätt att välja bland (kort: id, use_when, not_when), användarens regler "
                "(always_apply gäller alltid), how_to_personalize och how_to_manage_skills. Tar inga argument och aldrig "
                "användarens text."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_support",
            "description": (
                "Hämtar den fullständiga arbetsmetoden för ett valt stöd (id från get_connect_context, till exempel "
                "utredaren, mitt:leverantorssvar eller skill:offertgranskaren), kombinerad med användarens personliga "
                "regler. För en egen skill: hela SKILL.md, aktuell version och filer. Ange resource för att läsa en mall "
                "eller referensfil som metoden hänvisar till, till exempel references/checklista.md."
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
                "befintligt (id). Ett nytt kräver name, purpose, use_when och instructions (steps och quality_rules "
                "är valfria). active: false stänger av, delete: true tar bort. För en enstaka önskan om svar eller "
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
            "description": "Visar versionshistoriken för arbetsprofilen (target: profile), ett eget arbetssätt (target: mitt:-id) eller en egen skill (target: skill:-id).",
            "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
        },
        {
            "name": "restore_my_version",
            "description": (
                "Återställer en tidigare version av profilen, ett eget arbetssätt eller en egen skill. Återställningen blir en ny version, "
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
        *skill_tool_definitions(),
    ]


_SKILL_SPEC = {
    "type": "object",
    "description": "Skillens innehåll.",
    "properties": {
        "name": {"type": "string", "description": "Namn, t.ex. Offertgranskaren."},
        "description": {"type": "string", "description": "Vad skillen gör, en eller två meningar (max 1024 tecken)."},
        "use_when": {"type": "string", "description": "När skillen ska användas."},
        "not_when": {"type": "string", "description": "När skillen inte ska användas."},
        "instructions": {"type": "string", "description": "Fullständiga instruktioner i Markdown."},
        "steps": {"type": "array", "items": {"type": "string"}, "description": "Arbetssteg i ordning (valfritt)."},
        "quality_rules": {"type": "array", "items": {"type": "string"}, "description": "Kvalitetsregler (valfritt)."},
        "language": {"type": "string", "enum": ["sv", "en"]},
        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Krav, t.ex. kodkörning eller ett annat verktyg (valfritt)."},
        "files": {
            "type": "array",
            "description": "Textfiler (valfritt): path under references/ eller assets/, ändelse .md, .txt, .csv eller .json.",
            "items": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        },
    },
}


def skill_tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "name": "list_my_skills",
            "description": "Listar användarens egna skills med kort information och status (aktiv/avstängd), utan instruktionerna.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_my_skill",
            "description": (
                "Hämtar en egen skill för att visa eller ändra den: alla fält, SKILL.md, filer och version. "
                "Ange version för en äldre version. För att använda skillen i en uppgift: get_support(id)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "skill:-id från indexet."},
                    "version": {"type": "integer"},
                },
                "required": ["id"],
            },
        },
        {
            "name": "validate_my_skill",
            "description": "Kontrollerar en skill (format, fält, filnamn, hänvisningar) och visar SKILL.md utan att spara något.",
            "inputSchema": {
                "type": "object",
                "properties": {"skill": _SKILL_SPEC, "id": {"type": "string", "description": "skill:-id om det gäller en befintlig skill."}},
                "required": ["skill"],
            },
        },
        {
            "name": "create_my_skill",
            "description": (
                "Skapar en ny privat skill på användarens konto ('skapa en skill som …'). Kräver name, description, "
                "use_when, not_when och instructions. Utan confirmed: förhandsvisning med confirm_text och SKILL.md. "
                "Med confirmed: true (efter ett uttryckligt ja) och nytt request_id: sparar och verifierar."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"skill": _SKILL_SPEC, "confirmed": _CONFIRMED, "request_id": _REQUEST_ID},
                "required": ["skill"],
            },
        },
        {
            "name": "update_my_skill",
            "description": (
                "Ändrar en egen skill och sparar en ny version; tidigare versioner finns kvar. Ange id, changes (bara de "
                "fält som ändras, med fältets hela nya värde) och expected_version (versionen du utgick från). Utan "
                "confirmed: förhandsvisning. Med confirmed: true efter ett uttryckligt ja: sparar och verifierar."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "changes": {**_SKILL_SPEC, "description": "Fälten som ändras."},
                    "expected_version": {"type": "integer"},
                    "note": {"type": "string", "description": "Kort beskrivning av ändringen, utan personuppgifter."},
                    "confirmed": _CONFIRMED,
                    "request_id": _REQUEST_ID,
                },
                "required": ["id", "changes", "expected_version"],
            },
        },
        {
            "name": "set_my_skill_active",
            "description": (
                "Slår av eller på en egen skill för automatiskt val. En avstängd skill finns kvar och kan läsas. "
                "Utan confirmed: förhandsvisning. Med confirmed: true efter ett ja: sparar."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "active": {"type": "boolean"}, "confirmed": _CONFIRMED, "request_id": _REQUEST_ID},
                "required": ["id", "active"],
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

    def _skills(self, token: str) -> list[Mapping[str, object]]:
        """Användarens skills. Ett fel här får aldrig stoppa specialisterna."""
        lister = getattr(self._library, "list_my_skills", None)
        if lister is None:
            return []
        try:
            return list(lister(access_token=token))
        except Exception:  # noqa: BLE001 - t.ex. miljö utan skill-RPC:erna
            logger.warning("skills_unavailable")
            return []

    def context(self, token: str, subject: str) -> dict[str, object]:
        profile, ways = self._load(token)
        profile_doc = profile[1] if profile else None
        rules = profile_doc.get("rules", []) if profile_doc else []
        supports = [
            {**entry, "use_when": _trigger_part(str(entry["use_when"])), "in_short": IN_SHORT.get(str(entry["id"]), "")}
            for entry in self._catalog.index()
        ]
        return {
            "user_id": subject,
            "how_to_use": SERVER_INSTRUCTIONS,
            "routing_rules": ROUTING_RULES,
            **sk.context_block(self._skills(token)),
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
            "how_to_manage_skills": HOW_TO_MANAGE_SKILLS,
            "catalog_version": self._catalog.source_commit[:12],
        }

    def support(self, token: str, support_id: str, resource: str | None) -> dict[str, object]:
        if support_id.startswith(sk.SKILL_PREFIX):
            return self._skill_support(token, support_id, resource)
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
            payload["how_to_apply"] = HOW_TO_APPLY
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
        payload["how_to_apply"] = HOW_TO_APPLY
        if payload["my_adaptations"]:
            payload["adaptation_hint"] = (
                "Användaren har ett eget arbetssätt som bygger på den här specialisten. Passar det uppgiften: hämta det "
                "med get_support(id) och följ det i stället."
            )
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
        known = (
            set(self._catalog.ids())
            | {personal.way_id(doc) for _, doc in ways}
            | {sk.skill_id(row.get("slug")) for row in self._skills(token)}
        )
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
        if target.startswith(sk.SKILL_PREFIX):
            skill = self._require_skill(token, target, include_files=False)
            versions = self._library.list_my_skill_versions(access_token=token, skill_id=str(skill["id"]))
            result: dict[str, object] = {"target": target, "versions": [dict(row) for row in versions]}
            if len(versions) == 1:
                result["message"] = "Bara nuvarande version finns. Det finns ingen tidigare version att gå tillbaka till ännu."
            return result
        profile, ways = self._load(token)
        if target == "profile" and profile is None:
            return {"target": target, "versions": [], "message": NO_HISTORY_MESSAGE}
        _, doc = self._target(token, target)
        versions = personal.history_view(doc)
        result: dict[str, object] = {"target": target, "versions": versions}
        if len(versions) == 1:
            result["message"] = "Bara nuvarande version finns. Det finns ingen tidigare version att gå tillbaka till ännu."
        return result

    def restore(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        target = arguments.get("target")
        version = arguments.get("version")
        if not isinstance(target, str) or isinstance(version, bool) or not isinstance(version, int):
            raise ToolInputError("Ange target och version.")
        if target.startswith(sk.SKILL_PREFIX):
            return self._restore_skill(token, target, version, arguments)
        if target == "profile" and self._load(token)[0] is None:
            raise ToolInputError(NO_HISTORY_MESSAGE)
        prompt_id, doc = self._target(token, target)
        if not personal.history_versions(doc):
            raise ToolInputError("Det finns ingen tidigare version att gå tillbaka till ännu.")
        new_doc = personal.restore(doc, version)
        changes_view = personal.diff(doc, new_doc)
        if target == "profile":
            detail = self._profile_confirm_text(doc, new_doc, self._load(token)[1])
        else:
            detail = self._way_confirm_text(doc, new_doc)
        confirm_text = "Går tillbaka till hur det var tidigare. " + detail
        if arguments.get("confirmed") is not True:
            return {**_preview(changes_view, new_doc["version"]), "confirm_text": confirm_text}
        request_id = _request_id(arguments)
        with _personal_write():
            if target == "profile":
                self._library.update_my_prompt(access_token=token, prompt_id=prompt_id, title="Min arbetsprofil (Connect)", content=personal.render_profile(new_doc), summary="Personliga inställningar för Promptbanken Connect.", category=personal.PROFILE_CATEGORY, request_id=request_id)
            else:
                self._library.update_my_prompt(access_token=token, prompt_id=prompt_id, title=f"{new_doc['name']} (mitt arbetssätt)"[:200], content=personal.render_way(new_doc), summary=str(new_doc["purpose"])[:500], category=personal.WAY_CATEGORY, request_id=request_id)
        self._verify(token, target, new_doc["version"])
        return {
            "status": "saved",
            "verified": True,
            "target": target,
            "version": new_doc["version"],
            "restored_from": version,
            "changes": changes_view,
            "saved_text": "Sparat. " + confirm_text.removesuffix(" Vill du spara det?"),
        }

    # ------------------------------------------------------------ egna skills

    def _skill_lookup(self, ident: object, *, version: int | None = None, file_path: str | None = None, include_files: bool = True, token: str) -> Mapping[str, object] | None:
        if not isinstance(ident, str) or not ident.strip():
            raise ToolInputError("Ange skillens id, till exempel skill:offertgranskaren.")
        value = ident.strip()
        kwargs: dict[str, object] = {"version": version, "file_path": file_path, "include_files": include_files}
        if _is_uuid(value):
            kwargs["skill_id"] = value
        else:
            kwargs["slug"] = sk.slug_from_id(value)
        return self._library.get_my_skill(access_token=token, **kwargs)  # type: ignore[arg-type]

    def _require_skill(self, token: str, ident: object, *, include_files: bool = True, version: int | None = None) -> Mapping[str, object]:
        skill = self._skill_lookup(ident, version=version, include_files=include_files, token=token)
        if skill is None:
            raise NotFound()
        return skill

    def _skill_support(self, token: str, support_id: str, resource: str | None) -> dict[str, object]:
        if resource:
            item = self._skill_lookup(support_id, file_path=resource, token=token)
            if item is None:
                raise NotFound()
            logger.info("support_resource_fetched kind=skill")
            return {"id": support_id, "resource": item.get("path"), "version": item.get("version"), "content": item.get("content")}

        skill = self._require_skill(token, support_id)
        logger.info("support_fetched kind=skill")
        files = [item for item in skill.get("files", []) or [] if isinstance(item, Mapping)]
        total = sum(int(item.get("chars") or 0) for item in files)
        if total <= sk.INLINE_FILES_LIMIT:
            file_view = [{"path": item.get("path"), "content": item.get("content")} for item in files]
        else:
            file_view = [{"path": item.get("path"), "chars": item.get("chars")} for item in files]
        profile, _ways = self._load(token)
        profile_doc = profile[1] if profile else None
        sid = sk.skill_id(skill.get("slug"))
        payload: dict[str, object] = {
            "id": sid,
            "name": skill.get("name"),
            "source": sk.SOURCE,
            "version": skill.get("version"),
            "active": skill.get("is_active", True),
            "instructions": skill.get("skill_md"),
            "files": file_view,
            "dependencies": {
                "declared": skill.get("dependencies") or [],
                "how_to_read_resources": "Hämta en fil med get_support(id, resource: \"<path>\") när instruktionen hänvisar till den.",
                "note": "Skillen består bara av text. Inget körs på servern.",
            },
            "personal_rules": personal.applicable_rules(profile_doc, sid),
            "profile": profile_doc.get("profile", {}) if profile_doc else {},
            "precedence": personal.PRECEDENCE,
            "how_to_apply": HOW_TO_APPLY,
        }
        if not skill.get("is_active", True):
            payload["inactive_note"] = (
                "Skillen är avstängd för automatiskt val. Använd den bara om användaren bad om den vid namn."
            )
        return payload

    def list_skills(self, token: str) -> dict[str, object]:
        rows = self._skills(token)
        items = [
            {**sk.index_entry(row), "active": row.get("is_active", True), "files": row.get("file_count", 0), "updated_at": row.get("updated_at")}
            for row in rows
        ]
        result: dict[str, object] = {"items": items}
        if not items:
            result["message"] = "Du har inga egna skills ännu. Be till exempel: 'skapa en skill som hjälper mig granska leverantörsofferter'."
        return result

    def get_skill(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        version = arguments.get("version")
        if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
            raise ToolInputError("version måste vara ett heltal.")
        skill = self._require_skill(token, arguments.get("id"), version=version)  # type: ignore[arg-type]
        return {**dict(skill), "id": sk.skill_id(skill.get("slug")), "source": sk.SOURCE}

    def validate_skill(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        spec = arguments.get("skill")
        if not isinstance(spec, Mapping):
            raise ToolInputError("Ange skill som ett objekt.")
        skill_uuid = None
        if arguments.get("id") is not None:
            skill_uuid = str(self._require_skill(token, arguments.get("id"), include_files=False)["id"])
        result = self._library.validate_my_skill(access_token=token, spec=spec, skill_id=skill_uuid)
        findings = personal.privacy_findings(sk.privacy_values(spec))
        return {
            "valid": bool(result.get("valid")) and not findings,
            "errors": list(result.get("errors") or []),
            "privacy_findings": findings,
            "id": sk.skill_id(result.get("slug")) if result.get("slug") else None,
            "skill_md": result.get("skill_md"),
        }

    def _validated(self, token: str, spec: Mapping[str, object], skill_uuid: str | None) -> tuple[dict[str, object] | None, Mapping[str, object]]:
        """(stopp-svar eller None, valideringsresultat)."""
        findings = personal.privacy_findings(sk.privacy_values(spec))
        if findings:
            return _blocked(findings, []), {}
        result = self._library.validate_my_skill(access_token=token, spec=spec, skill_id=skill_uuid)
        if not result.get("valid"):
            return {
                "status": "invalid",
                "errors": list(result.get("errors") or []),
                "message": "Inget är sparat. Rätta punkterna i errors och försök igen.",
            }, result
        return None, result

    def create_skill(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        spec = arguments.get("skill")
        if not isinstance(spec, Mapping):
            raise ToolInputError("Ange skill som ett objekt med name, description, use_when, not_when och instructions.")
        if arguments.get("confirmed") is True:
            # Databasen validerar, kontrollerar idempotens och sparar i ett steg.
            request_id = _request_id(arguments)
            findings = personal.privacy_findings(sk.privacy_values(spec))
            if findings:
                return _blocked(findings, [])
            created = self._library.create_my_skill(access_token=token, spec=spec, request_id=request_id)
            sid = sk.skill_id(created.get("slug"))
            self._verify_skill(token, sid, int(created.get("version") or 1))
            confirm_text = sk.confirm_text_create(spec)
            return {
                "status": "saved",
                "verified": True,
                "id": sid,
                "version": created.get("version"),
                "saved_text": "Sparat. " + confirm_text.removesuffix(" Vill du spara den?"),
            }
        stop, result = self._validated(token, spec, None)
        if stop:
            return stop
        normalized = dict(result["spec"])  # type: ignore[arg-type]
        sid = sk.skill_id(normalized.get("slug"))
        confirm_text = sk.confirm_text_create(normalized)
        if arguments.get("confirmed") is not True:
            return {
                "status": "preview",
                "id": sid,
                "will_become_version": 1,
                "confirm_text": confirm_text,
                "skill_md": result.get("skill_md"),
                "message": "Inget är sparat. Visa confirm_text och spara med confirmed: true och ett nytt request_id först efter ett uttryckligt ja.",
            }
        raise ToolInputError("Ogiltigt läge.")  # pragma: no cover

    def update_skill(self, token: str, arguments: Mapping[str, object], *, intro: str = "") -> dict[str, object]:
        changes = arguments.get("changes")
        expected = arguments.get("expected_version")
        if not isinstance(changes, Mapping) or not changes:
            raise ToolInputError("Ange changes med de fält som ska ändras.")
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise ToolInputError("Ange expected_version: versionen ändringen utgår från (från get_my_skill).")
        unknown = [key for key in changes if key not in sk.SPEC_FIELDS]
        if unknown:
            raise ToolInputError("Okända fält: " + ", ".join(unknown) + ".")
        current = self._require_skill(token, arguments.get("id"))
        if "slug" in changes and changes["slug"] != current.get("slug"):
            raise ToolInputError("Skillens id kan inte ändras. Skapa en ny skill om du vill ha ett annat id.")
        sid = sk.skill_id(current.get("slug"))
        base = sk.spec_from_skill(current)
        new_spec = sk.merge_changes(base, changes)
        if arguments.get("confirmed") is True:
            # Databasen avgör version, idempotens och giltighet atomiskt.
            request_id = _request_id(arguments)
            note = arguments.get("note")
            if note is not None and not isinstance(note, str):
                raise ToolInputError("note måste vara en text.")
            findings = personal.privacy_findings([*sk.privacy_values(new_spec), note])
            if findings:
                return _blocked(findings, [])
            saved = self._library.update_my_skill(
                access_token=token, skill_id=str(current["id"]), spec=new_spec,
                expected_version=expected, note=note, request_id=request_id,
            )
            self._verify_skill_at_least(token, sid, int(saved.get("version") or expected + 1))
            return {
                "status": "saved",
                "verified": True,
                "id": sid,
                "version": saved.get("version"),
                "previous_version": saved.get("previous_version", expected),
                "saved_text": "Sparat. " + intro + f"Din skill ”{current.get('name')}” är nu version {saved.get('version')}; den tidigare versionen finns kvar.",
            }
        if int(current.get("version") or 0) != expected:
            raise ConnectWriteError(
                f"Versionskonflikt: skillen är nu version {current.get('version')}, men ändringen utgick från version "
                f"{expected}. Inget sparades. Hämta skillen igen och gör om ändringen.",
                kind="conflict",
            )
        stop, result = self._validated(token, new_spec, str(current["id"]))
        if stop:
            return stop
        normalized = dict(result["spec"])  # type: ignore[arg-type]
        fields = sk.changed_fields(base, normalized)
        if not fields:
            raise ToolInputError("Det gäller redan. Inget har ändrats.")
        confirm_text = intro + sk.confirm_text_update(current.get("name"), fields, expected + 1)
        return {
                "status": "preview",
                "id": sid,
                "will_become_version": expected + 1,
                "changes": [
                    {"field": field, "before": _clip(base.get(field)), "after": _clip(normalized.get(field))} for field in fields
                ],
                "confirm_text": confirm_text,
                "skill_md": result.get("skill_md"),
                "message": "Inget är sparat. Visa confirm_text och spara med confirmed: true och ett nytt request_id först efter ett uttryckligt ja.",
        }

    def set_skill_active(self, token: str, arguments: Mapping[str, object]) -> dict[str, object]:
        active = arguments.get("active")
        if not isinstance(active, bool):
            raise ToolInputError("Ange active som true eller false.")
        current = self._require_skill(token, arguments.get("id"), include_files=False)
        sid = sk.skill_id(current.get("slug"))
        if bool(current.get("is_active", True)) == active:
            return {"status": "unchanged", "id": sid, "active": active, "message": "Det gäller redan. Inget har ändrats."}
        confirm_text = sk.confirm_text_active(current.get("name"), active)
        if arguments.get("confirmed") is not True:
            return {"status": "preview", "id": sid, "active": active, "confirm_text": confirm_text,
                    "message": "Inget är ändrat. Visa confirm_text och spara med confirmed: true och ett nytt request_id först efter ett ja."}
        self._library.set_my_skill_active(access_token=token, skill_id=str(current["id"]), active=active, request_id=_request_id(arguments))
        check = self._require_skill(token, sid, include_files=False)
        if bool(check.get("is_active", True)) != active:
            raise ToolInputError("Ändringen gick inte att bekräfta och är troligen inte sparad. Säg inte till användaren att den är sparad.")
        return {"status": "saved", "verified": True, "id": sid, "active": active,
                "saved_text": "Klart. " + confirm_text.removesuffix(" Vill du det?")}

    def _restore_skill(self, token: str, target: str, version: int, arguments: Mapping[str, object]) -> dict[str, object]:
        current = self._require_skill(token, target, include_files=False)
        old = self._skill_lookup(target, version=version, token=token)
        if old is None:
            raise ToolInputError(f"Version {version} av skillen finns inte. Se get_my_history.")
        old_spec = sk.spec_from_skill(old)
        changes = {key: old_spec.get(key) for key in sk.SPEC_FIELDS if key != "slug"}
        return self.update_skill(
            token,
            {
                "id": target,
                "changes": changes,
                "expected_version": int(current.get("version") or 0),
                "note": f"Återställd från version {version}",
                "confirmed": arguments.get("confirmed"),
                "request_id": arguments.get("request_id"),
            },
            intro="Går tillbaka till hur det var tidigare. ",
        )

    def _verify_skill_at_least(self, token: str, sid: str, version: int) -> None:
        """Efter en uppdatering: minst den sparade versionen (en samtidig ändring kan ha hunnit före läsningen)."""
        check = self._skill_lookup(sid, include_files=False, token=token)
        if check is None or int(check.get("version") or 0) < version:
            raise ToolInputError(
                "Ändringen gick inte att bekräfta och är troligen inte sparad. Hämta skillen igen och försök med ett nytt "
                "request_id. Säg inte till användaren att den är sparad."
            )

    def _verify_skill(self, token: str, sid: str, version: int) -> None:
        check = self._skill_lookup(sid, include_files=False, token=token)
        if check is None or int(check.get("version") or 0) != version:
            raise ToolInputError(
                "Ändringen gick inte att bekräfta och är troligen inte sparad. Hämta skillen igen och försök med ett nytt "
                "request_id. Säg inte till användaren att den är sparad."
            )

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
            if use_when[:4].casefold() == "när ":
                use_when = use_when[4:]
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
            raise ToolInputError(
                "Hittar inget eget arbetssätt med det id:t. Hämta get_connect_context för att se användarens arbetssätt."
            )
        return match

    @staticmethod
    def _check_version(current: Mapping[str, object] | None, expected: object) -> None:
        if expected is None:
            return
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise ToolInputError("expected_version måste vara ett heltal.")
        actual = int(current.get("version", 0)) if current else 0
        if actual != expected:
            raise ToolInputError(
                f"Inget sparades: inställningarna har ändrats sedan de lästes (nu version {actual}, angiven {expected}). "
                "Hämta get_connect_context, visa förhandsvisningen igen och spara först efter ett nytt ja."
            )


def _trigger_part(use_when: str) -> str:
    """Specialistens 'Använd när …'. Vad den gör finns redan i in_short, så indexet hålls kort."""
    index = use_when.find("Använd när")
    return use_when[index:] if index > 0 else use_when


def _is_uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _clip(value: object, limit: int = 400) -> object:
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1] + "…"
    if isinstance(value, list):
        return [_clip(item, 200) for item in value[:20]]
    return value


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
