"""Användarens egna skills i Connect.

En skill lagras i Promptbanken (Creator) som content_items med type 'skill'.
Databasen är auktoritativ: den validerar, renderar SKILL.md, räknar upp
versionen atomiskt och sparar varje version oföränderlig. Den här modulen
formar bara det som visas för modellen och användaren.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

SKILL_PREFIX = "skill:"
SOURCE = "creator_skill"

SPEC_FIELDS = (
    "name",
    "slug",
    "description",
    "use_when",
    "not_when",
    "instructions",
    "steps",
    "quality_rules",
    "language",
    "dependencies",
    "files",
    "extends",
)

FIELD_LABELS = {
    "name": "namn",
    "slug": "id",
    "description": "beskrivning",
    "use_when": "när den används",
    "not_when": "när den inte används",
    "instructions": "instruktioner",
    "steps": "arbetssteg",
    "quality_rules": "kvalitetsregler",
    "language": "språk",
    "dependencies": "beroenden",
    "files": "filer",
    "extends": "bygger på",
}

# Kontextbudget för skill-indexet i get_connect_context (tecken i JSON).
CONTEXT_BUDGET = 3500
MAX_LISTED = 12
INLINE_FILES_LIMIT = 6000


def skill_id(slug: object) -> str:
    return SKILL_PREFIX + str(slug)


def slug_from_id(value: str) -> str:
    return value[len(SKILL_PREFIX):] if value.startswith(SKILL_PREFIX) else value


def _short(text: object, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def index_entry(row: Mapping[str, object], *, compact: bool = False) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": skill_id(row.get("slug")),
        "name": row.get("name"),
        "purpose": _short(row.get("description"), 160 if compact else 240),
        "use_when": _short(row.get("use_when"), 200 if compact else 300),
        "not_when": _short(row.get("not_when"), 140 if compact else 220),
        "version": row.get("version"),
        "source": SOURCE,
    }
    if row.get("extends"):
        entry["extends"] = row["extends"]
    return entry


def context_block(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Kort skill-index inom en fast budget. Fullständiga SKILL.md skickas aldrig här."""
    import json

    active = [row for row in rows if row.get("is_active", True)]
    inactive = [{"id": skill_id(row.get("slug")), "name": row.get("name")} for row in rows if not row.get("is_active", True)]
    listed: list[dict[str, object]] = []
    only_names: list[dict[str, object]] = []
    for compact in (False, True):
        listed = [index_entry(row, compact=compact) for row in active[:MAX_LISTED]]
        only_names = [{"id": skill_id(row.get("slug")), "name": row.get("name")} for row in active[MAX_LISTED:]]
        while listed and len(json.dumps(listed, ensure_ascii=False)) > CONTEXT_BUDGET:
            moved = listed.pop()
            only_names.insert(0, {"id": moved["id"], "name": moved["name"]})
        if not only_names:
            break
    block: dict[str, object] = {"my_skills": listed}
    if only_names:
        block["more_skills"] = only_names
        block["more_skills_note"] = (
            "Fler aktiva skills finns. Hämta en med get_support(id) om namnet passar uppgiften, eller list_my_skills."
        )
    if inactive:
        block["inactive_skills"] = inactive
    return block


def merge_changes(current: Mapping[str, object], changes: Mapping[str, object]) -> dict[str, object]:
    """Ny fullständig spec: aktuella fält, med de ändrade fälten ersatta. None tar bort ett valfritt fält."""
    spec = {key: current[key] for key in SPEC_FIELDS if key in current and current[key] not in (None, [], "")}
    for key, value in changes.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value
    return spec


def spec_from_skill(skill: Mapping[str, object]) -> dict[str, object]:
    """Spec-fält ur get_my_skill-svaret (med filinnehåll)."""
    spec: dict[str, object] = {}
    for key in SPEC_FIELDS:
        if key == "files":
            files = [
                {"path": item.get("path"), "content": item.get("content")}
                for item in skill.get("files", []) or []
                if isinstance(item, Mapping) and isinstance(item.get("content"), str)
            ]
            if files:
                spec["files"] = files
        elif skill.get(key) not in (None, [], ""):
            spec[key] = skill[key]
    return spec


