# Admin-MCP OAuth VPS Rollout and Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Driftsätt den fristående Admin-MCP-tjänsten på VPS:en med en kontrollerad OAuth-övergång och avveckla den gamla statiska adminlösningen först efter verifierad stabilitet.

**Architecture:** Databasmigrationen rullas ut bakåtkompatibelt först, därefter startas den nya containern internt på port 8012 utan publik trafik. En verklig OAuth-klient registreras och godkänns, sedan läggs DNS/Caddy till; gamla `/admin` hålls fryst som rollback tills nya tjänsten klarat kontrakt, säkerhet, E2E och en definierad observationsperiod.

**Tech Stack:** Ubuntu VPS, Docker, Docker Compose v1.29.2, Caddy 2.6.2, Supabase CLI/Postgres, PowerShell, HTTPS MCP/OAuth 2.1

**Spec:** `../specs/2026-09-11-admin-mcp-oauth-service-design.md`

## Global Constraints

- Läs och följ databasplanen och serviceplanen före denna plan; rollout börjar bara när båda completion gates är gröna.
- Varje SSH-kommando använder `wenstrompeter@185.157.222.12` och den verifierade nyckeln `$env:USERPROFILE\.ssh\promptbanken_vps`.
- Kontrollera `df -h /` och `docker system df` före pull, build, restart eller cleanup.
- Under 600 MB ledigt är build blockerad; över 1 GB är rekommenderat.
- VPS:en använder `docker-compose` v1.29.2. Använd aldrig `docker compose`, `docker-compose up -d --build` eller `--force-recreate`.
- Stoppa om något berört VPS-repo har lokala ändringar.
- Kräv ett uttryckligt användargodkännande före reboot, produktionsmigration, containerbyte, proxyändring, rollback och borttagning av gamla adminlösningen.
- Bygg en gång; ersätt endast namngiven service med `docker-compose rm -sf admin-mcp` följt av `docker-compose up -d admin-mcp`.
- Tjänsten är inte driftsatt förrän localhost-health, containerlogg, publik HTTPS, OAuth discovery och fullständigt kontraktstest passerar.
- Skriv aldrig ut eller spara access/refresh tokens, publishable key, e-postadress eller `.env`-innehåll i releaseunderlag.
- Open 1.2.2 ska ge 62/62 i sitt separata publika kontraktstest före Admin-MCP-rollout.
- Connects sex verktyg och Openens nio verktyg får inte ändras av första Admin-MCP-release.

---

## File Structure

- Create in new repo: `deploy/Caddyfile.admin-mcp` — versionsstyrd kandidat för ny host.
- Create in new repo: `docs/deploy-runbook.md` — exakta preflight-, deploy-, verify- och rollbackkommandon.
- Create in new repo: `docs/release-evidence/1.0.0.md` — endast icke-känsliga resultat och commit/image-id.
- Modify after cutover only: `mcp_promptbanken/docker-compose.yml`, `mcp_promptbanken/deploy/Caddyfile`, `mcp_promptbanken/mcp-server/server/mcp_server.py`, gamla adminmoduler/tester/kontrakt och arbetsminnesfiler.

### Task 1: Gör VPS:en byggbar och lås Open-baseline

**Files:**
- No repository changes.

**Interfaces:**
- Consumes: nuvarande VPS, installerade kärnor och befintlig Open 1.2.2-plan.
- Produces: minst 600 MB ledigt, verifierad boot-kärna och Open-kontrakt 62/62.

- [ ] **Step 1: Ta en färsk read-only preflight**

```powershell
ssh -o BatchMode=yes -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'uname -r; df -h /; docker system df; docker ps -a; dpkg -l "linux-image*" "linux-headers*"'
```

Spara: aktiv kärna, ledigt rootutrymme, reclaimable images/cache och exakta
containerstatusar. Avbryt vid oväntad stoppad produktionscontainer.

- [ ] **Step 2: Begär godkännande och starta om till senaste installerade kärna**

Efter användarens uttryckliga godkännande:

```powershell
ssh -t -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 "sudo reboot"
```

Vänta tills SSH svarar igen. Kör `uname -r` och kontrollera att den nyare
installerade kärnan är aktiv innan gamla paket får tas bort.

- [ ] **Step 3: Frigör utrymme med säkra engångsåtgärder**

