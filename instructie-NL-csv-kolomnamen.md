# Instructie voor de NL-chat (Tiptopshop) — CSV-kolommen op naam zoeken

Gebouwd, getest en uitgerold in het **BE-project** (Dreamhouse&Garden) op 5 augustus
2026. Zit vrijwel zeker ook in NL: het is dezelfde codeconstructie, niet iets
BE-specifieks.

Bouw de fix in `bol-repricing` (NL/Tiptopshop) met de **NL-URLs**.

## Het probleem

Peter kan het "geen koopblok"-bestand bijna elke ochtend niet downloaden bij
bol.com. Hij plakt dan zelf de kolommen **Productnaam** en **EAN** in een CSV met
twee kolommen en uploadt die onder de naam `bolcom_productinformatie.csv`.

Dat is prima — bijna alles in het programma zoekt de EAN op via de kolomnaam en
werkt met beide formaten. Maar `add_eans_to_csv()` in `src/sync_buybox.py` doet
het anders. Die zet een artikel terug in de lijst wanneer het zijn koopblok
verliest, en schrijft daarbij naar **vaste kolomnummers**:

```python
num_cols = len(lines[0].split(";"))
row = [""] * num_cols
row[0] = f"Hersteld na koopblok-verlies {ean}"
row[1] = ean
row[2] = ean          # <-- bestaat niet in een bestand met 2 kolommen
```

Bij het brede bol.com-bestand (~225 kolommen) gaat dat goed. Bij Peters
2-koloms bestand bestaat `row[2]` niet en crasht de functie met een IndexError —
precies op het moment dat het ertoe doet: een artikel dat zojuist zijn koopblok
verloor, wordt dan niet teruggezet in de lijst.

**Waarom het nog niet opgevallen is:** in BE werd het smalle bestand elke ochtend
handmatig omgezet naar het brede formaat vóórdat er iets draaide. Daardoor is de
crash nooit opgetreden. Dat is een handmatige stap die vergeten kan worden.
Controleer of dat in NL ook zo gaat.

## De fix

Zoek de kolommen op **naam** in plaats van op positie. Vervang het blok
hierboven door:

```python
header_cols = [c.strip().strip('"') for c in next(csv.reader([lines[0]], delimiter=';'))]
num_cols = len(header_cols)
try:
    ean_idx = header_cols.index("EAN")
except ValueError:
    print("   [WARN] No EAN column in CSV header - not re-adding anything")
    return False
naam_idx = header_cols.index("Productnaam") if "Productnaam" in header_cols else None
ref_idx = header_cols.index("Interne referentie") if "Interne referentie" in header_cols else None

for ean in eans:
    row = [""] * num_cols
    row[ean_idx] = ean
    if naam_idx is not None:
        row[naam_idx] = f"Hersteld na koopblok-verlies {ean}"
    if ref_idx is not None:
        row[ref_idx] = ean
    lines.append(";".join(row))
```

Let op: `import csv` staat waarschijnlijk nog niet bovenaan `sync_buybox.py` —
in BE moest die toegevoegd worden.

De "Interne referentie"-kolom zit alleen in het brede bol.com-bestand en herhaalt
daar normaal de EAN. Vullen als hij bestaat, overslaan als hij ontbreekt.

## Controleer meteen of er meer plekken zijn

```bash
grep -n "row\[0\]\|row\[1\]\|row\[2\]\|split(\";\")" src/*.py
```

In BE was `add_eans_to_csv()` de enige plek. `remove_eans_from_csv()` in de
engine zocht al op kolomnaam en was dus goed. Controleer dat in NL ook.

## Testen vóór uitrol

Test de kolomlogica los, zonder te uploaden, op drie gevallen:

1. **Smal** (`Productnaam;EAN`) — EAN moet in kolom 2 landen, naam in kolom 1,
   en `csv.DictReader` moet de EAN's daarna terugvinden
2. **Breed** (`Productnaam;Interne referentie;EAN;...`) — EAN in de EAN-kolom,
   "Interne referentie" ook gevuld
3. **Zonder EAN-kolom** — moet netjes weigeren met een waarschuwing, niet crashen

In BE: alle drie correct.

## Uitrol

De cloud-job draait de versie op **GitHub**, niet de lokale. Upload het gewijzigde
`src/sync_buybox.py` los via de Contents API, niet via `setup_upload.py` (dat
overschrijft ook de statusbestanden met lokale stubs).

## Wat het oplevert

Peter uploadt zijn twee kolommen zoals hij nu al doet, en het werkt overal —
geen omzetstap meer nodig, door niemand. Het brede bestand van bol.com blijft
net zo goed werken.
