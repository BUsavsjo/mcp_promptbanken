# OpenAI app-katalog: teknisk readiness

## Bakgrund

`/mcp` är sedan `2026-07-31` beslutat som det öppna, frysta publika
ChatGPT-kontraktet (se `DECISIONS.md`, "Endpoint-strategi inför
ChatGPT-publicering"). De 9 publika verktygen har redan review-klara
annotationer (`readOnlyHint`/`destructiveHint`/`openWorldHint`, testat i
`mcp-server/tests/test_openai_publication_contract.py`), och en extern
testrapport har redan bekräftat att ChatGPT pratar med endpointen som
anonym klient.

Peter vill nu ta nästa steg: publicera i OpenAI:s publika app-katalog
(inte bara låta enskilda användare lägga till servern som en personlig
connector). Enligt OpenAI:s aktuella (2026-08) submissionskrav
(`developers.openai.com/apps-sdk/app-submission-guidelines`,
`developers.openai.com/plugins/deploy/submission`) återstår tre
tekniska luckor innan submission-portalen kan fyllas i fullständigt:

1. Domänverifiering — portalen kräver en token hostad på
   `/.well-known/openai-apps-challenge` på samma domän som `/mcp`.
2. Privacy policy måste exakt spegla vilka datafält de publika verktygens
   svar faktiskt innehåller — `privacy.html` har redan en rimlig
   basbeskrivning av anonym användningsstatistik, men nämner aldrig de 9
   verktygens faktiska svarsinnehåll specifikt.
3. Submission-portalens Testing-flik kräver minst 5 positiva och 3
   negativa testcase med repro-steg — finns inte som dokument idag.

Resten av submissionskraven (utvecklarverifiering, logo, kategori,
kort/lång beskrivning, support-URL, country availability) är antingen
manuella portal-steg eller produkttext/grafik — uttryckligen utanför den
här specen (se Icke-mål).

## Mål

1. `/.well-known/openai-apps-challenge` svarar med en konfigurerbar token,
   nåbar utan auth, på produktionsdomänen.
2. En kort audit-tabell som visar exakt vilka fält varje publikt verktygs
   svar innehåller, och `privacy.html` uppdaterad om audit hittar ett fält
   som inte redan är täckt av den befintliga texten.
3. Ett testcase-dokument (5 positiva, 3 negativa) med repro-steg, redo att
   klistras in i submission-portalen.

## Icke-mål

- Ingen utvecklarverifiering, inget portal-konto-arbete — manuellt,
  Peters jobb.
- Ingen logo, kategori, kort/lång beskrivning, support-URL — separat
  delprojekt (produkttext/branding).
- Ingen ändring av vilka 9 verktyg som är publika, inga nya verktyg,
  inga ändringar av verktygens input-scheman utöver vad som redan finns.
- Ingen OAuth — redan beslutat (`DECISIONS.md`) att `/mcp` förblir anonymt
  och OAuth läggs till som *tillägg* senare för Valvet, inte del av den
  här submissionen.
- Ingen ändring av `/sse` eller `/mcp/key` — de publiceras aldrig som
  ChatGPT-URL (redan beslutat).

## Berörda ytor

### `mcp_promptbanken`

- `mcp-server/server/mcp_server.py` — ny route, undantag i
  `BearerAuthMiddleware`.
- `mcp-server/tests/` — test för den nya routen.
- Deploy: `PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN` miljövariabel på VPS:en
  (`docker-compose.yml`/`.env`, inte hemligt — värdet är en publik token
  OpenAI själva ger ut).
- Nytt dokument `docs/openai-submission-test-cases.md` (eller liknande) —
  de 8 testcasen.

### `promptbanken`

- `privacy.html` — eventuell textjustering om audit hittar odokumenterade
  fält.

## Del 1: Domänverifieringsroute

Ny route i samma Starlette-routningslista som övriga (`mcp_server.py`,
runt rad 3504-3537, mönster `Route("/healthz", endpoint=_healthz)`):

```python
async def _openai_apps_challenge(request: Request) -> PlainTextResponse:
    token = os.environ.get("PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN", "")
    if not token:
        return PlainTextResponse("", status_code=404)
    return PlainTextResponse(token)
```

Route-registrering: `Route("/.well-known/openai-apps-challenge",
endpoint=_openai_apps_challenge, methods=["GET"])`, tillagd i samma lista
som `/healthz` m.fl.

Svaret måste vara **exakt** token som plain text, inget JSON, ingen lista
— OpenAI:s portal läser råtexten rakt av (se Bakgrund-avsnittets citat ur
deras dokumentation).

**Kritiskt undantag i `BearerAuthMiddleware`:** middlewaren undantar idag
bara `{"/healthz", "/mcp"}` från globalt bearer-krav (`mcp_server.py:3364`,
med en befintlig kommentar om att detta är en "deploy footgun" — se rad
3389). `/.well-known/openai-apps-challenge` måste läggas till i samma
undantagsset, annars svarar routen 401 på OpenAI:s verifieringsanrop
istället för token, och verifieringen misslyckas tyst.

Token-värdet i sig kommer från OpenAI:s submission-portal när Peter
startar submission-flödet där — koden här bygger bara den generella
förmågan att servera valfri token via miljövariabel. Ingen hemlighet:
värdet är designat av OpenAI för att vara läsbart av vem som helst som
kontrollerar domänen.

## Del 2: Datafälts-audit mot privacy.html

Kör de 9 publika verktygen (`health_check`, `get_client_routing_instructions`,
`list_templates`, `search_templates`, `get_template`, `list_packages`,
`get_package`, `list_package_prompts`, `recommend_packages`) mot
produktions-`/mcp` med representativa anrop, och lista varje toppnivåfält
i svaret. Jämför mot `privacy.html`s befintliga stycke om anonym
statistik (rad 48: nämner redan att promptinnehåll, råa söktermer,
IP-adresser, e-post, user-agent och nyckelmaterial *inte* sparas i
statistiken — men det stycket beskriver telemetri, inte verktygens
faktiska svarsdata).

Audit-tabellen (fogas in i denna spec eller ett separat kort dokument,
avgörs vid implementation) ska visa: verktygsnamn, fält i svaret,
huruvida fältet är produktdata (prompttexter, mallmetadata — förväntat
och OK) eller något som skulle kräva ny disclosure (t.ex. om ett svar av
misstag innehåller ett internt ID, en tidsstämpel med finkornig
spårbarhet, eller liknande).

Om audit inte hittar något odokumenterat: ingen ändring av
`privacy.html`, audit-tabellen är själva leveransen (visar att readiness
redan finns). Om audit hittar ett fält som bör nämnas: lägg till en kort
mening i samma stycke, inte en ny sektion.

## Del 3: Testcase-dokument

Nytt dokument, 5 positiva + 3 negativa, vart och ett med: verktygsnamn,
exakt input, förväntat utfall, en rad om varför det är ett meningsfullt
testfall för granskaren.

**Positiva (förslag, låses vid implementation efter faktisk verifiering
mot prod):**
1. `search_templates` med en vanlig svensk sökfras → relevanta träffar.
2. `get_template` med en känd, publicerad slug → fullständig malltext.
3. `list_packages` utan filter → lista över publicerade paket.
4. `get_package` med känd paket-slug → paketdetaljer + medlemsprompts.
5. `recommend_packages` med en kontext-indikation → relevant paketförslag.

**Negativa:**
1. `get_template` med okänd/påhittad slug → tydligt "hittades inte"-svar,
   ingen krasch, inget stacktrace-läckage.
2. `search_templates` med tom sökfråga → tomt eller brett resultat, inte
   fel.
3. `get_package` med fel typ på input (t.ex. numerisk slug där schema
   kräver text) → schemavalideringsfel med begriplig text, inget internt
   Python-traceback i svaret.

## Verifiering

1. `curl https://mcp.promptbanken.se/.well-known/openai-apps-challenge`
   svarar 200 med exakt tokenvärdet, ingen auth-header behövs.
2. Samma anrop med en felaktig/saknad `Authorization`-header svarar
   fortfarande 200 (bekräftar `BearerAuthMiddleware`-undantaget verkar).
3. `python -m pytest mcp-server/tests/test_openai_publication_contract.py`
   — befintlig svit fortsatt grön, ny route har ett eget litet test.
4. Audit-tabellen manuellt verifierad mot minst ett riktigt svar per
   verktyg (inte bara läst ur källkoden).
5. Efter deploy: kör alla 8 testcase manuellt mot produktion, bekräfta
   verkligt utfall matchar dokumenterat förväntat utfall innan de klistras
   in i portalen.

## Rekommenderad implementationordning

1. Route + middleware-undantag + eget test (kod, `mcp_promptbanken`).
2. Deploy till VPS, sätt `PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN` (platshållarvärde
   tills Peter har det riktiga från portalen), verifiera routen live.
3. Datafälts-audit mot produktion, uppdatera `privacy.html` vid behov
   (`promptbanken`-repot).
4. Testcase-dokument, verifierat manuellt mot produktion.
