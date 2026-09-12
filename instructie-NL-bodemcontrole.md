# Instructie voor de NL-chat (Tiptopshop) — bodemprijs-bewaking voor bevroren artikelen

Deze fix is op 27 juli gebouwd en getest in het **BE-project** (Dreamhouse&Garden,
repo `peterhoman/bol-repricing-be`). Peter wil hem ook in NL, zodat beide
projecten identiek werken. Bouw hem in `bol-repricing` (NL/Tiptopshop) met de
NL-formules en NL-URLs — kopieer geen BE-waarden.

## Het probleem

Een bevroren artikel (koopblok gewonnen, staat in `frozen.json`) wordt op zijn
winnende klantprijs vastgehouden: nooit verlaagd, nooit gereset. Elk ander
codepad berekent de bodemprijs elke run opnieuw uit de **verse** B-Living
klantprijs en klemt daarop vast, dus een inkoopprijsverhoging corrigeert zichzelf
daar binnen één run.

Bij bevroren artikelen gebeurde dat niet. Verhoogt B-Living de inkoopprijs van een
artikel dat vorige week bevroren is, dan blijven we op de oude prijs verkopen —
mogelijk maanden, onder de margegrens, zonder dat iets dat opmerkt.

Gecontroleerd op 27 juli in BE: op dat moment stond geen enkel bevroren artikel
onder zijn bodem. Het is dus een gat dat gedicht wordt, geen reparatie van
bekende schade. **Controleer bij NL wel of daar wél artikelen onder de bodem
staan** — dat kan daar anders liggen.

## Wat te bouwen

### 1. Nieuwe methode in de repricing-engine

Naam: `clamp_frozen_to_floor(self, frozen: dict) -> list`

Gedrag:
- Loop over elke EAN in `frozen`
- Sla over als de EAN niet in de verse B-Living-feed zit
- Bereken `floor = self.calculate_minimum_price(verse_klantprijs)`
- Bereken `held_price = self.calculate_normal_price(vastgehouden_klantprijs)`
- Is `held_price < floor - 0.01`, dan:
  `frozen[ean] = self.calculate_klantprijs_for_target_price(floor)`
- Wijzigt `frozen` **in place**, geeft een lijst `(ean, oude_prijs, nieuwe_prijs)` terug
- Print een regel per opgetild artikel, zodat het in de runlog zichtbaar is

**Belangrijk: alleen omhoog, nooit omlaag.** Een bevroren artikel dat ruim boven
zijn bodem staat is een winnaar die marge maakt — die blijft exact staan. De
`- 0.01` marge voorkomt dat afrondingsruis onnodige aanpassingen triggert.

### 2. Aanroepen op twee plekken

**a) In de stateless cloud-run** (bij BE: `run_single_iteration_stateless`),
direct ná het auto-unfreeze-blok en vóór de artikelenlus:

```python
if self.clamp_frozen_to_floor(frozen):
    self.upload_json_to_github(frozen, "frozen.json")
```

**b) In de ochtend-snelstart** (bij BE: `match_competitor_prices`), direct na het
laden van frozen/big_gap/master_tracked/last_published:

```python
frozen_lifted = self.clamp_frozen_to_floor(frozen)
```

De snelstart publiceert alle bevroren prijzen óók in de XML, dus die mag geen
verouderde prijs meenemen.

Let op bij (b): in BE stond de upload van `frozen.json` achter `if newly_won:`.
Die moet gesplitst worden, anders blijft een optilling zonder nieuwe winnaars
onopgeslagen:

```python
if newly_won or frozen_lifted:
    self.upload_json_to_github(frozen, "frozen.json")
if newly_won:
    self.remove_eans_from_csv(set(newly_won))
```

Controleer of NL dezelfde constructie heeft.

### 3. Vangnet in de audit-functie

Voeg als derde controle toe aan de bestaande consistentie-audit: geen enkele EAN
in `adjustments` mag onder de actuele bodemprijs gepubliceerd worden.

```python
below_floor = []
for ean, kp in adjustments.items():
    if ean not in self.bliving_klantprijzen:
        continue
    floor = self.calculate_minimum_price(self.bliving_klantprijzen[ean])
    price = self.calculate_normal_price(kp)
    if price < floor - 0.01:
        below_floor.append(f"{ean} (EUR{price:.2f} < floor EUR{floor:.2f})")
if below_floor:
    issues.append(...)
```

Waarom naast de actieve fix: er is nóg een pad dat een eerder opgeslagen prijs
opnieuw publiceert zonder herberekening — de `last_published`-prijs die wordt
vastgehouden na een mislukte buybox-check. Dat pad wordt bij de eerstvolgende
cloud-run vanzelf tegen de bodem geklemd, dus het venster is klein (in BE: één
cent, maximaal ~30 minuten). De audit-controle vangt dat én elk toekomstig pad
dat nu nog niet bestaat, en laat een spoor achter in `audit_report.json`.

## Testen vóór uitrol

Twee tests, allebei zonder naar GitHub te uploaden (stub
`upload_json_to_github` af met een lambda die `True` teruggeeft):

1. **Echte data**: draai `clamp_frozen_to_floor` op de huidige `frozen.json`.
   Uitkomst in BE was 0 opgetild. Wijkt NL af, meld dat aan Peter met de lijst —
   dan is er wél geld weggelekt en wil hij dat weten.
2. **Kunstmatig geval**: halveer de klantprijs van één bevroren artikel en
   controleer dat het exact naar de bodem wordt getild en dat alle andere
   artikelen ongewijzigd blijven.

## Gevolg om aan Peter te melden

Als een optilling daadwerkelijk gebeurt, stijgt de prijs van een bevroren winnaar
en kan het koopblok daardoor wegvallen. Dat is bewust: Peters harde regel is dat
er nooit onder de bodemprijs verkocht wordt, en die weegt zwaarder dan het behoud
van een koopblok.

## Uitrol

De cloud-job draait de versie die op **GitHub** staat, niet de lokale. Upload het
gewijzigde engine-bestand dus naar de NL-repo, anders werkt de fix alleen lokaal
bij de snelstart.
