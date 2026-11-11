"""Personligt lager ovanpå de gemensamma metoderna.

Profil och egna arbetssätt lagras som vanliga privata Creator-prompter, så att
ingen parallell innehållsmodell behövs. Varje dokument har en läsbar
sammanfattning och ett maskinläsbart block (`connect-data`) med aktuell
version och en kort versionshistorik.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

PROFILE_CATEGORY = "connect-profil"
WAY_CATEGORY = "connect-arbetssatt"
WAY_PREFIX = "mitt:"
SCHEMA = 1
MAX_HISTORY = 10
MAX_CONTENT = 20000

PROFILE_FIELDS = {
    "role": "Roll",
    "work_context": "Arbetskontext",
    "language": "Språk",
    "tone": "Tonalitet",
    "writing_principles": "Principer för kommunikation och text",
    "preferred_structure": "Föredragen struktur på underlag",
    "quality_rules": "Personliga kvalitetsregler",
}
LIST_FIELDS = {"writing_principles", "quality_rules"}

WAY_FIELDS = {
    "name": "Namn",
    "purpose": "Syfte",
    "use_when": "Används när",
    "not_when": "Används inte när",
    "instructions": "Arbetsinstruktion",
    "steps": "Steg",
    "quality_rules": "Kvalitetsregler",
    "extends": "Bygger på gemensam metod",
    "active": "Aktivt",
}
WAY_LIST_FIELDS = {"steps", "quality_rules"}
WAY_REQUIRED = ("name", "purpose", "use_when", "instructions")

DATA_BLOCK = re.compile(r"```connect-data\n(.*?)\n```", re.S)

PRECEDENCE = (
    "Ordning vid konflikt: 1) Promptbankens säkerhets- och integritetsregler och metodens regler som aldrig bryts, "
    "2) grundmetodens kvalitetskrav, 3) användarens personliga arbetssätt, 4) personliga regler och profil "
    "(format, ton, struktur, ordning). En personlig regel som skulle sätta en kvalitets- eller säkerhetsregel ur spel "
    "följs inte; säg kort till användaren varför."
)

_PRIVACY_PATTERNS = (
    ("personnummer", re.compile(r"\b(19|20)?\d{6}[-+ ]?\d{4}\b")),
    ("e-postadress", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("telefonnummer", re.compile(r"(?<!\d)(\+46|0)[\d\s-]{7,12}\d\b")),
)


class PersonalError(ValueError):
    """Ett användbart fel om ett personligt dokument."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:60] or "arbetssatt"


def parse_document(content: object) -> dict[str, object] | None:
    if not isinstance(content, str):
        return None
    match = DATA_BLOCK.search(content)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("connect_type") not in {"profile", "way"}:
        return None
    return data


def privacy_findings(values: Sequence[object]) -> list[str]:
    text = "\n".join(_flatten(values))
    return sorted({label for label, pattern in _PRIVACY_PATTERNS if pattern.search(text)})


def _flatten(values: Sequence[object]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, Mapping):
            out.extend(_flatten(list(value.values())))
        elif isinstance(value, (list, tuple)):
            out.extend(_flatten(list(value)))
    return out


