# Instructie voor de NL-chat (Tiptopshop) — je kunt de prijs van ELKE concurrent gewoon uitlezen

Gebouwd, getest en live in BE op 1 september 2026. Dit is de belangrijkste
vondst sinds we met margeherstel begonnen, en voor NL is hij meer waard dan
voor ons: zelfde mechaniek, veel meer orders.

## De aanname die al die tijd fout was

We dachten allebei: zolang WIJ het koopblok hebben, toont bol.com alleen onze
eigen prijs, dus we kunnen niet zien of er nog iemand achter ons zit. Daarom
werd margeherstel gokwerk — de probe zette de prijs op vol, wachtte 90 minuten
en keek of het koopblok bleef.

Dat klopt voor de productpagina. Maar er is een tweede pagina:

```
https://www.bol.com/be/nl/prijsoverzicht/<slug>/<product-id>/?sort=price&sortOrder=asc
```

(NL: `/nl/nl/prijsoverzicht/...`)

Die staat achter de link "Bij N partners verkrijgbaar" op de productpagina, en
hij is **gewoon server-rendered HTML** — geen browser nodig, `requests.get()`
volstaat. Alle verkopers met hun prijzen staan erin, ook als wij winnen.

## Hoe je hem uitleest

De slug en het product-id haal je uit de gewone zoek-URL die je al gebruikt:

```python
m = re.search(r"/p/([^/]+)/(\d+)", product_url)
slug, pid = m.group(1), m.group(2)
```

Elk aanbod op de overzichtspagina zit in een blok gemarkeerd met
`data-testid="offer-compare-item"`. Splits daarop en lees per blok:

```python
prijs    = re.search(r"De prijs van dit product is (\d+) euro(?: en (\d+) cent)?", seg)
verkoper = re.search(r"Verkocht door ([^.<|]{2,60})", seg)
```

Die voorleeszin is veel stabieler dan de visuele prijsopmaak. **Let op:** bij
artikelen met korting staat er tekst tussen prijs en verkoper ("De adviesprijs
is ... Je bespaart 3%."), dus zoek de twee delen apart — één gecombineerd
patroon breekt daarop. Dat kostte ons de eerste poging.

De volledige functie staat in BE als `check_all_offers()` in
`src/phase2_repricing.py`.

## Wat je ermee doet: stoppen met proberen, gaan rekenen

Zodra je de concurrent ziet, is de hele probe overbodig. Per bevroren artikel:

| situatie | actie |
|---|---|
| geen andere verkoper | stapje omhoog (wij: max €5 per ronde, niet ineens naar vol) |
| goedkoopste ander BOVEN ons | omhoog naar net eronder (−€0,02) |
| goedkoopste ander ONDER ons | **niets doen** |

Dat laatste is belangrijk. Gemeten in BE: wij op €255,03 tegen een concurrent
op €254,95 — en wij hebben tóch het koopblok, op onze verkopersbeoordeling 8,9
tegen hun 8,1 en een kortere levertijd. Duurder zijn kan dus prima. Verlagen
zou marge weggeven voor een koopblok dat we al hebben; verhogen zou het risico
lopen. Met rust laten.

Altijd klemmen op `[bodemprijs, volle prijs]`.

Waarom niet ineens naar de volle prijs als er geen concurrent is: een pagina
die je niet goed geparsed hebt ziet er precies zo uit. Een stap van €5 komt
binnen een paar dagen op hetzelfde punt uit, met één stap risico als je het mis
hebt.

## Wat het in BE opleverde

Eerste live ronde, 40 bevroren artikelen bekeken:

| | |
|---|---|
| prijs verhoogd | **19** |
| ongemoeid gelaten (concurrent zit onder ons) | 18 |
| check mislukt | 3 |
| **opbrengst** | **+€66,26 per verkoopcyclus** |

Grootste posten: +€6,92, +€5,90, +€5,43, +€5,09. Allemaal netjes twee cent
onder een echte, met naam bekende concurrent — geen gok.

Controle na afloop: 0 artikelen onder de bodemprijs, 0 boven de volle prijs.

Opvallend: drie namen komen steeds terug (Bohemian Living NL, Cactula, Izziet).
Dat zijn dropshippers die net als wij bij de leverancier bestellen. Kijk of je
in NL hetzelfde patroon ziet.

## Waarom dit de probe vervangt

De probe werkte in augustus (15/15, 11/13) en faalde daarna volledig (0/15 op
24/8, 0/13 op 31/8). De verklaring is nu duidelijk: die concurrenten waren
terug, en de sprong naar de volle prijs is altijd te ver. Het echte plafond ligt
een paar euro hoger dan onze prijs, niet dertig.

Met deze pagina hoef je niet meer te gokken, niet 90 minuten te wachten en niets
meer terug te zetten. In BE draait de dagelijkse taak van 10:45 sinds vandaag op
`probe_recovery.py optimize 40`; `probe_check` blijft staan maar heeft niets
meer te doen.

## Testen vóór uitrol

1. Haal de overzichtspagina op voor twee artikelen waarvan je de verkopers via
   de browser kent, en controleer dat de namen en bedragen kloppen.
2. Test er één mét korting — dat is het geval waar het patroon op breekt.
3. Droogloop over ~20 bevroren artikelen: laat zien wat er zou veranderen
   zonder iets te uploaden.
4. Na de live ronde: controleer dat niets onder de bodem of boven de volle
   prijs staat.

## Tot slot

Peter merkte dit zelf op, door te vragen of ik niet gewoon in zijn browser kon
klikken. Wij hadden allebei de aanname "we kunnen de concurrent niet zien" al
weken als vaststaand feit behandeld en er omheen gebouwd. De les is de moeite
waard: als een beperking het hele ontwerp bepaalt, is het de moeite waard om
hem af en toe opnieuw te toetsen.
