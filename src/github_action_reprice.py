#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entry point for the scheduled GitHub Actions job.

Runs ONE repricing iteration and exits (no infinite loop, no sleeping).
GitHub Actions itself provides the schedule (cron), so this script can be
completely stateless - it reads its "current position" from the last
published repricing_current.xml on GitHub instead of relying on memory.
"""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phase2_repricing import RepricingEngine

# CSV via de Contents-API, niet raw (fix 18/8): raw cachet minuten en
# racet daardoor met onze eigen API-schrijfacties - zie _fresh_headers().
CSV_URL = "https://api.github.com/repos/peterhoman/bol-repricing-be/contents/bolcom_productinformatie.csv"
RAW_BASE = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/"

if __name__ == "__main__":
    # Preflight (added 17 Aug): raw.githubusercontent.com rate-limited us with
    # 429s that day (Channable got them too). Every load_* helper in the engine
    # silently returns {}/[] on a non-200, so a run during such an outage would
    # see "no frozen articles, no tracking, fresh day" and publish a feed with
    # every price back at full - wiping all frozen winners in one upload. If we
    # cannot read the critical state, the only safe move is to not run at all:
    # a skipped run keeps yesterday's feed, which is always better than a
    # destroyed one. The run after the outage picks up normally.
    for critical in ("frozen.json", "state.json", "master_tracked.json"):
        try:
            r = requests.get(RAW_BASE + critical, timeout=30)
            status = r.status_code
        except Exception as exc:
            status = str(exc)
        if status != 200:
            print(f"[ABORT] Cannot read {critical} (status {status}) - "
                  f"refusing to reprice with incomplete state. Feed stays as-is.")
            sys.exit(1)

    engine = RepricingEngine(CSV_URL)

    if not engine.products:
        # Fresh-start situation (BE project): no daily CSV uploaded yet. Keep
        # going anyway - regenerating the XML from the fresh B-Living feed
        # keeps stock/prices current in Channable, and tracked EANs (frozen/
        # master_tracked/big_gap, all loaded from GitHub) are still processed
        # by the union in run_single_iteration_stateless, so nothing reverts.
        print("\n[WARN] No products in CSV - continuing with feed refresh + tracked EANs only")

    if not engine.bliving_klantprijzen:
        print("\n[ERROR] No klantprijzen loaded from B-Living feed")
        sys.exit(1)

    # NOTE: live buybox checking (scraping bol.com's product pages) does not
    # work from GitHub Actions - bol.com returns 403 Forbidden for requests
    # from cloud/datacenter IP ranges. It only works from a residential
    # connection (tested locally). So it's disabled here to avoid wasting
    # ~2-3 minutes per run on checks that always fail anyway.
    adjustments, new_state, buybox_won = engine.run_single_iteration_stateless(check_buybox_live=False)

    if buybox_won:
        print(f"\n[BUYBOX] Won buybox this run, price held steady: {buybox_won}")

    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    xml_path = str(output_dir / "repricing_current.xml")

    if not engine.generate_reprice_xml(xml_path, adjustments):
        print("\n[ERROR] Failed to generate XML")
        sys.exit(1)

    if not engine.upload_to_github(xml_path, "repricing_current.xml"):
        print("\n[ERROR] Failed to upload XML to GitHub")
        sys.exit(1)

    # state.json is a nice-to-have (just remembers which day we're on) - the
    # important work (the actual price update) is already done and uploaded
    # above. Retry once, but don't fail the whole run over it: a transient
    # GitHub API hiccup here shouldn't be reported as a repricing failure.
    if not engine.upload_json_to_github(new_state, "state.json"):
        print("\n[WARN] state.json upload failed, retrying once...")
        if not engine.upload_json_to_github(new_state, "state.json"):
            print("[WARN] state.json upload failed again - continuing anyway, "
                  "the price update itself already succeeded")

    print("\n[DONE] Single repricing iteration complete")