Efter nytt godkännande för cleanup:

```powershell
ssh -t -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 "sudo apt-get autoremove --purge && sudo apt-get clean && sudo journalctl --vacuum-size=100M"
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'docker image prune -f; docker system prune -f; df -h /; docker system df'
```

Kör varje cleanup högst en gång. Om mindre än 600 MB är ledigt efteråt:
stoppa; bygg inte. Mellan 600 MB och 1 GB: bekräfta att basimagen redan är
cachad och varna innan den namngivna builden.

- [ ] **Step 4: Färdigställ Open 1.2.2 som separat release**

Följ den befintliga Open 1.2.2-planen och
`promptbanken-vps-deploy`-workflowet. Efter publik deploy:

```powershell
Set-Location .\mcp_promptbanken
& "$env:USERPROFILE\.codex\skills\promptbanken-mcp-contract-test\scripts\test-mcp-contract.ps1" -Contract ".\mcp-server\mcp-contract.json" -Profile public -OutputPath ".\mcp-contract-result.json"
```

Förväntat: exit code 0 och 62/62 faktiskt körda kontroller; inga SKIP.

- [ ] **Step 5: Registrera preflightbevis**

I releaseunderlaget för Admin-MCP skriv de faktiskt verifierade värdena för
aktiv kärna, ledigt rootutrymme, Open 62/62 och produktionscommit. Använd
aldrig exempelvärden eller osäker status.

### Task 2: Skapa privat fjärrrepo och en ren VPS-checkout

**Files:**
- Remote create: `BUsavsjo/promptbanken-admin-mcp` som privat repo.
- VPS create: `/home/wenstrompeter/promptbanken-admin-mcp`.

**Interfaces:**
- Consumes: rent lokalt service-repo med grönt completion gate.
- Produces: privat origin och ren checkout på exakt verifierad commit.

- [ ] **Step 1: Kontrollera lokal Git-status och GitHub CLI**

```powershell
Set-Location ..\promptbanken-admin-mcp
git status --short
git log -1 --oneline
gh auth status
```

Förväntat: arbetsytan är ren och GitHub CLI är autentiserad för
`BUsavsjo`. Om kontot eller ägarskapet avviker, stoppa före extern åtgärd.

- [ ] **Step 2: Begär godkännande och skapa privat repo**

Efter uttryckligt godkännande:

```powershell
gh repo create BUsavsjo/promptbanken-admin-mcp --private --source . --remote origin --push
git remote -v
```

Förväntat: både fetch och push pekar på
`https://github.com/BUsavsjo/promptbanken-admin-mcp.git`.

- [ ] **Step 3: Skapa en dedikerad read-only deploynyckel**

Efter att det privata repot finns:

```powershell
$deployPublicKey = ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'test -f ~/.ssh/promptbanken_admin_mcp_deploy || ssh-keygen -t ed25519 -N "" -f ~/.ssh/promptbanken_admin_mcp_deploy -C "promptbanken-admin-mcp-vps"; sed -n "1p" ~/.ssh/promptbanken_admin_mcp_deploy.pub'
gh api repos/BUsavsjo/promptbanken-admin-mcp/keys --method POST -f title="Promptbanken Admin MCP VPS read-only" -f key="$deployPublicKey" -F read_only=true
```

Verifiera att API-svaret har `read_only=true`. Privatnyckeln lämnar aldrig
VPS:en; endast den publika nyckeln skickas till GitHub.

- [ ] **Step 4: Preflighta målplatsen på VPS**

```powershell
ssh -o BatchMode=yes -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'test ! -e ~/promptbanken-admin-mcp; df -h /'
```

Förväntat: pathen finns inte och disken är fortfarande över buildgränsen.
Om pathen finns ska den inspekteras; radera eller skriv inte över den.

