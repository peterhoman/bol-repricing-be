#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Margin-recovery probe for frozen (buybox-won) articles.

Problem: once an article wins the buybox at a reduced price, the main tool
holds it there forever - even if the competitor later raises their price or
goes out of stock, we'd never know and never claim back that margin.

This script tests recovery in two phases, run separately (because Channable
only re-imports our feed once per hour, so we can't verify instantly):

  python src/probe_recovery.py candidates [n]
      Show the n best candidates (default 15) without changing anything.

  python src/probe_recovery.py auto [n]
      Pick the n best candidates automatically and start probing them.
      Selection: frozen EANs sorted by recoverable margin (full price at the
      CURRENT purchase price minus the price we're frozen at), keeping only
      those worth at least MIN_GAIN and not probed in the last COOLDOWN_DAYS.

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
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase2_repricing import RepricingEngine

from dotenv import load_dotenv
load_dotenv()

CSV_URL = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/bolcom_productinformatie.csv"
GITHUB_REPO = os.getenv("GITHUB_REPO")

# Candidate selection (see instructie-NL-margeherstel-probe.md for the numbers
# behind these). Round 1 on 21 July probed the 15 biggest gaps and kept 9;
# round 2 on 22 July probed the next 15 and kept only 1. So the margin is in
# the head of the distribution, not the tail - hence a minimum gain rather
# than "probe everything that's below full price".
MIN_GAIN = 10.0        # euro of recoverable selling price, below this it isn't worth the risk
COOLDOWN_DAYS = 14     # don't retry a reverted EAN before the competitor has had time to move
DEFAULT_BATCH = 15


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


def select_candidates(engine, limit):
    """
    Rank frozen EANs by how much selling price we could reclaim, and return
    the best `limit` of them as (ean, current_price, full_price, gain) tuples.

    Excluded automatically:
      - EANs no longer in the B-Living feed (no current purchase price)
      - EANs already at (or above) their full price - nothing to recover.
        This also silently excludes winners from earlier rounds: a KEPT probe
        left the article AT its full price, so its gain is 0 from then on.
      - EANs probed within COOLDOWN_DAYS. Without this a reverted article
        looks like a top candidate again the very next day (its safe price was
        restored), so every round would re-probe the same losers.
    """
    frozen = fetch_json("frozen.json", {})
    history = fetch_json("probe_history.json", {})
    today = date.today()

    candidates = []
    skipped_cooldown = 0
    for ean, frozen_klantprijs in frozen.items():
        fresh_klantprijs = engine.bliving_klantprijzen.get(ean)
        if fresh_klantprijs is None:
            continue

        last = history.get(ean)
        if last:
            try:
                if (today - date.fromisoformat(last)).days < COOLDOWN_DAYS:
                    skipped_cooldown += 1
                    continue
            except ValueError:
                pass

        current_price = engine.calculate_normal_price(frozen_klantprijs)
        full_price = engine.calculate_normal_price(fresh_klantprijs)
        gain = round(full_price - current_price, 2)
        if gain >= MIN_GAIN:
            candidates.append((ean, round(current_price, 2), round(full_price, 2), gain))

    candidates.sort(key=lambda c: -c[3])
    if skipped_cooldown:
        print(f"   ({skipped_cooldown} EAN(s) skipped - probed within the last {COOLDOWN_DAYS} days)")
    return candidates[:limit]


def phase_candidates(limit):
    engine = RepricingEngine(CSV_URL)
    picks = select_candidates(engine, limit)
    if not picks:
        print(f"\n[DONE] No candidates with at least EUR{MIN_GAIN:.2f} to recover")
        return []
    total = sum(c[3] for c in picks)
    print(f"\n[CANDIDATES] Top {len(picks)} by recoverable margin "
          f"(EUR{total:.2f} in total):")
    for ean, now, full, gain in picks:
        print(f"   {ean}  EUR{now:8.2f} -> EUR{full:8.2f}   +EUR{gain:6.2f}")
    return picks


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

    # Record every probed EAN (kept AND reverted) so select_candidates() can
    # honour the cooldown. Without this, a reverted article is restored to its
    # safe price and immediately looks like a top candidate again tomorrow.
    history = fetch_json("probe_history.json", {})
    today = date.today().isoformat()
    for ean in probe_backup:
        history[ean] = today
    upload_json(history, "probe_history.json",
                f"Probe history: {len(probe_backup)} EAN(s) probed on {today}")

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
    if command == "candidates":
        phase_candidates(int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BATCH)
    elif command == "auto":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BATCH
        engine = RepricingEngine(CSV_URL)
        picks = select_candidates(engine, limit)
        if not picks:
            print(f"\n[DONE] No candidates with at least EUR{MIN_GAIN:.2f} to recover")
            sys.exit(0)
        total = sum(c[3] for c in picks)
        print(f"\n[AUTO] Probing {len(picks)} EAN(s), EUR{total:.2f} of margin at stake:")
        for ean, now, full, gain in picks:
            print(f"   {ean}  EUR{now:8.2f} -> EUR{full:8.2f}   +EUR{gain:6.2f}")
        phase_start([c[0] for c in picks])
    elif command == "start":
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
