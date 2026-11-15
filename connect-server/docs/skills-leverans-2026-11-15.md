# Egna Skills i Connect DEV – leverans och klienttest (2026-11-15)

Gren: `feat/connect-skills` (från `feat/connect-dev-activation`).
Databas: `promptbanken` gren `feat/creator-skills`, migrationerna
`20261115200000`, `20261115200100`, `20261115200200`, körda på DEV
(`dklxriwjskyglqeombvv`). Ingen ändring i PROD.

Driftsatt: `connect-dev.promptbanken.se`, image
`promptbanken-connect:skills-candidate` (serverversion 0.4.0).
Rollback på VPS:en:
`cd ~/promptbanken-connect-dev && cp docker-compose.yml.before-skills docker-compose.yml && docker-compose up -d`
(vid `KeyError: 'ContainerConfig'`: `docker rm -f` den omdöpta containern och kör `docker-compose up -d` igen).

## MCP-kontrakt (core, 13 verktyg)

Oförändrade: `get_connect_context`, `get_support`, `get_open_item`,
`save_my_profile`, `save_my_way_of_working`, `get_my_history`,
`restore_my_version`.

Nya: `list_my_skills`, `get_my_skill`, `validate_my_skill`,
`create_my_skill`, `update_my_skill`, `set_my_skill_active`.

- Skrivningar: utan `confirmed` förhandsvisning med `confirm_text`; med
  `confirmed: true` och `request_id` sparar databasen (validering,
  idempotens, versionskonflikt) och Connect läser tillbaka (`verified: true`).
- `get_connect_context`: `my_skills` (aktiva, korta: id, name, purpose,
  use_when, not_when, version, `source: creator_skill`) inom egen budget på
  3 500 tecken, `more_skills` med bara namn när budgeten är slut,
  `inactive_skills`, och `how_to_manage_skills`.
- `get_support("skill:<slug>")`: hela SKILL.md, version, filer (inline upp
  till 6 000 tecken, annars lista och `resource`), deklarerade beroenden,
  personliga regler för skillen, `precedence`, `how_to_apply`.
- `get_my_history` / `restore_my_version` stöder `skill:`-mål; återställning
  blir en ny version.
- Specialisternas `use_when` i indexet är kortad till meningen "Använd när …"
  (vad de gör finns i `in_short`; hela beskrivningen finns i `get_support`).

## Automatiska resultat

| Svit | Resultat |
| --- | --- |
| Connect pytest | 154/154 (27 nya i `tests/test_skills.py` och `tests/test_data.py`) |
| DB-test `promptbanken/supabase/tests/verify_creator_skills_dev.sql` | 20/20 på DEV, rullas tillbaka |
| promptbanken `npm test` | 369/369, bygget godkänt |
| Live mot `connect-dev.promptbanken.se` (syntetiska konton) | 32/32: skapa, idempotens, läsa, kontext utan SKILL.md, resurs, path traversal, regel ovanpå, ny version, gammal version kvar, inaktuell version nekas, samtidiga uppdateringar (en sparas, en nekas), av/på, annan användare nekas, nio specialister, `get_open_item`, `prompts/list` |
| Creator-webben (lokal förhandsvisning mot DEV-databasen, och `dev.promptbanken.se/creator-skills`) | Samma skill (version 3) visas med identisk SKILL.md och fil; skapa, validering, version 2, jämförelse, av/på verifierade |

Kontextstorlek live med två skills och en profil: 11 641 tecken.

## Klienttest i ChatGPT – INTE GENOMFÖRT

Det som kräver en riktig AI-klient är inte mätt. Ett lyckat direkt
MCP-anrop bevisar inte automatisk aktivering.

### Förberedelser

1. Använd ett syntetiskt testkonto i Promptbanken dev. Offertgranskaren finns
   redan på `free.user@test.se` (version 3, aktiv). Använder du ett annat
   konto: be ChatGPT skapa den först (fall S1).
2. ChatGPT → Appar och kopplingar → Connect DEV
   (`https://connect-dev.promptbanken.se/mcp`). Uppdatera kopplingen så att
   verktygslistan (13 verktyg) laddas om. Logga in med testkontot.
3. Ny chatt per fall. Nämn aldrig Promptbanken, Connect, skill-id eller verktyg
   om inte fallet säger det.

### Fall

| # | Meddelande | Förväntat |
| --- | --- | --- |
| S1 | Skapa en skill som hjälper mig att granska leverantörsofferter. | Frågor vid behov, förhandsvisning med confirm_text. Inget sparas före ja. Efter ja: "Sparat" bara med verified. |
| S2 | Hjälp mig granska en offert. (klistra in en påhittad offert) | **Automatisk aktivering:** `get_connect_context`, sedan `get_support("skill:offertgranskaren")`. Svaret följer stegen och kontrollerar betalningsvillkor (version ≥ 2). |
| S3 | Använd min Offertgranskare på den här offerten. | Skillen hämtas. |
| S4 | Förbättra min Offertgranskare så att den också kontrollerar garantitiden. | `get_my_skill`, förhandsvisning av `update_my_skill`, ny version efter ja. |
| S5 | (ny chatt) Granska den här offerten åt mig. | Den nya versionen används. |
| S6 | Hjälp mig planera en workshop för 20 personer. | Workshopledaren, inte skillen. |
| S7 | Vad betyder ramavtal? | Inget Connect-anrop. |
| S8 | (efter att skillen stängts av) Hjälp mig granska en offert. | Skillen väljs inte automatiskt. |

Notera per fall: anropades Connect, vilket stöd hämtades, följdes metoden,
syntes tekniska ord, sparades något utan ja. Fler fall:
`evals/connect_auto_cases.json` (`PB-CONNECT-SKILL-01` … `11`), räkna med
`scripts/score_evals.py`.

## Kända begränsningar

- Skills kan inte tas bort, bara stängas av; avstängda räknas mot taket
  (Free 5, övriga 50 – antaget, kräver produktbeslut).
- Connect-token är fortfarande en generell Supabase-token (audience
  `authenticated`). Databasen skyddar skills mot direkta skrivningar, men
  PROD-blockeraren kvarstår.
- Integritetskontrollen fångar personnummer, e-post och telefon, inte namn.
- Ingen ZIP-export ännu; SKILL.md och filerna är förberedda för
  `scripts/skills/package-skill.mjs`.
- Codex-granskning kunde inte köras (Codex-kontot avvisar standardmodellen).
