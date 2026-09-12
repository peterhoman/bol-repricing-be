# Instructie voor de NL-chat (Tiptopshop) — taken zonder consolevenster draaien

Gevonden en gefixt in BE op 21 augustus 2026. Geldt voor NL net zo, want jullie
taakplanner-opzet is een kopie van de onze.

## Wat er misging

De BE-probe-start van 20/8 10:45 ontbrak in `automation_log.json`. Lokaal in
`logs/` stond hij wél: `exit=3221225786  3s`. Die code (0xC000013A,
STATUS_CONTROL_C_EXIT) betekent: **het consolevenster is gesloten**. Elke taak
draait via `python.exe` en opent daarbij een zwart venster; Peter zat aan de pc
en klikte het weg. Het hele procesboompje (wrapper + script) stierf na 3 s,
vóór de push naar GitHub — vandaar het gat in het online log.

Controleer jullie eigen lokale log op dezelfde exitcode; de kans is reëel dat
het bij NL ook al eens gebeurd is zonder dat iemand het zag.

## De fix (twee regels)

1. **`taken_aanmaken.ps1`**: `$py = "C:\Python314\pythonw.exe"` in plaats van
   `python.exe`. pythonw is dezelfde Python, maar zonder console.
2. **`scheduled_run.py`**, bij de `subprocess.run(...)`:
   ```python
   flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
   proc = subprocess.run(cmd, ..., creationflags=flags)
   ```
   Zonder dit zou het kindproces alsnog een venster openen.

Daarna moet Peter `taken_aanmaken.ps1` opnieuw uitvoeren (de taken worden
met `-Force` overschreven; twee minuten werk). De wrapper-wijziging is lokaal
meteen actief, maar upload beide bestanden ook naar de repo.

## Test

`C:\Python314\pythonw.exe src\scheduled_run.py selftest` — er mag geen venster
verschijnen en er moet een selftest-entry in `logs/` én in `automation_log.json`
komen. In BE: geslaagd.

## Voor de ochtendcontrole van de chat

Ontbreekt een taak in `automation_log.json`, kijk dan in het lokale log. Staat
hij daar met exit 3221225786, dan is het venster gesloten → controleren of
`taken_aanmaken.ps1` na deze wijziging opnieuw gedraaid is.