- [ ] **Step 5: Klona och verifiera commit**

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'GIT_SSH_COMMAND="ssh -i /home/wenstrompeter/.ssh/promptbanken_admin_mcp_deploy -o IdentitiesOnly=yes" git clone git@github.com:BUsavsjo/promptbanken-admin-mcp.git ~/promptbanken-admin-mcp && cd ~/promptbanken-admin-mcp && git config core.sshCommand "ssh -i /home/wenstrompeter/.ssh/promptbanken_admin_mcp_deploy -o IdentitiesOnly=yes" && git status --short && git rev-parse HEAD'
```

Jämför VPS-hashen med lokala `git rev-parse HEAD`. Fortsätt bara vid exakt
match och tom VPS-status.

### Task 3: Applicera den bakåtkompatibla databasmigrationen i produktion

**Files:**
- Production database migration history only.
- Modify evidence: `promptbanken-admin-mcp/docs/release-evidence/1.0.0.md`.

**Interfaces:**
- Consumes: stagingverifierad migration från databasplanen.
- Produces: produktions-RPC:er som accepterar webbsession utan klient men nekar okänd OAuth-klient.

- [ ] **Step 1: Verifiera exakt migrationsdiff och historik**

Från rent `promptbanken`-worktree:

```powershell
npx supabase --version
npx supabase migration list --help
npx supabase migration list
git status --short
git show --stat --oneline HEAD
```

Förväntat: endast granskad Admin-MCP-migration väntar; inga orelaterade
migrationer eller arbetsyteändringar.

- [ ] **Step 2: Ta ett read-only produktionsprov före ändringen**

Med befintlig webbsession: verifiera att admin kan lista drafts. Med Connect:
verifiera `tools/list` visar exakt sex verktyg. Med Open: verifiera nio
publika verktyg och kontrakt 62/62.

- [ ] **Step 3: Begär godkännande och kör produktionsmigration**

Upptäck först stödda flaggor:

```powershell
npx supabase db push --help
```

Efter uttryckligt godkännande: kör repots dokumenterade, länkade
produktions-`db push` utan `--include-all` eller annan flagga som skulle
ta med orelaterade migrationer. Kör därefter `npx supabase migration list`.

- [ ] **Step 4: Verifiera bakåtkompatibilitet omedelbart**

Kör samma tre prov igen:

- webbadministration utan `client_id` fungerar,
- Connect visar sex verktyg och vanliga läsanrop fungerar,
- Open ger 62/62.

Verifiera dessutom att en plattformsägare med Connect-`client_id` får
`allowed=false` från `get_admin_mcp_context`, utan att skriva token till
disk eller terminaloutput.

- [ ] **Step 5: Kontrollera advisors och dokumentera**

Kör Supabase advisors och registrera endast antal nya/total warnings och
bedömning. Vid ny security-varning: spärra fortsättningen och åtgärda innan
containern startas.

### Task 4: Bygg och starta Admin-MCP internt på port 8012

**Files:**
- VPS create: `/home/wenstrompeter/promptbanken-admin-mcp/.env` med mode 0600.
- Modify evidence: `docs/release-evidence/1.0.0.md`.

**Interfaces:**
- Consumes: ren checkout, publik Supabase-konfiguration och produktionsmigration.
- Produces: frisk localhostservice utan DNS/Caddy.

- [ ] **Step 1: Skapa `.env` utan att skriva värden i kommandologgen**

Lägg följande fyra namn i filen via en interaktiv, dold administrativ väg:

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
OAUTH_ISSUER
OAUTH_JWKS_URL
```

Använd samma Supabase-projekt/issuer/JWKS som Connect. Kör:

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'chmod 600 ~/promptbanken-admin-mcp/.env; cd ~/promptbanken-admin-mcp && sed -E "s/=.*/=<redacted>/" .env'
```

Förväntat: exakt fyra variabelnamn visas, alla värden redigerade. Ingen
service-role-, admin-key- eller refresh-token-variabel.

- [ ] **Step 2: Kontrollera disk, Git och compose före build**

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'cd ~/promptbanken-admin-mcp && git status --short && git rev-parse HEAD && docker-compose config --services && df -h / && docker system df'
```

Förväntat: rent repo, bara service `admin-mcp`, tillräcklig disk.

- [ ] **Step 3: Bygg exakt en gång utan start**

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'cd ~/promptbanken-admin-mcp && docker-compose build admin-mcp'
```

Registrera image-id med `docker image inspect promptbanken-admin-mcp:latest`.
Bygg inte igen om ett senare `up` får Compose `ContainerConfig`-fel.

- [ ] **Step 4: Begär godkännande och starta bara den nya servicen**

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'cd ~/promptbanken-admin-mcp && docker-compose rm -sf admin-mcp && docker-compose up -d admin-mcp'
```

