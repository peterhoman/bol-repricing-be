# Instructie voor de NL-chat (Tiptopshop) — afrondfout klantprijs

**Jullie hadden gelijk, wij zaten fout.** De BE-chat noemde dit eerst "één cent,
maximaal ~30 minuten, corrigeert zichzelf". Dat klopt niet: het is structureel en
herhaalt zich elke run. Hieronder de gemeten cijfers en de fix zoals die in BE is
gebouwd, getest en uitgerold op 27 juli.

Bouw hem in `bol-repricing` (NL/Tiptopshop) met de **NL-formules en NL-URLs** —
neem geen BE-getallen over.

## De oorzaak

`calculate_klantprijs_for_target_price()` rondde af met `round()`.

De klantprijs gaat met 2 decimalen de feed in, en Channable vermenigvuldigt hem
(bij BE ×2,6, bij NL ×2,4). Rondt `round()` de klantprijs een halve cent naar
beneden af, dan valt de verkoopprijs die Channable eruit berekent tot ~1,3 cent
lager uit dan gevraagd.

Als de aanroeper aan het klemmen was op de **bodemprijs**, landde het artikel
daardoor precies één cent ónder de bodem. En dat corrigeert zichzelf niet: de
volgende run doet exact dezelfde berekening en komt op dezelfde cent uit.

## Gemeten in BE (meet dit ook in NL, de aantallen zullen verschillen)

| Meting | Uitkomst |
|---|---|
| Artikelen in de feed die bij klemmen een cent te laag uitkwamen | 1501 van 5262 = **28,5%** |
| Artikelen die op 27/7 daadwerkelijk live een cent te laag stonden | **85** |
| Tekort per artikel | steeds exact €0,01 |

## De fix

Rond de klantprijs **naar boven** af op de cent, nooit naar beneden:

```python
import math

def _ceil_cent(value: float) -> float:
    return math.ceil(round(max(value, 0) * 100, 6)) / 100
```

Gebruik `_ceil_cent(...)` in plaats van `round(..., 2)` in beide takken van
`calculate_klantprijs_for_target_price()` (de tak boven en onder de
klantprijs-grens).

De `round(x * 100, 6)` vóór de `ceil` is nodig: zonder die tussenstap tilt een
float-artefact als `15.9700000001` de prijs onnodig een cent omhoog.

**Waarom naar boven veilig is:** bij het onderbieden van een concurrent word je
hooguit ~1,3 cent duurder dan bedoeld — ruim binnen de €0,02 onderbieding, dus je
blijft onder de concurrent. Bij het klemmen op de bodem kom je nooit meer
eronder. Naar boven afwijken is hier altijd de goede kant.

## Marges bij bodemvergelijkingen: 0,005 in plaats van 0,01

Overal waar je vergelijkt of iets onder de bodem zit, moet de tolerantie **kleiner
zijn dan een cent**. Met `< floor - 0.01` glipt precies-een-cent-eronder er
ongemerkt doorheen — dat is precies wat deze fout zo lang verborgen hield. In BE
meldde de eerste telling daardoor 3 artikelen in plaats van 85.

Gebruik `< floor - 0.005`. In BE geldt dat op twee plekken: in
`clamp_frozen_to_floor()` en in de nieuwe audit-controle op onder-de-bodem
publiceren (zie `instructie-NL-bodemcontrole.md`).

## Testen vóór uitrol

Draai over de héle B-Living-feed: bereken per artikel de bodemprijs, zet die om
naar een klantprijs met de aangepaste functie, reken terug naar de verkoopprijs
en tel hoeveel er onder de bodem uitkomen.

- **Vóór de fix** in BE: 1501 onder de bodem
- **Na de fix** in BE: 0 onder de bodem, maximaal €0,02 erboven

Test daarnaast het onderbieden: vraag een doelprijs van bijvoorbeeld €50,00 en
controleer dat de werkelijke verkoopprijs nooit lager uitkomt dan die doelprijs.

## Uitrol

De cloud-job draait de versie die op **GitHub** staat, niet de lokale. Upload het
gewijzigde engine-bestand dus naar de NL-repo, anders werkt de fix alleen bij de
lokale ochtend-snelstart.

De 85 te lage prijzen in BE zijn niet apart hersteld: de eerstvolgende cloud-run
herberekent ze met de nieuwe code en zet ze vanzelf goed. Dat geldt in NL ook.

## Nog open in BE (ter info, niet ingebouwd)

De `last_published`-prijs die wordt vastgehouden na een mislukte buybox-check
wordt niet actief tegen de bodem geklemd. Dat venster is klein — de
eerstvolgende cloud-run corrigeert het — en audit-controle 3 signaleert het als
het gebeurt. Als jullie dat wél willen dichtzetten, hoor ik het graag, dan doen
we het in beide projecten.
