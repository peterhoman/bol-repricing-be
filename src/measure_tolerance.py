"""
Meet hoeveel PRIJSNADEEL ons koopblok verdraagt (BE, Dreamhouse&Garden).

Aanleiding (2 september 2026)
----------------------------
Sinds 1/9 lezen we via de prijsoverzichtspagina alle concurrentprijzen. Daar
viel iets op: bij 8716522103465 stonden wij op EUR255,03 tegen EUR254,95 van
Bohemian Living NL - en toch hadden WIJ het koopblok. `probe_recovery.py`
gaat nooit boven de goedkoopste concurrent zitten, dus als dat vaker voorkomt
laten we marge liggen.

De NL-chat (Tiptopshop) mat op 1/9 het spiegelbeeld: zij gaven hun prijs-
voordeel weg en hielden het koopblok in 12% van de gevallen waar de concurrent
sneller levert, 20% bij gelijke levertijd, 100% waar de concurrent trager is.
Hun conclusie: het koopblok verdraagt een prijsnadeel precies voor zover je
een levertijdvoordeel hebt. Dit script test die regel op ONZE cijfers.

Wat het doet
------------
Voor elke bevroren EAN, in een run:
  1. check_buybox()      - hebben WIJ het koopblok nu echt? (productpagina)
  2. check_all_offers()  - alle verkopers met prijs (prijsoverzichtspagina)
  3. levertijd + beoordeling per verkoper uit datzelfde overzicht

Dat is sterker bewijs dan "staat in frozen": frozen zegt alleen dat we het
koopblok hadden bij de laatste sync, dit meet het op hetzelfde moment als de
prijzen.

Het script SCHRIJFT NIETS en past geen prijzen aan - het is puur een meting.

Draaien: NOOIT tegelijk met match_prices/sync_buybox/probe_recovery (bol.com
geeft dan rate-limiting). Dus na de sync van 14:15, of voor 09:00.

    python src/measure_tolerance.py [aantal]
"""

import json
import re
import sys
import time
import datetime
import requests

sys.path.insert(0, "src")
from phase2_repricing import (RepricingEngine, levertijd_naar_dagen,  # noqa: E402
                              vergelijk_levertijd)

SELLER = "Dreamhouse&Garden"
PAUSE = 0.3  # zelfde pauze als de andere scrapers
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# levertijd_naar_dagen() en vergelijk_levertijd() staan sinds 3/9 in
# phase2_repricing.py, omdat optimize() ze ook gebruikt.


def parse_overzicht(html: str, vandaag: datetime.date):
    """
    Lees per verkoper prijs, levertijd en beoordeling uit de
    prijsoverzichtspagina.

    Prijs komt uit dezelfde voorleeszin die check_all_offers() gebruikt (die
    is stabieler dan de visuele opmaak). Levertijd staat direct achter
    "Inclusief verzendkosten", beoordeling helemaal vooraan in het blok.
    """
    resultaat = []
    for blok in html.split('data-testid="offer-compare-item"')[1:]:
        seg = blok[:6000]
        # Twee leesvormen van hetzelfde blok:
        #   tekst - tags weg, voor de beoordeling die vooraan staat
        #   pipe  - elke tag wordt '|', zodat veldgrenzen bewaard blijven.
        # De levertijd staat als los veld direct achter "Inclusief
        # verzendkosten" ("...|Inclusief verzendkosten|1 - 2 weken|"); zonder
        # die grens loopt een regex door in de opmaak erachter.
        tekst = re.sub(r"<[^>]+>", " ", seg)
        tekst = re.sub(r"\s+", " ", tekst).strip()
        pipe = re.sub(r"<[^>]+>", "|", seg)
        pipe = re.sub(r"[ \t\r\n]+", " ", pipe)
        pipe = re.sub(r"\|+", "|", pipe)

        # Prijs en verkoper uit de RUWE html lezen, net als check_all_offers().
        # Op de tag-gestripte tekst werkt dat niet: daar ontbreekt de '<' die
        # "Verkocht door <naam>" afkapt, waardoor de regex doorloopt tot de
        # eerstvolgende punt en de halve prijszin als verkopersnaam oppikt
        # (gevonden 2/9 - alle checks meldden "eigen aanbod niet gevonden").
        prijs = re.search(r"De prijs van dit product is (\d+) euro(?: en (\d+) cent)?", seg)
        verkoper = re.search(r"Verkocht door ([^.<|]{2,60})", seg)
        if not (prijs and verkoper):
            continue

        euro = int(prijs.group(1))
        cent = int(prijs.group(2) or 0)

        lever = re.search(r"Inclusief verzendkosten\|([^|]{2,60})", pipe)
        levertekst = lever.group(1).strip() if lever else ""

        beoordeling = None
        b = re.match(r"^>?\s*(\d{1,2},\d)", tekst)
        if b:
            try:
                beoordeling = float(b.group(1).replace(",", "."))
            except ValueError:
                beoordeling = None

        resultaat.append({
            "seller": verkoper.group(1).replace("&amp;", "&").strip(),
            "price": round(euro + cent / 100, 2),
            "levertekst": levertekst,
            "leverbereik": levertijd_naar_dagen(levertekst, vandaag),
            "beoordeling": beoordeling,
        })
    return resultaat


