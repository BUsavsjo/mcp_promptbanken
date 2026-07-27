# Logg

## 2026-07-25 (Externt regressionstest: fix av publik verktygsyta och search_templates-krasch)

### Gjort
- Läste den externa testrapporten för den öppna MCP-katalogen och avgränsade arbetet till de två blockerande P0-fynd som gick att verifiera direkt i koden: `search_templates` som kraschar på meningsfull fritext, och publik `tools/list` som exponerar privata/skrivande verktyg utan nyckel.
- Lade till två nya regressionstester i `mcp-server/tests/test_catalog_context_tools.py`: ett som reproducerar kraschen när katalogmetadata innehåller `null` i textfält, och ett som låser att `tools/list` utan MCP-nyckel bara returnerar den publika read-only-katalogytan.
- Fixade `_search_templates_payload()` i `mcp-server/server/mcp_server.py` så att `title`, `syfte`, `output_format`, `area_label`, `tone_hint` och `tags` normaliseras defensivt till sträng/lista innan fritextmatchning byggs. Därmed dör inte sökningen längre på `TypeError` när katalog-RPC:n returnerar `null`.
- Gjorde `tools/list` kapabilitetsstyrd i samma fil: `_tool_definitions(mcp_key)` filtrerar nu bort användarspecifika, Valvet- och skrivverktyg när anropet saknar MCP-nyckel. Den öppna connectorn visar därmed bara publik katalog, skill-metadata, status och routing.

### Verifierat
- `.venv\\Scripts\\python.exe -m unittest tests.test_catalog_context_tools -v` -> 5 tester gröna.
- `.venv\\Scripts\\python.exe -m compileall server tests` -> grönt.
- `npm run check:python` -> grönt.

### Kvarstår
- Ingen deploy till VPS/produktionen i detta pass.
- Testrapportens P1/P2-fynd kvarstår, främst `context_key: null`, ofullständig `area`-metadata i katalogadaptern och föråldrade routinginstruktioner.

## 2026-07-25 (Kontextprofiler i öppen katalog för hostade MCP:n)

### Gjort
- Portade hostade katalogläsningen från gamla `get_pro_templates_for_mcp_key`-formatet till den nya publika katalogen i `promptbanken`-repot via nya RPC-anrop i `mcp-server/server/catalog.py`: `list_published_prompts`, `get_published_prompt`, `list_published_packages`, `get_published_package`, `list_published_package_prompts`, alla med `p_context_keys text[]`.
- Behöll bakåtkompatibla tool-namn för användarsidan: `list_templates`, `search_templates`, `get_template` finns kvar men accepterar nu valfri `context_keys`-lista och läser från den nya katalogen i stället. Lade också till nya kompletterande tools `list_packages`, `get_package`, `list_package_prompts`.
- Lade ett tunt adapterlager i `mcp_server.py` som mappar nya katalogfält (`summary`, `audience_label`, `tone_hint`, `slug`) till det äldre template-formatet så befintliga klienter inte behöver byta direkt.
- Uppdaterade `hosted_guard.py` så `context_keys` och de nya paketverktygen tillåts och valideras i hosted-läge.
- Lade till riktade regressionstester i `mcp-server/tests/test_catalog_context_tools.py` för tre saker: `list_templates(context_keys)` via JSON-RPC-dispatch, tool-schema/definitions för nya parametrar och pakettools, samt att hosted guard accepterar `context_keys`.

### Verifierat
- `python -m unittest tests.test_catalog_context_tools -v` -> 3 tester gröna.
- `python -m compileall server tests` -> grönt.
- `npm run check:python` -> grönt (`Listing 'server'...` utan fel).

### Kvarstår
- Deploy till VPS/produktionen är inte gjord i detta arbetspass.
- Ingen liveverifiering mot `https://mcp.promptbanken.se/mcp` ännu efter denna kodändring.

## 2026-07-25 (Docker healthcheck + autoheal efter tyst hang)

### Gjort
- Upptäckt via ny VPS-deploy-skillens statuskoll: `promptbanken-mcp`-containern hade hängt sen ca 10:35 (TCP accepterade anslutningar, HTTP-svar kom aldrig — inget krasch i loggarna, `docker ps` visade ändå "Up"). `docker-compose`s `restart: unless-stopped` fångar bara process-exit, inte ett hängande event loop.
- Lade till `healthcheck` i `docker-compose.yml` för `promptbanken-mcp` (Python `urllib` mot `/healthz`, ingen curl i imagen) + en `autoheal`-sidecar (`willfarrell/autoheal`, pinnad på digest) som restartar containern automatiskt när Docker markerar den `unhealthy`.
- Deploy: `ef7b53d` pushat till origin/main, dragit på VPS:en, `docker-compose up -d --build`. Samma kända `KeyError: 'ContainerConfig'`-bugg vid recreate som tidigare (se 2026-07-20-posten) — löst med samma workaround (`docker rm -f` på den omdöpta containern, sedan plain `up -d`). Verifierat: `docker ps` visar `healthy`, `/healthz` svarar 200.
- Bakgrunds-säkerhetsgranskning flaggade `docker.sock`-mounten i `autoheal` som container-escape-risk (root-ekvivalent host-access om autoheal-imagen komprometteras) och den opinnade `willfarrell/autoheal:latest`-taggen som supply-chain-risk. Den andra fixad direkt (pinnad till digest). Den första är ett inneboende tradeoff i autoheal-mönstret — kvar i TODO.md för medvetet beslut, inte byggt bort.

