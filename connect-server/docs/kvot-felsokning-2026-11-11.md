# Felsökning: Free-kvoten stoppar personliga anpassningar (2026-11-11)

Utfört med läsning i `promptbanken-dev`. Ingen data och inget abonnemang är
ändrat. Användar-id och adresser redovisas inte här.

## Fynd

| Fråga | Svar |
| --- | --- |
| Vilken användare identifierar Connect DEV? | Den användare som OAuth-token tillhör (`sub`). ChatGPT-testet körde med kontot `wenstrompeter` (Free). Claude-testerna i samma period körde med ett annat konto, där taket tillfälligt höjts till 100. Därför lyckades sparningar i Claude men inte i ChatGPT. |
| Kontonivå och kvot | `wenstrompeter`: plan `free`, `max_prompts = 3`. |
| Antal privata prompter | 3 aktiva (`module = 'kommun'`, ej arkiverade): vanliga Creator-utkast. Ingen Connect-profil och inget arbetssätt. |
| Varför samma kvot? | Connect lagrar profil och egna arbetssätt som privata Creator-prompter (`connect_create_my_prompt` → `app_private.create_my_creator_prompt`). Raden får standardmodulen `kommun`, och triggern `enforce_content_access_model` räknar alla aktiva `kommun`-prompter mot `workspaces.max_prompts`. Kategorin (`connect-profil`, `connect-arbetssatt`) påverkar inte räkningen. |
| Rätt identitet vid sparning och läsning? | Ja. Läsning (`list_my_creator_prompts`) och skrivning (`connect_*`-RPC:er, `security invoker`) använder samma token och `auth.uid()`. Sista lyckade Connect-skrivning för kontot är 2026-11-10; dagens försök nekades av kvoten innan något skrevs. |
| Avsiktlig eller felaktig kvotkontroll? | Mekanismen är avsiktlig: Free får 3 privata prompter. Att den även träffar Connect-anpassningar är en **oavsiktlig sidoeffekt** av lagringsvalet. Den noterades som avvikelse i `vnext-leverans.md` men har inget produktbeslut bakom sig. |

## Grundorsak

Personliga anpassningar lagras som vanliga privata prompter. Ett Free-konto
med tre egna prompter har därför noll utrymme för personalisering, och den
första sparningen ("kortare sammanfattningar") nekas. Det motsäger
produktlöftet "Din AI. Ditt sätt att arbeta.".

## Förslag som fungerar för Free

**Undanta Connect-anpassningar från prompttaket och ge dem ett eget, litet tak.**
Migrering i `promptbanken` (dev först), i `enforce_content_access_model`:

1. Rader med `category = 'connect-profil'` räknas inte mot `max_prompts`.
   Högst **1** aktiv profil per användare. Den bär alla personliga regler.
2. Rader med `category = 'connect-arbetssatt'` räknas inte mot `max_prompts`,
   men har eget tak: förslagsvis **3 på Free**, **20 på Pro**.
3. Taken kontrolleras bara när en rad blir aktiv (samma princip som
   `capacity_check_on_activation`), så en nedgradering låser inget innehåll.

Effekt: varje Free-användare kan alltid spara regler och några egna
arbetssätt, oavsett hur många vanliga prompter de har. Inga befintliga data
behöver flyttas, och Connect-koden behöver inte ändras.

**Risk och motåtgärd:** kategorin är fri text i Creator. En användare skulle
kunna sätta `connect-arbetssatt` på vanliga prompter för att komma runt
taket. Det egna taket (3 eller 20) begränsar det. Vill man stänga det helt
låter man bara Connects RPC:er sätta dessa kategorier.

**Alternativ som inte rekommenderas:** att spara anpassningar som
`module = 'valvet'` (Valvets tak 50/1000) blandar ihop två produkter och är
svårt att förklara. Att höja Free-taket generellt är ett abonnemangsbeslut.

## Beslut som behövs

Produktbeslut B1: godkänn undantaget och taken (1 profil, 3/20 arbetssätt).
Därefter migrering på dev, test med ett Free-konto som har 3 prompter, och
sedan PROD efter separat godkännande. Inget av detta är genomfört.

## Tills dess

Connect visar ett begripligt besked: inget har ändrats, varför, vad
användaren kan göra, och att önskemålet följs i samtalet. Verifierat live.
