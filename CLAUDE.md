# CLAUDE.md — Bol.com BE Repricing (Dreamhouse&Garden)

Complete projectcontext voor elke nieuwe chat/sessie. Dit bestand is zelfstandig:
alles wat je nodig hebt om direct aan het werk te kunnen staat hierin.

## Scope — lees dit eerst

**Dit project werkt UITSLUITEND voor het Bol.com BELGIË-account, verkoper
"Dreamhouse&Garden".** Er bestaat een apart zusterproject `bol-repricing`
(NL/Tiptopshop) met een eigen chat, eigen repo, eigen formules en eigen
Channable-feed. **Raak dat NL-project nooit aan vanuit deze chat** — ook niet
voor een "identieke" bugfix; meld het alleen aan Peter zodat de NL-chat het
oppakt.

## Kernfeiten

- Marketplace: **bol.com/be/nl** (alle URLs `/be/nl/`, nooit `/nl/nl/`)
- Verkoper (buybox-detectie): exact `Dreamhouse&Garden` (geen spaties; zo
  staat het in bol.com's JSON-LD `offers.seller.name`; vergelijking is
  case-insensitive)
- GitHub-repo (bron van waarheid): `peterhoman/bol-repricing-be` (public)
- Channable-project: "B-living feeds -dreamhouse&garden" (ID 138815), import
  "B-living feed met korting", leest de vaste URL:
  `https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/repricing_current.xml`
- B-Living leveranciersfeed (zelfde als NL-project):
  `https://www.b-living.eu/feeds/product-feed-15003253-bbed70ea1f95308232732fe3b662e36f2fab51359cce3fc9ff7e33cac2ef9b07.xml`
- `.env` in deze map: `GITHUB_TOKEN` (fine-grained PAT, alleen deze repo,
  Contents/Workflows/Actions R&W, geen vervaldatum) + `GITHUB_REPO`

## Prijsformules (ALLEEN voor dit BE-account!)

Channable berekent de verkoopprijs uit de `klantprijs` die wij in de XML
publiceren. Onze code moet daar exact mee sporen:

- **Normale verkoopprijs:** klantprijs < 10 → `(klantprijs + 1) × 2.6 + 8.5`;
  anders → `klantprijs × 2.6 + 8.5`
- **Bodemprijs (absoluut minimum, NOOIT eronder):** klantprijs < 10 →
  `(klantprijs + 1) × 2.2 + 8.5`; anders → `klantprijs × 2.2 + 8.5`
  - LET OP: tot 23 juli stond hier fout `× 2.1` zonder +1-regel — daardoor is
    één artikel te goedkoop verkocht (€17,05 i.p.v. bodem €19,65). Peter heeft
    ×2,2 mét +1-regel expliciet bevestigd. Documentatie die ×2,1 noemt is
    verouderd.
- **Inverse** (gewenste verkoopprijs → klantprijs):
  `calculate_klantprijs_for_target_price()` in `src/phase2_repricing.py`.
  In de overlapzone rond de €10-grens zijn twee klantprijzen mogelijk; de
  functie kiest er één — dat is correct zolang de verkoopprijs klopt.

## Architectuur

1. **Cloud (stateless):** GitHub Actions (`.github/workflows/reprice.yml`)
   draait `src/github_action_reprice.py` — 24 cron-runs per dag, elk ~5 min ná
   een Channable-importslot (sloten: 07:45–21:15 Amsterdam, elke ~30 min,
   identiek aan het NL-project). Leest CSV/state/frozen van GitHub, doet één
   verlaagstap van €0,50 (of €10 bij big-gap), klemt op de bodem, genereert en
   uploadt `repricing_current.xml`.
   - Cron staat in UTC voor ZOMERTIJD (CEST=UTC+2). **In de herfst (klok naar
     CET) alle cron-uren 1 verlagen!**
   - `concurrency: group: reprice` voorkomt botsende cloud-runs onderling,
     maar weet niets van de lokale scripts. Valt `match_prices.py` samen met
     een cron-slot, dan uploadt de lokale run de XML eerst en faalt de
     cloud-run met **409: is at ... but expected ...** (gezien 9/8, 09:37).
     Dat is correct gedrag: de cloud-run had juist de OUDERE prijzen en werd
     geblokkeerd. De eerstvolgende run herstelt het vanzelf.
     Bij een rode "workflow failed"-mail dus eerst het tijdstip vergelijken
     met de ochtendrun. Alleen echt onderzoeken als meerdere runs achter
     elkaar falen, of als er níéts van ons tegelijk draaide.
   - Draait ook door zonder CSV-artikelen (verse-start-modus: alleen
     feed-verversing + gevolgde EANs).
