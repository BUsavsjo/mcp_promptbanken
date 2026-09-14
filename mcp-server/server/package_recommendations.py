"""Rollbaserade paketrekommendationer (delprojekt 5). Statisk mappning
område -> roller, godkänd av Peter 2026-07-19 (se
docs/superpowers/specs/2026-07-19-rollbaserade-rekommendationer-design.md
i promptbanken-repot). Ingen nyckel, ingen lagrad roll -- ren funktion av
en klient-skickad rollterm.

Mappningen är data, inte kontrakt: `role` är en fri sträng i den granskade
1.2.2-definitionen och `recommended_areas` är otypade strängar, så både
rollvokabulären och ordningen får ändras utan ny granskning.

Den statiska kartan är en grund. Ovanpå den läses roller ur paketets
målgrupp (`audience_label`, "Vem det är för" på webben), som sätts med
admin-MCP -- så nya paket och nya yrkesroller når rätt person utan kodändring.
"""
from __future__ import annotations

import logging
from typing import Any

from .skill_router import SkillRouter

logger = logging.getLogger(__name__)

# None = universellt (matchar alltid, oavsett roll). Varje publicerat paket
# ska finnas här -- ett paket som saknas kan aldrig rekommenderas till någon.
# test_every_published_area_is_accounted_for vaktar den regeln.
_AREA_ROLES: dict[str, set[str] | None] = {
    "kommunikation": {"kommunikator", "handlaggare", "kundcenter", "samordnare", "rektor", "administrator"},
    "forandringsledning": {"samordnare", "verksamhetsutvecklare", "chef", "rektor", "projektledare"},
    "processer": {"verksamhetsutvecklare", "utredare", "samordnare", "rektor", "analytiker", "projektledare"},
    "behov-till-effekt": {"verksamhetsutvecklare", "utredare", "samordnare", "chef", "projektledare"},
    "beslutsberedning": {"utredare", "handlaggare", "chef", "sekreterare", "rektor", "analytiker"},
    "visuellt": {"kommunikator", "pedagog", "larare"},
    "ledarskap": {"chef", "samordnare", "rektor"},
    "hr": {"hr", "chef", "rektor"},
    "skola-undervisning-larare": {"larare", "pedagog", "rektor"},
    "supportarenden": {"kundcenter", "handlaggare", "administrator"},
    "skarpare-funktionskrav": {"upphandlare", "inkopare", "utredare", "verksamhetsutvecklare"},
    "fran-ide-till-artikel": {"kommunikator", "journalist", "redaktor"},
    "workshop-och-facilitering": {
        "facilitator", "samordnare", "chef", "pedagog", "larare", "verksamhetsutvecklare", "projektledare",
    },
    # Workflowen är breda: de bär ett arbetssätt, inte en yrkesroll.
    "fran-fraga-till-researchunderlag": {
        "utredare", "analytiker", "samordnare", "handlaggare", "chef", "verksamhetsutvecklare",
        "kommunikator", "journalist", "redaktor", "upphandlare", "projektledare",
    },
    "data-till-forbattring": {"analytiker", "verksamhetsutvecklare", "utredare", "chef", "samordnare", "projektledare"},
    "behov-till-verifierad-digital-losning": {
        "verksamhetsutvecklare", "upphandlare", "inkopare", "utredare", "projektledare", "systemforvaltare", "chef",
    },
    "fran-behov-till-validerad-produkt": {"verksamhetsutvecklare", "produktagare", "entreprenor", "projektledare", "chef"},
    "fran-budskap-till-tydlig-dragning": {"chef", "projektledare", "utredare", "kommunikator", "samordnare", "larare"},
    "fran-ide-till-beslutsbart-business-case": {
        "chef", "verksamhetsutvecklare", "ekonom", "analytiker", "projektledare", "utredare",
    },
    # Universella: skrivstöd och arbetssätt som inte hör till en yrkesroll.
    "arbetsbank": None,
    "vardagspaket": None,
    "anti-slop": None,
    "hall-traden": None,
    "sag-emot-mig": None,
    "bemot-argument": None,
    "superplanlage": None,
}

