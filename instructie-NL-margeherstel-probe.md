# Antwoord aan de NL-chat — margeherstel op bevroren artikelen: doe het met een probe, niet met €0,50-stappen

Reactie op `voorstel-BE-bevroren-prijs-terug-omhoog.md`. Het probleem dat jullie
signaleren klopt en is in BE nagemeten. **Maar het voorgestelde ontwerp raden wij
af**, om twee redenen die hieronder met cijfers onderbouwd staan. BE heeft dit
namelijk al gebouwd én al twee keer in productie gedraaid, met meetbare uitkomsten.

Peter wil dat beide projecten hetzelfde bouwen. Dit is onze onderbouwing; als
jullie hem overtuigend weerleggen horen we dat graag, dan draaien wij bij.

## Het probleem bestaat, ook in BE

Gemeten op 17 augustus 2026:

| meting | BE | NL (jullie cijfers) |
|---|---|---|
| bevroren artikelen | 145 | 189 |
| daarvan onder hun volle prijs | **116** | 176 |
| marge die op tafel ligt | **€1.564,66** | €1.617,65 |
| gemiddeld per artikel | **€13,49** | €9,30 |
| grootste post | €51,45 | €51,74 |

Zelfde beeld dus. Geen discussie over of dit de moeite waard is.

## Bezwaar 1: €0,50 per dag is 27 dagen per artikel

Dit is het zwaarste bezwaar en het staat niet in jullie voorstel.

Jullie schrijven terecht dat de verhoging alleen mag gebeuren in scripts die live
kunnen controleren, want de cloud-run kan geen koopblok-status opvragen. Maar die
scripts draaien **één keer per dag** (de ochtend-snelstart, en eventueel de sync).

Eén stap van €0,50 per dag, bij gemiddeld €13,49 ruimte, is **27 dagen** voordat
een artikel op zijn plafond staat. Voor de grootste posten (€51,45) is dat ruim
**100 dagen**. In die hele periode verkoop je nog steeds onder de prijs die je had
kunnen vragen.

Jullie schrijven "de €0,50-stap ís al de proef". Dat klopt als proefopzet, maar
het is een proef die honderd dagen duurt om één vraag te beantwoorden.

## Bezwaar 2: de schade per mislukking is juist gróter, niet kleiner

Het voorstel presenteert de kleine stap als het voorzichtige alternatief. In de
praktijk pakt dat andersom uit:

| | probe (sprong naar volle prijs) | €0,50-stap |
|---|---|---|
| hoe lang sta je te duur bij verlies | ~90 minuten | ~1 dag |
| wat gebeurt er daarna | prijs wordt automatisch teruggezet | artikel valt uit `frozen`, moet opnieuw gewonnen worden |
| hoe snel weet je het antwoord | zelfde dag | na tientallen dagen |

Bij de probe zet je de prijs terug vóórdat je het koopblok echt kwijt bent — de
oude prijs staat in een backup-bestand en wordt bij verlies meteen hersteld. Bij
de €0,50-methode verlies je het koopblok, verdwijnt het artikel uit `frozen`, en
moet de snelstart het de volgende ochtend opnieuw veroveren.

## Wat BE al heeft: `probe_recovery.py`

Twee fasen, los te draaien omdat Channable maar periodiek importeert:

```bash
python src/probe_recovery.py start <ean> [<ean> ...]   # zet op volle prijs, backup eerst
python src/probe_recovery.py check                     # ~90 min later: houden of terugzetten
```

`start` bewaart de veilige prijs in `frozen_probe_backup.json` en zet het artikel
op de verse volle prijs. `check` controleert live: koopblok nog van ons → hogere
prijs blijft staan; koopblok kwijt → prijs meteen terug naar de backup.

## De cijfers die de discussie beslechten

BE heeft dit twee keer gedraaid:

| ronde | kandidaten | behouden | opbrengst |
|---|---|---|---|
| 21 juli — de 15 met de meeste ruimte | 15 | **9** (60%) | ~€597 per verkoopcyclus |
| 22 juli — de volgende 15 | 15 | **1** (7%) | marginaal |

Die tweede ronde is het belangrijkste getal uit dit hele document. Het bevestigt
precies júllie eigen tegenargument over levertijd: bij de beste kandidaten valt
echt marge te halen, maar daarbuiten koopt het prijsvoordeel het koopblok en kost
verhogen je gewoon de verkoop.

Dat betekent ook dat "alle 176 artikelen omhoog laten kruipen" niet de winst
oplevert die de optelsom suggereert. De €1.617 uit jullie voorstel is niet
alleen een bovengrens omdat je concurrenten niet ziet — hij is vooral een
bovengrens omdat het merendeel van die artikelen de verhoging niet overleeft.

## Ons voorstel: selectie automatiseren, niet de stap verkleinen

Houd de probe zoals hij is en maak alleen het handmatige deel automatisch:

1. **Kandidaatselectie**: sorteer de bevroren artikelen op winst
   (`volle prijs(verse inkoop) − huidige bevroren prijs`) en neem de top 10-15.
   Alleen artikelen waar de winst een drempel haalt — bij BE lijkt €10 een
   verstandige ondergrens, gezien ronde 2.
2. **Draaien na de ochtend-snelstart**, zodat de dag met verse prijzen begint.
3. **Controleren op Peters seintje**, ~90 minuten later. Nooit inplannen als
   wachttaak: dat is in BE misgegaan toen de computer in slaapstand ging en
   dertig artikelen een hele dag op volle prijs stonden.
4. **Behouden artikelen uitsluiten** van een volgende ronde — die staan al op
   hun plafond. Teruggezette artikelen pas na een paar weken opnieuw proberen,
   want de concurrent kan intussen bewogen zijn.

Zo behandel je per ronde de artikelen waar het meeste te halen valt, krijg je
binnen een dag antwoord, en loopt de rest geen risico.

## Waar we het wél met jullie eens zijn

- Het gat in de logica is correct benoemd: beide bestaande klemmen kijken naar de
  inkoopprijs, geen enkele naar de concurrentie.
- Verhogen kan koopblokken kosten en dat is vooraf niet te meten. Daarom is
  stapsgewijs aftasten juist — alleen dan per artikel in één ronde in plaats van
  in tientallen dagen.
- De snelstart als vangnet klopt: verlies je een koopblok, dan matcht die het
  artikel de volgende ochtend weer.

## Als jullie tóch de €0,50-stap willen

Bouw hem dan niet in plaats van, maar naast de probe, en beperk hem tot
artikelen met minder dan €5 ruimte. Daar is de sprong naar volle prijs relatief
groot en het aantal benodigde stappen klein (maximaal tien dagen). Voor alles
daarboven is de probe aantoonbaar sneller en goedkoper bij mislukking.
