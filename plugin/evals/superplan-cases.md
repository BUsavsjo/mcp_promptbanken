# Superplan – testfall

Körs manuellt i ChatGPT (developer mode, pluginet installerat mot dev) och i Codex. Notera för varje fall: aktiverades skillen, vilka verktyg anropades, och stämmer förväntat beteende.

| # | Kategori | Användarens meddelande | Förväntat |
|---|---|---|---|
| 1 | Direkt | "Kör superplan: vi behöver en plan för att införa digitala signaturer på förvaltningen." | Skillen aktiveras. `list_package_prompts("superplanlage")`, sedan `get_template` för första fasen. Högst tre fokuserade frågor, inga fasnamn. |
| 2 | Direkt | "Hjälp mig hela vägen med en kommunikationsplan för en omorganisation, kör." | Tolkas som delegation. Kort riktningssammanfattning utan extra bekräftelse om inget nytt antagande tillkommit. |
| 3 | Indirekt | "Jag har ett rörigt uppdrag om att minska väntetider i kundtjänst och vet inte var jag ska börja." | Skillen aktiveras. Riktningsfasen startar. |
| 4 | Indirekt | "Ta fram ett beslutsunderlag åt mig om vi ska byta ärendesystem." | Skillen aktiveras. I utförandet rekommenderas en specialist (t.ex. business case- eller konsekvensanalysflödet) med ett kort skäl. |
| 5 | Ofullständig | "Kör superplan." | En naturlig fråga om vad uppdraget gäller. Ingen katalogsökning innan uppdraget är känt. |
| 6 | Ofullständig | "Superplan för mitt projekt." | En fråga som kan ändra vad som ska göras (mål eller leverans), inte en lång lista. |
| 7 | Utanför | "Vad betyder PGSA?" | Skillen aktiveras inte. Vanligt svar. |
| 8 | Utanför | "Hitta en mall för ett vardagsmejl." | Skillen aktiveras inte. `search_templates` direkt. |
| 9 | Kantfall | Ny chatt: "Fortsätt mitt superplan-uppdrag om digitala signaturer, vi hade låst riktningen." | Ber om senaste riktning/överenskommelse och fortsätter från specifikationsfasen. |
| 10 | Kantfall | Dev-MCP stoppad i admin, sedan "Kör superplan för en workshop om arbetsmiljö." | Säger att katalogen inte gick att nå, erbjuder att fortsätta utan den, hittar inte på mallinnehåll. |
| 11 | Integritet | "Kör superplan på den här skrivelsen: [inklistrad text med namn och personnummer]" | Söktermer till `search_templates` är allmänna ("skrivelse granskning"), aldrig namn eller personnummer. |
| 12 | Routing till workflow | Fortsättning på fall 3 där förbättringsflödet väljs. | `list_package_prompts("forbattringside-till-synlig-effekt", current_step=1)` – stegvisaren visas i ChatGPT. |
