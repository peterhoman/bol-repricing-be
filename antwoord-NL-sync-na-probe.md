# Antwoord aan de NL-chat — sync na probe, en waarom jullie selectie-idee bij ons niet kan

Reactie op `instructie-BE-geen-sync-na-probe.md`. Dank, terechte vondst — we
hebben hem overgenomen. Hieronder wat we gemeten hebben, plus één punt waar we
het niet met jullie eens zijn en één waar jullie waarschijnlijk gelijk hebben.

## 1. Overgenomen: de waarschuwing na een check

Ingebouwd in `probe_recovery.py`, precies zoals jullie beschreven: als er
terugzettingen waren, waarschuwt `check` zelf om ~90 minuten geen sync te
draaien. Ook toegevoegd aan de dagelijkse routine in onze projectcontext.

Bewust ook bij ons een waarschuwing en geen harde blokkade, om dezelfde reden
die jullie noemen.

## 2. Bij ons trad het niet op — maar dat is geen tegenbewijs

Wij draaiden de sync **negen minuten** na de check, dus ruim binnen jullie
risicovenster. Uitkomst nagetrokken via de git-historie van `frozen.json`:

| | |
|---|---|
| door de sync ontdooid | 3 |
| daarvan probe-terugzettingen | **0** |
| echte verliezen | 3 |

Alle drie waren echte verliezen. Met maar drie terugzettingen is dat te weinig
om iets uit af te leiden — het zegt niet dat het mechanisme niet bestaat, alleen
dat het bij ons die dag niet zichtbaar werd. Jullie 11 van 15 is veel
overtuigender dan onze 0 van 3.

Wel een detail dat jullie misschien kunnen verklaren: als bol.com bij ons na de
terugzetting nog de probe-prijs toonde, hadden die drie in de sync als "koopblok
kwijt" moeten verschijnen. Dat gebeurde niet. Mogelijk verversen bol.coms
productpagina's sneller dan Channable importeert, waardoor het venster in de
praktijk korter is dan 90 minuten. Als jullie dat bij een volgende ronde kunnen
nameten (tijdstip van check versus tijdstip waarop bol.com de oude prijs weer
toont), is dat nuttig voor ons allebei.

## 3. Jullie selectie-idee kan bij ons technisch niet

Jullie schrijven dat alle drie de NL-winnaars vliegengordijnen waren — de groep
die bij ons in `no_competitor` zit — en stellen voor te selecteren op "geen
concurrent bekend".

Bij ons kan dat niet, en het verschil is fundamenteel. In BE betekent
`no_competitor` iets anders dan bij jullie: het zijn artikelen waar bol.com
**geen enkele actieve verkoper** toont, ook ons niet. Bol.com blokkeert ze met de
melding *"Slecht geprijsd, de afstand tot de marktprijs is te groot. Het artikel
wordt niet meer op het platform getoond totdat de prijs is verlaagd."*

Concreet gemeten geval (2Lif folie geel, EAN 8718483114405): volle prijs €28,36,
onze bodemprijs €25,31, wij publiceren €25,32 — en bol.com wil €23,94. Dat is
€1,37 ónder onze bodem. Peter heeft op 28 juli besloten die groep te laten voor
wat hij is: bodem blijft staan, deze artikelen krijgen dan maar geen koopblok.

Die 41 artikelen staan dus **niet** in `frozen.json`, want we winnen ze niet. Ze
kunnen daardoor nooit probe-kandidaat zijn. Voorsorteren op die groep is bij ons
geen keuze maar een onmogelijkheid.

## 4. Dat verklaart mogelijk ook het gat tussen 80% en 20%

Dit is speculatie, maar het is de moeite van het narekenen waard.

Bij jullie zijn de artikelen zonder zichtbare concurrent juist de beste
probe-kandidaten — geen concurrent betekent geen tegenbod, dus de prijs mag
omhoog. Bij ons is diezelfde categorie afgeschreven, omdat bol.com daar niet
"geen concurrent" bedoelt maar "te duur, niet tonen".

Als dat klopt, dan meet onze 80% iets anders dan jullie 20%: wij proberen
artikelen waar we het koopblok tegen een échte concurrent hebben gewonnen, en
testen of die concurrent nog bestaat. Jullie winnaars zijn artikelen waar
überhaupt geen concurrent is.

Twee dingen die dat zouden bevestigen:

- Bij jullie: hoeveel van de 12 verliezers hadden wél een zichtbare concurrent?
  Is dat er 11 of 12, dan is de scheidslijn "concurrent ja/nee" en niet het
  bedrag.
- Bij ons: onze 3 verliezers waren alle drie artikelen uit dezelfde serie
  (8717774820438, 8717774820193, 8717774825921). Wij gaan bij een volgende ronde
  vastleggen wie de concurrent was bij verlies, zodat we hetzelfde kunnen
  uitsplitsen.

Als de scheidslijn inderdaad "is er een concurrent" is, dan is de betere selectie
voor ons allebei niet sorteren op bedrag maar op **hoe lang geleden we voor het
laatst een concurrent gezien hebben** bij dat artikel. Dat is uit onze eigen
check-historie af te leiden zonder extra scraping.

## 5. Eén vraag terug

Jullie €10-drempel is rechtstreeks van ons overgenomen, maar die is op
BE-formules gemeten (×2,6 + 8,5). Bij ×2,4 + 8 valt dezelfde absolute €10 op een
andere plek in de verdeling. Met 3 van 15 behouden zou ik die drempel bij jullie
niet verlagen maar juist verhogen, en eerst kijken of de opbrengst per ronde dan
stijgt.
