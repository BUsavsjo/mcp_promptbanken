# search_templates role-as-ranking-signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `search_templates`' `role` parameter from hard-filtering out templates whose area isn't among the role's recommended areas — make it a ranking bonus instead — and add match-explanation fields (`matched_role`, `role_match_source`, `recommended_areas`) to `recommend()`'s output so clients/testers can see why a role was (or wasn't) recognized.

**Architecture:** Two files change. `package_recommendations.py`'s `recommend()` gains three additive output fields computed from data it already has (no new inputs, no new state). `mcp_server.py`'s `_search_templates_payload()` drops the `allowed_areas` hard-filter branch and instead adds a `+5` score bonus to templates whose area is role-recommended, applied after the query-token inclusion cutoff so role can only re-rank already-relevant results, never rescue or exclude any. A `SERVICE_VERSION` constant bump and two docstring edits round it out.

**Tech Stack:** Python 3.12, no test framework in this repo (`CLAUDE.md`: "Inga automatiserade tester finns i repot ännu"). Verification uses the established manual pattern: a throwaway fixture script run via the venv's `python.exe`, then a live check against the deployed hosted server.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-search-templates-role-ranking-design.md`
- `area` and `risk_level` remain hard filters, applied before query scoring — unchanged.
- Query-token scoring weights (+2 title/tags, +1 syfte/output_format/area_label) and the "score > 0 required for inclusion when tokens is non-empty" cutoff are unchanged.
- Role bonus is exactly `+5`, added only to templates that already survived the area/risk_level/query cutoff — it must never be able to add a template back in or remove one.
- `recommend()`'s existing `role_recognized` and `packages` fields keep their current values/shape exactly — the three new fields are additive only.
- `role_match_source` values are exactly `"exact"`, `"compound"`, or `null` — no other values.
- `SERVICE_VERSION` default becomes exactly `"1.2.0"`.
- No new input parameters anywhere — `hosted_guard.py`'s allowlists need no changes.

---

### Task 1: `recommend()` gains matched_role / role_match_source / recommended_areas

**Files:**
- Modify: `mcp-server/server/package_recommendations.py:25-54` (the whole `recommend()` function body)

**Interfaces:**
- Consumes: `SkillRouter._terms(text: str) -> set[str]`, `SkillRouter._normalize(text: str) -> str` (both existing, unchanged, imported already at the top of this file), `_AREA_ROLES: dict[str, set[str] | None]` (existing module constant, unchanged).
- Produces: `recommend(role: str, templates: list[dict[str, Any]]) -> dict[str, Any]` — same signature as today, return dict now has five keys: `role_recognized: bool`, `packages: list[dict]` (unchanged shape/values), plus new `matched_role: str | None`, `role_match_source: str | None` (one of `"exact"`, `"compound"`, `None`), `recommended_areas: list[str]`. Task 2's `_search_templates_payload` reads these three new keys by name.

- [ ] **Step 1: Read current state to confirm line numbers**

Run: `grep -n "def recommend" mcp-server/server/package_recommendations.py`

Expected: one match, `def recommend(role: str, templates: list[dict[str, Any]]) -> dict[str, Any]:` at or near line 25 (line number may have drifted slightly — use the printed output to confirm, not the hardcoded number).

- [ ] **Step 2: Replace the function body**

Find:

```python
def recommend(role: str, templates: list[dict[str, Any]]) -> dict[str, Any]:
    """templates: the full list_templates() payload (area/area_label per row)."""
    areas: dict[str, str] = {}
    for t in templates:
        areas.setdefault(t["area"], t["area_label"])

    counts: dict[str, int] = {}
    for t in templates:
        counts[t["area"]] = counts.get(t["area"], 0) + 1

    # SkillRouter._terms splits on non-word chars, drops stopwords/short terms --
    # lets a compound role ("IT-samordnare barn och utbildning") match on any of
    # its component words, not just an exact whole-string role name.
    role_terms = SkillRouter._terms(role) | {SkillRouter._normalize(role)}
    matched_areas = [
        area
        for area, roles in _AREA_ROLES.items()
        if area in areas and (roles is None or role_terms & {SkillRouter._normalize(r) for r in roles})
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
```

Replace with:

