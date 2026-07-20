# search_templates: role som rankningssignal, inte filter

## Syfte

Peters omtest (samma dag som `84a7c46` fixade AND-matchning och exakt
rollmatchning) hittade en kvarvarande brist: `role` i `search_templates`
används idag som ett HÅRT filter — en mall vars område inte finns bland
rollens rekommenderade områden faller bort helt, även om frågan i övrigt
matchar perfekt. Konkret repro: `query="driftstörning"`,
`role="IT-samordnare barn och utbildning"`, `area="kommunikation"` gav
noll träffar, trots att `driftstörning` finns i katalogen (kommunikation
är inte bland `samordnare`s rekommenderade områden). Denna spec gör `role`
till en rankningssignal istället för ett filter, utan att röra
rolligenkänningslogiken från `84a7c46`.

## Nuläge

`_search_templates_payload()` (`mcp-server/server/mcp_server.py:193-242`):

```python
allowed_areas: set[str] | None = None
role_recognized: bool | None = None
if role:
    recommendation = _recommend_packages(role, templates)
    role_recognized = recommendation["role_recognized"]
    if role_recognized:
        allowed_areas = {p["area"] for p in recommendation["packages"]}
...
for t in templates:
    if area and t["area"] != area:
        continue
    if risk_level and t.get("risk_level") != risk_level:
        continue
    if allowed_areas is not None and t["area"] not in allowed_areas:
        continue
    ...
```

`allowed_areas` (rad 219) är ett hårt filter — exakt samma prioritet som
`area`/`risk_level`, fast den ska inte vara det.

## Ändringar

### 1. Filtrerings-/rankningsordning (`mcp_server.py`, `_search_templates_payload`)

Ny ordning, i linje med Peters prioritetslista:

1. `area` — hårt filter (oförändrat).
2. `risk_level` — hårt filter (oförändrat).
3. Query-tokens avgör relevans (oförändrad poängsättning: +2 vid
   träff i titel/taggar, +1 vid träff i syfte/outputformat/area_label).
   Finns tokens: mall inkluderas bara vid poäng > 0 (oförändrat cutoff).
   Inga tokens (tom query): alla kvarvarande mallar inkluderas med
   grundpoäng 0 (oförändrat).
4. `role` — bonuspoäng, appliceras EFTER inklusions-cutoffen i punkt 3,
   bara på mallar som redan finns kvar: `+5` om mallens `area` finns i
   rollens rekommenderade områden (samma `_recommend_packages`-anrop som
   idag, bara inte längre använt för att exkludera).

`allowed_areas`-variabeln och dess `continue`-gren (rad 219-220) tas bort.
Role-bonusen läggs till i samma loop, efter query-poängen är beräknad:

```python
role_bonus_areas: set[str] = set()
role_recognized: bool | None = None
recommendation: dict[str, Any] | None = None
if role:
    recommendation = _recommend_packages(role, templates)
    role_recognized = recommendation["role_recognized"]
    if role_recognized:
        role_bonus_areas = {p["area"] for p in recommendation["packages"]}

...
for t in templates:
    if area and t["area"] != area:
        continue
    if risk_level and t.get("risk_level") != risk_level:
        continue
    if tokens:
        strong = (...)
        weak = (...)
        score = sum(...)
        if score <= 0:
            continue
    else:
        score = 0
    if t["area"] in role_bonus_areas:
        score += 5
    scored.append((score, t))
```

Effekt på Peters exempel: `driftstörning` + `IT-samordnare...` +
`area=kommunikation` — `area`-filtret släpper igenom kommunikations-mallar
(inkl. Driftstörningsinformation), query-poängen matchar `driftstörning`
i titeln (+2), rollbonusen blir 0 (kommunikation är inte bland
`samordnare`s områden) — mallen inkluderas ändå eftersom query-poängen
redan var > 0. Ingen mall kan längre försvinna enbart för att den ligger
utanför rollens rekommenderade områden.

### 2. `role`-beskrivning (`mcp_server.py`)

Lägg till en `description` på `role`-fältet, både i den hostade
JSON-RPC-definitionens `inputSchema.properties.role` (idag
`{"type": "string"}` utan beskrivning, rad ~1446) och i den lokala
`@mcp.tool() def search_templates(...)`-docstringen (rad ~486-490):

> "Ranks results toward relevant job functions. Does not exclude
> templates from other areas."

### 3. Rollmatchnings-förklaring (`package_recommendations.py`, `recommend()`)

