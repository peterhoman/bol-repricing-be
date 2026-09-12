# Instructie voor de NL-chat (Tiptopshop) — `no_competitor.json` inbouwen

Deze fix is op 25 juli 2026 gebouwd en gedeployed in het **BE-project**
(Dreamhouse&Garden). Bouw hetzelfde in het NL-project zodat beide projecten
identiek werken. **Pas alle URLs/namen aan naar het NL-project** — de code
hieronder bevat BE-specifieke raw-URLs.

## Het probleem

Een groep EAN's (BE: 49 stuks) faalt elke live-check met de fout
`"no product url in search results"`.

Dat betekent **niet** dat het artikel gedelist is. Het betekent: bol.com's
zoekresultaat levert geen productpagina op omdat er **geen enkele actieve
verkoper** is. Wij zijn de enige verkoper en ons eigen aanbod staat op
"Niet te koop" omdat het te duur is. Bevestigd door Peter in het
verkoopaccount: de artikelen staan er gewoon in, met status "Niet te koop"
en zonder koopblok.

Gevolg in de oude logica:
- niet in `frozen.json` (nooit een win te bevestigen),
- niet in `big_gap.json` (geen concurrentprijs, dus geen gat te meten),
- dus vallen ze in de **normale** tak → elke nieuwe kalenderdag reset hun
  prijs terug naar de verse volle B-Living-klantprijs.

Ze zakken daarna wel weer met €0,50 per cloud-run, maar élke ochtend springt
de prijs eerst terug naar (bijna) vol — en dat is precies wat de "te duur /
Niet te koop"-status telkens opnieuw triggert. Ze komen er zo nooit uit.

## De fix

Nieuw statusbestand `no_competitor.json` — een **platte lijst EAN's**
(`["8718483114405", ...]`), net als `master_tracked.json`.

Semantiek: vrijgesteld van de dagelijkse reset (zelfde principe als
`big_gap.json`), maar met **normale €0,50-stappen** — er is geen concurrentgat
om in te lopen, alleen de bodemprijs als eindpunt. Zo zakken ze dag na dag
door tot de bodem in plaats van elke ochtend terug te springen.

**Belangrijk: NIET in `big_gap.json` proppen.** Dat bestand stuurt ook de
€10-stap-teller en de vliegengordijn-uitsluiting; die logica past hier niet.
Aparte lijst dus.

## Wijzigingen in `src/phase2_repricing.py`

### 1. Nieuwe laadfunctie (naast `load_big_gap`)

```python
def load_no_competitor(self) -> set:
    url = "https://raw.githubusercontent.com/<NL-REPO>/main/no_competitor.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return set(r.json())
    except Exception:
        pass
    return set()
```

Zet er een docstring bij die uitlegt dat "no product url" = geen actieve
verkoper (niet: gedelist), anders herintroduceert een volgende sessie de
verkeerde aanname.

### 2. In `run_single_iteration_stateless()` (de cloud-run)

- Naast `big_gap` ook laden: `no_competitor = self.load_no_competitor()`
- Toevoegen aan de EAN-union:
  ```python
  all_eans = (master_tracked | set(self.products.keys()) | set(frozen.keys())
              | set(big_gap.keys()) | no_competitor)
  ```
- **De kern** — een `elif`-tak tussen de big-gap-tak en de normale tak:
  ```python
  elif ean in no_competitor:
      baseline_klantprijs = last_published.get(ean, original_klantprijs)
      step = 0.50
  ```
  (dus: géén `original_klantprijs if is_new_day else ...` — dat is nu juist
  de terugsprong die we willen voorkomen)
- Print-regel toevoegen bij de andere `[STATELESS]`-tellingen.
- `no_competitor` doorgeven aan `audit_tracking_consistency(...)`.

### 3. In `audit_tracking_consistency()`

Extra parameter `no_competitor: set = frozenset()` en meenemen in
`all_tracked`, anders meldt de audit deze EAN's onterecht als
"UNTRACKED REDUCTION" (ze hebben immers een verlaagde prijs).

```python
all_tracked = master_tracked | set(frozen.keys()) | set(big_gap.keys()) | no_competitor
```

### 4. In `match_competitor_prices()` (de lokale ochtendrun — onderhoudt de lijst)

- `no_competitor = self.load_no_competitor()` bij de andere loads.
- **Toevoegen** in de mislukt-tak, alleen bij deze specifieke fout:
  ```python
  error = result.get("error", "?")
  failed_eans[ean] = error
  if error == "no product url in search results":
      no_competitor.add(ean)
  ```
  Let op: alleen deze foutmelding. Een time-out of rate-limit mag hier
  nooit in belanden — dan zou een tijdelijke storing een artikel permanent
  van de dagelijkse reset uitsluiten.
- **Verwijderen** zodra er wél een productpagina resolvet (er is weer een
  verkoper) — direct na de `found`-check, vóór de has_buybox-tak:
  ```python
  no_competitor.discard(ean)
  ```
- Winnaars eruit + uploaden, bij de andere uploads:
  ```python
  no_competitor -= set(newly_won)
  self.upload_json_to_github(sorted(no_competitor), "no_competitor.json")
  ```
- Regel toevoegen aan de eindrapportage.

## Initieel vullen (anders werkt het pas na de volgende ochtendrun)

Vul `no_competitor.json` eenmalig met de EAN's uit de huidige
`failed_checks.json` die reden `"no product url in search results"` hebben.
Controleer vooraf dat er **geen overlap met `frozen.json`** is (moet 0 zijn).

## Verifieer vóór het deployen

Doe een droogloop van `run_single_iteration_stateless(check_buybox_live=False)`
met `upload_json_to_github` gemonkeypatcht naar een no-op, en check:
- alle EAN's uit `no_competitor` zitten in `adjustments` (0 missend),
- ze staan allemaal op een **verlaagde** prijs, niet op de volle klantprijs,
- de audit meldt 0 issues.

In BE gaf dat: 49/49 aanwezig, 49 op verlaagde prijs, 0 issues.

## Let op bij het deployen

`setup_upload.py` uploadt óók de lokale statusbestanden — en die zijn lokaal
vaak lege stubs. Dat zou de live status op GitHub wissen. Upload alleen
`src/phase2_repricing.py` los via de Contents API.

## Bewust NIET gedaan (ter overweging)

`sync_buybox.py` doet ook live-checks maar onderhoudt deze lijst niet. Dat is
bewust: de ochtendrun checkt sowieso alle kandidaten, dus toevoegen/verwijderen
gebeurt daar binnen een dag alsnog. Wil je het toch, dan is dezelfde
add/discard-logica nodig in beide check-loops van dat script.