## 2026-07-20 (Peters andra MCP-omtest: role som filter, inte rankning)

### Gjort
- Peter identifierade att `role` i `search_templates` fortfarande hårdfiltrerade bort mallar utanför rollens rekommenderade områden, trots `84a7c46`s rollmatchningsfix. Konkret repro: `driftstörning` + `IT-samordnare...` + `area=kommunikation` gav 0 träffar.
- Fixat: `allowed_areas`-hårdfiltret i `_search_templates_payload` (`mcp_server.py`) borttaget, ersatt med en `+5`-rankningsbonus som läggs till efter query-scoreens inklusions-gräns — role kan bara omrangordna, aldrig lägga till/ta bort träffar. `recommend()` (`package_recommendations.py`) utökad additivt med `matched_role`/`role_match_source` (`exact`/`compound`/`null`)/`recommended_areas` för felsökning av rollmatchning. `role`-parameterns beskrivning uppdaterad i både lokal docstring och hostat JSON-RPC-schema. `SERVICE_VERSION` höjt `1.1.0` -> `1.2.0`.
- Verifierat: fixture-skript mot båda ändrade filerna (inkl. Peters exakta repro-frågor), sedan fullt liveanrop mot produktion mot hela Peters acceptanstabell efter deploy.

## 2026-07-20 (Peters MCP-omtest efter search_templates/get_template)

### Gjort
- Peter körde om MCP-testet mot den uppdaterade servern. Positivt: `search_templates`+`get_template`-kedjan fungerar (sök → välj → hämta full prompt), stavfelstolerans (prefix-substring), filter på område/risknivå/kort roll, tydligt felmeddelande på okänt mall-id.
- Kvarvarande fynd: naturligt formulerade sökfraser ("informera personalen om en driftstörning") gav 0 träffar trots att kärnordet fanns i katalogen (gammal AND-all-tokens-logik krävde att ALLA ord matchade); den fullständiga rollen "IT-samordnare barn och utbildning" kändes fortfarande inte igen trots att "samordnare" ensamt gjorde det.
- Fixat båda: `_search_templates_payload` (`mcp_server.py`) bytt till poängsatt OR-matchning (titel/tagg-match ger +2, syfte/outputformat/area_label-match ger +1, mall inkluderas vid poäng > 0, resultat sorteras poäng-fallande) med tokenisering via samma `SkillRouter.STOPWORDS`/`_terms`-mekanism som redan finns för `route_skill` (ingen ny stoppordslista, inget hårdkodat undantag för "informera"/"personalen" som Peter föreslog som exempel — den generiska funktionsordslistan räckte). `recommend()` (`package_recommendations.py`) tokeniserar nu rollsträngen med `SkillRouter._terms()` istället för att kräva exakt helsträngsmatchning — fixar även `recommend_packages` rakt av, samma funktion används av båda verktygen.
- Hittade ett eget falskt larm under verifieringen: `curl` från Git Bash-skalet skickade "ö" fel-kodat (inte UTF-8) och triggade en `UnicodeDecodeError`/500 i servern — bekräftat vara ett terminal/curl-encoding-problem (inte en serverbugg) genom att skicka om exakt samma anrop via Python/httpx (garanterad UTF-8), som gav 200 OK med korrekt resultat.
- Verifierat i tre lager igen: 19 enhetstester (utökade med Peters exakta repro-frågor + regressionstest att stavfelstolerans/tidigare gröna fall inte gått sönder), smoke-test mot riktig produktions-Supabase-data, full HTTP/JSON-RPC-runda mot lokalt startad hosted-server (`python -m server.http_server`).

## 2026-07-20 (Peters MCP-användartest, uppföljning)

