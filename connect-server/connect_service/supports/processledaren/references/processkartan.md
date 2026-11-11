# Överlämning till Processkartan-skillen

Processkartan är ett verktyg i Promptbanken (https://processkartan.promptbanken.se). Det finns en egen skill, `processkartan`, som gör processkartor i verktygets filformat, kontrollerar dem och lämnar över JSON som kan klistras in. Den här skillen (Processledaren) ska **använda** den, inte kopiera den.

## Varför

- Formatet och valideringen ägs av Processkartan-skillen och kan ändras där. Dubbletter blir fel med tiden.
- Processledaren ansvarar för det som kommer före och efter kartan: uppdrag, nuläge, analys, ansvar och förbättringar.

## Så lämnar du över

1. Kontrollera om en skill som heter `processkartan` finns bland användarens skills. Skriv inte att du har den om du inte sett den.
2. Fyll i `assets/processbeskrivning.md` med en **avidentifierad** beskrivning: roller (inte personer), start, steg i ordning, beslutspunkter med två utfall, slingor, slut och dina antaganden.
3. Be Processkartan-skillen göra kartan av beskrivningen, till exempel: *"Använd processkartan och gör en processkarta av den här beskrivningen."*
4. Processkartan-skillen lämnar tillbaka en fil och JSON att klistra in i Processkartan. Låt den redovisa sina antaganden.
5. Gå igenom kartan med användaren (stämmer ordningen? saknas undantag eller slut?) och gå vidare till analysen.

## Om skillen saknas

- Leverera processen som numrerad lista eller tabell: roller, steg, beslutspunkter (med utfall), slingor och slut.
- Säg att användaren kan göra en karta med Processkartan-skillen (https://github.com/Pwenstrom/processkartan-skill/releases/latest, `skill.zip`) eller använda mallen *Från beskrivning till processkarta* i Promptbankens katalog.
- Skriv inte själv någon Processkartan-JSON och hitta inte på något annat kartformat som om det vore verktygets.
- Behöver användaren en enkel bild direkt: en tydlig numrerad lista är att föredra framför en bild som kan vara fel.

## Personuppgifter

Processkartan sparar kartor lokalt i användarens webbläsare. Skillen får ändå aldrig innehålla personnamn. Skriv roller.