```python
def recommend(role: str, templates: list[dict[str, Any]]) -> dict[str, Any]:
    """templates: the full list_templates() payload (area/area_label per row)."""
    areas: dict[str, str] = {}
    for t in templates:
        areas.setdefault(t["area"], t["area_label"])

    counts: dict[str, int] = {}
    for t in templates:
        counts[t["area"]] = counts.get(t["area"], 0) + 1

    # SkillRouter._terms splits on non-word chars, drops stopwords/short terms --
    # lets a compound role ("IT-samordnare barn och utbildning") match on any of
    # its component words, not just an exact whole-string role name.
    normalized_whole = SkillRouter._normalize(role)
    role_terms = SkillRouter._terms(role) | {normalized_whole}
    matched_areas = [
        area
        for area, roles in _AREA_ROLES.items()
        if area in areas and (roles is None or role_terms & {SkillRouter._normalize(r) for r in roles})
    ]

    role_recognized = bool(matched_areas) and any(
        _AREA_ROLES[area] is not None for area in matched_areas
    )
    result_areas = matched_areas if role_recognized else list(areas.keys())

    packages = [
        {"area": area, "area_label": areas[area], "template_count": counts.get(area, 0)}
        for area in result_areas
    ]

    all_role_words = {
        SkillRouter._normalize(r) for roles in _AREA_ROLES.values() if roles for r in roles
    }
    matched_role_terms = role_terms & all_role_words
    matched_role = sorted(matched_role_terms)[0] if matched_role_terms else None
    if matched_role is None:
        role_match_source = None
    elif normalized_whole in all_role_words:
        role_match_source = "exact"
    else:
        role_match_source = "compound"

    return {
        "role_recognized": role_recognized,
        "packages": packages,
        "matched_role": matched_role,
        "role_match_source": role_match_source,
        "recommended_areas": [p["area"] for p in packages],
    }
```

- [ ] **Step 3: Syntax-check the file**

Run: `python -c "import ast; ast.parse(open('mcp-server/server/package_recommendations.py', encoding='utf-8').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Verify with a fixture script**

Save this as `mcp-server/_verify_task1.py` (delete it in Step 5 after it passes — it is scratch, not part of the plan's file list):

```python
import sys
sys.path.insert(0, ".")
from server.package_recommendations import recommend

templates = [
    {"area": "forandringsledning", "area_label": "Förändringsledning"},
    {"area": "processer", "area_label": "Processer"},
    {"area": "ledarskap", "area_label": "Ledarskap"},
    {"area": "kommunikation", "area_label": "Kommunikation"},
    {"area": "arbetsbank", "area_label": "Arbetsbank"},
]

compound = recommend("IT-samordnare barn och utbildning", templates)
assert compound["role_recognized"] is True
assert compound["matched_role"] == "samordnare"
assert compound["role_match_source"] == "compound"
assert set(compound["recommended_areas"]) == {"forandringsledning", "processer", "ledarskap", "arbetsbank"}
assert compound["recommended_areas"] == [p["area"] for p in compound["packages"]]

exact = recommend("samordnare", templates)
assert exact["role_recognized"] is True
assert exact["matched_role"] == "samordnare"
assert exact["role_match_source"] == "exact"
assert set(exact["recommended_areas"]) == {"forandringsledning", "processer", "ledarskap", "arbetsbank"}

unknown = recommend("astronaut", templates)
assert unknown["role_recognized"] is False
assert unknown["matched_role"] is None
assert unknown["role_match_source"] is None
assert set(unknown["recommended_areas"]) == {"forandringsledning", "processer", "ledarskap", "kommunikation", "arbetsbank"}