def meet(limiet=None):
    vandaag = datetime.date.today()
    engine = RepricingEngine("bolcom_productinformatie.csv")
    frozen = engine.load_frozen_eans()
    eans = list(frozen.keys())
    if limiet:
        eans = eans[:limiet]

    print(f"[MEET] {len(eans)} bevroren artikel(en), gestart {datetime.datetime.now():%H:%M:%S}")
    sessie = requests.Session()
    rijen, mislukt = [], []

    for i, ean in enumerate(eans, 1):
        if i % 25 == 0:
            print(f"   {i}/{len(eans)} ...")
        try:
            zoek = sessie.get(f"https://www.bol.com/be/nl/s/?searchtext={ean}",
                              headers=UA, timeout=15)
            urls = re.findall(r'"(/be/nl/p/[^"]+)"', zoek.text)
            if not urls:
                mislukt.append((ean, "geen productpagina in zoekresultaat"))
                time.sleep(PAUSE)
                continue
            m = re.search(r"/p/([^/]+)/(\d+)", urls[0])
            if not m:
                mislukt.append((ean, "url niet te lezen"))
                time.sleep(PAUSE)
                continue
            slug, pid = m.group(1), m.group(2)
            time.sleep(PAUSE)

            # 1. wie heeft NU het koopblok
            bb = engine.check_buybox(ean, sessie, SELLER)
            time.sleep(PAUSE)

            # 2. alle verkopers met prijs, levertijd, beoordeling
            pag = sessie.get(
                f"https://www.bol.com/be/nl/prijsoverzicht/{slug}/{pid}/"
                f"?sort=price&sortOrder=asc", headers=UA, timeout=20)
            time.sleep(PAUSE)
            if pag.status_code != 200:
                mislukt.append((ean, f"overzicht status {pag.status_code}"))
                continue

            aanbod = parse_overzicht(pag.text, vandaag)
            if not aanbod:
                mislukt.append((ean, "geen aanbod gelezen"))
                continue

            wij = next((o for o in aanbod if o["seller"].lower() == SELLER.lower()), None)
            anderen = [o for o in aanbod if o["seller"].lower() != SELLER.lower()]
            if not wij:
                mislukt.append((ean, "eigen aanbod niet gevonden op overzicht"))
                continue

            goedkoopste = min(anderen, key=lambda o: o["price"]) if anderen else None
            rijen.append({
                "ean": ean,
                "koopblok": bb.get("has_buybox") if bb.get("found") else None,
                "winnaar": bb.get("seller") if bb.get("found") else None,
                "onze_prijs": wij["price"],
                "onze_leverbereik": wij["leverbereik"],
                "onze_levertekst": wij["levertekst"],
                "onze_beoordeling": wij["beoordeling"],
                "aantal_anderen": len(anderen),
                "goedkoopste": goedkoopste["price"] if goedkoopste else None,
                "goedkoopste_verkoper": goedkoopste["seller"] if goedkoopste else None,
                "goedkoopste_leverbereik": goedkoopste["leverbereik"] if goedkoopste else None,
                "goedkoopste_levertekst": goedkoopste["levertekst"] if goedkoopste else None,
                "goedkoopste_beoordeling": goedkoopste["beoordeling"] if goedkoopste else None,
            })
        except Exception as e:
            mislukt.append((ean, str(e)[:80]))

    return rijen, mislukt