- [ ] **Step 5: Verifiera localhost och resursläge**

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'cd ~/promptbanken-admin-mcp && docker-compose ps && curl -fsS localhost:8012/healthz && docker-compose logs --tail=80 admin-mcp && docker stats --no-stream && df -h /'
```

Förväntat: healthy, rätt 1.0.0-health JSON, inga restartar, inga hemligheter,
och Open/Connect-containrarna är fortfarande up.

### Task 5: Förbered Supabase OAuth för den första Admin-MCP-klienten

**Files:**
- No repository or production data changes.

**Interfaces:**
- Consumes: Supabase dynamisk klientregistrering och intern Admin-MCP.
- Produces: verifierad discovery och en säker metod att identifiera en nekad klient efter att publik HTTPS finns.

- [ ] **Step 1: Verifiera OAuth discovery före registrering**

Kontrollera Supabase authorization server metadata och kräv:

- `code_challenge_methods_supported` innehåller `S256`,
- `registration_endpoint` finns,
- authorization, token och JWKS URLs ligger under rätt issuer,
- token endpoint hanteras som valfri 2xx.

- [ ] **Step 2: Verifiera säker identifiering av nekad klient**

Kontrollera lokalt att ett `oauth_client_denied`-event innehåller endast
`client_id`, korrelations-id och utfall. Det får inte innehålla användar-id,
e-post, token, claims eller Supabase response body. Denna loggrad används för
att hitta den dynamiskt registrerade klienten efter Task 6.

### Task 6: Lägg DNS och en strikt Caddy-host

**Files:**
- Create: `promptbanken-admin-mcp/deploy/Caddyfile.admin-mcp`
- VPS candidate: `/home/wenstrompeter/Caddyfile.admin-mcp.candidate`
- Modify after approval: `/etc/caddy/Caddyfile`

**Interfaces:**
- Consumes: frisk localhostservice och verifierad OAuth discovery.
- Produces: `https://admin-mcp.promptbanken.se` med endast tre routes.

- [ ] **Step 1: Skriv den versionsstyrda site-blocket**

```caddyfile
admin-mcp.promptbanken.se {
    handle /healthz {
        reverse_proxy 127.0.0.1:8012
    }

    handle /.well-known/oauth-protected-resource/mcp {
        reverse_proxy 127.0.0.1:8012
    }

    handle /mcp {
        @options {
            method OPTIONS
        }
        handle @options {
            header Access-Control-Allow-Origin "*"
            header Access-Control-Allow-Methods "POST, OPTIONS"
            header Access-Control-Allow-Headers "Content-Type, Authorization, Accept, MCP-Protocol-Version"
            header Access-Control-Expose-Headers "WWW-Authenticate"
            respond 204
        }
        header Access-Control-Allow-Origin "*"
        header Access-Control-Expose-Headers "WWW-Authenticate"
        request_body {
            max_size 64KB
        }
        reverse_proxy 127.0.0.1:8012
    }

    handle {
        respond "Not found" 404
    }

    log {
        output file /var/log/caddy/admin_mcp_access.log {
            roll_size 20MiB
            roll_keep 5
            roll_keep_for 720h
        }
        format filter {
            wrap json
            fields {
                request>headers>Authorization delete
                request>headers>Cookie delete
                request>remote_ip delete
                request>remote_port delete
                request>client_ip delete
            }
        }
    }
}
```

- [ ] **Step 2: Lägg DNS-posten**

Skapa en proxied A-post hos nuvarande DNS-leverantör:

```text
Type: A
Name: admin-mcp
Target: 185.157.222.12
Proxy: enabled
```

Verifiera med `Resolve-DnsName admin-mcp.promptbanken.se -Type A`. Eftersom
Cloudflare-proxy används förväntas Cloudflare-adresser, inte VPS-adressen
direkt.

- [ ] **Step 3: Förbered komplett Caddy-kandidat och visa diff**

Läs hela `/etc/caddy/Caddyfile`, lägg blocket i en komplett kandidat under
`/home/wenstrompeter/`, och kör på VPS:

```bash
caddy validate --config ~/Caddyfile.admin-mcp.candidate --adapter caddyfile
diff -u /etc/caddy/Caddyfile ~/Caddyfile.admin-mcp.candidate
```

Diffen får endast lägga till Admin-MCP-blocket.