`recommend()` returnerar idag `{"role_recognized": bool, "packages": [...]}`.
Utökas additivt (inget befintligt fält tas bort eller byter betydelse) med:

- `matched_role`: det specifika kända rollordet som triggade matchningen
  (t.ex. `"samordnare"`), eller `null` om `role_recognized` är `false`.
- `role_match_source`: `"exact"` om hela den normaliserade rollsträngen
  själv är ett känt rollord (t.ex. `role="samordnare"`), `"compound"` om
  ett känt rollord hittades som ETT delord i en flerordig/sammansatt
  rollsträng (t.ex. `"samordnare"` inuti `"IT-samordnare barn och
  utbildning"`). `null` om inte igenkänd. (Peters exempel använde
  `"compound_title"` — förenklat till `"compound"` här eftersom det inte
  finns något separat titelbegrepp i denna funktion, bara den råa
  rollsträngen. Flagga om den ursprungliga etiketten föredras.)
- `recommended_areas`: samma områden som redan finns i `packages[].area`,
  som en platt lista (`[p["area"] for p in packages]`) — bekvämlighetsfält
  för klienter som bara vill ha områdesnamnen utan att packa upp
  `packages`. `packages` (med `area_label`/`template_count`) behålls
  oförändrat.

`_search_templates_payload` vidarebefordrar alla tre nya fälten till sitt
svar när `role` skickas in, på samma sätt som den redan gör med
`role_recognized` (rad 240-241).

Implementation i `recommend()`: när `role_terms & {normalized roles för
ett område}` ger en träff, avgörs `matched_role` som det specifika
rollordet ur områdets rollmängd som fanns i skärningen (första träffen är
tillräckligt — samma rollord är per definition samma oavsett vilket
matchat område man tittar på, eftersom `_AREA_ROLES` är en delad
rollvokabulär). `role_match_source` avgörs genom att jämföra: matchade
`SkillRouter._normalize(role)` (hela strängen) direkt mot rollmängden →
`"exact"`; annars (matchade via ett delord ur `SkillRouter._terms(role)`)
→ `"compound"`.

### 4. Versionsbump

`SERVICE_VERSION = os.getenv("PROMPTBANKEN_MCP_VERSION", "1.1.0")` →
default `"1.2.0"` (`mcp_server.py:131`). Minor-bump eftersom både
svarsform (nya fält) och filtreringsbeteende ändras — mer än en patch.
Ingen ny `build`-fält läggs till (YAGNI, en versionsbump räcker för det
Peter efterfrågade).

## Uttryckligen oförändrat

- Rolligenkänningslogiken i sig (`84a7c46`s tokeniserade delords-matchning
  i `recommend()`s `matched_areas`-beräkning) — bara vad `role_recognized`
  ANVÄNDS till i `search_templates` ändras (rankning istället för filter).
- `area`/`risk_level` som hårda filter, `query`-poängsättningens
  trösklar/vikter (+2/+1 per token).
- `recommend_packages`-verktygets `packages`-fält (form/innehåll
  oförändrat, bara tre nya syskonfält).
- Inga nya input-parametrar — `hosted_guard.py`s allowlist för
  `search_templates`/`recommend_packages` behöver inga ändringar.

## Testplan

Manuell verifiering (inget testramverk i repot), samma mönster som
`84a7c46`: en lokal fixture-baserad kontroll av scoring-/bonuslogiken samt
en full runda mot produktions-liknande data efter deploy.

Acceptanstabellen från Peters rapport, körd mot den riktiga hostade
servern efter deploy:

| Sökning | Förväntat resultat |
|---|---|
| `driftstörning` | Driftstörningsinformation |
| `driftstörning` + IT-samordnare | Driftstörningsinformation |
| `driftstörning` + kommunikation (area) | Driftstörningsinformation |
| `driftstörning` + IT-samordnare + kommunikation (area) | Driftstörningsinformation |
| Endast IT-samordnare (ingen query) | Rollrekommenderade mallar först, hela katalogen kvar |
| Okänd roll + `driftstörning` | Träff ändå, `role_recognized: false` |

Dessutom: `recommend_packages(role="IT-samordnare barn och utbildning")`
ska ge `matched_role: "samordnare"`, `role_match_source: "compound"`,
`recommended_areas: ["forandringsledning", "processer", "ledarskap",
"arbetsbank"]`. `recommend_packages(role="samordnare")` ska ge
`role_match_source: "exact"` med samma `recommended_areas`.

## Dokumentation

`DECISIONS.md`/`LOG.md`/`TODO.md` uppdateras efter verifiering, samma
mönster som `84a7c46`.