### Gjort
- Peter körde ett MCP-fokuserat användartest (ansluta/status, `list_templates`, hitta mall utifrån behov, hämta full prompt, `recommend_packages` per yrkesroll, kontrollera datahantering). Positivt: stabila svar, fullständiga promptar, integritetsmodellen (råtext skickas aldrig till Promptbanken) upplevdes bra.
- Fynd loggade i TODO.md "Nästa steg": saknat publikt `search_templates`/`get_template` (hela 42-mallarskatalogen måste hämtas idag), rollen "IT-samordnare barn och utbildning" känns inte igen av `recommend_packages`, oklart för användaren varför både 21 skills och 42 mallar finns. Peter prioriterade `search_templates`/`get_template` först.
- Byggde `search_templates(query?, role?, area?, risk_level?, limit?)` + `get_template(template_id)` i `mcp_server.py`/`hosted_guard.py` (tools/list-schema, JSON-RPC-dispatch, `@mcp.tool()`, guard-allowlist + argumentvalidering). Klient-sidig filtrering ovanpå samma `get_pro_templates_for_mcp_key`-data som `list_templates`/`recommend_packages` redan hämtar — ingen ny RPC/REST/migration. Se DECISIONS.md.
- Hittade och fixade en egen bugg under testningen: `limit=0` klamrades fel (`limit or 10` behandlade `0` som "ej satt" och gav 10 istället för att klamra till minimum 1) — bytt till `min(limit, ...)` utan `or`-fallback, eftersom anropsvägarna redan garanterar ett int-värde.
- Verifierat i tre lager: (1) 15 enhetstester av filterlogiken med handskriven exempeldata (query/area/risk_level/role-filtrering, `role_recognized` true/false, limit-klamring, `get_template` hit/miss, att summeringar utelämnar `prompt_text`) — alla gröna efter fixen; (2) samma anrop mot riktig produktions-Supabase-data (`get_pro_templates_for_mcp_key` via lokal process med riktiga `SUPABASE_URL`/`SUPABASE_ANON_KEY`); (3) full HTTP/JSON-RPC-runda mot en lokalt startad hosted-server (`python -m server.http_server`, samma kodväg som produktion) — bekräftade bland annat att `role="IT-samordnare barn och utbildning"` verkligen ger `role_recognized: false` (reproducerar Peters fynd) och att guarden korrekt avvisar fel typ på `limit` och saknat `template_id` (`-32602`).
- Ej gjort denna omgång (kvar i TODO "Nästa steg", Peter valde att inte prioritera nu): rollmappningsfixen för "IT-samordnare barn och utbildning" och förtydligande av skills-vs-mallar-distinktionen i verktygsbeskrivningarna.

## 2026-07-20

### Gjort
- Döpte om MCP-verktyget `list_pro_templates` → `list_templates` (`mcp_server.py`: tools/list-schema, JSON-RPC-dispatch, `@mcp.tool()`-funktion; `hosted_guard.py`: allowlist på båda ställena). Katalogen har varit öppen för alla sedan 2026-07-19 (se DECISIONS.md), och det gamla namnet upplevdes förvirrande av Peter trots dokumenterad "namnet är historiskt"-förklaring. Modulen `pro_templates.py`, RPC:n `get_pro_templates_for_mcp_key` och REST-pathen `/api/v1/pro-templates` byttes INTE — internt/historiskt, syns inte för MCP-klienter. Dokumentation uppdaterad i README.md/CLAUDE.md, nytt beslutslogg-inlägg i DECISIONS.md.
- Pushat till origin/main (`cc5affc`) och deployat på VPS:en med Peters explicita go-ahead (två separata bekräftelser krävdes — push och docker-rebuild klassades båda som riskabla av auto-mode-klassificeraren).
- Deploy-anmärkning: `docker compose` (v2-pluginet) saknas nu på VPS:en — bara gamla fristående `docker-compose` 1.29.2 kvar (`unknown command: docker compose`, inga cli-plugins installerade). Byggde och körde med `docker-compose` istället. Stötte på samma kända `KeyError: 'ContainerConfig'`-bugg som 2026-07-19 vid recreate av befintlig container — löst med samma workaround (`docker-compose stop`+`rm -f`+`up -d` istället för direkt `up -d --build`).
- Verifierat live mot `mcp.promptbanken.se`: `/healthz` ok, `tools/list` visar `list_templates` (inte `list_pro_templates`), `tools/call list_templates` returnerar full katalog (`unlocked: true`, 42 mallar), inga fel i containerloggarna.

## 2026-07-19

