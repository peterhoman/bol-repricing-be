#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Two-way buybox sync - run this periodically (from a residential connection,
e.g. Peter's own machine - bol.com blocks buybox checks from cloud IPs).

1. Checks every ACTIVE (not-yet-frozen) tracked EAN: did it just win the
   buybox? If so, freeze it at its current price. If not, and the gap to
   whoever IS winning is >= EUR10, mark it for accelerated EUR10-per-step
   reduction (see big_gap.json) - unless it's a 2Lif/Sun Arts vliegengordijn,
   which can never win on price alone (Peter's purchase cost is too high)
   and would just get burned down to the price floor for nothing.
2. Checks every FROZEN EAN: does it still have the buybox? If a competitor
   undercut it since it was frozen, UNFREEZE it so the tool resumes
   reducing its price again from where it's currently held.

Usage:
    python src/sync_buybox.py
"""
import os
import sys
import json
import time
import base64
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase2_repricing import RepricingEngine

load_dotenv()

CSV_URL = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/bolcom_productinformatie.csv"
GITHUB_REPO = os.getenv("GITHUB_REPO")


def github_headers():
    token = os.getenv("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def upload_json(data, filename, message):
    headers = github_headers()
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    content_b64 = base64.b64encode(json.dumps(data, indent=2).encode("utf-8")).decode("utf-8")
    get_r = requests.get(api_url, headers=headers, timeout=15)
    sha = get_r.json().get("sha") if get_r.status_code == 200 else None
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


def add_eans_to_csv(eans):
    """Re-add EANs (that lost buybox and dropped out of tracking) to the CSV."""
    if not eans:
        return
    headers = github_headers()
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/bolcom_productinformatie.csv"
    raw = requests.get(CSV_URL, timeout=30).text
    lines = raw.rstrip("\n").split("\n")
    num_cols = len(lines[0].split(";"))
    for ean in eans:
        row = [""] * num_cols
        row[0] = f"Hersteld na koopblok-verlies {ean}"
        row[1] = ean
        row[2] = ean
        lines.append(";".join(row))
    new_content = "\n".join(lines)
    content_b64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    get_r = requests.get(api_url, headers=headers, timeout=15)
    sha = get_r.json()["sha"]
    r = requests.put(api_url, headers=headers,
                      json={"message": f"Re-add {len(eans)} EAN(s) that lost buybox while frozen",
                            "content": content_b64, "sha": sha})
    return r.status_code in (200, 201)


def main():
    engine = RepricingEngine(CSV_URL)
    frozen = json.loads(requests.get(
        f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/frozen.json", timeout=15).text or "{}")
    big_gap = json.loads(requests.get(
        f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/big_gap.json", timeout=15).text or "{}")
    last_published = engine.load_last_published_klantprijzen()

    session = requests.Session()

    print(f"\n[1/2] Checking {len(engine.products)} active (not yet frozen) articles for NEW wins "
          f"(and big price gaps)...")
    new_wins = {}
    big_gap_added = {}
    big_gap_cleared = []
    for i, ean in enumerate(engine.products):
        if ean in frozen:
            continue
        result = engine.check_buybox(ean, session)
        if result.get("found"):
            if result.get("has_buybox"):
                price = float(result.get("price"))
                new_wins[ean] = engine.calculate_klantprijs_for_target_price(price)
            else:
                competitor_price = float(result.get("price"))
                our_klantprijs = last_published.get(ean, engine.bliving_klantprijzen.get(ean, 0))
                our_price = engine.calculate_normal_price(our_klantprijs)
                gap = round(our_price - competitor_price, 2)

                if gap >= 10 and not engine.is_excluded_from_big_steps(ean):
                    big_gap_added[ean] = int(gap // 10)
                elif ean in big_gap:
                    # Gap has closed (or item no longer qualifies) - remove
                    # the exemption so it rejoins normal daily-reset behavior
                    big_gap_cleared.append(ean)
        time.sleep(0.3)
        if (i + 1) % 50 == 0:
            print(f"   {i+1}/{len(engine.products)} checked...")

    print(f"   -> {len(new_wins)} new winner(s) found")
    print(f"   -> {len(big_gap_added)} article(s) newly flagged for EUR10 steps "
          f"(>=EUR10 behind): {sorted(big_gap_added.keys())}")
    if big_gap_cleared:
        print(f"   -> {len(big_gap_cleared)} article(s) cleared from big-gap tracking "
              f"(gap closed): {sorted(big_gap_cleared)}")

    big_gap.update(big_gap_added)
    for ean in big_gap_cleared:
        big_gap.pop(ean, None)
    upload_json(big_gap, "big_gap.json",
                f"Sync: +{len(big_gap_added)} new big-gap EANs, -{len(big_gap_cleared)} cleared")

    print(f"\n[2/2] Re-checking {len(frozen)} frozen articles - did any LOSE the buybox?")
    lost_buybox = []
    for i, ean in enumerate(frozen):
        result = engine.check_buybox(ean, session)
        if result.get("found") and not result.get("has_buybox"):
            lost_buybox.append(ean)
        time.sleep(0.3)
        if (i + 1) % 50 == 0:
            print(f"   {i+1}/{len(frozen)} checked...")

    print(f"   -> {len(lost_buybox)} article(s) LOST the buybox - unfreezing")

    # Apply changes
    frozen.update(new_wins)
    for ean in lost_buybox:
        del frozen[ean]

    upload_json(frozen, "frozen.json",
                f"Sync: +{len(new_wins)} new winners, -{len(lost_buybox)} lost buybox")

    # A newly-won EAN no longer needs big-gap tracking - it's frozen now
    won_and_was_big_gap = [e for e in new_wins if e in big_gap]
    if won_and_was_big_gap:
        for ean in won_and_was_big_gap:
            del big_gap[ean]
        upload_json(big_gap, "big_gap.json",
                    f"Remove {len(won_and_was_big_gap)} EAN(s) from big-gap tracking - they won the buybox")

    # Any lost-buybox EAN that isn't in today's CSV needs to be re-added so it resumes reducing
    not_in_csv = [e for e in lost_buybox if e not in engine.products]
    if not_in_csv:
        add_eans_to_csv(not_in_csv)
        print(f"   Re-added {len(not_in_csv)} EAN(s) to CSV (they'd dropped out while frozen)")

    if new_wins or lost_buybox or big_gap_added or big_gap_cleared:
        trigger_workflow()

    print(f"\n[DONE] Frozen total now: {len(frozen)} "
          f"(+{len(new_wins)} new, -{len(lost_buybox)} unfrozen)")
    print(f"[DONE] Big-gap total now: {len(big_gap)} "
          f"(+{len(big_gap_added)} new, -{len(big_gap_cleared) + len(won_and_was_big_gap)} cleared)")


if __name__ == "__main__":
    main()