2. **Lokaal (alleen vanaf Peters eigen internetverbinding!):** bol.com geeft
   403 op datacenter-IP's, dus alles met live buybox-checks draait op deze
   machine: `match_prices.py`, `sync_buybox.py`, `probe_recovery.py`.
   Tussen checks zit 0,3s pauze; draai NOOIT twee scrape-scripts tegelijk
   (ook niet NL+BE parallel — geeft rate-limiting, ~26% mislukte checks).

## Databestanden op GitHub (vaste namen, nooit hernoemen)

- `bolcom_productinformatie.csv` — Peters dagelijkse "geen koopblok"-export
  uit het BE-verkoopaccount (kolommen o.a. Productnaam;Interne referentie;EAN,
  scheidingsteken `;`, velden kunnen quotes + newlines bevatten).
  **Twee formaten, allebei goed (sinds 5/8):** de brede bol.com-export (~225
  kolommen) én een smal bestand met alleen `Productnaam;EAN`. Dat laatste maakt
  Peter zelf, want de download bij bol.com faalt bijna elke ochtend — dan plakt
  hij die twee kolommen in een CSV onder dezelfde naam. Soms uploadt hij een
  `.xlsx`; die leest de pijplijn NIET, zet hem dan eerst om (kolommen op naam
  lezen, niet op positie). Alle code zoekt kolommen sinds 5/8 op naam, dus
  omzetten naar het brede formaat is niet meer nodig.
- `repricing_current.xml` — gegenereerde prijsfeed (Channable leest deze)
- `frozen.json` `{ean: klantprijs}` — bevestigde koopblok-WINNAARS, prijs wordt
  exact vastgehouden (niet zakken, niet stijgen)
