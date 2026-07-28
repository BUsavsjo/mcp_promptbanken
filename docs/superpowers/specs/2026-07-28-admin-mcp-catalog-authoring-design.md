# Admin-MCP: AI-klient-driven katalogförfattande via ny `/admin`-route

## Syfte

En separat, platform_owner-scopad MCP-yta (`/admin`) på den hostade
`mcp_promptbanken`-servern, så en AI-klient (Peter) kan skapa, redigera och
publicera prompts/paket i den öppna katalogen konversationellt, istället för
att fylla i formulär i `admin.html`. Måste hållas strikt separat från den
read-only `/mcp`/`/sse`-ytan (se
`2026-07-27-render-contract-parametric-templates-design.md`) — ingen
regression av det beslutet.

## Verifierad nulägesbild (2026-07-28)

### Två separata malldatabaser — viktigt för scope

- `public.pro_prompt_templates` (skapad `20260702160000`): den ÄLDRE, flata
  Pro-mallkatalogen (42 rader), har redan `risk_level`/`area`/`tags`/
  `output_format`/`security_examples`. Läses av `list_my_private_prompts` m.fl.
  via `get_pro_templates_for_mcp_key`. `copy_template_to_valvet`/
  `copy_template_to_valvet_for_key` (`promptbanken`-repot,
  `20260727141513_repair_valvet_provenance_schema.sql`) kopierar FRÅN denna
  tabell till `content_items`, med `source_version` = en sha256-hash av
  mallens innehåll vid kopieringstillfället.
- `public.catalog_prompts`/`catalog_prompt_variants`/`catalog_packages`
  (skapad `20260721100000_catalog_core.sql`): den NYARE "dynamiska
  katalogplattformen", byggd explicit för att både webben och MCP:n ska läsa
  samma data. `mcp_server.py`s `list_templates`/`get_template`/`list_packages`/
  `get_package`/`list_package_prompts` läser DENNA tabellfamilj, via
  `catalog.py`s `list_published_prompts`/`get_published_prompt` m.fl.
  (`from . import catalog as _catalog`, `mcp_server.py:23`).
  `admin.js` skriver redan till denna familj via RPC:er
  (`create_catalog_prompt`, `upsert_catalog_prompt_variant`,
  `publish_catalog_prompt`, paket-motsvarigheter), alla i
  `20260721150000_catalog_write_rpc_authorization.sql`, alla självkontrollerande
  `app_private.current_user_is_platform_owner()`.

**Konsekvens för scope:** Admin-MCP:t ska skriva till `catalog_prompts`-familjen
(det MCP:n faktiskt serverar), INTE till `pro_prompt_templates`. Det innebär
att prereq "versionering/rollback så Valvet-kopior inte tyst går sönder"
(ursprungligen identifierad 2026-07-27) **inte gäller** detta projekt —
`catalog_prompts` har idag ingen kopieringsrelation till Valvet alls. Flaggas
som öppen fråga för framtiden (om/när Valvet-kopiering utökas till att även
gälla `catalog_prompts`), inte som blockerare nu.

### Bekräftade luckor i skriv-RPC:erna

- `upsert_catalog_prompt_variant`/paket-motsvarigheten accepterar INTE
  `parameter_schema`/`default_bindings`/`binding_overrides` — dessa kolumner
  lades till i `20260725133000_catalog_parameter_schemas.sql` men
  RPC-signaturen uppdaterades aldrig. De ~10 parametriserade rader som finns
  idag (`20260725140000_sync_parameterized_catalog_prompts.sql`) sattes via en
  engångs-seed-migration, inte via någon app-RPC.
- `catalog_prompts`/`catalog_prompt_variants` saknar helt kolumnerna
  `risk_level`/`area`/`tags`/`output_format` (till skillnad från
  `pro_prompt_templates`, som redan har dem).

### Auth-mismatch (den centrala arkitekturfrågan)

`app_private.current_user_is_platform_owner()` läser `auth.uid()` — kräver en
riktig Supabase Auth-session (`Authorization: Bearer <access_token>`,
roll `authenticated`). Dagens MCP-modell (`X-MCP-Key` → hash-slagning mot
`api_keys`) har ingen `auth.uid()` alls. De två auth-modellerna är
oförenliga utan brygga.

## Beslut (Peter, 2026-07-28)

1. **Auth-brygga:** riktig Supabase-JWT, inte en ny nyckeltyp. Servern håller
   Peters platform_owner-**refresh_token** som hemlighet
   (`SUPABASE_ADMIN_REFRESH_TOKEN`, engångsinloggning för att hämta den),
   växlar in ett färskt access_token per anrop/cache:ar kort. RLS och
   befintliga RPC:er förblir helt oförändrade.
2. **Scope:** fullt paket i ett svep — text-prompts, parametriska fält, ny
   metadata-migration, paketstöd, audit/rate-limit, contract-test — inte en
   smal v1 följt av uppföljande specs.