# Ord folk faktiskt skriver -> rollordet katalogen är mappad på. Slår före
# sammansättningsregeln nedan, så "socialsekreterare" blir handläggare och
# inte sekreterare.
_ROLE_SYNONYMS: dict[str, str] = {
    "forskollarare": "larare",
    "grundskollarare": "larare",
    "gymnasielarare": "larare",
    "speciallarare": "larare",
    "specialpedagog": "pedagog",
    "fritidspedagog": "pedagog",
    "skolledare": "rektor",
    "personal": "hr",
    "personalchef": "hr",
    "personalspecialist": "hr",
    "personalvetare": "hr",
    "personalhandlaggare": "hr",
    "rekryterare": "hr",
    "lonespecialist": "hr",
    "hrbp": "hr",
    "socialsekreterare": "handlaggare",
    "kundtjanst": "kundcenter",
    "support": "kundcenter",
    "servicecenter": "kundcenter",
    "kontaktcenter": "kundcenter",
    "vaxel": "kundcenter",
    "inkopschef": "inkopare",
    "upphandlingsstrateg": "upphandlare",
    "informator": "kommunikator",
    "pressekreterare": "kommunikator",
    "skribent": "journalist",
    "webbredaktor": "redaktor",
    "moteshandlaggare": "sekreterare",
    "namndsekreterare": "sekreterare",
    "statistiker": "analytiker",
    "controller": "analytiker",
    "forskare": "utredare",
    "kvalitetsutvecklare": "verksamhetsutvecklare",
    "produktchef": "produktagare",
    "foretagare": "entreprenor",
    "grundare": "entreprenor",
    "projektchef": "projektledare",
}

_ROLE_AREA_PRIORITY = {
    "verksamhetsutvecklare": [
        "behov-till-effekt",
        "behov-till-verifierad-digital-losning",
        "data-till-forbattring",
        "fran-behov-till-validerad-produkt",
        "processer",
        "forandringsledning",
        "arbetsbank",
    ],
    # chatgpt-app-submission.json, testfall 1, visar de tre första för chef.
    "chef": [
        "forandringsledning",
        "beslutsberedning",
        "ledarskap",
        "behov-till-effekt",
        "fran-fraga-till-researchunderlag",
        "data-till-forbattring",
        "behov-till-verifierad-digital-losning",
        "hr",
        "workshop-och-facilitering",
        "fran-behov-till-validerad-produkt",
        "arbetsbank",
    ],
    "utredare": [
        "beslutsberedning",
        "fran-fraga-till-researchunderlag",
        "data-till-forbattring",
        "processer",
    ],
    "analytiker": [
        "data-till-forbattring",
        "fran-fraga-till-researchunderlag",
        "beslutsberedning",
        "processer",
    ],
    "projektledare": [
        "behov-till-effekt",
        "forandringsledning",
        "behov-till-verifierad-digital-losning",
        "processer",
        "workshop-och-facilitering",
    ],
    "rektor": [
        "ledarskap",
        "kommunikation",
        "processer",
        "forandringsledning",
        "beslutsberedning",
        "arbetsbank",
    ],
    "samordnare": [
        "forandringsledning",
        "processer",
        "behov-till-effekt",
        "fran-fraga-till-researchunderlag",
        "ledarskap",
        "kommunikation",
        "arbetsbank",
    ],
}

# Kortare rollord än så här får inte matcha som efterled: "hr" i slutet av ett
# ord säger ingenting, medan "chef" i "enhetschef" gör det.
_MIN_COMPOUND_HEAD = 4

# Samma gräns åt andra hållet: ett områdesord måste vara så här långt för att
# få matcha inuti en okänd rollterm ("upphandling" i "upphandlingsjurist").
_MIN_LEXICAL_WORD = 4

# Svensk böjning gör att ord som hör ihop sällan är delsträngar av varandra:
# "handläggare" och "handläggning" delar bara stammen. Så här många lika
# inledande tecken räknas som samma ord -- kort nog för att fånga stammen,
# långt nog för att "bibliotekarie" inte ska matcha "beslutsberedning".
_MIN_LEXICAL_PREFIX = 6

# Universella paket är bra för alla och säger därför inget om rollen. Fler än
# så här dränker rollens egna paket i svaret.
_MAX_UNIVERSAL_SUGGESTIONS = 2

# De två bredaste först: vardagsskrivande, sedan att bygga egna mallar.
_UNIVERSAL_ORDER = [
    "vardagspaket",
    "arbetsbank",
    "anti-slop",
    "hall-traden",
    "sag-emot-mig",
    "bemot-argument",
    "superplanlage",
]

# Ett publicerat paket som saknas i _AREA_ROLES loggas en gång per process.
# Det är den enda signalen om att kartan halkat efter katalogen igen.
_UNMAPPED_AREAS_LOGGED: set[str] = set()


# Ord i en målgruppstext som inte säger något om yrket ("För alla som arbetar
# med ..."). Stoppord och ord under fyra tecken faller bort redan innan.
_AUDIENCE_FILLER = {
    "alla", "andra", "arbetar", "behover", "eller", "inom", "jobbar", "manga", "personer", "samt", "sina", "vill",
}

