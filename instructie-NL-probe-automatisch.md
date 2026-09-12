# Instructie voor de NL-chat (Tiptopshop) — automatische kandidaatselectie voor margeherstel

Gebouwd, getest en gedraaid in het **BE-project** (Dreamhouse&Garden) op 17 augustus
2026. Peter wil dat NL hetzelfde krijgt.

Lees eerst `instructie-NL-margeherstel-probe.md` in deze map — daar staat waarom
we voor de probe kiezen en niet voor de €0,50-stappen uit jullie voorstel. Dit
document is het bouwrecept.

Bouw het in `bol-repricing` met de **NL-formules en NL-URLs**. Alle bedragen
hieronder zijn BE-cijfers; meet je eigen drempel.

## Resultaat van de eerste automatische ronde in BE

| | |
|---|---|
| kandidaten (top 15 op terug te halen marge) | 15 |
| hogere prijs behouden | **12 (80%)** |
| koopblok verloren, automatisch teruggezet | 3 |
| terugverdiend | **€521,74 per verkoopcyclus** |

Ter vergelijking, de twee handmatige rondes van juli: 9 van 15 (60%) en 1 van 15
(7%). Het verschil zit hem in de selectie — die tweede ronde pakte artikelen met
te weinig ruimte. Vandaar de minimumdrempel hieronder.

## Wat er al moet staan

De twee-fasen-probe zelf: `probe_recovery.py start <eans>` zet bevroren artikelen
op hun volle prijs met een backup, `check` controleert ~90 minuten later live en
zet verliezers terug. Heeft NL dat script niet, bouw dat dan eerst — zonder de
automatische backup-en-terugzetten is dit onverantwoord.

## Wat toe te voegen

### 1. Instelbare grenzen bovenaan het bestand

```python
MIN_GAIN = 10.0        # euro terug te halen verkoopprijs; daaronder niet proberen
COOLDOWN_DAYS = 14     # niet opnieuw proberen voor de concurrent tijd had te bewegen
DEFAULT_BATCH = 15
```

`MIN_GAIN` is de belangrijkste knop. In BE bleek €10 een goede ondergrens; meet
zelf waar bij NL de opbrengst omslaat. Begin desnoods hoger en zak later.

### 2. `select_candidates(engine, limit)`

Rangschik de bevroren artikelen op **terug te halen marge**:

```
winst = volle prijs(VERSE inkoopprijs) − huidige bevroren verkoopprijs
```

Let op dat je de verse inkoopprijs uit de leveranciersfeed gebruikt, niet de
prijs waarop het artikel ooit bevroren werd — anders reken je met verouderde
inkoop.

Sluit uit:

- artikelen die niet meer in de feed staan (geen actuele inkoopprijs)
- artikelen die al op of boven hun volle prijs staan. Dit sluit meteen de
  winnaars van eerdere rondes uit: die staan ná een geslaagde probe precies op
  hun volle prijs, dus hun winst is nul.
- artikelen die binnen `COOLDOWN_DAYS` geprobeerd zijn

Sorteer aflopend op winst, geef de beste `limit` terug.

**De wachttijd is niet optioneel.** Een teruggezet artikel krijgt zijn veilige
lage prijs terug en staat daardoor de volgende dag weer bovenaan de lijst. Zonder
wachttijd probeer je elke ronde dezelfde verliezers.

### 3. `probe_history.json` op GitHub

`{ean: "JJJJ-MM-DD"}`, de datum van de laatste probe. Schrijf in de **check-fase**
élke geprobeerde EAN weg, dus zowel behouden als teruggezet:

```python
history = fetch_json("probe_history.json", {})
today = date.today().isoformat()
for ean in probe_backup:
    history[ean] = today
upload_json(history, "probe_history.json", f"Probe history: {len(probe_backup)} EAN(s) probed on {today}")
```

Doe dit vóór je `frozen_probe_backup.json` leegmaakt, anders ben je de lijst kwijt.

### 4. Twee commando's erbij

```bash
python src/probe_recovery.py candidates [n]   # alleen tonen, verandert niets
python src/probe_recovery.py auto [n]         # selecteren en meteen starten
```

`candidates` is puur om te kijken. Handig om Peter eerst de lijst te laten zien
voor je een ronde start, zeker de eerste keer.

## Testen vóór uitrol

1. **Droogloop**: `candidates 20` en controleer dat de winst per artikel klopt
   met een handmatige berekening van twee willekeurige regels.
2. **Uitsluiting werkt**: een artikel dat al op zijn volle prijs staat mag niet
   in de lijst voorkomen.
3. **Wachttijd werkt**: draai `candidates` direct na een check-ronde; de zojuist
   geprobeerde EAN's moeten overgeslagen worden (het script meldt hoeveel).
4. **Bodem blijft heilig**: na de ronde moeten de bestaande bodemcontrole en de
   bandcontrole `[bodemprijs, volle prijs]` nog steeds 0 overtredingen geven.

## Werkwijze per ronde

1. Draai de ochtend-snelstart eerst, zodat de dag met verse prijzen begint.
2. `python src/probe_recovery.py auto 15`
3. **Wacht op Peters seintje**, ~90 minuten later. Plan dit NOOIT in als
   wachttaak: in BE is dat misgegaan toen de computer in slaapstand ging en
   dertig artikelen een hele dag op volle prijs stonden.
4. `python src/probe_recovery.py check`
5. Rapporteer: behouden, teruggezet, en het terugverdiende bedrag.

Draai geen twee scrape-scripts tegelijk — niet de probe naast de sync, en ook
niet NL naast BE. Dat geeft rate-limiting bij bol.com.

## Hoe vaak

Er kan meerdere rondes per dag, zolang er kandidaten boven de drempel zijn: de
wachttijd geldt alleen voor wat je al geprobeerd hebt. BE draaide op 17 augustus
twee rondes op één dag (15 + 20 artikelen). Ga door tot de winst per artikel in
de buurt van de drempel komt; daaronder is het risico niet meer de moeite waard.

## Uitrol

De cloud-job draait de versie op **GitHub**, niet de lokale. Upload het gewijzigde
`src/probe_recovery.py` los via de Contents API, niet via `setup_upload.py` (dat
overschrijft ook de statusbestanden met lokale stubs).