3. **Route:** ny `/admin`-route i `mcp_server.py`s befintliga Starlette
   route-lista, egen FastMCP-verktygsuppsättning, gated av ett dedikerat
   bearer-secret `PROMPTBANKEN_ADMIN_KEY` (skilt från
   `PROMPTBANKEN_MCP_API_KEY`). **Fail-closed**: servern vägrar montera
   `/admin` om secret saknas — till skillnad från dagens valfria globala
   bearer-mönster. Detta är den enda spärren mellan "internet" och
   plattformsbred katalogskrivning, eftersom servern internt alltid agerar
   som platform_owner oavsett anropare — RLS diskriminerar inte mellan
   "Peters AI-klient" och "vem som helst som hittar routen".

## Migration (ny, i `promptbanken`-repot)

- `catalog_prompts`/`catalog_prompt_variants`: lägg till `risk_level text`,
  `area text`, `tags text[]`, `output_format text`. Backfill:e befintliga
  ~10 rader (rimliga default-värden, manuellt kuraterat av Peter eller ett
  engångsskript) INNAN kolumnerna sätts `not null`.
- Utöka `upsert_catalog_prompt_variant`/paket-motsvarigheten med parametrarna
  `p_parameter_schema jsonb`, `p_default_bindings jsonb`,
  `p_binding_overrides jsonb`, samt `p_risk_level text`, `p_area text`,
  `p_tags text[]`, `p_output_format text`. Grundläggande strukturvalidering i
  plpgsql (t.ex. `parameter_schema` måste vara ett jsonb-objekt om satt,
  `binding_overrides` måste vara en jsonb-array) — ingen extern
  schema-valideringslib, men avvisa uppenbart fel form innan insert/update.
- Skärp `publish_catalog_prompt`/`publish_catalog_package`: kräv att
  `risk_level`/`area`/`tags`/`output_format` är satta (inte bara att
  `generell`-varianten finns) innan status kan bli `published`.
- Ny tabell `app_private.admin_write_attempts` (prompt/package-id, tool,
  gammal/ny variant-snapshot som jsonb, `created_at`) — loggar VARJE
  admin-skrivning (inte bara avvisade, till skillnad från
  `mcp_write_attempts`), ger manuell SQL-rollback-väg utan att bygga en
  rollback-UI i v1.

## Nya MCP-verktyg (`mcp_promptbanken`-repot, prefix `admin_`)

- `admin_create_prompt(slug, title, summary, prompt_text, risk_level, area, tags, output_format, parameter_schema?, default_bindings?, binding_overrides?)`
  — skapar draft + `generell`-variant i ett anrop.
- `admin_upsert_prompt_variant(prompt_id, context_key, ...)` — lägg
  till/redigera en kontextvariant (skola/kommun/etc). Redigering av en redan
  publicerad prompt går genom samma verktyg (upsert, inte insert-only) — se
  `admin_write_attempts` ovan för historik istället för en dedikerad
  rollback-mekanism.
- `admin_list_draft_prompts()` / `admin_get_prompt(prompt_id)` — granska
  innan publicering.
- `admin_publish_prompt(prompt_id, confirm: bool)` — explicit
  `confirm`-flagga (samma mönster som `copy_template_to_valvet`/
  `archive_my_item`).
- `admin_create_package`, `admin_add_prompt_to_package`,
  `admin_publish_package(confirm: bool)` — paket-motsvarigheter.

Alla åtta verktyg läggs i `hosted_guard.py`s allowlist under en EGEN
metod-uppsättning (inte `allowed_methods`/`allowed_tool_args` som redan
gäller `/mcp`/`/sse` — dessa 8 namn får ALDRIG förekomma där), och i en
separat FastMCP-instans/route som bara monteras på `/admin`.

## Audit/rate-limit

Separat rate-limit-räknare från `mcp_write_attempts` (den är per
användarnyckel; detta är enanvändar-men-plattformsbrett — ett komprometterat
`PROMPTBANKEN_ADMIN_KEY` är en helt annan risknivå). Tak t.ex. 30
skrivningar/60s, samma mönster som `copy_template_to_valvet_for_key`s
räknare.

## Contract-test admin-profil

Utöka `promptbanken-mcp-contract-test` med en `admin`-profil:

1. Anropa `/mcp`, `/sse`, `/api/v1/*` UTAN `PROMPTBANKEN_ADMIN_KEY` och
   bekräfta att inget av de 8 `admin_*`-verktygen syns i `tools/list`.
2. Anropa `/admin` UTAN `PROMPTBANKEN_ADMIN_KEY` och bekräfta 401.
3. Anropa `/admin` MED nyckeln: full runda
   create → upsert_variant → publish → verifiera på `/mcp` (`get_template`
   ser den nya publicerade prompten), mot en slit-och-släng-slug.

## Öppna frågor / senare (inte blockerande för detta projekt)

- Om Valvet-kopiering någon gång utökas till att gälla `catalog_prompts`
  (inte bara `pro_prompt_templates`), måste versionering/provenance-frågan
  tas upp på nytt då.
- Ingen dedikerad rollback-UI/verktyg i v1 — `admin_write_attempts`-loggen
  räcker för manuell SQL-återställning tills ett verkligt behov uppstår.