### Gjort
- Delprojekt 6 (öppen katalog, promptbanken-repot): `list_pro_templates`/`get_pro_templates_for_mcp_key` gav teaser (`prompt_text: null`) trots att katalog-Pro avvecklats på DB-sidan — Python-lagrets `pro_templates.py` hade fortfarande ett `if not mcp_key: return []`/`ProTemplatesNotConfigured`-krav på nyckel som stängde ute anrop utan `X-MCP-Key`. Fixad: nyckel krävs inte längre, bara `SUPABASE_URL`/`SUPABASE_ANON_KEY`. Verktygsbeskrivningarna för `list_pro_templates` uppdaterade (båda definitionsställena) — "namnet är historiskt", inget Pro-krav. Se `promptbanken/docs/superpowers/specs/2026-07-19-oppen-katalog-design.md`.
- Delprojekt 4 (MCP-exponering av promptpaket): fyra nya verktyg — `list_active_packages`, `activate_package`, `deactivate_package`, `copy_template_to_valvet`. Ny fil-oberoende utökning av `vault.py` (fyra wrapperfunktioner mot fyra nya `_for_key`-RPC:er i promptbanken-repot: `list_active_packages_for_key`, `activate_package_for_key`, `deactivate_package_for_key`, `copy_template_to_valvet_for_key`, migration `20260719120000_mcp_package_rpcs.sql`). Aktivera/avaktivera är medvetet HELT utanför `mcp_write_attempts` (ingen rate-limit, ingen loggning) — ren UI-konfigurationsflagga, inte en skrivhandling. `copy_template_to_valvet` kräver `confirm=true` (samma mönster som `archive_my_item`), delar rate limit (20/60s) och månadskvot med övriga skrivverktyg. Se `promptbanken/docs/superpowers/specs/2026-07-19-mcp-paket-exponering-design.md`.
- Delprojekt 5 (rollbaserade rekommendationer): nytt keyless read-only-verktyg `recommend_packages(role)`. Ny fil `mcp-server/server/package_recommendations.py` — statisk mappning område↔roll (samma 13-rollers-vokabulär som redan finns i `skills.json`), återanvänder `SkillRouter._normalize` rakt av (ingen ny normaliseringslogik). `arbetsbank`-området är universellt (matchar alla roller). Okänd/ej igenkänd roll ger alla 7 paket med `role_recognized: false` istället för ett tomt svar. Ingen DB-migration, ingen ny RPC — bygger direkt ovanpå redan öppna `list_pro_templates()`. Se `promptbanken/docs/superpowers/specs/2026-07-19-rollbaserade-rekommendationer-design.md`.
- Alla tre delprojekt inkopplade på samma tre ställen varje hostat verktyg kräver (`_tool_definitions()`, manuell JSON-RPC-dispatch, `@mcp.tool()`-registrering) plus REST-endpoints under `/api/v1/vault/packages*` och `hosted_guard.py`s allowlist.
- Verifierat: SQL-nivå direkt mot produktions-Supabase (riktig nyckel-hash, idempotent aktivering/avaktivering, `confirm`-krav, kopia-fält, delad kvot/rate-limit), Python-modulen importerad och smoke-testad lokalt (`.venv`), samt fullt end-to-end live mot `mcp.promptbanken.se` efter VPS-deploy (`docker-compose up -d --build`, känd `ContainerConfig`-workaround) — `tools/list` visar 23 verktyg, `recommend_packages` med tre rolltest (`chef`, `KOMMUNIKATÖR` versaler, okänd roll) gav exakt förväntat utfall.
- Detta slutför Promptbanken/Valvet-visionens alla 6 delprojekt (1: plansida, 2: kopiera→Valvet, 3: promptpaket, 4: MCP-paket, 5: rollrekommendationer, 6: öppen katalog) — samtliga byggda, deployade och verifierade i produktion samma dag.

## 2026-07-17

### Gjort
- Slutförde Plan B Task 3 i `worktree-valvet-plan-b`: `save_my_item`, `update_my_item` och `archive_my_item` är inkopplade som FastMCP-tools, manuella `tools/list`-definitioner, JSON-RPC-dispatch och REST-routes i `mcp_server.py`.
- Lade till write-felklassificering och separat loggning via `vault.log_write_attempt`, inklusive `invalid_key`, `not_pro`, `rate_limited`, `quota_reached`, `not_found` och optimistic-locking-konflikt.
- Utökade `hosted_guard.py` med allowlist och argumentvalidering för de tre skrivverktygen. REST, guard och JSON-RPC avvisar även fel typ på valfria strängfält och `restore`.
- Verifierade med `ast.parse`, `compileall`, `npm run check:python`, riktade payload-/guard-/JSON-RPC-tester och REST-tester med mockat RPC-lager.
- Startade servern lokalt på port 8766 och verifierade `/healthz` samt att `/mcp` `tools/list` annonserar exakt de tre nya skrivverktygen.
- Task 3 fick task-recension (spec ✅, Approved, ingen fix-loop) — se `.superpowers/sdd/progress.md`.
- Slutförde Plan B Task 4: full end-to-end-verifiering mot staging (`cohyrgxeatqexkqihktu`). Temporära Free/Pro-testnycklar skapades via Supabase MCP (samma mönster som Plan A:s egen staging-verifiering), hela curl-flödet i planen kördes och matchade spec exakt: idempotent save, Free-nekad update, Pro:s fullständiga CRUD, optimistic-locking-konflikt, `confirm`-kravet, `tools/list`/`tools/call` matchade REST, `hosted_guard` (körde i `warn`-läge) loggade korrekt `hosted_payload_warning reason=unexpected_arguments`. All testdata städad efteråt, staging återställt till ursprungsläge.
- Hittade och fixade en riktig bugg under Task 4-verifieringen: `vault.log_write_attempt` gick via `_call_rpc`, som alltid anropar `.json()` på svaret — men RPC:n returnerar 204 No Content (void), så varje loggat write-försök kastade internt och rapporterades felaktigt som `vault_log_write_attempt_failed`, trots att loggraden faktiskt skrevs. Fixad till samma mönster som `pro_templates.log_write_attempt` (parsar aldrig svarskroppen). Omverifierad efter fixen.
- Slutförde Plan B Task 5: dokumenterade de sex Valvet-verktygen i README.md (ny sektion + hosted-tool-listan), CLAUDE.md (ny sektion, uppdaterad Driftlägen-rad) och TODO.md.

