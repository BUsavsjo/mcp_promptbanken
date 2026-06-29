# Data och säkerhet

## Grundregel
Lägg inte personuppgifter, elevdata, vårdnadshavaruppgifter, API-nycklar, tokens, `.env`-filer, rådata eller exporter från verksamhetssystem i Git.

## Får finnas i repo
- Källkod
- Dokumentation
- Promptmallar som är avsedda att vara offentliga eller interna utan känsliga uppgifter
- Anonymiserad exempeldata
- Testdata utan koppling till verkliga personer

## Ska inte finnas i repo
- `.env`
- API-nycklar
- Tokens
- CSV-filer med personuppgifter
- Excel-filer med elevdata
- Exporter från verksamhetssystem
- Bearbetade datakällor med personuppgifter
- Lokala analysfiler
- Loggar som innehåller personuppgifter, tokens eller användartext

## Rekommenderad lokal struktur
```text
data/example/       # anonymiserad exempeldata
data/private/       # lokal data, ignoreras av Git
exports/            # lokala exporter, ignoreras av Git
```

## Vid osäkerhet
Om du är osäker på om data får versionshanteras, låt bli att committa den.

## Projektets särskilda risk
Promptbanken MCP ska i hosted-läge vara metadata-only. Skicka inte användarens uppgift, dokumenttext, personuppgifter eller sekretessbelagd information till hosted-servern.

I local-läge kan servern bearbeta användartext på användarens egen maskin. Även då ska loggar, exporter och testfiler hållas fria från känslig information.