def way_to_skill(fields: Mapping[str, object]) -> dict[str, object]:
    """Fält från save_my_way_of_working till skillens fält. purpose blir description."""
    mapping = {
        "name": "name",
        "purpose": "description",
        "use_when": "use_when",
        "not_when": "not_when",
        "instructions": "instructions",
        "steps": "steps",
        "quality_rules": "quality_rules",
        "extends": "extends",
    }
    return {target: fields[source] for source, target in mapping.items() if source in fields}


def changed_fields(before: Mapping[str, object] | None, after: Mapping[str, object]) -> list[str]:
    before = before or {}
    return [key for key in SPEC_FIELDS if before.get(key) != after.get(key) and key != "slug"]


def confirm_text_create(spec: Mapping[str, object]) -> str:
    use_when = _short(spec.get("use_when"), 200).rstrip(".")
    files = spec.get("files") or []
    extra = f" Med {len(files)} referensfil{'er' if len(files) != 1 else ''}." if files else ""
    return (
        f"Ny privat skill: ”{spec.get('name')}”. Används när: {use_when}.{extra} "
        "Den sparas på ditt Promptbanken-konto och kan användas i kommande samtal. Vill du spara den?"
    )


def confirm_text_update(name: object, fields: Sequence[str], new_version: int) -> str:
    labels = ", ".join(FIELD_LABELS.get(field, field) for field in fields) or "inga fält"
    return f"Ändrar din skill ”{name}”: {labels}. Det blir en ny version; den tidigare finns kvar. Vill du spara det?"


def confirm_text_active(name: object, active: bool) -> str:
    if active:
        return f"Slår på din skill ”{name}” så att den kan väljas automatiskt igen. Vill du det?"
    return f"Stänger av din skill ”{name}”. Den finns kvar och kan slås på igen, men väljs inte automatiskt. Vill du det?"


def privacy_values(spec: Mapping[str, object]) -> list[object]:
    values: list[object] = [spec.get(key) for key in SPEC_FIELDS if key != "files"]
    for item in spec.get("files") or []:
        if isinstance(item, Mapping):
            values.append(item.get("content"))
    return values


# ---------------------------------------------------------------- inskick och katalog

CATALOG_PREFIX = "katalog:"

_STATE_LABELS = {
    "review": "Väntar på granskning",
    "changes_requested": "Ändringar begärda",
    "rejected": "Avslagen",
    "withdrawn": "Tillbakadragen",
}


KIND_LABELS = {"prompt": "prompt", "skill": "skill", "package": "paket"}


def submission_status_label(row: Mapping[str, object]) -> str:
    state = str(row.get("state") or "")
    if state == "published":
        if row.get("catalog_status") == "published" and row.get("catalog_published_version"):
            return "Godkänd och publicerad i katalogen"
        return "Godkänd, inte publicerad ännu"
    return _STATE_LABELS.get(state, state)


def confirm_text_submit(name: object, version: int | None, distribution: bool, kind: str = "skill") -> str:
    spread = (
        "Den får spridas via Promptbanken till AI-tjänster som ChatGPT när den publiceras."
        if distribution
        else "Den publiceras bara på promptbanken.se, inte till andra AI-tjänster."
    )
    what = f"din {KIND_LABELS.get(kind, kind)}"
    version_text = f", version {version}," if version else ""
    return (
        f"Jag skickar ”{name}”{version_text} till Promptbankens granskning. {spread} "
        f"Originalet förblir privat och kan fortsätta ändras. Vill du skicka {what}?"
    )


def catalog_entry(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": CATALOG_PREFIX + str(row.get("slug")),
        "name": row.get("name"),
        "purpose": _short(row.get("description"), 200),
        "use_when": _short(row.get("use_when"), 240),
        "not_when": _short(row.get("not_when"), 160),
        "version": row.get("version"),
        "creator": row.get("creator_display_name"),
        "source": "promptbanken_catalog",
    }