### Nuläge
- Plan B (Task 1–5) är klar i `worktree-valvet-plan-b`. Alla sex Valvet-verktyg är implementerade, task-recenserade och live-verifierade mot staging. Väntar på slutlig helbranch-recension innan branchen avslutas.

### Nästa steg
- Slutlig helbranch-recension av Plan B, sedan avsluta branchen (merge/PR-beslut).
- Produktionsdeploy kräver ett separat, uttryckligt beslut (se `AGENTS.md`/`CLAUDE.md` om deploy-flödet) — inte del av Plan B.

## 2026-07-16

### Gjort
- Systemuppdatering av VPS:en (`promptbanken-dev`): 178+ uppgraderingsbara paket, inklusive `docker.io` 28.2.2 → 29.1.3 och en ny kärna (`6.8.0-79` → `6.8.0-134`).
- **Stötte på flera diskrelaterade problem eftersom rotpartitionen bara är 4.4G:**
  - `apt-get upgrade -y` av alla paket i ett svep gick inte (behöver 700-900MB temp-utrymme) — löst genom att dela upp i ~50-paket-omgångar med `apt-get clean` mellan varje.
  - Borttagning av gamla `linux-headers-6.8.0-79*` för att spara utrymme utlöste istället en full kärnuppgradering (apt löste "ta bort headers" som "installera ny kärna + headers, ta bort gamla headers") — disk gick från 651M till 121M ledigt istället för att öka. Löst genom att slutföra uppgraderingen: reboot till nya kärnan, sedan `apt-get purge` av gamla `linux-image`/`linux-modules`/`linux-modules-extra`.
  - `linux-firmware` (641MB) hoppades medvetet över — irrelevant på en VPS utan fysisk hårdvara.
  - Hittade en `unattended-upgrades`-process som hållit dpkg-låset sedan 23 maj (nästan 2 månader) — dödad manuellt efter att ha verifierat att den var övergiven (ny process från `apt-daily.timer` samma dag fick köra klart normalt istället för att dödas).
  - Hittade och tog bort en **övergiven journalkatalog** (`/var/log/journal/<gammalt-maskin-ID>`, ~209M) som inte längre matchade `/etc/machine-id` — `journalctl --vacuum` vacuumade fel katalog och rapporterade 0B frigjort trots att katalogen var stor. Satte även `SystemMaxUse=100M` i `journald.conf` (var kommenterad ut) för att förhindra att journalen växer okontrollerat igen.
- Verifierade Docker/container-hälsa efter varje risky steg (reboot, docker.io-uppgradering): `restart: unless-stopped` + `docker enabled` fungerade som väntat, containern kom upp automatiskt varje gång, `/healthz` svarade friskt genomgående.
- Testade och verifierade `claude-ssh` MCP-pluginet för produktionsdeploy (se 2026-07-13-posten nedan för själva deploy-testet).

- Hittade att `/var/log/btmp`+`btmp.1` (188M) och `auth.log`+`auth.log.1` (51M) vuxit stora av pågående SSH-brute-force-skanning (normalt bakgrundsbrus för en publik VPS). `fail2ban` var inte installerat — installerat och aktiverat (`sshd`-jailen aktiv direkt, bannar upprepade IP:n automatiskt).

### Nästa steg
- `fwupd` och `linux-firmware` lämnas medvetet "kept back" — ingen åtgärd behövs, irrelevanta på denna VPS.
- Övervaka disken periodiskt (`df -h /`) — 4.4G är permanent knappt, se `TODO.md` för ev. diskutökning hos providern.
- Trunkera `/var/log/btmp`/`auth.log` för att frigöra ~230M (säkert, bara loggar) — inte gjort än.

## 2026-07-13

### Gjort
- Testade och verifierade `claude-ssh` MCP-pluginet mot VPS:en (`wenstrompeter@promptbanken-dev`) — fungerar för `git pull` och `docker-compose`-kommandon utan sudo (användaren är i `docker`-gruppen). Sudo-kommandon (t.ex. `journalctl --vacuum-time`, `apt-get clean`) kräver lösenord och kan inte köras via pluginet — användaren kör dessa manuellt.
- Disk var kritiskt full (`/dev/sda2` 96%, 189M ledigt): `docker image prune -a -f` (51.77MB), plus manuell `journalctl --vacuum-time=7d` + `apt-get clean` av användaren → 189M → 377M ledigt (92%).
- Verifierade Dockers resursförbrukning: 144MB disk (1 image), 6.3MB RAM av 378.8MB limit — försumbart, disktrycket kom från systemloggar/apt-cache, inte Docker.
- Verifierade hela deploy-flödet end-to-end via SSH: `git pull` (hämtade `5e021c2`) → `docker-compose up -d --build` → stötte på den kända `ContainerConfig`-buggen (se `LOG.md` 2026-07-12 och [[project_vps_docker_compose_version]]) → löst med `docker rm -f <renamed_container>` + `docker-compose up -d` → container uppe, loggar rena.

### Nästa steg
- Överväg att sätta `SystemMaxUse` i `/etc/systemd/journald.conf` så journalen inte växer okontrollerat igen (kräver sudo, användaren gör det manuellt).
- Städa bort den övergivna dubblettklonen på VPS:en (kvarstående TODO-punkt, se `TODO.md`).

