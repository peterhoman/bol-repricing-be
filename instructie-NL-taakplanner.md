# Instructie voor de NL-chat (Tiptopshop) — volledige automatisering via de Windows-taakplanner

Gebouwd, getest en in gebruik in het **BE-project** (Dreamhouse&Garden) op
17 augustus 2026. Peter wil dat NL exact hetzelfde krijgt, zodat hij alleen nog
's ochtends het bestand hoeft te uploaden en verder niets.

Bouw het in `bol-repricing` met de **NL-URLs en NL-bestandsnamen**.

## Wat het oplost

Tot nu toe moest Peter voor elke stap een seintje geven (snelstart, probe-start,
probe-check, sync), omdat live buybox-checks alleen vanaf zijn thuisverbinding
kunnen én er wachttijden tussen stappen zitten. Gevolg: tijdens twee dagen
afwezigheid verloor BE 42 koopblokken, en bevroren artikelen bleven op een te
lage prijs staan zolang niemand een probe-ronde startte.

De oplossing: de Windows-**taakplanner** (geen wachttaak in een sessie!). Die
zit in het besturingssysteem, wekt de pc uit de slaapstand per taak
(`-WakeToRun`), en haalt gemiste taken in zodra de pc weer aan is
(`-StartWhenAvailable`). De pc moet in slaapstand staan, niet uit.

## Onderdeel 1: wrapper-script `src/scheduled_run.py`

Kopieer het BE-bestand en pas de repo-URL aan. Kern:

- kent de taken `morning` (snelstart), `probe_start` (`probe_recovery.py auto 15`),
  `probe_check` (`probe_recovery.py check`), `sync`, en `selftest`
- draait het betreffende script als subprocess met een timeout van 45 minuten
- schrijft de volledige uitvoer naar `logs/automation-JJJJ-MM.log` (lokaal)
- pusht een compacte samenvatting (taak, tijdstip, duur, exitcode, resultaatregels)
  naar **`automation_log.json` op GitHub**, laatste 60 runs
- een run die crasht of timeout krijgt staat dus óók in het log, met reden

Die GitHub-log is het belangrijkste onderdeel: het is het enige dat een verse
chatsessie kan lezen. Elke ochtend hoort de chat eerst dat log te controleren en
afwijkingen aan Peter te melden vóór er iets nieuws gestart wordt.

## Onderdeel 2: vier geplande taken

BE-schema (kies voor NL ANDERE tijden, zie waarschuwing hieronder):

| tijd BE | taak |
|---|---|
| 08:15 | morning |
| 10:00 | probe_start |
| 11:30 | probe_check |
| 13:30 | sync |

Aanmaken via een PowerShell-script dat Peter zelf eenmalig uitvoert (rechtsklik
→ Uitvoeren met PowerShell, of via "Openen in Terminal" met
`powershell -ExecutionPolicy Bypass -File .\taken_aanmaken.ps1`). Kopieer
`taken_aanmaken.ps1` uit de BE-map en pas python-pad, projectpad en taaknamen
aan. Instellingen per taak: `-WakeToRun -AllowStartIfOnBatteries
-DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit 1 uur`.

Claude kan de taken NIET zelf registreren (permissieblokkade) — Peter voert het
script uit, de chat controleert daarna het log.

## WAARSCHUWING 1: kies andere tijden dan BE

NL en BE draaien op dezelfde computer en dezelfde internetverbinding. Twee
scrape-scripts tegelijk geeft rate-limiting bij bol.com (~26% mislukte checks,
eerder gemeten). De BE-sloten hierboven zijn bezet; leg de NL-taken er ruim
tussen, minimaal 45 minuten verschoven, bijvoorbeeld 09:00 / 10:45 / 12:15 /
14:15. Controleer ook dat de NL-tijden niet botsen met de duur van de
BE-taken (snelstart en sync duren 10-20 minuten, dat past ruim).

## WAARSCHUWING 2: wektimers

Controleer vóór het aanmaken of activeringstimers aan staan:

```
powercfg /q SCHEME_CURRENT 238C9FA8-0AAD-41ED-83F4-97BE242C8F20 BD3B718A-0680-4D9D-8AB2-E1D2B4AC806D
```