- [ ] **Step 4: Begär godkännande och installera/reloada**

```powershell
ssh -t -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 "sudo cp -- /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak.admin-mcp-1.0.0 && sudo install -m 0644 /home/wenstrompeter/Caddyfile.admin-mcp.candidate /etc/caddy/Caddyfile && sudo caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile"
```

- [ ] **Step 5: Verifiera exakt publik routeyta**

```powershell
curl.exe -fsS https://admin-mcp.promptbanken.se/healthz
curl.exe -fsS https://admin-mcp.promptbanken.se/.well-known/oauth-protected-resource/mcp
curl.exe -i -X POST https://admin-mcp.promptbanken.se/mcp -H "Content-Type: application/json" --data-binary "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}"
curl.exe -i https://admin-mcp.promptbanken.se/
curl.exe -i https://admin-mcp.promptbanken.se/admin
```

Förväntat: health 200, metadata 200, MCP utan token 401 med
`resource_metadata`, root 404 och `/admin` 404.

### Task 7: Kör full OAuth-, kontrakts- och audit-E2E

**Files:**
- Modify: `promptbanken-admin-mcp/docs/release-evidence/1.0.0.md`

**Interfaces:**
- Consumes: publik HTTPS, en ännu inte godkänd dynamisk klient, platform_owner-konto och live-contract runner.
- Produces: verifierat releaseunderlag utan personuppgifter eller tokens.

- [ ] **Step 1: Registrera, kontrollera och godkänn den riktiga OAuth-klienten**

Samtyckessidan ska vara `https://app.promptbanken.se/oauth/consent` och visa
rätt klient. Token ska ha giltig signatur, issuer, `aud=authenticated`,
`sub` och ett icke-tomt `client_id`. Första anropet ska ge 403 och en sanerad
`oauth_client_denied`-loggrad.

Verifiera i Supabase att klientnamn och exakta redirect URIs hör till den
avsedda Codex/ChatGPT-klienten. Avvisa localhost/HTTPS-URI:er som inte matchar
den initierade klienten. Efter uttryckligt godkännande: lägg det verkliga id:t
som driftdata:

```sql
insert into app_private.admin_mcp_oauth_clients (
    client_id, label, enabled, approved_by
)
values (
    :'verified_client_id',
    'Codex desktop Admin-MCP',
    true,
    :'platform_owner_user_id'::uuid
)
on conflict (client_id) do update
set label = excluded.label,
    enabled = true,
    approved_by = excluded.approved_by;
```

`verified_client_id` och `platform_owner_user_id` anges som lokala
`psql`-variabler från verifierad driftkontext; de skrivs aldrig i repo.
Sätt därefter raden `enabled=false`, verifiera 403 på nästa request, sätt
`enabled=true` och verifiera 200. Detta bevisar omedelbar revokering utan
rollcache. Spara bara booleska resultat.

- [ ] **Step 2: Kör live-kontraktet**

```powershell
Set-Location ..\promptbanken-admin-mcp
& .\scripts\test-live-contract.ps1 -BaseUrl "https://admin-mcp.promptbanken.se"
```

Förväntat: exit code 0, 21/21 fulla definitioner matchar, Open-verktyg
blockeras och `get_admin_context` visar tillåten plattformsägare. Testtoken
ska läsas från processmiljö och rensas direkt efter körning.

- [ ] **Step 3: Kör säkerhetsmatrisen**

Verifiera via publik URL:

- ingen token → 401,
- trasig/utgången token → 401,
- giltig icke-admin → 403,
- giltig Connect-token för plattformsägaren → 403,
- avstängd Admin-klient → 403,
- godkänd Admin-klient + plattformsägare → 200.

Kör därefter Open- och Connect-`tools/list` igen och bekräfta 9 respektive 6
verktyg utan adminnamn.

- [ ] **Step 4: Kör en städbar adminrundtur**

Använd slug `admin-mcp-e2e-1-0-0`:

1. skapa draft,
2. hämta draft,
3. uppdatera generell variant,
4. lista historik,
5. återställ version med `confirm=true`,
6. kontrollera audit med rätt `auth.uid()` och `client_id`,
7. radera draft med `confirm=true`,
8. verifiera att draften inte finns.