## 2026-07-12

### Gjort
- Designade och byggde `save_workspace_prompt`: första write-verktyget i den hostade servern, Pro-gated, se `docs/superpowers/specs/2026-07-12-mcp-save-as-template-write-design.md` och plan `docs/superpowers/plans/2026-07-12-save-workspace-prompt-write.md`.
- Ny RPC `app_private.save_prompt_for_key` i `promptbanken`-repot: pinnad `search_path`, rate limit + observability via `app_private.mcp_write_attempts`, idempotens via `idempotency_key`, innehållsvalidering, återanvänder `enforce_content_access_model`-triggern oförändrad via en transaktionslokal `auth.uid()`-koppling.
- Porterade `check_input_risk` från lokala `promptbanken/mcp-server/` hit — behövdes för att "generalisera → check → godkänn → spara"-flödet ska fungera mot den publika adressen. Fann och städade en pre-existing duplicerad `SERVER_MODE=="local"`-gated registrering av samma tool under vägen.
- Ny REST-endpoint `POST /api/v1/my-prompts`, första POST-endpointen i detta repo.
- Uppdaterade `hosted_guard.py`s allowlist för de två nya verktygen.
- **Bugg hittad under staging-verifiering och fixad samma dag:** log-innan-raise-mönstret i `save_prompt_for_key` persisterade aldrig avvisade försök (Postgres rullar tillbaka hela transaktionen vid `raise exception`). Löst med en ny separat RPC `app_private.log_write_attempt`, anropad av Python som ett eget HTTP-anrop efter att felet fångats. Se `DECISIONS.md`.
- Verifierat end-to-end mot staging med en dedikerad Pro-testnyckel (samtliga 6 utfall i `mcp_write_attempts` korrekta efter fixen).

### Nästa steg
- Deploya till produktion (Task 8 i planen) efter merge till `main`.
- Framtida: delning till `shared_workspace_addons` via write, semantisk dubblettdetektering, `search_path`-uppstädning på de äldre läs-RPC:erna, IP-baserad rate limit för ogiltig-nyckel-spam — se speccens "Uttryckligen utanför scope v1" och `TODO.md`.

### Produktionsdeploy (samma dag, senare på passet)
- Slutgranskning (whole-branch review) godkänd med ett Important-fynd: `save_workspace_prompt` returnerade rått PostgREST-JSON som felmeddelande istället för det rena svenska meddelandet — fixat innan merge.
- Mergade `feature/save-workspace-prompt` → `main` i båda repona, pushat.
- VPS-deploy stötte på den kända `docker-compose` 1.29.2 `ContainerConfig`-buggen, löst med dokumenterad workaround (`stop`/`rm -f`/`up -d`).
- **Ny bugg hittad vid första riktiga produktionsanropet:** `app_private.save_prompt_for_key`/`log_write_attempt` saknade `public`-schema-wrappers — PostgREST exponerar bara `public` via `/rest/v1/rpc/`, samma mönster som `get_workspace_prompts_for_key` redan följer men som missades här. Detta smet igenom alla tidigare granskningar eftersom Task 7:s staging-verifiering anropade `app_private.*` direkt i SQL Editor, aldrig via den faktiska PostgREST-vägen som Python-koden använder — produktionscurlen var första riktiga nätverkstestet av RPC:n. Fixat med migration `20260712120000_public_wrappers_for_save_prompt.sql`, committad direkt till `main` som hotfix (`cee016a`), applicerad mot både produktion och staging.
- Verifierat end-to-end i produktion med en riktig Pro-testnyckel: lyckad skrivning, idempotens (samma anrop två gånger → samma rad), synlig i `admin.html` under "Mina prompts". Testnyckeln borttagen från admin och raden i "Mina prompts" raderad efter verifiering.
- **Lärdom för framtida RPC-arbete:** verifiera alltid minst en gång via den faktiska PostgREST REST-vägen (`curl .../rest/v1/rpc/...` eller motsvarande via servern), inte bara direktanrop i SQL Editor — annars missas saknade `public`-wrappers tills produktion.

## 2026-07-08

