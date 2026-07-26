# OpenAI Submission Checklist

## Server
- [ ] Produktions-URL: `https://mcp.promptbanken.se/mcp`
- [ ] Anonym `initialize`, `tools/list` och samtliga nio publika `tools/call` fungerar
- [ ] Inga privata eller skrivande verktyg syns eller kan anropas
- [ ] Verktygsnamn, svenska titlar, beskrivningar, scheman och annotations är verifierade

## Listing
- [ ] Plugin-namn och kort beskrivning är slutgranskade
- [ ] Logotyp är kvadratisk och godkänd för publicering
- [ ] Privacy policy har publik HTTPS-URL
- [ ] Användarvillkor har publik HTTPS-URL
- [ ] Supportkontakt och support-URL fungerar

## Review Evidence
- [ ] Testprompt för att söka en mall är dokumenterad med förväntat svar
- [ ] Testprompt för att lista paket är dokumenterad med förväntat svar
- [ ] Testprompt för rollrekommendation är dokumenterad med förväntat svar
- [ ] Testprompt utan träff ger tom lista utan fel
- [ ] Test av privat verktygsnamn ger säkert MCP-fel utan sidoeffekt

## Security
- [ ] Loggar innehåller inte rå prompttext, MCP-nycklar eller personuppgifter
- [ ] Rate limiting och timeout-beteende är verifierat
- [ ] Privacy- och routinginstruktionen förbjuder rå persondata till den öppna MCP:n
