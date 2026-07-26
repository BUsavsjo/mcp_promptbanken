from __future__ import annotations

import re
from typing import Any


DEFAULT_BINDINGS = {
    "kontext": "generell",
    "roll": "handläggare",
    "malgrupp": "invånare",
    "ton": "tydligt och vänligt",
}

TONE_FORMS = {
    "tydlig och vänlig": ("tydlig och vänlig", "tydligt och vänligt"),
    "tydligt och vänligt": ("tydlig och vänlig", "tydligt och vänligt"),
    "formell": ("formell", "formellt"),
    "formellt": ("formell", "formellt"),
    "neutral": ("neutral", "neutralt"),
    "neutralt": ("neutral", "neutralt"),
    "pedagogisk": ("pedagogisk", "pedagogiskt"),
    "pedagogiskt": ("pedagogisk", "pedagogiskt"),
    "varm och trygg": ("varm och trygg", "varmt och tryggt"),
    "varmt och tryggt": ("varm och trygg", "varmt och tryggt"),
}


def _schema_allowed_keys(schema: dict[str, Any] | None) -> set[str]:
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if isinstance(fields, list):
        allowed = {
            field.get("key")
            for field in fields
            if isinstance(field, dict) and isinstance(field.get("key"), str)
        }
    else:
        allowed = set(DEFAULT_BINDINGS)

    legacy_field = schema.get("legacy_fallback_field") if isinstance(schema, dict) else None
    allowed.add(legacy_field if isinstance(legacy_field, str) and legacy_field else "input")
    if "ton" in allowed:
        allowed.add("ton_neutrum")
    return allowed


def resolve_bindings(
    schema: dict[str, Any] | None,
    default_bindings: dict[str, Any] | None,
    binding_overrides: list[dict[str, Any]] | None,
    render_bindings: dict[str, Any] | None,
) -> dict[str, Any]:
    allowed = _schema_allowed_keys(schema)
    source = {
        **DEFAULT_BINDINGS,
        **(default_bindings or {}),
        **(render_bindings or {}),
    }
    bindings = {key: source[key] for key in allowed if key in source}

    for rule in binding_overrides or []:
        when = rule.get("when") if isinstance(rule, dict) else None
        set_values = rule.get("set") if isinstance(rule, dict) else None
        if not isinstance(when, dict) or not isinstance(set_values, dict):
            continue
        if all(bindings.get(key) == value for key, value in when.items()):
            bindings.update({key: value for key, value in set_values.items() if key in allowed})

    tone = str(bindings.get("ton") or "").strip()
    if tone:
        common_form, neuter_form = TONE_FORMS.get(tone.casefold(), (tone, tone))
        bindings["ton"] = common_form
        bindings["ton_neutrum"] = neuter_form

    return bindings


def render_template_text(template: str, bindings: dict[str, Any], schema: dict[str, Any] | None) -> str:
    legacy_field = schema.get("legacy_fallback_field") if isinstance(schema, dict) else None
    fallback_field = legacy_field if isinstance(legacy_field, str) and legacy_field else "input"
    normalized = str(template or "").replace("[]", "{{" + fallback_field + "}}")
    normalized = re.sub(
        r"\bett\s+\{\{\s*ton\s*\}\}",
        "ett {{ton_neutrum}}",
        normalized,
        flags=re.IGNORECASE,
    )

    def replace_match(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(bindings.get(key, ""))

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace_match, normalized)


def render_template_variant(variant: dict[str, Any], render_bindings: dict[str, Any] | None = None) -> str:
    schema = variant.get("parameter_schema")
    normalized_schema = schema if isinstance(schema, dict) else None
    default_bindings = dict(variant.get("default_bindings") or {})
    if variant.get("audience_label"):
        default_bindings.setdefault("malgrupp", variant["audience_label"])
    if variant.get("tone_hint"):
        default_bindings.setdefault("ton", variant["tone_hint"])
    bindings = resolve_bindings(
        normalized_schema,
        default_bindings,
        variant.get("binding_overrides") if isinstance(variant.get("binding_overrides"), list) else None,
        render_bindings,
    )
    return render_template_text(
        str(variant.get("prompt_text") or variant.get("intro_text") or ""),
        bindings,
        normalized_schema,
    )
