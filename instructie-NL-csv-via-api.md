# URGENT voor de NL-chat — jullie sync-winnaars van vandaag zijn mogelijk 23 seconden later gewist

Gevonden, hersteld en structureel gefixt in BE op 18 augustus. **Controleer dit
eerst, vóór alles**, want jullie sync van 13:30 vandaag (+20 winnaars, 1
ontdooid) had precies de combinatie waarbij deze bug toeslaat.

## Controleer NU: zijn jullie 20 winnaars er nog?

Haal de commit-historie van `frozen.json` op (via de API) en kijk naar de
minuten ná jullie sync-commit. Het foutpatroon is onmiskenbaar:

```
12:23:15  Sync: +18 new winners, -12 lost buybox     -> 130 bevroren
12:23:38  Update frozen.json (cloud-run)             -> 112 bevroren  (-18!)
```

In BE werden alle 18 verse winnaars **23 seconden na de sync** weer ontdooid.
Gisteren gebeurde hetzelfde met 4 winnaars — dat hadden wij toen als "normale
auto-unfreeze, ze stonden immers in de CSV" afgedaan. Dat was fout gediagnosticeerd.

Als jullie aantal ná de sync-commit met precies het aantal nieuwe winnaars is
gezakt: zelfde bug. Zo niet: toch de fixes hieronder doorvoeren, want dan is het
geluk geweest (bij ons ging het op 11/8 óók goed — toen waren er 0 terugzettingen).

## De oorzaak: raw-lezen racet met onze eigen API-schrijfacties

De keten in `sync_buybox.py`:

1. `remove_eans_from_csv()` haalt de winnaars uit de CSV — schrijft via de **API** (vers)
2. `add_eans_to_csv()` zet verliezers terug — maar **leest de CSV eerst via de
   raw-URL**, en de CDN serveerde nog de versie van vóór stap 1
3. gevolg: de functie bouwt verder op de oude lijst en zet de zojuist
   verwijderde winnaars ongemerkt terug in de CSV
4. de door de sync getriggerde cloud-run ziet ze in de CSV staan → auto-unfreeze
   wist ze allemaal

De bug slaat dus alleen toe als een sync **én** nieuwe winnaars **én**
terugzettingen heeft. Daarom bleef hij wekenlang onzichtbaar.

Dit is valkuil 1 (CDN-vertraging) in een nieuwe vorm: niet "wacht na Peters
upload", maar **elke leesactie die binnen minuten op een eigen schrijfactie
volgt, kan de oude versie krijgen**.

## Herstel (als jullie winnaars gewist zijn)

Volgorde is belangrijk — eerst de CSV, dan frozen, anders wist de volgende
cloud-run ze opnieuw:

1. Lees de CSV via de **Contents-API** en verwijder de gewiste winnaars eruit
   (op EAN-kolomnaam), upload via de API
2. Pak de frozen-waarden uit de sync-commit (`?ref=<sha>` op de Contents-API)
   en zet de gewiste EANs terug in het huidige `frozen.json`
3. Trigger de workflow zodat de feed ze weer vasthoudt

Controleer daarna dat het aantal stabiel blijft over de eerstvolgende cron-run.

## De structurele fix: CSV overal via de Contents-API lezen

**a. Engine** — geef `_get_with_retries()` een headers-helper:

```python
@staticmethod
def _fresh_headers(url: str) -> dict:
    if "api.github.com" not in url:
        return {}
    headers = {"Accept": "application/vnd.github.raw"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
```

en gebruik hem in de GET: `requests.get(url, timeout=timeout, headers=self._fresh_headers(url))`.
Met het `Accept: application/vnd.github.raw`-mediatype geeft de Contents-API de
kale bestandsinhoud terug — dezelfde tekst als de raw-URL, maar altijd vers.

**b. Alle vier de `CSV_URL`-constanten** (github_action_reprice, match_prices,
probe_recovery, sync_buybox) omzetten van
`https://raw.githubusercontent.com/<repo>/main/bolcom_productinformatie.csv`
naar `https://api.github.com/repos/<repo>/contents/bolcom_productinformatie.csv`.
De engine-loader werkt dan ongewijzigd, maar leest vers.

**c. `add_eans_to_csv()` in sync_buybox.py** — de raw-leesregel vervangen door
een API-read met dezelfde raw-Accept-header (deze functie heeft een eigen
`requests.get`, buiten de engine om).

**d. `remove_eans_from_csv()` in de engine** — leest ook zelf
(`requests.get(self.csv_path)`); vervang door `self._get_with_retries(self.csv_path)`.

Token-limiet is geen zorg: geauthenticeerd is de limiet 5000 verzoeken/uur, en
de cloud-runner heeft `GITHUB_TOKEN` al in zijn omgeving.

## Testen (zoals in BE gedaan)

1. Alle gewijzigde bestanden syntax-checken
2. Engine één keer laden met de API-URL: verwacht exact het juiste aantal
   producten (bij ons 187 = 193 − 18 verwijderd + 12 teruggezet)
3. Na uitrol: eerstvolgende cron-run afwachten en controleren dat frozen
   stabiel blijft

## Uitrol

Alle gewijzigde bestanden los via de Contents-API uploaden (niet
`setup_upload.py`). De cloud draait de GitHub-versie.