def rapporteer(rijen, mislukt):
    print("\n" + "=" * 68)
    print("RESULTAAT")
    print("=" * 68)
    print(f"Gemeten: {len(rijen)}   mislukt: {len(mislukt)}")

    met_bb = [r for r in rijen if r["koopblok"] is True]
    zonder = [r for r in rijen if r["koopblok"] is False]
    onbekend = [r for r in rijen if r["koopblok"] is None]
    print(f"Koopblok NU van ons: {len(met_bb)} | kwijt: {len(zonder)} | onbepaald: {len(onbekend)}")

    solo = [r for r in met_bb if r["aantal_anderen"] == 0]
    concur = [r for r in met_bb if r["aantal_anderen"] > 0]
    print(f"Waarvan zonder enige concurrent: {len(solo)}")
    print(f"Met minstens een concurrent:     {len(concur)}")

    # DE KERNVRAAG: koopblok van ons terwijl iemand goedkoper is
    duurder = [r for r in concur if r["goedkoopste"] is not None
               and r["goedkoopste"] < r["onze_prijs"]]
    print(f"\n>>> KOOPBLOK VAN ONS TERWIJL EEN ANDER GOEDKOPER IS: "
          f"{len(duurder)} van {len(concur)}"
          f" ({100*len(duurder)//max(len(concur),1)}%)")

    if duurder:
        verschillen = sorted(round(r["onze_prijs"] - r["goedkoopste"], 2) for r in duurder)
        mid = verschillen[len(verschillen) // 2]
        print(f"    prijsverschil: min EUR{verschillen[0]:.2f} | "
              f"mediaan EUR{mid:.2f} | max EUR{verschillen[-1]:.2f}")
        pct = sorted(100 * (r["onze_prijs"] - r["goedkoopste"]) / r["goedkoopste"]
                     for r in duurder)
        print(f"    als percentage: min {pct[0]:.2f}% | "
              f"mediaan {pct[len(pct)//2]:.2f}% | max {pct[-1]:.2f}%")

        # levertijd erbij: verklaart die de tolerantie, zoals bij NL?
        telling = {}
        for r in duurder:
            k = vergelijk_levertijd(r["onze_leverbereik"], r["goedkoopste_leverbereik"])
            telling[k] = telling.get(k, 0) + 1
        print("    concurrent levert: " + " | ".join(
            f"{k} {v}" for k, v in sorted(telling.items(), key=lambda x: -x[1])))

        print("\n    Grootste marges die we nu laten liggen:")
        for r in sorted(duurder, key=lambda x: x["onze_prijs"] - x["goedkoopste"],
                        reverse=True)[:12]:
            d = r["onze_prijs"] - r["goedkoopste"]
            print(f"      {r['ean']}  wij EUR{r['onze_prijs']:>8.2f} ({r['onze_levertekst']})"
                  f"  vs EUR{r['goedkoopste']:>8.2f} {r['goedkoopste_verkoper'][:22]}"
                  f" ({r['goedkoopste_levertekst']})  +EUR{d:.2f}")

    # controlegroep: koopblok kwijt terwijl wij duurder zijn
    kwijt_duurder = [r for r in zonder if r["goedkoopste"] is not None
                     and r["goedkoopste"] < r["onze_prijs"]]
    print(f"\nControle - koopblok KWIJT terwijl een ander goedkoper is: "
          f"{len(kwijt_duurder)} van {len(zonder)}")

    if mislukt:
        print(f"\nMislukte checks ({len(mislukt)}), eerste 10:")
        for ean, reden in mislukt[:10]:
            print(f"   {ean}: {reden}")

    return {"met_bb": len(met_bb), "concur": len(concur), "duurder": len(duurder)}


if __name__ == "__main__":
    limiet = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rijen, mislukt = meet(limiet)
    rapporteer(rijen, mislukt)

    stamp = datetime.date.today().isoformat()
    uit = f"logs/tolerantie-{stamp}.json"
    with open(uit, "w", encoding="utf-8") as f:
        json.dump({"gemeten_op": datetime.datetime.now().isoformat(),
                   "rijen": rijen,
                   "mislukt": [{"ean": e, "reden": r} for e, r in mislukt]},
                  f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Ruwe data weggeschreven naar {uit}")