`Current AC Power Setting Index: 0x00000001` betekent Inschakelen — goed. Bij
0x00000000 moet Peter het aanzetten (oude Configuratiescherm →
Energiebeheer → geavanceerde instellingen → Slaapstand → Wektimers toestaan).
Op deze pc stond het al goed, dus waarschijnlijk hoeft hier niets.

## WAARSCHUWING 3: de eerste BE-testrun faalde — bewust zo gelaten

De allereerste run via de taakplanner faalde met `Error 429` bij het laden van
de CSV van raw.githubusercontent.com (te veel verzoeken die dag). Dat is
tijdelijk en herstelt zichzelf, maar het toont twee dingen:

1. het logsysteem werkt — de fout stond binnen een minuut leesbaar op GitHub
2. een mislukte run is GEEN ramp: de volgende dag draait alles opnieuw, en de
   ochtendcontrole door de chat vangt het op

Bouw dus geen retry-logica; dat maakt het complexer zonder echte winst.

## Randvoorwaarden die al in de BE-scripts zitten (controleer of NL ze heeft)

- `probe_recovery.py auto/start` weigert na 20:30 (Channable importeert 's
  avonds niet meer; artikelen zouden anders de hele nacht op volle prijs staan)
- `probe_recovery.py check` weigert binnen 30 minuten na de start (te vroeg
  checken leest de OUDE prijs en houdt een niet-winnende prijs vast)
- de sync staat 2 uur ná de probe-check gepland vanwege het valse-verliezen-
  effect dat NL zelf ontdekte (Channable heeft teruggezette prijzen dan nog
  niet geïmporteerd)
- kandidaatselectie met MIN_GAIN en cooldown via `probe_history.json`

## Wat verandert er voor Peter

- 's ochtends het bestand in GitHub zetten — dat blijft
- verder niets: snelstart, probe-ronde, controle en sync gaan vanzelf
- de pc mag in slaapstand, niet uit
- seintjes geven hoeft niet meer

## Wat verandert er voor de chats

Elke sessie begint met het lezen van `automation_log.json` (via de Contents-API,
niet de raw-URL — die cachet en gaf vandaag nog een 429). Melden aan Peter:

- runs met `"result": "FAILED"` → uitleggen wat er misging
- een taak die helemaal ontbreekt op een dag → de pc heeft hem gemist
- vreemde aantallen in de resultaatregels (bv. 0 producten geladen, ongewoon
  veel REVERTED) → onderzoeken vóór de dagroutine verder gaat

## EXTRA (ook 17/8, urgent): noodstop in de cloud-run — dit raakt NL net zo hard

Tijdens het testen bleek raw.githubusercontent.com ons met 429 te blokkeren
(Channable kreeg dezelfde fout op BEIDE feeds — zie de Channable-mail van 15:58).
Alle `load_*`-functies in de engine geven bij een niet-200 stilletjes `{}`/`[]`
terug. Een cloud-run tijdens zo'n blokkade ziet dus "geen frozen, geen tracking,
verse dag" en publiceert een feed met ALLES op volle prijs — alle bevroren
winnaars gewist in één upload.

Fix in BE (`src/github_action_reprice.py`): vóór het draaien een preflight die
`frozen.json`, `state.json` en `master_tracked.json` via de raw-URL probeert te
lezen; is er één niet status 200, dan `sys.exit(1)` zónder iets te uploaden.
Een overgeslagen run houdt de feed van gisteren — altijd beter dan een
vernietigde. Rode workflow-mails tijdens zo'n storing zijn dus BEWUST en veilig.

Bouw dit ook in NL in, vóór de taakplanner-setup.

## Testvolgorde (zoals in BE gedaan)

1. `python src/scheduled_run.py selftest` — verschijnt er een entry in
   `logs/` én op GitHub?
2. Peter draait `taken_aanmaken.ps1` — vier taken "Ready"?
3. Start één taak handmatig (`Start-ScheduledTask`) en controleer dat de
   uitslag in beide logs staat, ook als hij faalt
4. De volgende ochtend: controleer of alle taken op tijd gedraaid hebben