# Målgruppstexter skriver yrken i plural: chefer, pedagoger, bibliotekarier.
_PLURAL_SUFFIXES = ("er", "ar", "or", "r")


def _all_role_words(area_roles: dict[str, set[str] | None] | None = None) -> set[str]:
    source = _AREA_ROLES if area_roles is None else area_roles
    return {SkillRouter._normalize(r) for roles in source.values() if roles for r in roles}


def _audience_role_words(label: str, known: set[str]) -> set[str]:
    """Yrkesorden i en målgruppstext. Ett känt rollord ("chefer" -> chef)
    vinner; ett okänt ord blir ett eget rollord, så nya yrken inte kräver
    kodändring."""
    roles: set[str] = set()
    for term in SkillRouter._terms(label.replace("-", " ")):
        if term in _AUDIENCE_FILLER or (len(term) < _MIN_COMPOUND_HEAD and term not in known):
            continue
        candidates = [term] + [
            term[: -len(suffix)] for suffix in _PLURAL_SUFFIXES
            if term.endswith(suffix) and len(term) - len(suffix) >= _MIN_COMPOUND_HEAD
        ]
        canonical = {role for candidate in candidates if (role := _canonical_role(candidate, known))}
        roles |= canonical or set(candidates)
    return roles


def _area_roles(audiences: dict[str, str | None] | None) -> dict[str, set[str] | None]:
    """Den statiska kartan plus rollerna ur varje pakets målgrupp. Målgruppen
    lägger bara till roller; universella paket förblir universella."""
    area_roles: dict[str, set[str] | None] = {
        area: (set(roles) if roles is not None else None) for area, roles in _AREA_ROLES.items()
    }
    if not audiences:
        return area_roles

    known = _all_role_words()
    for area, label in audiences.items():
        if not label or (area in _AREA_ROLES and _AREA_ROLES[area] is None):
            continue
        found = _audience_role_words(label, known)
        if found:
            area_roles[area] = (area_roles.get(area) or set()) | found
    return area_roles


def _canonical_role(term: str, role_words: set[str]) -> str | None:
    """Ett rollord i taget: exakt ord, känd synonym, eller sammansättning."""
    if term in role_words:
        return term
    synonym = _ROLE_SYNONYMS.get(term)
    if synonym:
        return synonym
    for word in role_words:
        if len(word) >= _MIN_COMPOUND_HEAD and len(term) > len(word) and term.endswith(word):
            return word
    return None


def _words(text: str) -> set[str]:
    return SkillRouter._terms(text.replace("-", " "))


def _shared_stem(first: str, second: str) -> bool:
    """Samma stam, olika böjning: handläggare/handläggning, process/processer."""
    shared = 0
    for a, b in zip(first, second):
        if a != b:
            break
        shared += 1
    return shared >= _MIN_LEXICAL_PREFIX


def _lexical_score(role_terms: set[str], area: str, label: str) -> int:
    """Hur mycket en okänd rollterm liknar paketets slug och rubrik."""
    area_words = _words(area) | _words(label or "")
    score = 0
    for term in role_terms:
        for word in area_words:
            if term == word:
                score += 2
            elif len(word) >= _MIN_LEXICAL_WORD and word in term:
                score += 1
            elif len(term) >= _MIN_LEXICAL_WORD and term in word:
                score += 1
            elif _shared_stem(term, word):
                score += 1
    return score


def _match_role(
    role: str, area_roles: dict[str, set[str] | None] | None = None
) -> tuple[set[str], str | None, str | None]:
    """-> (kanoniska rollord, matchat rollord, matchningskälla)."""
    role_words = _all_role_words(area_roles)
    normalized_whole = SkillRouter._normalize(role)
    # SkillRouter._terms splits on non-word chars, drops stopwords/short terms --
    # lets a compound role ("IT-samordnare barn och utbildning") match on any of
    # its component words, not just an exact whole-string role name.
    role_terms = SkillRouter._terms(role) | {normalized_whole}

    matched = {canonical for term in role_terms if (canonical := _canonical_role(term, role_words))}
    if not matched:
        return set(), None, None

    matched_role = sorted(matched)[0]
    source = "exact" if normalized_whole in role_words else "compound"
    return matched, matched_role, source


def _report_unmapped(areas: dict[str, str], area_roles: dict[str, set[str] | None]) -> list[str]:
    """Publicerade paket som varken kartan eller en målgrupp har rollmappat.
    Loggas, tappas aldrig tyst."""
    unmapped = [area for area in areas if area not in area_roles]
    for area in unmapped:
        if area not in _UNMAPPED_AREAS_LOGGED:
            _UNMAPPED_AREAS_LOGGED.add(area)
            logger.warning(
                "area_missing_role_mapping area=%s -- satt paketets malgrupp (audience_label) "
                "eller lagg till det i _AREA_ROLES, annars nas paketet bara av roller "
                "som rakar matcha dess slug",
                area,
            )
    return unmapped