print("ALL OK")
```

Run (PowerShell):

```
cd mcp-server
.\.venv\Scripts\python.exe _verify_task1.py
cd ..
```

Expected: `ALL OK`

- [ ] **Step 5: Delete the scratch verification file**

```
Remove-Item mcp-server\_verify_task1.py
```

- [ ] **Step 6: Commit**

```bash
git add mcp-server/server/package_recommendations.py
git commit -m "Lagg till matched_role/role_match_source/recommended_areas i recommend()"
```

---

### Task 2: `search_templates` uses role as a ranking bonus, not a filter

**Files:**
- Modify: `mcp-server/server/mcp_server.py:193-242` (`_search_templates_payload`)
- Modify: `mcp-server/server/mcp_server.py:486-490` (local `search_templates` docstring)
- Modify: `mcp-server/server/mcp_server.py:1446` (hosted JSON-RPC `role` property, currently no `description`)
- Modify: `mcp-server/server/mcp_server.py:131` (`SERVICE_VERSION` default)

**Interfaces:**
- Consumes: `recommend()`'s new return shape from Task 1 — specifically reads `role_recognized`, `packages` (via `{p["area"] for p in packages}`, same as today), and forwards `matched_role`/`role_match_source`/`recommended_areas` verbatim into its own payload when present.
- Produces: `_search_templates_payload(...)`'s return dict gains three new keys (`matched_role`, `role_match_source`, `recommended_areas`) alongside the existing `role_recognized`, all still only present when `role` was passed — same conditional-inclusion pattern the function already uses for `role_recognized`. No task after this one depends on these names.

- [ ] **Step 1: Read current state to confirm line numbers**

Run: `grep -n "def _search_templates_payload\|SERVICE_VERSION = \|def search_templates\|\"name\": \"search_templates\"" mcp-server/server/mcp_server.py`

Expected: matches near lines 131, 193, 486, 1434 (may have drifted — use the printed output).

- [ ] **Step 2: Replace `_search_templates_payload`'s body**

Find:

```python
def _search_templates_payload(
    query: str = "",
    role: str = "",
    area: str = "",
    risk_level: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    templates = _fetch_pro_templates("")

    allowed_areas: set[str] | None = None
    role_recognized: bool | None = None
    if role:
        recommendation = _recommend_packages(role, templates)
        role_recognized = recommendation["role_recognized"]
        if role_recognized:
            allowed_areas = {p["area"] for p in recommendation["packages"]}

    raw_tokens = re.findall(r"\w+", query.lower(), flags=re.UNICODE)
    tokens = [tok for tok in raw_tokens if len(tok) > 2 and SkillRouter._normalize(tok) not in SkillRouter.STOPWORDS]

    scored: list[tuple[int, dict[str, Any]]] = []
    for t in templates:
        if area and t["area"] != area:
            continue
        if risk_level and t.get("risk_level") != risk_level:
            continue
        if allowed_areas is not None and t["area"] not in allowed_areas:
            continue
        if tokens:
            strong = (t.get("title", "") + " " + " ".join(t.get("tags") or [])).lower()
            weak = " ".join([t.get("syfte", ""), t.get("output_format", ""), t.get("area_label", "")]).lower()
            score = sum(2 if tok in strong else 1 if tok in weak else 0 for tok in tokens)
            if score <= 0:
                continue
        else:
            score = 0
        scored.append((score, t))

    matches = [t for _, t in sorted(scored, key=lambda pair: pair[0], reverse=True)]
    clamped_limit = max(1, min(limit, len(templates) or 1))
    limited = matches[:clamped_limit]

    payload: dict[str, Any] = {
        "total_matches": len(matches),
        "returned": len(limited),
        "templates": [{k: t.get(k) for k in _TEMPLATE_SUMMARY_FIELDS} for t in limited],
    }
    if role:
        payload["role_recognized"] = role_recognized
    return payload
```

Replace with:

```python
def _search_templates_payload(
    query: str = "",
    role: str = "",
    area: str = "",
    risk_level: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    templates = _fetch_pro_templates("")

    role_bonus_areas: set[str] = set()
    recommendation: dict[str, Any] | None = None
    if role:
        recommendation = _recommend_packages(role, templates)
        if recommendation["role_recognized"]:
            role_bonus_areas = {p["area"] for p in recommendation["packages"]}

    raw_tokens = re.findall(r"\w+", query.lower(), flags=re.UNICODE)
    tokens = [tok for tok in raw_tokens if len(tok) > 2 and SkillRouter._normalize(tok) not in SkillRouter.STOPWORDS]

    scored: list[tuple[int, dict[str, Any]]] = []
    for t in templates:
        if area and t["area"] != area:
            continue
        if risk_level and t.get("risk_level") != risk_level:
            continue
        if tokens:
            strong = (t.get("title", "") + " " + " ".join(t.get("tags") or [])).lower()
            weak = " ".join([t.get("syfte", ""), t.get("output_format", ""), t.get("area_label", "")]).lower()
            score = sum(2 if tok in strong else 1 if tok in weak else 0 for tok in tokens)
            if score <= 0:
                continue
        else:
            score = 0
        if t["area"] in role_bonus_areas:
            score += 5
        scored.append((score, t))

    matches = [t for _, t in sorted(scored, key=lambda pair: pair[0], reverse=True)]
    clamped_limit = max(1, min(limit, len(templates) or 1))
    limited = matches[:clamped_limit]

    payload: dict[str, Any] = {
        "total_matches": len(matches),
        "returned": len(limited),
        "templates": [{k: t.get(k) for k in _TEMPLATE_SUMMARY_FIELDS} for t in limited],
    }
    if role and recommendation is not None:
        payload["role_recognized"] = recommendation["role_recognized"]
        payload["matched_role"] = recommendation["matched_role"]
        payload["role_match_source"] = recommendation["role_match_source"]
        payload["recommended_areas"] = recommendation["recommended_areas"]
    return payload
```

Note the `allowed_areas is not None and t["area"] not in allowed_areas: continue` line is gone entirely — that was the hard filter. The role bonus (`if t["area"] in role_bonus_areas: score += 5`) is added AFTER the `if score <= 0: continue` cutoff, so it can only affect the sort order of templates that already passed the query/area/risk_level gates, never add or remove one.

- [ ] **Step 3: Update the local docstring**

Find:

```python
    """Search the open Promptbanken template catalog without fetching all 42
    full prompts. Filter by free-text query (matched against title, syfte,
    tags, output format), role, area and/or risk_level. Returns lightweight
    summaries -- no prompt_text -- so use get_template(id) on a chosen result
    to fetch the full prompt."""
```

Replace with:

```python
    """Search the open Promptbanken template catalog without fetching all 42
    full prompts. Filter by free-text query (matched against title, syfte,
    tags, output format), area and/or risk_level. role ranks results toward
    relevant job functions -- it does not exclude templates from other
    areas. Returns lightweight summaries -- no prompt_text -- so use
    get_template(id) on a chosen result to fetch the full prompt."""
```

- [ ] **Step 4: Update the hosted JSON-RPC `role` property description**

Find (inside the `search_templates` entry of `_tool_definitions()`):

```python
                    "query": {"type": "string"},
                    "role": {"type": "string"},
                    "area": {
```

Replace with:

```python
                    "query": {"type": "string"},
                    "role": {
                        "type": "string",
                        "description": (
                            "Ranks results toward relevant job functions. Does not "
                            "exclude templates from other areas."
                        ),
                    },
                    "area": {
```

- [ ] **Step 5: Bump SERVICE_VERSION**

Find:

```python
SERVICE_VERSION = os.getenv("PROMPTBANKEN_MCP_VERSION", "1.1.0")
```

Replace with:

```python
SERVICE_VERSION = os.getenv("PROMPTBANKEN_MCP_VERSION", "1.2.0")
```

- [ ] **Step 6: Syntax-check the file**

Run: `python -c "import ast; ast.parse(open('mcp-server/server/mcp_server.py', encoding='utf-8').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 7: Verify with a fixture script**

Save as `mcp-server/_verify_task2.py` (delete after it passes):

```python
import sys, os
sys.path.insert(0, ".")
os.environ["PROMPTBANKEN_MCP_MODE"] = "hosted"
from server import mcp_server

templates = [
    {"id": "1", "title": "Driftstörningsinformation", "syfte": "Informera om avbrott", "area": "kommunikation", "area_label": "Kommunikation", "output_format": "", "tags": ["driftstörning"], "risk_level": "low"},
    {"id": "2", "title": "Rutin till processpaket", "syfte": "", "area": "processer", "area_label": "Processer", "output_format": "", "tags": ["process"], "risk_level": "low"},
]
mcp_server._fetch_pro_templates = lambda _key: templates

# query + role, no area: role can't exclude kommunikation even though
# samordnare's recommended areas don't include it.
r = mcp_server._search_templates_payload(query="driftstörning", role="IT-samordnare barn och utbildning")
assert r["total_matches"] == 1, r
assert r["templates"][0]["title"] == "Driftstörningsinformation"
assert r["role_recognized"] is True
assert r["matched_role"] == "samordnare"
assert r["role_match_source"] == "compound"
assert r["recommended_areas"] == ["forandringsledning", "processer", "ledarskap", "arbetsbank"]

# query + role + explicit conflicting area: area wins as a hard filter,
# role contributes zero bonus (kommunikation isn't role-recommended) but
# the template still appears because the query score alone was > 0.
r2 = mcp_server._search_templates_payload(query="driftstörning", role="IT-samordnare barn och utbildning", area="kommunikation")
assert r2["total_matches"] == 1, r2
assert r2["templates"][0]["title"] == "Driftstörningsinformation"

# role only, no query: nothing gets excluded, both templates returned.
r3 = mcp_server._search_templates_payload(role="IT-samordnare barn och utbildning")
assert r3["total_matches"] == 2, r3
assert r3["templates"][0]["title"] == "Rutin till processpaket", "role-bonused template (processer) should sort first"

# unknown role + query: still a hit, role_recognized False.
r4 = mcp_server._search_templates_payload(query="driftstörning", role="astronaut")
assert r4["total_matches"] == 1, r4
assert r4["role_recognized"] is False
assert r4["matched_role"] is None
assert r4["role_match_source"] is None

print("ALL OK")
```

Run (PowerShell):

```
cd mcp-server
.\.venv\Scripts\python.exe _verify_task2.py
cd ..
```

Expected: `ALL OK`

- [ ] **Step 8: Delete the scratch verification file**

```
Remove-Item mcp-server\_verify_task2.py
```

- [ ] **Step 9: Commit**

```bash
git add mcp-server/server/mcp_server.py
git commit -m "Gor role till en rankningssignal i search_templates, inte ett filter"
```

---

### Task 3: Documentation, deploy, and live verification

**Files:**
- Modify: `DECISIONS.md` (new dated entry, same pattern as the `84a7c46` entry already there)
- Modify: `LOG.md` (new dated entry)
- Modify: `TODO.md` (Klart section)
- No code files (deploy/verification only beyond the doc edits)

**Interfaces:**
- Consumes: the deployed VPS environment (`docker-compose`), the exact commit hashes from Tasks 1-2.
- Produces: nothing — final verification that Tasks 1-2 work in production against Peter's full acceptance table.

- [ ] **Step 1: Add a DECISIONS.md entry**

Add a new section at the top of `DECISIONS.md` (directly below the `# Beslut` header, above the existing `## 2026-07-20 - search_templates: OR/poängsatt matchning...` entry):

```markdown
## 2026-07-20 - search_templates: role som rankningssignal, inte filter

### Beslut
Peters andra omtest samma dag hittade att `role` i `search_templates`
fortfarande filtrerade bort mallar utanför rollens rekommenderade områden
(t.ex. `query=driftstörning` + `role=IT-samordnare...` + `area=kommunikation`
gav noll träffar). `allowed_areas`-hårdfiltret i `_search_templates_payload`
togs bort och ersattes med en `+5`-poängbonus som läggs till EFTER
query-poängens inklusions-gräns — role kan därmed bara omrangordna redan
relevanta träffar, aldrig lägga till eller ta bort någon. `recommend()`
utökades additivt med `matched_role`/`role_match_source`
(`"exact"`/`"compound"`/`null`)/`recommended_areas` för felsökning.
`SERVICE_VERSION` höjt till `1.2.0`. Se
`docs/superpowers/specs/2026-07-20-search-templates-role-ranking-design.md`.

### Skäl
Peters prioritetsordning var uttrycklig: area/risk_level är hårda filter,
query avgör relevans, role påverkar bara rangordningen. Föregående
implementation blandade ihop "role som rekommendation" med "role som
filter", vilket gjorde exakta träffar (rätt sökord, fel område enligt
rollen) osynliga trots att de var korrekta.

### Konsekvens
Ren beteendefix ovanpå redan deployad funktionalitet (`84a7c46`), ingen ny
yta, inga nya input-parametrar. Verifierat med fixture-skript för båda
filerna samt fullt liveanrop mot produktion med Peters exakta
acceptanstabell.
```

- [ ] **Step 2: Add a LOG.md entry**

Add a new section at the top of `LOG.md` (directly below the `# Logg` header):

```markdown
## 2026-07-20 (Peters andra MCP-omtest: role som filter, inte rankning)

### Gjort
- Peter identifierade att `role` i `search_templates` fortfarande hårdfiltrerade bort mallar utanför rollens rekommenderade områden, trots `84a7c46`s rollmatchningsfix. Konkret repro: `driftstörning` + `IT-samordnare...` + `area=kommunikation` gav 0 träffar.
- Fixat: `allowed_areas`-hårdfiltret i `_search_templates_payload` (`mcp_server.py`) borttaget, ersatt med en `+5`-rankningsbonus som läggs till efter query-scoreens inklusions-gräns — role kan bara omrangordna, aldrig lägga till/ta bort träffar. `recommend()` (`package_recommendations.py`) utökad additivt med `matched_role`/`role_match_source` (`exact`/`compound`/`null`)/`recommended_areas` för felsökning av rollmatchning. `role`-parameterns beskrivning uppdaterad i både lokal docstring och hostat JSON-RPC-schema. `SERVICE_VERSION` höjt `1.1.0` -> `1.2.0`.
- Verifierat: fixture-skript mot båda ändrade filerna (inkl. Peters exakta repro-frågor), sedan fullt liveanrop mot produktion mot hela Peters acceptanstabell efter deploy.
```

- [ ] **Step 3: Update TODO.md's Klart section**

Add a new first bullet directly below the `## Klart` header:

```markdown
- [x] **Fix (Peters andra MCP-omtest 2026-07-20):** `search_templates`s `role`-parameter är nu en rankningssignal (+5-poängbonus efter query-cutoffen), inte längre ett hårt filter — en mall med korrekt query-träff försvinner inte längre för att den ligger utanför rollens rekommenderade områden. `recommend()` returnerar nu även `matched_role`/`role_match_source`/`recommended_areas`. `SERVICE_VERSION` 1.1.0 -> 1.2.0. Se DECISIONS.md.
```

- [ ] **Step 4: Commit the documentation**

```bash
git add DECISIONS.md LOG.md TODO.md
git commit -m "Dokumentera role-som-rankningssignal-fixen i search_templates"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

- [ ] **Step 6: Deploy on the VPS**

```bash
cd /home/wenstrompeter/mcp_promptbanken
git pull origin main
docker-compose up -d --build
docker-compose ps
```

If it fails with `KeyError: 'ContainerConfig'` (the known `docker-compose` 1.29.2 recreate bug — see `TODO.md`), find and remove the stale container, then retry:

```bash
docker ps -a --filter name=promptbanken-mcp --format '{{.ID}}' | xargs -r docker rm -f
docker-compose up -d
docker-compose ps
```

- [ ] **Step 7: Verify the version bump live**

```bash
curl -s https://mcp.promptbanken.se/healthz
```

Expected: JSON containing `"version":"1.2.0"`.

- [ ] **Step 8: Verify Peter's full acceptance table live**

Run each of these against `https://mcp.promptbanken.se/mcp` (JSON-RPC `tools/call`, `name: "search_templates"` or `"recommend_packages"`) and confirm the expected result:

| Anrop | Förväntat |
|---|---|
| `search_templates(query="driftstörning")` | `templates[0].title == "Driftstörningsinformation"` |
| `search_templates(query="driftstörning", role="IT-samordnare barn och utbildning")` | samma, plus `role_recognized: true`, `matched_role: "samordnare"`, `role_match_source: "compound"` |
| `search_templates(query="driftstörning", area="kommunikation")` | samma |
| `search_templates(query="driftstörning", role="IT-samordnare barn och utbildning", area="kommunikation")` | samma (detta var 0 träffar innan denna fix) |
| `search_templates(role="IT-samordnare barn och utbildning")` (ingen query) | `total_matches` = hela katalogen, rollrekommenderade områden sorterade först |
| `search_templates(query="driftstörning", role="okänd-roll-xyz")` | fortfarande en träff, `role_recognized: false`, `matched_role: null` |
| `recommend_packages(role="samordnare")` | `role_match_source: "exact"` |

- [ ] **Step 9: If production doesn't match, do not silently patch docs**

If any row in Step 8's table doesn't match, treat it as a real bug (stale container from Step 6, or a genuine gap this plan missed) — fix the underlying cause and re-run Step 8 before considering this task complete. Do not edit DECISIONS.md/LOG.md/TODO.md wording to match an unexpected result without first confirming it isn't a stale-deploy artifact.
