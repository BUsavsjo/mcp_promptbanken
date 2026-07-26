from __future__ import annotations

import re
from typing import Any


DEFAULT_BINDINGS = {
    "kontext": "generell",
    "roll": "handläggare",
    "malgrupp": "invånare",
    "ton": "tydligt och vänligt",
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

    return bindings


def render_template_text(template: str, bindings: dict[str, Any], schema: dict[str, Any] | None) -> str:
    legacy_field = schema.get("legacy_fallback_field") if isinstance(schema, dict) else None
    fallback_field = legacy_field if isinstance(legacy_field, str) and legacy_field else "input"
    normalized = str(template or "").replace("[]", "{{" + fallback_field + "}}")

    def replace_match(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(bindings.get(key, ""))

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace_match, normalized)


def render_template_variant(variant: dict[str, Any], render_bindings: dict[str, Any] | None = None) -> str:
    schema = variant.get("parameter_schema")
    normalized_schema = schema if isinstance(schema, dict) else None
    bindings = resolve_bindings(
        normalized_schema,
        variant.get("default_bindings") if isinstance(variant.get("default_bindings"), dict) else None,
        variant.get("binding_overrides") if isinstance(variant.get("binding_overrides"), list) else None,
        render_bindings,
    )
    return render_template_text(
        str(variant.get("prompt_text") or variant.get("intro_text") or ""),
        bindings,
        normalized_schema,
    )