- `master_tracked.json` `[ean]` — élke EAN die ooit in een dag-CSV heeft
  gestaan. Groeit alleen; een EAN verlaat actieve tracking UITSLUITEND via een
  bevestigde win (→ frozen). "Niet in de CSV van vandaag" is GEEN bewijs van
  winst (bol's momentopname flipt) — daarom bestaat deze lijst.
- `big_gap.json` `{ean: resterende_€10_stappen}` — artikelen ≥€10 achter de
  winnaar; vrijgesteld van de dagelijkse reset. Vliegengordijnen (2Lif/Sun
  Arts, herkenbaar aan "vliegengordijn" in de B-Living-titel) worden hier
  nooit aan toegevoegd.
- `state.json` `{date}` — dagteller voor de reset
- `audit_report.json` — automatische consistentie-audit van elke cloud-run.
  Drie controles: (1) geen EAN tegelijk in frozen én big_gap, (2) geen
  verlaagde prijs zonder tracking, (3) niets gepubliceerd onder de actuele
  bodemprijs (toegevoegd 27/7, zie valkuil 7/8).
- `failed_checks.json` — EANs waarvan de laatste check mislukte, met reden.
  ~50 stuks structureel "no product url in search results". Betekenis is nu
  bekend (27/7): er is geen enkele andere verkoper, dus bol.com toont geen
  productpagina met JSON-LD. Zie `no_competitor.json`.
- `no_competitor.json` `[ean]` — EANs zonder enige zichtbare verkoper.
  Vrijgesteld van de dagelijkse reset (fix 26/7), zodat ze doorzakken naar de
  bodem in plaats van elke ochtend terug te springen naar volle prijs.
  **Zaak gesloten op 28/7 — niet heropenen.** Bol.com geeft in het
  verkoopaccount zelf de reden: *"Slecht geprijsd, de afstand tot de
  marktprijs is te groot. Het artikel wordt niet meer op het platform getoond
  totdat de prijs is verlaagd."* Het is dus wél een prijskwestie, maar
  gemeten tegen de marktprijs van vergelijkbare varianten, niet tegen een
  vast maximum. Uitgerekend op 8718483114405 (2Lif folie geel): volle prijs
  €28,36, onze bodem €25,31, wij publiceren €25,32, bol.com wil €23,94 — dat
  is €1,37 ónder de bodem, ofwel een bodemfactor van ×2,02 in plaats van
  ×2,2. **Peters beslissing (28/7): bodem blijft ×2,2, deze artikelen krijgen
  dan maar geen koopblok.** Ze blijven op de bodem staan en worden verder met
  rust gelaten. Geen skip-lijst, geen bodemverlaging, geen nieuwe voorstellen
  hierover.

## Concurrentprijzen zijn ZICHTBAAR (1/9) — de probe is hierdoor vervangen

Lange tijd gold de aanname: zolang wij het koopblok hebben toont bol.com alleen
onze eigen prijs, dus we weten niet wie er achter ons zit. Dat klopt voor de
productpagina, maar niet voor de **prijsoverzichtspagina**:

```
https://www.bol.com/be/nl/prijsoverzicht/<slug>/<product-id>/?sort=price&sortOrder=asc
```

Die staat achter "Bij N partners verkrijgbaar", is gewone server-rendered HTML
(geen browser nodig) en bevat álle verkopers met prijs. Uitgelezen door
`check_all_offers()` in `phase2_repricing.py`; splits op
`data-testid="offer-compare-item"` en lees per blok de voorleeszin
("De prijs van dit product is X euro en Y cent" + "Verkocht door Z"). **Zoek
prijs en verkoper apart** — bij korting staat er tekst tussen ("De adviesprijs
is ... Je bespaart 3%.") en breekt één gecombineerd patroon.

`probe_recovery.py optimize [n]` gebruikt dit en zet elk bevroren artikel op
de juiste prijs in plaats van te gokken:
- geen andere verkoper → stapje van max €5 omhoog (niet ineens naar vol: een
  slecht geparste pagina ziet er hetzelfde uit)
- goedkoopste ander BOVEN ons → naar net eronder (−€0,02)
- goedkoopste ander ONDER ons → **niets doen**; we winnen dan op beoordeling
  (8,9 vs 8,1) en levertijd. Gemeten: wij €255,03 vs concurrent €254,95 én
  toch het koopblok. Verlagen geeft marge weg, verhogen riskeert het.
Altijd klemmen op `[bodemprijs, volle prijs]`.

**De marge van €0,02 NIET verhogen naar de NL-waarde.** NL draaide dezelfde
ronde op 1/9 en verloor 47 van de 59 koopblokken op precies deze regel (80%),
wij 0 van 19. Beide kloppen, want de posities verschillen: gemeten 2/9 levert
BE **9 september** waar Izziet en Bohemian Living NL op **14 september** zitten
— wij zijn vijf dagen sneller én hebben 8,9 tegen hun 8,1 of geen beoordeling.
Bij NL is het omgekeerd (3-5 werkdagen tegen concurrenten die morgen leveren),
dus dáár compenseert een fors prijsverschil het levertijdnadeel en is
"net eronder" fataal. Onderliggende regel: hoeveel prijsverschil je nodig hebt
hangt af van je positie op levertijd en beoordeling, niet van een vast bedrag.
Peter heeft op 2/9 bevestigd dat BE blijft zoals het is.

Openstaande kans (niet gebouwd): wij houden het koopblok soms terwijl we
DUURDER zijn — 8716522103465 stond op €255,03 tegen €254,95 van Bohemian
Living NL en wij hadden het koopblok. `UNDERCUT_EUR` gaat nooit boven de
concurrent; voorzichtig testen of dat wél kan (bv. tot 1% erboven) kan extra
marge opleveren.

Eerste live ronde 1/9: 40 bekeken, **19 verhoogd, +€66,26 per verkoopcyclus**,
18 met rust gelaten, 3 mislukt; 0 onder de bodem, 0 boven de volle prijs.
Terugkerende concurrenten: Bohemian Living NL, Cactula, Izziet (dropshippers
die net als wij bij de leverancier bestellen).

De dagtaak van 10:45 draait sinds 1/9 `optimize 40`; `probe_check` blijft in het
schema maar heeft niets meer te doen. De oude probe-modi (`auto`, `step`) staan
er nog voor noodgevallen. Instructie voor NL:
`instructie-NL-concurrentprijzen-zichtbaar.md`.

## Kritieke valkuilen (allemaal in productie ontdekt — niet herintroduceren!)

1. **CDN-vertraging:** `raw.githubusercontent.com` cachet minuten. Na een
   upload (door Peter of een script) kan de raw-URL nog de OUDE versie geven.
   Vergelijk daarom eerst het CSV-regelaantal via de **Contents-API** (altijd
   vers) en wacht tot de raw-URL hetzelfde aantal geeft vóór je scripts start.
   Bestanden >1 MB (zoals de XML) via de blob-API ophalen, niet Contents.
2. **Zelfde-dag auto-unfreeze (fix 21/7):** de cloud-run ontdooit een frozen
   EAN dat nog in de CSV staat. Terecht bij een verse ochtend-CSV, fataal bij
   een zelfde-dag-bevriezing (CSV is ouder dan de win!). Daarom verwijdert
   `remove_eans_from_csv()` nieuwe winnaars direct uit de CSV op GitHub — die
   aanroep nooit weghalen uit `sync_buybox.py`/`match_competitor_prices()`.
3. **Winnaars vóór XML-generatie mergen (fix 21/7):** `frozen.update(newly_won)`
   moet VÓÓR het genereren van de XML — anders komen verse winnaars op volle
   prijs in de feed.
4. **Mislukte checks = positie vasthouden (fix 22/7):** een mislukte
   buybox-check mag een artikel nooit uit `adjustments` laten vallen (dan
   valt het terug naar volle prijs) — het houdt zijn laatst gepubliceerde
   klantprijs.
5. **Sync kijkt verder dan de CSV (fix 21/7):** `sync_buybox.py` checkt
   CSV ∪ master_tracked ∪ big_gap − frozen. Alleen-CSV mist "onzichtbare
   winnaars" die uit de export zijn gevallen.
6. **Probe-checks nooit via een slaap/achtergrondtaak plannen:** een 85-min
   wachttaak overleeft de slaapstand van Peters computer niet (30 artikelen
   stonden daardoor een hele dag op volle prijs). Vraag Peter om na ~1,5-2 uur
   een seintje ("check maar"). **Check bij elke sessiestart of
   `frozen_probe_backup.json` op GitHub leeg is** — zo niet: er hangt nog een
   probe open, draai dan eerst `python src/probe_recovery.py check`.
7. **Klantprijs ALTIJD naar boven afronden (fix 27/7, gevonden door NL):**
   `calculate_klantprijs_for_target_price()` rondde af met `round()`. De
   klantprijs gaat met 2 decimalen de feed in en Channable vermenigvuldigt met
   2,6 — een halve cent naar beneden afgerond werd dus tot 1,3 cent lagere
   verkoopprijs. Bij klemmen op de bodem landde het artikel daardoor één cent
   ONDER de bodem, bij 28,5% van de catalogus, en dat herstelde zich nooit
   want elke run deed dezelfde berekening (85 artikelen stonden 27/7 live een
   cent te laag). Nu wordt naar boven afgerond op de cent. Kost bij onderbieden
   hooguit ~1,3 cent extra — naar boven afwijken is hier altijd de veilige kant.
8. **Marges bij bodemvergelijkingen op 0,005 houden, niet 0,01 (fix 27/7):**
   met een marge van een hele cent glipt precies-een-cent-eronder er ongemerkt
   doorheen. Dat maskeerde valkuil 7 en zorgde ervoor dat een eerste telling
   3 artikelen meldde in plaats van 85. Geldt in `clamp_frozen_to_floor()` en
   in audit-controle 3.
9. **Bevroren winnaars worden nergens vanzelf herberekend (fix 27+29/7):** een
   frozen EAN houdt zijn prijs onbeperkt vast — geen reset, geen dagelijkse
   herberekening. Twee klemmen houden hem daarom binnen de band
   `[bodemprijs, volle prijs]`, elke run, in beide codepaden:
   - `clamp_frozen_to_floor()` (27/7) — tilt omhoog als B-Living de inkoop
     verhóógde, anders verkopen we onbeperkt onder de bodem.
   - `clamp_frozen_to_normal_price()` (29/7, overgenomen uit NL) — zet omlaag
     als B-Living de inkoop verláágde, anders staat het artikel duurder dan
     zijn eigen volle prijs. **Zet daar `frozen[ean] = verse klantprijs`, NOOIT
     via `calculate_klantprijs_for_target_price()`** — die rondt een cent naar
     boven af, waardoor het artikel elke run opnieuw "gecorrigeerd" wordt.
   Gemeten in BE op 29/7: 0 van 88, ook 0 over alle 25 historische snapshots
   (BE bevriest op de concurrentprijs, die ligt vrijwel altijd onder onze
   volle prijs). In NL waren het er 10 van 155. Staat hier als vangnet.
   Gevolg dat Peter kent en accepteert: een optilling kan het koopblok kosten —
   nooit onder de bodem verkopen weegt zwaarder.
11. **Nooit via raw lezen wat we zelf net via de API geschreven hebben
    (fix 18/8):** `add_eans_to_csv()` las de CSV via raw, seconden nadat
    `remove_eans_from_csv()` hem via de API had herschreven. De CDN gaf de
    oude versie, de re-add bouwde daarop verder en zette de 18 zojuist
    verwijderde sync-winnaars ongemerkt terug in de CSV — waarna de
    getriggerde cloud-run ze alle 18 ontdooide, 23 seconden na de sync.
    (Gisteren 17/8 hetzelfde met 4 winnaars; destijds fout gediagnosticeerd
    als normale auto-unfreeze. Slaat alleen toe als een sync én winnaars én
    terugzettingen heeft.) Fix: CSV overal via de Contents-API lezen met
    `Accept: application/vnd.github.raw` (zie `_fresh_headers()`); alle vier
    de `CSV_URL`-constanten wijzen nu naar de API. Nooit terugzetten naar
    raw. Instructie voor NL: `instructie-NL-csv-via-api.md`.
10. **CSV-kolommen ALTIJD op naam zoeken, nooit op positie (fix 5/8):**
    `add_eans_to_csv()` in `sync_buybox.py` schreef naar `row[2]` en crashte
    daardoor op Peters smalle 2-koloms bestand — precies bij het terugzetten
    van een artikel dat zojuist zijn koopblok verloor. Zoek `EAN`,
    `Productnaam` en `Interne referentie` via de header en vul de laatste twee
    alleen als ze bestaan. `remove_eans_from_csv()` deed dit al goed.
    Instructie voor NL: `instructie-NL-csv-kolomnamen.md`.

## AUTOMATISCH SINDS 17/8 — eerst lezen vóór je iets draait!

De dagelijkse routine draait sinds 17/8 via de **Windows-taakplanner** (vier
taken "Bol BE 1-4": 09:00 snelstart, 10:45 probe-start, 12:15 probe-check,
14:15 sync — sinds 18/8, BE ruilde met NL: NL kreeg de vroege sloten omdat
dat Peters belangrijkste winkel is), via `src/scheduled_run.py`. De taken wekken de pc uit de
slaapstand (`-WakeToRun`, wektimers staan aan) en halen gemiste runs in
(`-StartWhenAvailable`). Peter hoeft alleen nog 's ochtends de CSV te uploaden.

**Draai de routinestappen dus NIET meer handmatig** — dat geeft dubbele runs en
rate-limiting. Wat een sessie nog wél doet:

1. Bij sessiestart: `automation_log.json` lezen via de **Contents-API** (niet
   de raw-URL — die cachet én gaf op 17/8 een 429). Laatste 60 runs, per run
   taak/tijd/duur/exitcode/resultaatregels. FAILED-runs, ontbrekende taken of
   rare aantallen: uitzoeken en aan Peter melden. Volledige uitvoer staat
   lokaal in `logs/automation-JJJJ-MM.log`.
2. Handmatig ingrijpen alleen bij een storing of op Peters verzoek.
   NB: taak 2 ("probe starten") draait sinds 1/9 `probe_recovery.py optimize
   40`, niet meer de oude gok-probe. Taak 3 ("probe controleren") staat nog in
   het schema maar meldt normaal "No probes currently in progress" — dat is
   correct, niet een gemiste run.
3. `taken_aanmaken.ps1` (projectmap) maakt de taken opnieuw aan als dat ooit
   nodig is — Peter moet dat zelf uitvoeren (permissieblokkade voor Claude).
4. **Ontbreekt een taak in `automation_log.json` maar staat hij lokaal in
   `logs/` met exitcode 3221225786 (0xC000013A)?** Dan is het consolevenster
   gesloten (gezien 20/8, probe-start 10:45: Peter klikte het zwarte venster
   weg). Sinds 21/8 draaien de taken via `pythonw.exe` + `CREATE_NO_WINDOW`,
   dus er komt geen venster meer op. Komt de code toch terug: controleren of
   `taken_aanmaken.ps1` opnieuw gedraaid is na die wijziging.

**Storing 17/8, relevant voor logs van rond die datum:**
raw.githubusercontent.com gaf 429 op al onze bestanden (Channable kreeg
dezelfde fout op de feeds van NL én BE). Daarom zit er sinds 17/8 een
preflight in `github_action_reprice.py`: kan de cloud-run frozen/state/
master_tracked niet via raw lezen, dan stopt hij zónder upload — anders zou
hij een feed publiceren met alle bevroren prijzen gewist. Rode
workflow-mails tijdens zo'n storing zijn dus bewust en veilig.

## Oude handmatige ochtendroutine (alleen nog als noodprocedure bij een taakplanner-storing)

1. Controles: probe-backup leeg? CSV-uploadtijd + artikelaantal via
   Contents-API; wacht tot de raw-URL hetzelfde aantal geeft (zie valkuil 1).
2. `python src/match_prices.py` (in achtergrond, duurt ~10 min bij ~250
   artikelen): bevriest artikelen die al winnen, zet de rest op
   concurrentprijs −€0,02 (geklemd op de bodem), verwijdert winnaars uit de
   CSV, uploadt alles.
3. Rapporteer kort (tabelletje): nieuwe winnaars/totaal bevroren, onderboden,
   op bodem, mislukt. Signaleer daarna zelf verbeterkansen — Peter wil niet
   alleen cijfers horen.
4. ~2 uur later, op Peters seintje: `python src/sync_buybox.py` — verse
   winnaars bevriezen, verliezers ontdooien, big-gaps bijwerken. Rapporteer.
5. **Na een probe-check met terugzettingen: ~90 min GEEN sync draaien.** De
   teruggezette prijs staat wel in onze feed maar is nog niet door Channable
   geïmporteerd, dus bol.com toont nog de probe-prijs. Een sync leest dat live,
   denkt "koopblok kwijt" en ontdooit die artikelen voor niets. NL mat 11 valse
   verliezen van 15 op 17/8; BE had er die dag 0 van 3, dus het bijt niet altijd
   — maar het schaalt mee met het aantal terugzettingen. `probe_recovery.py check`
   waarschuwt hier sinds 17/8 zelf voor.
6. Optioneel (op afspraak): marge-herstel op bevroren artikelen. Sinds 17/8
   automatisch: `probe_recovery.py candidates [n]` toont de beste kandidaten,
   `auto [n]` selecteert én start, `check` (na Peters seintje, ~90 min later)
   houdt winnaars en zet verliezers terug. Selectie = hoogste winst
   (volle prijs bij VERSE inkoop − huidige bevroren prijs), minimaal
   `MIN_GAIN` (€10), met `COOLDOWN_DAYS` (14) via `probe_history.json`
   `{ean: {date, klantprijs}}` — **vlakke termijn, geen uitzonderingen.**
   Op 24/8 is geprobeerd die te versoepelen (7 dagen + vrijstelling zodra de
   bevroren prijs veranderd was, want dat leek een nieuwe cyclus). Uitkomst de
   volgende dag: 15 kandidaten, €768 in het spel, **0 behouden, 15 teruggezet**
   — tegen 12/15, 15/15 en 11/13 bij verse kandidaten. De redenering was
   omgekeerd: een recent VERANDERDE bevroren prijs betekent dat een concurrent
   ons actief onderbood, dus die is er nog. Een ONveranderde prijs is juist het
   gunstige signaal. Niet opnieuw versoepelen zonder nieuwe meting. Winnaars vallen vanzelf af (staan dan op volle prijs).
   Ronde-historie: 21/7 top-15 → 9 behouden (~€597); 22/7 volgende 15 → 1;
   17/8 ronde 1 (15, winst €32-51) → **12 behouden, €521,74**; 17/8 ronde 2
   (20, winst €17-32) → **8 behouden, €200,19**.
   **Vuistregel uit 17/8: onder ~€25 winst zakt het behoud naar ~40%.**
   Verhoog liever de drempel dan dieper in de lijst te graven.
   Selectiecriteria die NIET voorspellen (getest 17/8 met NL): bedrag, dagen
   onafgebroken bevroren, productgroep — onze 3 verliezers waren allemaal
   vliegengordijnen, maar 6 van de 12 winnaars óók. Niet opnieuw onderzoeken
   zonder nieuwe data.

## Werkwijze met Peter

- Nederlands, informeel ("je"), **stap voor stap, niet te veel informatie in
  één keer**. Als Peter zelf iets moet doen (GitHub UI, Channable): één stap
  per bericht, simpel uitgelegd, wachten op "klaar".
- Direct handelen bij de ochtendmelding; bij vragen over cijfers eerst zelf
  verifiëren tegen GitHub (`origin/main` / API), nooit uit het hoofd.
- Afwijkingen (bv. koopblok-teller daalt) eerst zelf verklaren
  (auto-unfreeze? bodem-fluctuatie? zie audit_report) vóór je het als
  probleem meldt.
- Peter accepteert bewust dat sommige artikelen nooit winnen (concurrent
  onder onze bodem) — geen features voorstellen om dat te "fixen".

## Status per 2 september 2026 (verifieer bij sessiestart tegen GitHub!)

- **129 bevroren koopblokken**, 42 in `no_competitor`, `big_gap` op 0, audit
  schoon, nul mislukte cloud-runs. Bevroren schommelt normaal tussen ~120 en
  ~150; dat is auto-unfreeze, geen probleem.
- **Alles draait automatisch** via de taakplanner (zie hoofdstuk hierboven).
  Peter uploadt 's ochtends alleen de export. Een sessie doet de
  ochtendcontrole op `automation_log.json` en rapporteert; verder niets
  handmatig draaien.
- **De grote verandering van 1/9:** concurrentprijzen zijn uitleesbaar via de
  prijsoverzichtspagina, waardoor de gok-probe vervangen is door
  `optimize` — zie het hoofdstuk daarover. Eerste ronde 19 verhoogd
  (+€66,26/cyclus), tweede ronde 1 verhoogd. **Alle 19 hielden hun koopblok**,
  gecontroleerd op 2/9.

### Openstaand / in de gaten houden

1. **Is €0,02 onder de concurrent genoeg?** Bij ons wel (19/19 gehouden), bij
   NL niet (47 van 59 verloren). Verklaring gemeten op 2/9: BE levert
   9 september waar de concurrenten op 14 september zitten — wij zijn vijf
   dagen sneller én hebben 8,9 tegen hun 8,1. Toch elke ochtend controleren
   of verhoogde artikelen in de export opduiken; de lijst van 1/9 staat in
   `logs/optimize-2026-09-01.txt`. `UNDERCUT_EUR` in `probe_recovery.py` is
   de knop.
2. **Kans, niet gebouwd:** wij houden het koopblok soms terwijl we DUURDER
   zijn (8716522103465: wij €255,03 vs Bohemian Living NL €254,95). De regel
   gaat nooit boven de concurrent. Voorzichtig testen of dat wél kan.
3. **NL bouwt een levertijd-afhankelijke regel** (concurrent trager → omhoog,
   sneller → niets doen). Wij nemen die niet over zolang onze cijfers goed
   blijven; wel het resultaat volgen.
4. Klein gat: de `last_published`-prijs die na een mislukte check wordt
   vastgehouden, wordt niet actief tegen de bodem geklemd. Audit-controle 3
   signaleert het en de eerstvolgende cloud-run corrigeert het.
5. **In de herfst het cron-schema 1 uur schuiven** (van zomer- naar wintertijd).

### Samenwerking NL/BE

Beide projecten bouwen dezelfde fixes, maar elk in de eigen repo met de eigen
formules. Overdracht gaat via een instructie-MD in deze map
(`instructie-NL-*.md` / `antwoord-NL-*.md`), nooit door in de andere repo te
werken. Belangrijk: **neem NL-instellingen niet klakkeloos over.** De
markten verschillen (levertijd, beoordeling, aantal verkopers) en dezelfde
regel kan daar tegengesteld uitpakken — zie de €0,02-kwestie hierboven.
