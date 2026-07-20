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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phase2_repricing import RepricingEngine

CSV_URL = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/bolcom_productinformatie.csv"

if __name__ == "__main__":
    engine = RepricingEngine(CSV_URL)

    if not engine.products:
        print("\n[ERROR] No products loaded from CSV")
        sys.exit(1)

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
