# Instructie voor de NL-chat (Tiptopshop) — gedateerde CSV-uploads automatisch overzetten

Gebouwd en live bewezen in BE op 20 augustus 2026. Peter wil beide projecten
gelijk houden.

## Het probleem

Bol.com's download heet tegenwoordig `JJJJMMDD_bolcom_productinformatie.csv`
(bijv. `20260820_...`). Uploadt Peter dat bestand ongewijzigd, dan staat het
naast de vaste naam die de pijplijn leest — en draait de ochtendrun **stilletjes
met de lijst van gisteren**. Niets faalt, niets waarschuwt; dat is de ergste
soort fout. In BE op 20/8 gebeurde dit; het viel alleen op omdat de chat de
commit-historie naliep.

## De fix: `normalize_dated_csv()` in de taakwrapper

In `scheduled_run.py` (de wrapper die de taakplanner aanroept), vóór de
`morning`-taak:

1. Lijst de repo-root via de Contents-API en zoek bestanden die matchen op
   `^\d{8}_bolcom_productinformatie\.csv$`; pak de nieuwste (hoogste datum).
2. **Veiligheidscheck:** vergelijk de laatste commit-datum van het gedateerde
   bestand met die van de vaste naam. Is het gedateerde bestand OUDER, laat het
   dan staan — anders overschrijft een oude achtergebleven upload een nieuwere.
3. Kopieer de content (base64 kan 1-op-1 door naar de PUT) naar
   `bolcom_productinformatie.csv` en verwijder daarna het gedateerde bestand.
4. Geef logregels terug met prefix `[CSV]` en laat `run()` die **vóór de
   subprocess-uitvoer** in het log zetten — prints uit de wrapper zelf komen
   nergens terecht, alleen de subprocess-output wordt gelogd. Voeg `[CSV]` ook
   toe aan de filterlijst voor de samenvatting naar `automation_log.json`.
5. Alles in een try/except dat bij een fout alleen een `[CSV]`-regel teruggeeft:
   de ochtendrun mag hier nooit op blokkeren.

BE-referentie: `src/scheduled_run.py` in de BE-repo, functie
`normalize_dated_csv()`.

## Let op

- Alleen `.csv`. Een gedateerde `.xlsx` wordt bewust NIET automatisch verwerkt
  (de pijplijn leest geen xlsx); die valt op doordat de run dan met de oude
  lijst draait en de chat het in de ochtendcontrole ziet.
- De wrapper draait LOKAAL via de taakplanner — de lokale bewerking is dus
  meteen actief, maar upload hem ook naar de repo zodat beide projecten en de
  instructies synchroon blijven.

## Testen

1. Syntax-check.
2. Draai de functie los terwijl er GEEN gedateerd bestand staat: moet stil
   niets doen.
3. Upload een gedateerd testbestand en draai de functie: vaste naam moet de
   inhoud krijgen, het gedateerde bestand moet weg zijn, en de functie moet
   één `[CSV]`-regel teruggeven. (In BE gebeurde deze test per ongeluk live:
   Peter had het gedateerde bestand net opnieuw geüpload en de eerste
   testaanroep verwerkte hem meteen correct.)

## Resultaat voor Peter

Hij hoeft downloads niet meer te hernoemen — uploaden onder de naam die
bol.com geeft is voortaan genoeg, in beide projecten.