Om slug redan finns från ett avbrutet test: inspektera status/historik och
städa med det avsedda delete-verktyget; skapa inte en serie dubblettslugs.

- [ ] **Step 5: Kontrollera loggar och resurser efter E2E**

```powershell
ssh -i "$env:USERPROFILE\.ssh\promptbanken_vps" wenstrompeter@185.157.222.12 'cd ~/promptbanken-admin-mcp && docker-compose ps && docker-compose logs --tail=120 admin-mcp && docker stats --no-stream && df -h /'
```

Granska att det inte finns token, full e-post, Supabase body eller stack trace.
Registrera commit, image-id, statuskoder, 21/21 och audit-match i
`docs/release-evidence/1.0.0.md`.

- [ ] **Step 6: Commit releaseunderlaget**

```powershell
git add docs/release-evidence/1.0.0.md
git commit -m "docs: record Admin MCP 1.0.0 production verification"
git push
```

### Task 8: Kör övergångsperiod och fatta separat cleanupbeslut

**Files:**
- Modify: arbetsminnesfiler i `mcp_promptbanken`.

**Interfaces:**
- Consumes: godkänd produktionstjänst.
- Produces: dokumenterat bevis för att gamla `/admin` kan tas bort.

- [ ] **Step 1: Frys gamla adminytan**

Lägg inga nya verktyg eller schemas i gamla `/admin`. Dokumentera att nya
Admin-MCP är primär och att gamla routen endast är rollback under observation.

- [ ] **Step 2: Uppfyll cutoverkriterierna**

Innan cleanup krävs:

- minst sju kalenderdagar utan auth-, audit- eller restartincident,
- minst tre separata OAuth-sessioner,
- minst en verklig create/update/history/restore/delete-runda,
- ett nytt fullständigt 21/21 live-kontraktstest,
- Open 62/62 och oförändrad Connect-lista,
- verifierad klientrevokering `enabled=false → 403`.

- [ ] **Step 3: Begär ett separat uttryckligt beslut**

Presentera bevisen och be användaren välja om gamla adminlösningen ska tas
bort. Börja inte Task 9 som automatisk fortsättning på första deploygodkännandet.

### Task 9: Ta bort gamla statiska adminlösningen i en separat cleanup-release

**Files:**
- Delete: `mcp_promptbanken/mcp-server/server/admin_auth.py`
- Delete: `mcp_promptbanken/mcp-server/server/admin_catalog.py`
- Delete: `mcp_promptbanken/mcp-server/tests/test_admin_auth.py`
- Delete: `mcp_promptbanken/mcp-server/tests/test_admin_catalog.py`
- Modify: `mcp_promptbanken/mcp-server/server/mcp_server.py`
- Modify: `mcp_promptbanken/mcp-server/tests/test_admin_route.py`
- Modify: `mcp_promptbanken/mcp-server/mcp-contract.json`
- Modify: `mcp_promptbanken/docker-compose.yml`
- Modify: `mcp_promptbanken/deploy/Caddyfile`
- Modify: `mcp_promptbanken/README.md`, `PROJECT.md`, `TODO.md`, `LOG.md`, `DECISIONS.md`

**Interfaces:**
- Consumes: separat cleanupgodkännande och uppfyllda cutoverkriterier.
- Produces: Open utan `/admin`, statisk nyckel, refresh token eller tokenvolym.

- [ ] **Step 1: Skriv regressionstestet före borttagning**

Ändra gamla `test_admin_route.py` så det kräver:

- `/admin` finns inte i Starlette-routes,
- `admin_*` finns inte i Open-profiler,
- miljönamn `PROMPTBANKEN_ADMIN_KEY`,
  `SUPABASE_ADMIN_REFRESH_TOKEN` och
  `ADMIN_REFRESH_TOKEN_STATE_PATH` saknas i compose,
- kontraktet saknar admin group/profile.

Kör testet och verifiera att det är rött innan kod tas bort.

- [ ] **Step 2: Ta bort bara gammal adminyta**

Ta bort route, middleware, imports, dispatch och tool definitions ur
`mcp_server.py`; radera de två gamla modulerna och deras specifika tester.
Ta bort admin group/profile ur Opens kontrakt. Ändra inte de nio publika
definitionerna eller snapshoten för 1.2.2.

- [ ] **Step 3: Ta bort hemligheter och volym ur compose/Caddy**