### Gjort
- Jämförde vad som är byggt i den hostade servern mot `promptbanken`-repots plan-läge och senaste utveckling. Hittade gapet: `promptbanken` bytte 2026-07-06 till "Pro + Delad arbetsyta"-modellen och byggde tre nya MCP-tools i sin lokala server (`list_my_private_prompts`, `list_my_shared_workspaces`, `list_shared_workspace_prompts`) som aldrig portades till den hostade `mcp_promptbanken`-servern — explicit noterat som öppen punkt i `promptbanken/TODO.md`.
- Portade alla tre verktygen hit: nya funktioner `list_private_prompts`/`list_shared_prompts`/`list_shared_workspaces` i `pro_templates.py` (samma anon-beviljade RPC-mönster som `list_pro_templates`, anropar `get_workspace_prompts_for_key`/`list_shared_workspaces_for_key`), nya `@mcp.tool()`-funktioner + `tools/call`-dispatch + REST-endpoints i `mcp_server.py`, och nya poster i `hosted_guard.py`s allowlist.
- Generaliserade `HostedMetadataGuard.inspect_tool_args()` — den hårdkodade tidigare att bara `get_skill` fick ha argument alls, vilket hade blockerat `list_shared_workspace_prompts(workspace_id)`. Bytt mot en `elif`-kedja per tool istället för ett `tool_name != "get_skill"`-specialfall.
- Verifierat manuellt: `ast.parse` på alla tre ändrade filer, importerat `mcp_server`-modulen och kört payload-funktionerna utan nyckel (ger korrekt `workspace_status: no_key`), samt kört `HostedMetadataGuard` mot giltiga/ogiltiga tool-anrop (rätt avvisning av saknat `workspace_id`, rätt avvisning av oväntat argument på ett nollargument-tool, `get_skill` fortsatt opåverkad).
- Uppdaterade README.md och CLAUDE.md med de nya verktygen/endpointerna.

### Nuläge
- Committat (`d127f5b`) och pushat till `origin/main`. Användaren har deployat till VPS:en (`mcp.promptbanken.se`).
- End-to-end-verifierat mot produktion med en riktig Pro-nyckel som är medlem i en delad arbetsyta ("demoyta", `00f21df9-a140-4b85-8070-7d8032d28604`):
  - `GET /api/v1/my-shared-workspaces` → gav ytan korrekt.
  - `GET /api/v1/shared-workspaces/{workspace_id}/prompts` → gav den delade mallen ("demo", `content: "demo yta shared"`).
  - Samma endpoint med ett påhittat `workspace_id` → tom lista, inte andras mallar. Säkerhetsgränsen håller i produktion.
  - `GET /api/v1/my-private-prompts` → gav nyckelns egna två privata mallar.
  - Utan nyckel (bägge nya endpoints) → `workspace_status: "no_key"` + tom lista, ingen krasch.
- Testnyckeln var en dedikerad testnyckel (inte en nyckel i produktionsbruk) och är återkallad efter testet, eftersom den stod i klartext i chattsessionen.

### Nästa steg
- Inga kvarstående steg för denna del av portningen. Nästa naturliga steg om projektet fortsätter i samma spår: bygg motsvarande kontextverktyg-stöd i eventuella klientintegrationer/dokumentation som pekar mot den hostade adressen (t.ex. `mcp.html` i `promptbanken`-repot, som idag bara nämner de äldre verktygen).

## 2026-07-01

### Gjort
- Säkrade upp Supabase-åtkomsten: service-role-nyckeln (bypassar RLS helt, läs/skriv på alla tabeller) ersatt med en dedikerad Postgres-roll `mcp_server` som bara får `execute` på `app_private.verify_mcp_key` och `app_private.get_workspace_prompts` — inget annat.
- Ny migration `promptbanken/supabase/migrations/20260701_mcp_server_role.sql`: skapar rollen, ger `usage` på `app_private`-schemat och `execute` på de två funktionerna, samt `grant mcp_server to authenticator` så PostgREST kan växla roll. Rent additiv, rör inga befintliga rättigheter för `anon`/`authenticated`/`public` — verifierat att promptbankens frontend (anon/publishable-nyckel, RPC `ensure_personal_workspace`, tabellerna `content_items`/`api_keys` via RLS) inte berörs alls.
- Upptäckte under testning att Supabase har två separata auktoriseringslager: `apikey`-headern valideras av gatewayen (Kong) mot projektets kända nycklar (`anon`/`service_role`) och känner inte till anpassade roller, medan `Authorization: Bearer` är det PostgREST läser `role`-claim från för att välja Postgres-roll. Löst genom att skicka `SUPABASE_ANON_KEY` (publik, ofarlig) i `apikey` och en egen `mcp_server`-signerad JWT (`SUPABASE_MCP_ROLE_JWT`) i `Authorization`.
- Uppdaterade `supabase_repository.py`, `docker-compose.yml` och `CLAUDE.md` att använda de nya env-variablerna istället för `SUPABASE_SERVICE_ROLE_KEY`. Committat och pushat till `main` (`a9304b4`).
- Verifierat end-to-end i produktion: byggde om och startade om containern på VPS:en, curl mot `/mcp` med en riktig `X-MCP-Key` gav 23 skills totalt (21 publika + 2 workspace-prompts), containerloggarna visade `200 OK` på båda RPC-anropen.

### Frågetecken/kvarstående
- JWT-secreten (från Dashboard → Settings → API) stod i klartext i en chattsession under detta arbetspass — inte roterad än, se `TODO.md`.
- Den gamla `SUPABASE_SERVICE_ROLE_KEY`-raden i `.env` på VPS:en bör tas bort helt om den inte redan är det (ersatt av de två nya variablerna).