def _clean_text(value: object, field: str, *, max_length: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersonalError(f"Fältet {field} måste vara en text.")
    if len(value) > max_length:
        raise PersonalError(f"Fältet {field} får vara högst {max_length} tecken.")
    return value.strip()


def _clean_list(value: object, field: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or len(value) > 30:
        raise PersonalError(f"Fältet {field} måste vara en lista med högst 30 punkter.")
    return [_clean_text(item, field, max_length=600) for item in value]


# ---------------------------------------------------------------- profil


def empty_profile() -> dict[str, object]:
    return {"connect_type": "profile", "schema": SCHEMA, "version": 0, "profile": {}, "rules": [], "history": []}


def _profile_state(doc: Mapping[str, object]) -> dict[str, object]:
    return {"profile": copy.deepcopy(doc.get("profile", {})), "rules": copy.deepcopy(doc.get("rules", []))}


def apply_profile_changes(
    current: Mapping[str, object] | None,
    changes: Mapping[str, object],
    *,
    note: str | None,
    known_targets: set[str],
) -> dict[str, object]:
    doc = copy.deepcopy(dict(current)) if current else empty_profile()
    profile = dict(doc.get("profile", {}))
    rules = [dict(rule) for rule in doc.get("rules", [])]

    profile_changes = changes.get("profile", {})
    if not isinstance(profile_changes, Mapping):
        raise PersonalError("profile måste vara ett objekt.")
    for key, value in profile_changes.items():
        if key not in PROFILE_FIELDS:
            raise PersonalError(f"Okänt profilfält: {key}.")
        if value is None or value == "" or value == []:
            profile.pop(key, None)
        elif key in LIST_FIELDS:
            profile[key] = _clean_list(value, key)
        else:
            profile[key] = _clean_text(value, key, max_length=1000)

    rule_changes = changes.get("rules", {})
    if not isinstance(rule_changes, Mapping):
        raise PersonalError("rules måste vara ett objekt med add, update och remove.")
    by_id = {rule["id"]: rule for rule in rules}
    for rule_id in rule_changes.get("remove", []) or []:
        if rule_id not in by_id:
            raise PersonalError(f"Regeln {rule_id} finns inte.")
        rules = [rule for rule in rules if rule["id"] != rule_id]
        by_id.pop(rule_id)
    for update in rule_changes.get("update", []) or []:
        if not isinstance(update, Mapping) or update.get("id") not in by_id:
            raise PersonalError("Varje uppdatering måste ange id för en befintlig regel.")
        rule = by_id[update["id"]]
        if "text" in update:
            rule["text"] = _clean_text(update["text"], "text", max_length=600)
        if "applies_to" in update:
            rule["applies_to"] = _clean_targets(update["applies_to"], known_targets)
        if "active" in update:
            if not isinstance(update["active"], bool):
                raise PersonalError("active måste vara true eller false.")
            rule["active"] = update["active"]
    next_number = max([int(rule["id"][1:]) for rule in rules if str(rule["id"])[1:].isdigit()] + [0]) + 1
    for addition in rule_changes.get("add", []) or []:
        if not isinstance(addition, Mapping):
            raise PersonalError("Varje ny regel måste vara ett objekt med text.")
        rules.append(
            {
                "id": f"r{next_number}",
                "text": _clean_text(addition.get("text"), "text", max_length=600),
                "applies_to": _clean_targets(addition.get("applies_to", ["all"]), known_targets),
                "active": True,
            }
        )
        next_number += 1
    if len(rules) > 40:
        raise PersonalError("Högst 40 personliga regler. Slå ihop eller ta bort regler först.")

    return _commit(doc, {"profile": profile, "rules": rules}, note=note)


def _clean_targets(value: object, known_targets: set[str]) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise PersonalError("applies_to måste vara en lista med \"all\", stöd-id eller mitt:-id.")
    targets = []
    for target in value:
        if target != "all" and target not in known_targets:
            raise PersonalError(f"Okänt mål för regel: {target}.")
        targets.append(target)
    return sorted(set(targets))


def _commit(doc: dict[str, object], new_state: Mapping[str, object], *, note: str | None) -> dict[str, object]:
    old_state = {key: doc.get(key) for key in new_state}
    if old_state == dict(new_state):
        raise PersonalError("Ändringen ändrar ingenting.")
    history = list(doc.get("history", []))
    if int(doc.get("version", 0)) > 0:
        history.append(
            {
                "version": doc["version"],
                "saved_at": doc.get("saved_at"),
                "note": doc.get("note"),
                "snapshot": copy.deepcopy(old_state),
            }
        )
    doc.update(copy.deepcopy(dict(new_state)))
    doc["history"] = history[-MAX_HISTORY:]
    doc["version"] = int(doc.get("version", 0)) + 1
    doc["saved_at"] = now_iso()
    doc["note"] = note.strip()[:300] if isinstance(note, str) and note.strip() else None
    return doc


def restore(doc: Mapping[str, object], version: int) -> dict[str, object]:
    for entry in doc.get("history", []):
        if entry.get("version") == version:
            return _commit(copy.deepcopy(dict(doc)), entry["snapshot"], note=f"Återställd från version {version}")
    raise PersonalError(f"Version {version} finns inte i historiken. Tillgängliga: {history_versions(doc)}.")


def history_versions(doc: Mapping[str, object]) -> list[int]:
    return [int(entry["version"]) for entry in doc.get("history", [])]


def history_view(doc: Mapping[str, object]) -> list[dict[str, object]]:
    current = {"version": doc.get("version"), "saved_at": doc.get("saved_at"), "note": doc.get("note"), "current": True}
    older = [
        {"version": entry["version"], "saved_at": entry.get("saved_at"), "note": entry.get("note"), "state": entry["snapshot"]}
        for entry in reversed(doc.get("history", []))
    ]
    return [current, *older]


def render_profile(doc: Mapping[str, object]) -> str:
    lines = [
        "# Min arbetsprofil (Promptbanken Connect)",
        "",
        "Den här prompten håller dina personliga inställningar för Connect. Ändra den helst via Connect i chatten.",
        "",
    ]
    profile = doc.get("profile", {})
    for key, label in PROFILE_FIELDS.items():
        value = profile.get(key)
        if not value:
            continue
        lines.append(f"**{label}:** " + ("; ".join(value) if isinstance(value, list) else str(value)))
    rules = doc.get("rules", [])
    if rules:
        lines += ["", "## Personliga regler"]
        for rule in rules:
            state = "" if rule.get("active", True) else " (inaktiv)"
            lines.append(f"- [{rule['id']}] {rule['text']} – gäller: {', '.join(rule['applies_to'])}{state}")
    return _with_data(lines, doc)


# ---------------------------------------------------------------- arbetssätt


def apply_way_changes(
    current: Mapping[str, object] | None,
    fields: Mapping[str, object],
    *,
    note: str | None,
    support_ids: set[str],
) -> dict[str, object]:
    doc = copy.deepcopy(dict(current)) if current else {"connect_type": "way", "schema": SCHEMA, "version": 0, "history": []}
    state = {key: copy.deepcopy(doc.get(key)) for key in WAY_FIELDS if key in doc}
    for key, value in fields.items():
        if key not in WAY_FIELDS:
            raise PersonalError(f"Okänt fält för arbetssätt: {key}.")
        if key == "active":
            if not isinstance(value, bool):
                raise PersonalError("active måste vara true eller false.")
            state[key] = value
        elif key == "extends":
            if value in (None, ""):
                state.pop("extends", None)
            elif value not in support_ids:
                raise PersonalError(f"extends måste vara ett av: {', '.join(sorted(support_ids))}.")
            else:
                state[key] = value
        elif value is None or value == "" or value == []:
            if key in WAY_REQUIRED:
                raise PersonalError(f"Fältet {key} krävs.")
            state.pop(key, None)
        elif key in WAY_LIST_FIELDS:
            state[key] = _clean_list(value, key)
        else:
            state[key] = _clean_text(value, key, max_length=8000 if key == "instructions" else 1000)
    missing = [key for key in WAY_REQUIRED if not state.get(key)]
    if missing:
        raise PersonalError("Arbetssättet saknar " + ", ".join(missing) + ".")
    state.setdefault("active", True)
    if not doc.get("id"):
        doc["id"] = slugify(str(state["name"]))
    return _commit(doc, state, note=note)


def way_id(doc: Mapping[str, object]) -> str:
    return WAY_PREFIX + str(doc["id"])


def way_index_entry(doc: Mapping[str, object]) -> dict[str, object]:
    entry = {
        "id": way_id(doc),
        "name": doc.get("name"),
        "use_when": doc.get("use_when"),
        "not_when": doc.get("not_when", ""),
        "version": doc.get("version"),
        "active": doc.get("active", True),
    }
    if doc.get("extends"):
        entry["extends"] = doc["extends"]
    return entry


def render_way(doc: Mapping[str, object]) -> str:
    lines = [f"# {doc['name']} (mitt arbetssätt i Promptbanken Connect)", ""]
    for key, label in WAY_FIELDS.items():
        value = doc.get(key)
        if key == "name" or value in (None, "", []):
            continue
        if isinstance(value, list):
            lines += [f"**{label}:**", *[f"- {item}" for item in value]]
        elif isinstance(value, bool):
            lines.append(f"**{label}:** {'ja' if value else 'nej'}")
        else:
            lines.append(f"**{label}:** {value}")
    return _with_data(lines, doc)


def way_instructions(doc: Mapping[str, object]) -> str:
    parts = [f"# {doc['name']}", "", f"Syfte: {doc['purpose']}", "", str(doc["instructions"])]
    if doc.get("steps"):
        parts += ["", "## Steg", *[f"{number}. {step}" for number, step in enumerate(doc["steps"], start=1)]]
    if doc.get("quality_rules"):
        parts += ["", "## Kvalitetsregler", *[f"- {rule}" for rule in doc["quality_rules"]]]
    return "\n".join(parts)


# ---------------------------------------------------------------- gemensamt


def _with_data(lines: list[str], doc: Mapping[str, object]) -> str:
    data = json.dumps(doc, ensure_ascii=False, indent=1)
    content = "\n".join(lines) + "\n\n```connect-data\n" + data + "\n```\n"
    trimmed = dict(doc)
    while len(content) > MAX_CONTENT and trimmed.get("history"):
        trimmed["history"] = list(trimmed["history"])[1:]
        data = json.dumps(trimmed, ensure_ascii=False, indent=1)
        content = "\n".join(lines) + "\n\n```connect-data\n" + data + "\n```\n"
    if len(content) > MAX_CONTENT:
        raise PersonalError("Dokumentet blir för stort (max 20 000 tecken). Korta ned instruktionen eller reglerna.")
    return content


def diff(before: Mapping[str, object] | None, after: Mapping[str, object]) -> list[dict[str, object]]:
    old = _flat_state(before or {})
    new = _flat_state(after)
    changes = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            changes.append({"field": key, "before": old.get(key), "after": new.get(key)})
    return changes


def _flat_state(doc: Mapping[str, object]) -> dict[str, object]:
    flat: dict[str, object] = {}
    if doc.get("connect_type") == "profile" or "profile" in doc:
        for key, value in dict(doc.get("profile", {})).items():
            flat[f"profile.{key}"] = value
        for rule in doc.get("rules", []):
            flat[f"rule.{rule['id']}"] = {"text": rule["text"], "applies_to": rule["applies_to"], "active": rule.get("active", True)}
    else:
        for key in WAY_FIELDS:
            if key in doc:
                flat[key] = doc[key]
    return flat


def overlapping_rules(rules: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    active = [rule for rule in rules if rule.get("active", True)]
    pairs = []
    for index, first in enumerate(active):
        for second in active[index + 1:]:
            a, b = _words(str(first["text"])), _words(str(second["text"]))
            if a and b and len(a & b) / len(a | b) >= 0.5:
                pairs.append({"rules": [first["id"], second["id"]], "reason": "Reglerna säger nästan samma sak."})
    return pairs


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"\w+", text.casefold()) if len(word) > 2}


def applicable_rules(profile_doc: Mapping[str, object] | None, target: str, extends: str | None = None) -> list[dict[str, object]]:
    if not profile_doc:
        return []
    targets = {"all", target} | ({extends} if extends else set())
    return [
        {"id": rule["id"], "text": rule["text"]}
        for rule in profile_doc.get("rules", [])
        if rule.get("active", True) and targets & set(rule.get("applies_to", []))
    ]