def _ordered_areas(
    matched: set[str],
    matched_role: str | None,
    role_terms: set[str],
    areas: dict[str, str],
    area_roles: dict[str, set[str] | None],
) -> tuple[list[str], list[str]]:
    """-> (rollens egna områden, universella områden) i visningsordning."""
    specific = [
        area
        for area, roles in area_roles.items()
        if area in areas and roles and matched & {SkillRouter._normalize(r) for r in roles}
    ]

    priority = _ROLE_AREA_PRIORITY.get(matched_role or "")
    if priority:
        rank = {area: index for index, area in enumerate(priority)}
        specific.sort(key=lambda area: rank.get(area, len(rank)))
    else:
        # Utan handplockad ordning: det område vars slug och rubrik ligger
        # närmast rollordet först, så "lärare" möts av skolpaketet.
        specific.sort(key=lambda area: -_lexical_score(role_terms, area, areas.get(area, "")))

    # Ett nyss publicerat paket finns inte i kartan. Utan det här steget vore
    # det osynligt för varje igenkänd roll tills någon uppdaterar koden --
    # exakt den drift som gjorde att lärare och HR slutade fungera. Liknar det
    # rollordet får det följa med ändå.
    for area in _report_unmapped(areas, area_roles):
        if _lexical_score(role_terms, area, areas.get(area, "")) > 0:
            specific.append(area)

    universal = [
        area for area in _UNIVERSAL_ORDER if area in areas and _AREA_ROLES.get(area) is None
    ]
    return specific, universal[:_MAX_UNIVERSAL_SUGGESTIONS]


def role_focus_areas(
    role: str,
    templates: list[dict[str, Any]],
    audiences: dict[str, str | None] | None = None,
) -> tuple[bool, list[str]]:
    """Områden som search_templates ska ranka mot. Tom lista = ingen signal.

    Igenkänd roll ger sina egna områden (inte de universella -- de säger
    inget om rollen). Okänd roll ger de områden vars slug och rubrik faktiskt
    överlappar rollordet, som mest tre stycken.
    """
    areas: dict[str, str] = {}
    for t in templates:
        areas.setdefault(t["area"], t["area_label"])

    area_roles = _area_roles(audiences)
    matched, matched_role, _ = _match_role(role, area_roles)
    role_terms = SkillRouter._terms(role) | {SkillRouter._normalize(role)}

    if matched:
        specific, _universal = _ordered_areas(matched, matched_role, role_terms, areas, area_roles)
        return True, specific

    scored = [(area, _lexical_score(role_terms, area, label)) for area, label in areas.items()]
    hits = sorted([pair for pair in scored if pair[1] > 0], key=lambda pair: -pair[1])
    return False, [area for area, _score in hits[:3]]


def recommend(
    role: str,
    templates: list[dict[str, Any]],
    audiences: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """templates: the full list_templates() payload (area/area_label per row).
    audiences: paketets målgrupp per slug, som lägger till roller ovanpå kartan."""
    areas: dict[str, str] = {}
    for t in templates:
        areas.setdefault(t["area"], t["area_label"])

    counts: dict[str, int] = {}
    for t in templates:
        counts[t["area"]] = counts.get(t["area"], 0) + 1

    area_roles = _area_roles(audiences)
    matched, matched_role, role_match_source = _match_role(role, area_roles)
    role_terms = SkillRouter._terms(role) | {SkillRouter._normalize(role)}
    role_recognized = bool(matched)

    if role_recognized:
        specific, universal = _ordered_areas(matched, matched_role, role_terms, areas, area_roles)
        result_areas = specific + universal
    else:
        # Okänd roll behåller hela katalogen -- det är vad verktygsbeskrivningen
        # lovar -- men sorteras så att det som liknar rollordet kommer först.
        # Utan träff faller sorteringen tillbaka på katalogens egen ordning.
        _report_unmapped(areas, area_roles)
        result_areas = sorted(
            areas.keys(),
            key=lambda area: -_lexical_score(role_terms, area, areas.get(area, "")),
        )

    packages = [
        {"area": area, "area_label": areas[area], "template_count": counts.get(area, 0)}
        for area in result_areas
    ]

    return {
        "role_recognized": role_recognized,
        "packages": packages,
        "matched_role": matched_role,
        "role_match_source": role_match_source,
        "recommended_areas": [p["area"] for p in packages],
    }
