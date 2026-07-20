#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Margin-recovery probe for frozen (buybox-won) articles.

Problem: once an article wins the buybox at a reduced price, the main tool
holds it there forever - even if the competitor later raises their price or
goes out of stock, we'd never know and never claim back that margin.

This script tests recovery in two phases, run separately (because Channable
only re-imports our feed once per hour, so we can't verify instantly):

  python src/probe_recovery.py start <ean> [<ean> ...]
      Temporarily sets the given frozen EAN(s) to their full NORMAL price
      (no discount) and pushes it live. Backs up the old (safe) price first.

  python src/probe_recovery.py check
      Run this AFTER Channable's next hourly import has had time to apply
      (wait ~70-90 minutes after "start"). Re-checks live buybox status for
      every EAN currently being probed:
        - Still has buybox -> keep the higher price (margin recovered!)
        - Lost the buybox  -> revert to the backed-up safe price immediately

Both phases must be run from a residential connection (e.g. Peter's own
machine) - bol.com blocks buybox-checking requests from cloud/datacenter
IPs, same limitation as the main tool's check_buybox().
"""
import os
import sys
import json
import requests
import base64
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase2_repricing import RepricingEngine

from dotenv import load_dotenv
load_dotenv()

CSV_URL = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/bolcom_productinformatie.csv"
GITHUB_REPO = os.getenv("GITHUB_REPO")


def github_headers():
    token = os.getenv("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def fetch_json(filename, default=None):
    r = requests.get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}", timeout=15)
    if r.status_code == 200:
        return r.json()
    return default if default is not None else {}


def upload_json(data, filename, message):
    headers = github_headers()
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    content_b64 = base64.b64encode(json.dumps(data, indent=2).encode("utf-8")).decode("utf-8")
    sha = None
    get_r = requests.get(api_url, headers=headers, timeout=15)
    if get_r.status_code == 200:
        sha = get_r.json().get("sha")
    payload = {"message": message, "content": content_b64}
    if sha:
        payload["sha"] = sha
    r = requests.put(api_url, headers=headers, json=payload, timeout=30)
    return r.status_code in (200, 201)


def trigger_workflow():
    headers = github_headers()
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/reprice.yml/dispatches"
    r = requests.post(api_url, headers=headers, json={"ref": "main"}, timeout=30)
    return r.status_code == 204


def phase_start(eans):
    engine = RepricingEngine(CSV_URL)
    frozen = fetch_json("frozen.json", {})
    probe_backup = fetch_json("frozen_probe_backup.json", {})

    updated = 0
    for ean in eans:
        if ean not in frozen:
            print(f"[SKIP] {ean} is not currently frozen (not a buybox winner) - nothing to probe")
            continue
        if ean not in engine.bliving_klantprijzen:
            print(f"[SKIP] {ean} not found in current B-Living feed")
            continue

        old_klantprijs = frozen[ean]
        fresh_klantprijs = engine.bliving_klantprijzen[ean]

        probe_backup[ean] = old_klantprijs
        frozen[ean] = fresh_klantprijs
        updated += 1
        print(f"[PROBE] {ean}: {old_klantprijs} -> {fresh_klantprijs} "
              f"(price {engine.calculate_normal_price(old_klantprijs):.2f} -> "
              f"{engine.calculate_normal_price(fresh_klantprijs):.2f})")

    if updated == 0:
        print("\n[DONE] Nothing to probe")
        return

    upload_json(frozen, "frozen.json", f"Probe recovery: test {updated} EAN(s) at full price")
    upload_json(probe_backup, "frozen_probe_backup.json", f"Backup before probing {updated} EAN(s)")
    trigger_workflow()

    print(f"\n[STARTED] {updated} EAN(s) set to full normal price and pushed.")
    print("Wait ~70-90 minutes (for Channable's next hourly import), then run:")
    print("  python src/probe_recovery.py check")


def phase_check():
    probe_backup = fetch_json("frozen_probe_backup.json", {})
    if not probe_backup:
        print("[DONE] No probes currently in progress")
        return

    engine = RepricingEngine(CSV_URL)
    frozen = fetch_json("frozen.json", {})
    session = requests.Session()

    kept = []
    reverted = []
    remaining_backup = {}

    for ean, old_klantprijs in probe_backup.items():
        result = engine.check_buybox(ean, session)
        if result.get("found") and result.get("has_buybox"):
            kept.append(ean)
            print(f"[KEPT] {ean}: still has buybox at the higher price - margin recovered!")
        else:
            frozen[ean] = old_klantprijs
            reverted.append(ean)
            print(f"[REVERTED] {ean}: lost buybox - restored to safe price {old_klantprijs}")
        import time
        time.sleep(0.3)

    upload_json(frozen, "frozen.json", f"Probe recovery result: kept {len(kept)}, reverted {len(reverted)}")
    upload_json({}, "frozen_probe_backup.json", "Clear probe backup - probe cycle complete")
    if reverted:
        trigger_workflow()

    print(f"\n[DONE] Kept higher price: {len(kept)} | Reverted to safe price: {len(reverted)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "start":
        eans = sys.argv[2:]
        if not eans:
            print("Usage: python src/probe_recovery.py start <ean> [<ean> ...]")
            sys.exit(1)
        phase_start(eans)
    elif command == "check":
        phase_check()
    else:
        print(__doc__)
        sys.exit(1)