Ta bort:

- `PROMPTBANKEN_ADMIN_KEY`,
- `SUPABASE_ADMIN_REFRESH_TOKEN`,
- `ADMIN_REFRESH_TOKEN_STATE_PATH`,
- mounten `admin-refresh-token-state`,
- top-level-volymen med samma namn,
- Caddys `handle /admin`.

Radera inte Docker-volymen på VPS ännu; behåll den återställningsbar tills
cleanup-releasen varit stabil.

- [ ] **Step 4: Kör hela Open-verifieringen**

```powershell
Set-Location .\mcp_promptbanken\mcp-server
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\pyright.exe
Set-Location ..
& "$env:USERPROFILE\.codex\skills\promptbanken-mcp-contract-test\scripts\test-mcp-contract.ps1" -Contract ".\mcp-server\mcp-contract.json" -Profile public
```

Förväntat: tester/lint/typer exit 0 och public 62/62.

- [ ] **Step 5: Commit och deploya som egen release**

```powershell
git add -A mcp-server/server/admin_auth.py mcp-server/server/admin_catalog.py mcp-server/tests/test_admin_auth.py mcp-server/tests/test_admin_catalog.py mcp-server/server/mcp_server.py mcp-server/tests/test_admin_route.py mcp-server/mcp-contract.json docker-compose.yml deploy/Caddyfile README.md PROJECT.md TODO.md LOG.md DECISIONS.md
git commit -m "refactor: remove legacy static Admin MCP route"
```

Följ `promptbanken-vps-deploy`: disk/Git preflight, tagga rollback-image,
bygg bara `promptbanken-mcp`, begär godkännande, `rm -sf` + `up -d`,
verifiera localhost och publik Open 62/62.

- [ ] **Step 6: Radera gamla hemligheter först efter verifierad cleanup**

Efter lyckad deploy:

1. ta bort gamla env-värden från VPS-hemlighetsfilen utan att visa dem,
2. starta om bara Open-servicen om compose behöver läsa om env,
3. verifiera Open 62/62 och Admin-MCP 21/21 igen,
4. vänta ytterligare en verifierad observationsperiod före radering av
   Docker-volymen.

Identifiera volymen exakt med `docker volume ls` och `docker volume inspect`.
Begär separat godkännande före `docker volume rm`; rapportera att raderingen
inte kan återställas.

## Rollback Matrix

| Felpunkt | Första åtgärd | Verifiering |
| --- | --- | --- |
| Migrationen påverkar webben | Spärra Admin-klient och använd migrationens granskade rollback/forward-fix; ändra inte Open-image | Webbadmin, Connect 6 tools, Open 62/62 |
| Ny container är sjuk före Caddy | `docker-compose stop admin-mcp` | Open/Connect fortsatt healthy |
| OAuth-klient misstänks | `update ... set enabled=false` för exakt klient | Nästa request 403 |
| Publik route ger fel | Återställ `/etc/caddy/Caddyfile.bak.admin-mcp-1.0.0` och reload | Admin-host borta, Open/Connect kvar |
| Ny image regresserar | Tagga tillbaka verifierad föregående Admin-MCP-image och gör scoped `rm -sf` + `up -d` | localhost + 21/21 |
| Cleanup av gamla Open-admin regresserar | Återtagga sparad Open rollback-image; gör scoped Open-restart | Open 62/62; rapportera repo/image-skillnad |

Varje rollback är en liveändring och kräver uttryckligt godkännande. Efter
rollback ska containerstatus, localhost-health, publika kontrakt, Git-hash,
image-id och disk registreras.

## Rollout Plan Completion Gate

Rollouten är klar först när:

- VPS har säker diskmarginal och kör verifierad ny kärna,
- Open 1.2.2 är 62/62 före och efter alla delade ändringar,
- databasmigrationen är verifierad i produktion utan Connect/webb-regression,
- Admin-MCP är healthy på 8012 och publik HTTPS,
- OAuth + PKCE, 21/21 kontrakt, säkerhetsmatris och städbar E2E passerar,
- audit visar verklig användare och klient,
- sju dagars observationskriterier är uppfyllda,
- gamla statiska adminlösningen har tagits bort i en separat godkänd release,
- gamla hemligheter och slutligen tokenvolymen är borttagna med separat
  verifiering.
