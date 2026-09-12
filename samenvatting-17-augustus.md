# Samenvatting 17 augustus 2026 — Bol.com BE (Dreamhouse&Garden)

## 1. Herstel na twee dagen afwezigheid

Peter was 15 en 16 augustus weg. Hij heeft wel elke dag zijn export geüpload,
maar de ochtend-snelstart kon niet draaien — die vereist zijn eigen
internetverbinding, omdat bol.com controles vanaf datacenter-IP's blokkeert.

Verloop van het aantal koopblokken:

| moment | bevroren | verandering |
|---|---|---|
| 14 aug, na de snelstart | 174 | — |
| 14 aug, na de cloud-run | 166 | −8 |
| 15 aug | 143 | −23 |
| 16 aug | 132 | −11 |
| 17 aug, na de snelstart | 145 | +13 |
| 17 aug, na de sync | 142 | −3 |

**42 koopblokken verloren in twee dagen.** Oorzaak: zonder snelstart springt elke
ochtend de dagelijkse reset aan, waarna niet-bevroren artikelen op volle prijs
staan en pas met stapjes van €0,50 per cloud-run weer zakken. Op die hogere prijs
verliezen we het koopblok, wat bol.com in de volgende dagexport meldt, waarna de
automatische ontdooiing het artikel uit `frozen.json` haalt.

Dit was vooraf voorspeld en doorgerekend (183 artikelen zouden terugspringen,
waarvan 41 niet binnen één dag konden herstellen). De voorspelling klopte.

**Openstaand voorstel:** de dagelijkse reset alleen laten aanslaan als er
daadwerkelijk een nieuwe export is geüpload. Dan is dit probleem structureel weg.
Nog niet gebouwd.

## 2. Marge-herstel: het probleem dat Peter signaleerde

Peter merkte op dat bevroren artikelen op een lage prijs blijven staan en nooit
meer omhoog gaan, ook niet als de concurrent verdwenen is. Terecht: er zaten twee
correcties op een bevroren prijs, maar die kijken allebei naar de **inkoopprijs**
(`clamp_frozen_to_floor` en `clamp_frozen_to_normal_price`), niet naar de
concurrentie.

Gemeten bij 145 bevroren artikelen:

| | |
|---|---|
| onder hun volle prijs | **116** |
| marge die op tafel lag | **€1.564,66** |
| gemiddeld per artikel | €13,49 |

## 3. Wat er gebouwd is

**Automatische kandidaatselectie in `probe_recovery.py`** (nieuw vandaag):

```bash
python src/probe_recovery.py candidates [n]   # tonen, verandert niets
python src/probe_recovery.py auto [n]         # selecteren en starten
python src/probe_recovery.py check            # ~90 min later: houden of terugzetten
```

Selectie op hoogste terug te halen marge, minimaal €10, met een wachttijd van 14
dagen bijgehouden in het nieuwe `probe_history.json`. Zonder die wachttijd staat
een teruggezet artikel morgen weer bovenaan de lijst, want zijn veilige prijs is
hersteld.

**Waarschuwing tegen een te vroege sync** (gemeld door de NL-chat): na een check
met terugzettingen staat de veilige prijs wel in onze feed, maar heeft Channable
die nog niet geïmporteerd. Een sync kijkt live op bol.com, ziet daar nog de
probe-prijs, en ontdooit die artikelen voor niets. NL mat 11 valse verliezen van
15; bij ons waren het er 0 van 3, maar het schaalt mee met het aantal
terugzettingen. `check` waarschuwt hier nu zelf voor.

## 4. Resultaat van de twee probe-rondes

| | ronde 1 | ronde 2 | totaal |
|---|---|---|---|
| kandidaten | 15 | 20 | 35 |
| winst per artikel | €32 – €51 | €17 – €32 | |
| behouden | **12 (80%)** | **8 (40%)** | 20 |
| teruggezet | 3 | 12 | 15 |
| terugverdiend | **€521,74** | **€200,19** | **€721,93** |

Ter vergelijking, de handmatige rondes van juli: 9 van 15 en 1 van 15.

**Vuistregel die hieruit volgt: onder ongeveer €25 winst zakt het behoud naar
40%.** Beter de drempel verhogen dan dieper in de lijst graven.

