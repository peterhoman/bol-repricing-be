# Bol.com BE Repricing — Dreamhouse&Garden

Automatische repricing voor het **Bol.com België**-account (verkoper
**Dreamhouse&Garden**). Dit is een zelfstandige kopie van het werkende
`bol-repricing`-project (NL/Tiptopshop), met alle bugfixes van dat project
al inbegrepen.

## Verschillen met het NL-project

| | NL (bol-repricing) | BE (dit project) |
|---|---|---|
| Marketplace | bol.com/nl/nl | **bol.com/be/nl** |
| Verkoper (buybox-detectie) | Tiptopshop | **Dreamhouse&Garden** |
| Normale prijs | klantprijs × 2.4 + 8 (< 4: +2 eerst) | **klantprijs × 2.6 + 8.5 (< 10: +1 eerst)** |
| Minimumprijs | klantprijs × 1.9 + 8 | **klantprijs × 2.1 + 8.5** (hogere marge i.v.m. verzendkosten/retouren BE) |
| Channable-project | (NL-project) | "B-living feeds -dreamhouse&garden" (ID 138815) |

Zelfde B-Living feed, zelfde architectuur: GitHub Actions (cron) genereert
`repricing_current.xml`, Channable importeert die via de vaste raw-URL.

## Vaste bestandsnamen (nooit hernoemen)

- `bolcom_productinformatie.csv` — dagelijkse "geen koopblok"-export (Peter uploadt, zelfde bestandsnaam)
- `repricing_current.xml` — door de tool gegenereerd; DIT is de Channable-import-URL
- `state.json`, `frozen.json`, `big_gap.json`, `master_tracked.json`, `audit_report.json` — statusbestanden

## Lokale scripts (alleen vanaf residentiële verbinding — bol.com blokkeert cloud-IP's)

- `python src/sync_buybox.py` — twee-weg buybox-sync (nieuwe winnaars bevriezen / verliezers ontdooien)
- `python src/match_prices.py` — ochtend-snelstart: direct de concurrent onderbieden (−€0.02)
- `python src/probe_recovery.py start|check` — marge-herstel testen voor bevroren artikelen

## Setup (eenmalig)

1. Maak public GitHub-repo `peterhoman/bol-repricing-be`
2. Maak een fine-grained PAT, alleen voor deze repo: Contents, Workflows, Actions (Read & write)
3. Zet token in `.env` (kopieer `.env.example`)
4. `python setup_upload.py` — uploadt alle projectbestanden naar de repo
5. Channable "XML-bestand url" wijzigen naar:
   `https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/repricing_current.xml`
6. Controleer dat de Channable-verkoopprijsregel voor dit project de BE-formule gebruikt
   (× 2.6 + 8.5; < 10: eerst +1)
7. Cron-schema in `.github/workflows/reprice.yml` afstemmen op de Channable-importsloten van DIT project