### Kringgått verktygsproblem
- `docker-compose up -d --force-recreate` (och även vanlig `up -d --build` vid recreate) kraschar med `KeyError: 'ContainerConfig'` på denna VPS — känd bugg i standalone `docker-compose` 1.29.2 mot images byggda med senare BuildKit-metadata. Kringgås med `docker-compose stop <tjänst> && docker-compose rm -f <tjänst> && docker-compose up -d <tjänst>` istället för `--force-recreate`.
- VPS:en har bara den äldre standalone `docker-compose` (bindestreck), inte `docker compose`-pluginet (mellanslag) — se [[project_vps_docker_compose_version]].

## 2026-06-30

### Gjort
- Granskade om Supabase-integrationen är klar. Slutsats: koden (`supabase_repository.py`) är skriven mot ett RPC-baserat schema (`app_private.verify_mcp_key`, `app_private.get_workspace_prompts`) som enligt `CLAUDE.md` ägs av det separata `promptbanken`-repot — inte verifierat live i denna session eftersom Supabase-MCP inte var ansluten.
- Uppdaterade `README.md`-avsnittet "Workspace-skills från Supabase" så det matchar den faktiska arkitekturen: `X-MCP-Key`-header per anrop (inte `PROMPTBANKEN_MCP_USER_KEY`-env), RPC-baserad nyckelverifiering (inte `mcp_keys`-tabellen), och en tydlig notis om att migrationen i det här repot är stale.

### Nuläge
- README var inaktuellt och beskrev en äldre arkitektur (tabellen `mcp_keys`, env-variabeln `PROMPTBANKEN_MCP_USER_KEY`) som inte längre stämmer med koden.
- Det är fortfarande inte verifierat att RPC-funktionerna faktiskt finns migrerade i den riktiga Supabase-databasen — det kräver tillgång till `promptbanken`-repot eller en ansluten Supabase-MCP.

### Nästa steg
- Verifiera RPC-funktionerna mot live-databasen (se `TODO.md`).
- Ta ställning till om den gamla `mcp_keys`-migrationen ska tas bort.

### Frågetecken
- Ska den stale migrationsfilen `20240629_create_mcp_keys.sql` tas bort helt, eller bara stå kvar som dokumenterat ej använd?

### Deploy till produktion (samma dag, senare på passet)
- Mergade `feature-mcp-streamable` → `main` (fast-forward, `76611bd` → `9ddd0f7`) och pushade till GitHub.
- På VPS:en (`mcp.promptbanken.se`, Caddy + Docker Compose v1 på `/home/wenstrompeter/mcp_promptbanken`): `git pull origin main`, satte upp `.env` med `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`, uppdaterade `/etc/caddy/Caddyfile` med routes för `/mcp`, `/api/v1/*`, `/openapi.json`, körde `docker-compose up -d --build`.
- Verifierade live: `/healthz` (skills_count 21), `/api/v1/skills` (öppen), `/sse` + `/messages/*` (befintlig klient återanslöt automatiskt utan problem), `/mcp` POST `tools/list` (gav exakt de 5 hosted metadata-tools, inga lokala läckte ut).
- Verifierade `/mcp` även från en riktig extern klient (ChatGPT) mot `https://mcp.promptbanken.se/mcp` utan nyckel — fungerar.
- Hittade och fixade en stale dubblettklon av repot inuti sig självt på VPS:en (`mcp_promptbanken/mcp_promptbanken/`, otrackad, oanvänd av Docker Compose) — lämnad orörd, städning är ett separat TODO.
- README hade fel i `SUPABASE_URL`-formatet under arbetet (en `/rest/v1/`-svans som skulle dubblera Supabase RPC-anropens path) — fångades och rättades innan rebuild.

### Beslut under deployen
- `PROMPTBANKEN_MCP_API_KEY` (global Bearer-token) lämnas medvetet tom i produktion. Servern ska vara helt öppen för `/sse` och `/mcp` (visar Promptbankens publika prompts), medan `X-MCP-Key`-headern per anrop är den separata mekanismen som lägger till en användares privata workspace-prompts ovanpå de öppna. Se [[project_promptbanken_overview]].

## 2026-06-15

### Gjort
- Skapade ett enkelt lokalt arbetsminne i projektroten.
- La till `PROJECT.md`, `TODO.md`, `LOG.md`, `DECISIONS.md`, `AGENTS.md` och `DATA-SAFETY.md`.
- Utökade `.gitignore` med skydd för hemligheter, lokal data, exporter, cache och vanliga byggartefakter.

### Nuläge
- Projektet är en minimal MCP-server för Promptbanken.
- Hosted-läget är avsett att vara metadata-only.
- Local-läget kan hantera användartext lokalt.
- Det fanns redan lokala ändringar i repot innan arbetsminnet skapades.

### Nästa steg
- Läs `PROJECT.md`, `TODO.md` och senaste posten i `LOG.md` vid nästa återstart.
- Verifiera att `.gitignore` inte blockerar filer som faktiskt ska versionshanteras.
- Fortsätt med verifiering av Streamable HTTP och hosted/local-lägen.

### Frågetecken
- Vilken MCP-klient ska vara primär målmiljö för verifiering?
- Ska arbetsminnet senare få en återkommande rutin, till exempel uppdatering inför varje commit?
