"""Rollbaserade paketrekommendationer (delprojekt 5). Statisk mappning
område -> roller, godkänd av Peter 2026-07-19 (se
docs/superpowers/specs/2026-07-19-rollbaserade-rekommendationer-design.md
i promptbanken-repot). Ingen nyckel, ingen lagrad roll -- ren funktion av
en klient-skickad rollterm.
"""
from __future__ import annotations

from typing import Any

from .skill_router import SkillRouter

# None = universellt (matchar alltid, oavsett roll).
_AREA_ROLES: dict[str, set[str] | None] = {
    "kommunikation": {"kommunikator", "handlaggare", "kundcenter"},
    "forandringsledning": {"samordnare", "verksamhetsutvecklare", "chef"},
    "processer": {"verksamhetsutvecklare", "utredare", "samordnare"},
    "beslutsberedning": {"utredare", "handlaggare", "chef", "sekreterare"},
    "visuellt": {"kommunikator", "pedagog"},
    "ledarskap": {"chef", "samordnare"},
    "arbetsbank": None,
}


def recommend(role: str, templates: list[dict[str, Any]]) -> dict[str, Any]:
    """templates: the full list_pro_templates() payload (area/area_label per row)."""
    areas: dict[str, str] = {}
    for t in templates:
        areas.setdefault(t["area"], t["area_label"])

    counts: dict[str, int] = {}
    for t in templates:
        counts[t["area"]] = counts.get(t["area"], 0) + 1

    normalized_role = SkillRouter._normalize(role)
    matched_areas = [
        area
        for area, roles in _AREA_ROLES.items()
        if area in areas and (roles is None or normalized_role in {SkillRouter._normalize(r) for r in roles})
    ]

    role_recognized = bool(matched_areas) and any(
        _AREA_ROLES[area] is not None for area in matched_areas
    )
    result_areas = matched_areas if role_recognized else list(areas.keys())

    packages = [
        {"area": area, "area_label": areas[area], "template_count": counts.get(area, 0)}
        for area in result_areas
    ]
    return {"role_recognized": role_recognized, "packages": packages}