## 5. Wat er nu nog ligt

| winst per artikel | kandidaten | waarde |
|---|---|---|
| ≥ €25 | **0** | — |
| ≥ €15 | 5 | €81,62 |
| ≥ €10 | 18 | €230,33 |

De bovenkant van de lijst is opgeruimd. De 18 die overblijven zitten allemaal in
de zone waar het behoud laag is.

## 6. Waarom dit niet volautomatisch kan — het kernprobleem

De probe bestaat noodzakelijkerwijs uit twee stappen met een pauze ertussen:

1. **`auto`** zet de artikelen op hun volle prijs in onze feed op GitHub
2. **wachten** tot Channable die feed importeert en bol.com de nieuwe prijs toont
3. **`check`** kijkt live op bol.com of we het koopblok nog hebben, en zet
   verliezers terug

Twee harde beperkingen maken stap 3 onautomatiseerbaar:

**a. De controle vereist Peters eigen internetverbinding.** Bol.com geeft
403 Forbidden op verzoeken vanaf datacenter- en cloud-IP's. De GitHub
Actions-runners draaien in de cloud, dus de cloud-job kan geen koopblok-status
opvragen. Dat geldt voor alles wat live checkt: `match_prices.py`,
`sync_buybox.py` en `probe_recovery.py check`.

**b. Er moet 70 tot 90 minuten tussen stap 1 en 3 zitten.** Channable importeert
onze feed periodiek, niet direct. Controleren vóór die import meet de oude prijs
en geeft dus een waardeloos antwoord.

De voor de hand liggende oplossing — een wachttaak van 90 minuten op Peters
computer — is hier al een keer geprobeerd en mislukt: de computer ging in
slaapstand, de taak overleefde dat niet, en dertig artikelen stonden een hele dag
op volle prijs. Sindsdien is de regel dat de controle alleen op Peters seintje
draait.

**Samengevat:** de stap die niet geautomatiseerd kan worden is niet het rekenwerk
maar het *live kijken op bol.com*, en dat kan alleen vanaf een gewone
thuisverbinding op een moment dat de computer aan staat.

## 7. Denkrichtingen voor een oplossing

Niet uitgewerkt, wel het overwegen waard:

- **Een machine die altijd aan staat op een residentieel IP.** Een kleine
  computer die thuis blijft draaien kan de checks op vaste tijden uitvoeren
  zonder dat iemand een seintje hoeft te geven. Lost beide beperkingen in één
  keer op: residentieel IP én geen slaapstand.
- **Slaapstand uitschakelen op de bestaande computer** en de taak via de
  Windows-taakplanner draaien in plaats van als wachttaak binnen een sessie.
  Goedkoper, maar de computer moet dan wel aan blijven.
- **Een proxy met een residentieel IP** vanuit de cloud-job. Technisch mogelijk,
  maar betaald en het schendt mogelijk bol.coms voorwaarden — niet aan te raden.
- **Accepteren en inplannen**: één vast moment per week waarop Peter een seintje
  geeft. Kost niets, werkt altijd, en de meting van vandaag laat zien dat de
  achterstand in twee rondes weg te werken is.

## 8. Overige uitkomsten van vandaag

**Drie selectiecriteria getest en alle drie verworpen** (samen met de NL-chat):
sorteren op bedrag voorspelt niet of een artikel zijn hogere prijs houdt, het
aantal dagen onafgebroken bevroren ook niet, en productgroep evenmin — onze drie
verliezers waren allemaal vliegengordijnen, maar zes van onze twaalf winnaars
ook. Conclusie: blijven sorteren op bedrag, omdat dat bij gelijke trefkans de
opbrengst per treffer maximaliseert.

**Verschil met NL is groot en onverklaard:** zelfde ontwerp en zelfde drempel,
maar NL hield 3 van 15 (€84,35) tegen onze 12 van 15 (€521,74). Vermoedelijk
marktverschil — bol.com NL heeft meer verkopers.

**Instructies uitgewisseld met de NL-chat:** vier documenten in deze map, over de
probe-aanpak, de automatische selectie, het sync-timingprobleem en de verworpen
selectiecriteria.
