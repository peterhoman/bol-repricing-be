#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import io
import csv
import re
import json
import time
import base64
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

from dotenv import load_dotenv

load_dotenv()

class RepricingEngine:
    """Main repricing engine for Bol.com buybox optimization."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.products = {}
        self.price_history = {}
        self.bliving_klantprijzen = {}
        self.bliving_titels = {}
        self.load_products()
        self.load_bliving_feed()

    def _get_with_retries(self, url: str, timeout: int = 30, retries: int = 3, backoff: int = 10):
        """
        GET a URL with a few retries on connection failures (timeouts,
        DNS hiccups, etc.) before giving up. Ported from the NL project
        after a couple of confusing "Repricing failed" emails that were
        actually just the B-Living SUPPLIER server briefly timing out, not
        a real problem with the code - retrying a couple of times with a
        short pause turns most of those transient blips into a silent
        success instead of a failed GitHub Actions run.
        """
        last_exception = None
        for attempt in range(1, retries + 1):
            try:
                return requests.get(url, timeout=timeout)
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < retries:
                    print(f"   Attempt {attempt}/{retries} failed ({e}), retrying in {backoff}s...")
                    time.sleep(backoff)
        raise last_exception

    def load_products(self):
        """Load products from CSV (330 without buybox) via GitHub."""
        print(f"\n[LOAD] Reading CSV from GitHub...")

        try:
            # Download from GitHub
            response = self._get_with_retries(self.csv_path)
            if response.status_code != 200:
                print(f"   Error: {response.status_code}")
                return False

            # Parse CSV from response - auto-detect the delimiter (Peter
            # sometimes uploads a manual backup CSV built from a spreadsheet
            # export, which typically uses commas, unlike Bol.com's own
            # semicolon-delimited export) so both work without him having to
            # get the exact format right.
            sample = response.text[:2000]
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=';,').delimiter
            except csv.Error:
                delimiter = ';'

            lines = response.text.split('\n')
            reader = csv.DictReader(lines, delimiter=delimiter)

            for row in reader:
                try:
                    ean = (row.get('EAN') or row.get('ean') or '').strip()
                    if not ean:
                        continue

                    product_name = (row.get('Productnaam') or row.get('productnaam') or '')[:50]

                    self.products[ean] = {
                        'ean': ean,
                        'name': product_name,
                        'current_price': None,
                        'has_buybox': False,
                        'last_check': None
                    }
                except:
                    pass

            print(f"   Loaded {len(self.products)} products")
            return True
        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_bliving_feed(self):
        """Download B-Living XML feed and extract klantprijzen + titles."""
        print(f"\n[FEED] Downloading B-Living feed...")

        feed_url = "https://www.b-living.eu/feeds/product-feed-15003253-bbed70ea1f95308232732fe3b662e36f2fab51359cce3fc9ff7e33cac2ef9b07.xml"

        try:
            response = self._get_with_retries(feed_url)
            if response.status_code != 200:
                print(f"   Error: {response.status_code}")
                return False

            root = ET.fromstring(response.content)

            for product in root.findall('product'):
                try:
                    ean = product.findtext('ean', '').strip()
                    klantprijs_text = product.findtext('klantprijs', '0').strip()
                    klantprijs = float(klantprijs_text)

                    self.bliving_klantprijzen[ean] = klantprijs
                    self.bliving_titels[ean] = (product.findtext('titel', '') or '').strip()
                except:
                    pass

            print(f"   Loaded {len(self.bliving_klantprijzen)} klantprijzen from B-Living")
            return True
        except Exception as e:
            print(f"   Error: {e}")
            return False

    def is_excluded_from_big_steps(self, ean: str) -> bool:
        """
        2Lif and Sun Arts vliegengordijnen never get the aggressive big-step
        reduction, even when the price gap to a competitor is large. Peter's
        purchase cost on these specific items is too high to ever compete on
        price against the dropshipping competitor that targets them - jumping
        toward the price floor in big steps would just burn margin for
        nothing, since the buybox was never winnable there in the first place.
        """
        titel = self.bliving_titels.get(ean, '')
        return 'vliegengordijn' in titel.lower()

    def calculate_normal_price(self, klantprijs: float) -> float:
        """Calculate normal price using Channable formula for this account."""
        if klantprijs < 10:
            # (klantprijs + 1) × 2.6 + 8.5
            return round(((klantprijs + 1) * 2.6) + 8.5, 2)
        else:
            # klantprijs × 2.6 + 8.5
            return round((klantprijs * 2.6) + 8.5, 2)

    def calculate_minimum_price(self, klantprijs: float) -> float:
        """Calculate minimum price (klantprijs × 2.1 + 8.5).

        Higher multiplier than the NL account (1.9): cross-border shipping to
        Belgium costs more and BE customers return more often.
        """
        return round((klantprijs * 2.1) + 8.5, 2)

    def calculate_klantprijs_for_target_price(self, target_price: float) -> float:
        """
        Calculate the klantprijs needed to make Channable produce target_price
        as the selling price.

        Channable uses:
          if klantprijs < 10: price = (klantprijs + 1) * 2.6 + 8.5
          else: price = klantprijs * 2.6 + 8.5

        We solve for klantprijs directly from the DESIRED target_price
        (not from a "reduction relative to the original price" - that was
        a bug, since it ignored all previous iterations and always reset
        back to "original price - 0.50").
        """
        # Try the >= 10 branch first (most products fall here)
        candidate = (target_price - 8.5) / 2.6
        if candidate >= 10:
            return round(max(candidate, 0), 2)

        # Otherwise use the < 10 branch
        candidate_low = ((target_price - 8.5) / 2.6) - 1
        return round(max(candidate_low, 0), 2)

    def generate_reprice_xml(self, output_path: str, adjustments: dict) -> bool:
        """
        Generate XML for Channable import.

        Adjustments dict contains EAN -> NEW_KLANTPRIJS
        Channable will recalculate selling price using its formula
        """
        print(f"\n[XML] Generating repricing XML...")

        try:
            # Download original B-Living feed
            feed_url = "https://www.b-living.eu/feeds/product-feed-15003253-bbed70ea1f95308232732fe3b662e36f2fab51359cce3fc9ff7e33cac2ef9b07.xml"
            response = requests.get(feed_url, timeout=30)
            root = ET.fromstring(response.content)

            # Modify klantprijs for adjusted articles
            for product in root.findall('product'):
                ean = product.findtext('ean', '').strip()

                if ean in adjustments:
                    # adjustments[ean] is NEW KLANTPRIJS
                    klantprijs_elem = product.find('klantprijs')
                    if klantprijs_elem is not None:
                        klantprijs_elem.text = f"{adjustments[ean]:.2f}"

            # Write XML
            tree = ET.ElementTree(root)
            tree.write(output_path, encoding='utf-8', xml_declaration=True)

            print(f"   Generated: {output_path}")
            print(f"   Articles adjusted: {len(adjustments)}")
            return True
        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def upload_to_github(self, file_path: str, github_filename: str = "repricing_current.xml") -> bool:
        """
        Upload file to GitHub repo via Contents API using a Personal Access Token.
        Always overwrites the SAME filename, so the Channable import URL never changes.
        """
        print(f"\n[GITHUB] Uploading {github_filename}...")

        github_token = os.getenv("GITHUB_TOKEN")
        github_repo = os.getenv("GITHUB_REPO")

        if not github_token or not github_repo:
            print("   Error: GITHUB_TOKEN or GITHUB_REPO not set in .env")
            return False

        api_url = f"https://api.github.com/repos/{github_repo}/contents/{github_filename}"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        try:
            with open(file_path, 'rb') as f:
                content_b64 = base64.b64encode(f.read()).decode('utf-8')

            # Get existing file's SHA (required by GitHub API to update a file)
            sha = None
            get_response = requests.get(api_url, headers=headers, timeout=15)
            if get_response.status_code == 200:
                sha = get_response.json().get('sha')

            payload = {
                "message": f"Update repricing feed {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "content": content_b64
            }
            if sha:
                payload["sha"] = sha

            put_response = requests.put(api_url, headers=headers, json=payload, timeout=30)

            if put_response.status_code in (200, 201):
                print(f"   Uploaded successfully!")
                return True
            else:
                print(f"   Error {put_response.status_code}: {put_response.text[:300]}")
                return False
        except Exception as e:
            print(f"   Error: {e}")
            return False

    def upload_json_to_github(self, data: dict, github_filename: str) -> bool:
        """Upload a small JSON state file to GitHub (used to remember progress between runs)."""
        content_b64 = base64.b64encode(json.dumps(data, indent=2).encode('utf-8')).decode('utf-8')

        github_token = os.getenv("GITHUB_TOKEN")
        github_repo = os.getenv("GITHUB_REPO")
        if not github_token or not github_repo:
            print("   Error: GITHUB_TOKEN or GITHUB_REPO not set in .env")
            return False

        api_url = f"https://api.github.com/repos/{github_repo}/contents/{github_filename}"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        try:
            sha = None
            get_response = requests.get(api_url, headers=headers, timeout=15)
            if get_response.status_code == 200:
                sha = get_response.json().get('sha')

            payload = {
                "message": f"Update {github_filename} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "content": content_b64
            }
            if sha:
                payload["sha"] = sha

            put_response = requests.put(api_url, headers=headers, json=payload, timeout=30)
            return put_response.status_code in (200, 201)
        except Exception as e:
            print(f"   Error uploading {github_filename}: {e}")
            return False

    def load_last_published_klantprijzen(self) -> dict:
        """
        Fetch the currently-published repricing_current.xml from GitHub and
        extract the klantprijs that was last used per EAN. This lets a fresh,
        stateless run (e.g. a GitHub Actions run with no memory of previous
        runs) continue reducing prices from where the last run left off.
        """
        url = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/repricing_current.xml"
        result = {}
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                return result
            root = ET.fromstring(r.content)
            for product in root.findall('product'):
                ean = product.findtext('ean', '').strip()
                kp_text = product.findtext('klantprijs', '').strip()
                if ean and kp_text:
                    try:
                        result[ean] = float(kp_text)
                    except ValueError:
                        pass
        except Exception as e:
            print(f"   [WARN] Could not load last published klantprijzen: {e}")
        return result

    def load_big_gap(self) -> dict:
        """
        Fetch big_gap.json from GitHub: {ean: remaining_big_steps}.

        EANs in here are far more expensive than the current buybox winner
        (>= EUR10 detected during a periodic local check). While present in
        this file, they are exempt from the daily reset - they keep
        continuing from their last published price, day after day, instead
        of snapping back to the fresh normal price every morning (which
        would erase all progress before ever reaching the competitor).
        remaining_big_steps > 0 -> take EUR10 steps; == 0 -> fine EUR0.50
        steps, but still exempt from the daily reset until a local check
        removes the EAN (because it won the buybox, or the gap has closed).
        """
        url = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/big_gap.json"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def load_state(self) -> dict:
        """Fetch state.json from GitHub (tracks the date of the last repricing run)."""
        url = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/state.json"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def load_master_tracked(self) -> list:
        """
        Fetch master_tracked.json from GitHub: every EAN that has EVER
        appeared in a daily "no buybox" CSV, ever-growing, never shrinking
        on its own.

        Why this exists: Peter's daily CSV export is Bol.com's own
        buybox-status snapshot at ONE moment. Buybox can flip back and
        forth during the day (seen live: a EUR0.95 gap flipping status
        multiple times across consecutive days). Previously, an EAN that
        was actively being reduced yesterday but simply happened to be
        absent from TODAY's fresh CSV (because it looked "won" at that one
        export moment) would silently fall out of `adjustments` entirely -
        no longer frozen (never confirmed as a real win), no longer in
        today's CSV, no longer in big_gap - and revert straight back to the
        full undiscounted price with zero tracking, undoing all progress.
        (Found and confirmed live for EAN 8716522107326 on 19 July - it was
        in the CSV on 18 July, absent on 19 July despite still lacking the
        buybox with only a EUR0.95 gap.)

        Fix: once an EAN is EVER seen in any day's CSV, it stays in this
        master list and keeps being actively reduced regardless of whether
        later daily CSVs include it - UNTIL a local buybox check actually
        CONFIRMS a win (moves it to frozen.json, which is the only proper
        way an EAN should leave active tracking).
        """
        url = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/master_tracked.json"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def audit_tracking_consistency(self, adjustments: dict, frozen: dict, big_gap: dict,
                                    master_tracked: set) -> list:
        """
        Automatic daily/every-run consistency audit (Peter's request, 19 July,
        after having to manually discover a silent-tracking-loss bug himself -
        this exists so that class of bug gets caught by the tool itself from
        now on, not by him noticing a stuck price).

        Takes the values already computed this run (rather than re-fetching
        frozen/big_gap/master_tracked/adjustments fresh from GitHub) - partly
        for efficiency, but mainly because raw.githubusercontent.com has a
        few minutes of CDN lag after an upload, which caused confusing
        false-stale-reads during testing earlier this project. Using the
        in-memory values this run already computed avoids that entirely.

        Checks:
          1. No EAN should be in BOTH frozen.json and big_gap.json at once
             (they're meant to be mutually exclusive states).
          2. No EAN should currently have a REDUCED (non-full) klantprijs
             while being absent from every tracking list
             (master_tracked/frozen/big_gap) - that exact pattern is what a
             silent tracking-loss bug looks like (the bug that hit EAN
             8716522107326 on 19 July).

        Returns a list of human-readable issue strings (empty if all clear).
        Also uploads the report to audit_report.json on GitHub so Peter or a
        future session can see the history of what was found each run.
        """
        issues = []

        overlap = set(frozen.keys()) & set(big_gap.keys())
        if overlap:
            issues.append(f"CONFLICT: {len(overlap)} EAN(s) in BOTH frozen.json and "
                           f"big_gap.json: {sorted(overlap)}")

        all_tracked = master_tracked | set(frozen.keys()) | set(big_gap.keys())
        untracked_reductions = []
        for ean, kp in adjustments.items():
            if ean not in self.bliving_klantprijzen:
                continue
            fresh_kp = self.bliving_klantprijzen[ean]
            if kp < fresh_kp - 0.01 and ean not in all_tracked:
                untracked_reductions.append(ean)
        if untracked_reductions:
            issues.append(f"UNTRACKED REDUCTION: {len(untracked_reductions)} EAN(s) have a "
                           f"reduced price but aren't in master_tracked/frozen/big_gap - "
                           f"this is the exact silent-tracking-loss pattern found on 19 July: "
                           f"{sorted(untracked_reductions)}")

        from datetime import datetime as _dt
        report = {
            "checked_at": _dt.now().isoformat(),
            "issues_found": len(issues),
            "issues": issues,
        }
        self.upload_json_to_github(report, "audit_report.json")

        if issues:
            print(f"\n[AUDIT] {len(issues)} issue(s) found:")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print(f"\n[AUDIT] No consistency issues found")

        return issues

    def load_frozen_eans(self) -> dict:
        """
        Fetch frozen.json from GitHub: {ean: klantprijs} for EANs that have
        been confirmed (via a manual/local buybox check, since the automated
        cloud job can't check live buybox status - bol.com blocks datacenter
        IPs) to have already won the buybox. These are held at their current
        klantprijs indefinitely - never reduced further, never bumped back up
        (bumping up could immediately lose the buybox again).
        """
        url = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/frozen.json"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def check_buybox(self, ean: str, session: requests.Session, seller_name: str = "Dreamhouse&Garden") -> dict:
        """
        Check the LIVE buybox status for one EAN by reading Bol.com's own
        public product page (no API key needed - just the structured
        schema.org JSON-LD data that's on every product page for SEO).

        1. Search bol.com for the EAN to find the product page URL.
        2. Fetch that product page and parse its JSON-LD blocks.
        3. Find the variant matching this EAN (gtin13) and read its
           offers.seller.name - that's whoever currently "wins" the buybox.

        Returns: {'found': bool, 'has_buybox': bool, 'price': float, 'seller': str}
        or {'found': False, 'error': '...'} if anything didn't resolve.
        """
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        try:
            search_r = session.get(f"https://www.bol.com/be/nl/s/?searchtext={ean}", headers=headers, timeout=15)
            if search_r.status_code != 200:
                return {"found": False, "error": f"search status {search_r.status_code}"}

            urls = re.findall(r'"(/be/nl/p/[^"]+)"', search_r.text)
            if not urls:
                return {"found": False, "error": "no product url in search results"}
            product_url = "https://www.bol.com" + urls[0]

            product_r = session.get(product_url, headers=headers, timeout=15)
            if product_r.status_code != 200:
                return {"found": False, "error": f"product page status {product_r.status_code}"}

            blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', product_r.text, re.DOTALL)
            for block in blocks:
                try:
                    data = json.loads(block)
                except Exception:
                    continue
                candidates = data.get("hasVariant", [data]) if isinstance(data, dict) else []
                for c in candidates:
                    if c.get("gtin13") == ean:
                        offers = c.get("offers", {})
                        seller = offers.get("seller", {}).get("name", "")
                        return {
                            "found": True,
                            "price": offers.get("price"),
                            "seller": seller,
                            "has_buybox": seller.lower() == seller_name.lower(),
                        }
            return {"found": False, "error": "ean not found in JSON-LD"}
        except Exception as e:
            return {"found": False, "error": str(e)}

    def run_single_iteration_stateless(self, check_buybox_live: bool = True) -> tuple:
        """
        Stateless version of run_iteration, meant to be triggered by an external
        scheduler (e.g. GitHub Actions cron) where no Python process stays running
        and no in-memory state survives between runs.

        Instead of tracking 'current_price' in memory, it reads the klantprijs
        values from the LAST PUBLISHED repricing_current.xml as the starting
        point for one more €0.50 reduction step. If it's a new calendar day
        (tracked via state.json), it resets to the fresh B-Living klantprijs
        instead of continuing yesterday's reduced prices.

        If check_buybox_live is True, each EAN's actual buybox status is checked
        against Bol.com's public product page before deciding what to do:
          - Has buybox already -> HOLD the current price (don't reduce further,
            and don't bump back up either - jumping back to the normal price
            could immediately lose the buybox again to whoever is still low).
          - Does not have buybox -> reduce by another €0.50 as before.

        Returns: (adjustments dict EAN->new_klantprijs, new_state dict, buybox_won list)
        """
        from datetime import date
        today_str = date.today().isoformat()

        state = self.load_state()
        is_new_day = state.get('date') != today_str

        # Always load last_published (not just when continuing within the
        # same day) - big-gap EANs need their last position regardless of
        # day, since they're exempt from the daily reset (see big_gap below).
        last_published = self.load_last_published_klantprijzen()
        frozen = self.load_frozen_eans()
        big_gap = self.load_big_gap()
        master_tracked = set(self.load_master_tracked())

        # Auto-unfreeze: if a frozen EAN reappears in today's "no buybox" CSV,
        # that's bol.com's OWN data telling us we lost the buybox again - no
        # live scraping needed to know this. Resume reducing it from its
        # frozen (held) price rather than jumping back to the full price.
        lost_via_csv = set(frozen.keys()) & set(self.products.keys())
        for ean in lost_via_csv:
            last_published[ean] = frozen.pop(ean)
        if lost_via_csv:
            print(f"[STATELESS] Auto-unfroze {len(lost_via_csv)} EAN(s) that reappeared "
                  f"in today's CSV (lost buybox again): {sorted(lost_via_csv)}")
            self.upload_json_to_github(frozen, "frozen.json")

        # Grow master_tracked with today's CSV + anything just auto-unfrozen.
        # This list only ever grows (until an EAN is CONFIRMED won via
        # frozen.json) - an EAN dropping out of a single day's CSV is not
        # reliable proof of a win (bol.com's own buybox status can flip
        # within a day), so we never let that alone erase active tracking.
        new_master_tracked = master_tracked | set(self.products.keys()) | lost_via_csv
        if new_master_tracked != master_tracked:
            self.upload_json_to_github(sorted(new_master_tracked), "master_tracked.json")
        master_tracked = new_master_tracked

        print(f"\n[STATELESS] New day reset: {is_new_day} (last state date: {state.get('date')})")
        print(f"[STATELESS] Frozen (buybox already won) EANs: {len(frozen)}")
        print(f"[STATELESS] Big-gap (>=EUR10 behind, exempt from daily reset) EANs: {len(big_gap)}")
        print(f"[STATELESS] Master-tracked (ever seen in a CSV) EANs: {len(master_tracked)}")

        session = requests.Session()

        adjustments = {}
        at_minimum = 0
        buybox_won = []
        buybox_checks_failed = 0

        # Frozen, big-gap, AND master-tracked EANs must all be processed even
        # if they've dropped out of today's CSV (expected - once an EAN wins
        # the buybox, or is deep into a big-gap recovery, or bol.com's own
        # snapshot just happened to miss it that one day, Peter's daily
        # "no buybox" export doesn't necessarily still include it). Without
        # this union, those EANs would silently disappear from `adjustments`,
        # and the next XML generation would revert them to the fresh,
        # undiscounted B-Living price - undoing all progress. (This bug
        # actually happened twice: to EAN 8716522110005 on 1 July - fixed by
        # adding frozen to the union - and to EAN 8716522107326 on 19 July,
        # which was never frozen at all, just a plain active EAN that
        # vanished from one day's CSV - fixed by adding master_tracked.)
        all_eans = master_tracked | set(self.products.keys()) | set(frozen.keys()) | set(big_gap.keys())

        big_gap_steps_taken = 0

        for i, ean in enumerate(all_eans):
            if ean not in self.bliving_klantprijzen:
                continue

            # Frozen: confirmed buybox winner (via manual/local check) - hold steady, skip everything else
            if ean in frozen:
                adjustments[ean] = frozen[ean]
                buybox_won.append(ean)
                continue

            original_klantprijs = self.bliving_klantprijzen[ean]
            minimum_price = self.calculate_minimum_price(original_klantprijs)

            in_big_gap = ean in big_gap
            if in_big_gap:
                # Exempt from the daily reset - always continue from wherever
                # it was last, big-step or fine-step, day after day, until a
                # local check wins it (-> frozen) or removes it (gap closed).
                baseline_klantprijs = last_published.get(ean, original_klantprijs)
                step = 10.0 if big_gap[ean] > 0 else 0.50
                if big_gap[ean] > 0:
                    big_gap[ean] -= 1
                    big_gap_steps_taken += 1
            else:
                # Normal EAN: continue within the day, or reset fresh on a new day
                baseline_klantprijs = original_klantprijs if is_new_day else last_published.get(ean, original_klantprijs)
                step = 0.50

            has_buybox = False
            if check_buybox_live:
                result = self.check_buybox(ean, session)
                if result.get("found"):
                    has_buybox = result.get("has_buybox", False)
                    if has_buybox:
                        buybox_won.append(ean)
                else:
                    buybox_checks_failed += 1
                    if buybox_checks_failed <= 3:
                        print(f"   [DEBUG] Buybox check failed for {ean}: {result.get('error')}")
                time.sleep(0.3)  # be polite to bol.com, avoid hammering their servers

            if has_buybox:
                # Already winning - hold the price steady, don't reduce further
                # (and don't jump back up, that could lose the buybox again)
                adjustments[ean] = baseline_klantprijs
                continue

            current_selling_price = self.calculate_normal_price(baseline_klantprijs)
            new_selling_price = current_selling_price - step
            if new_selling_price < minimum_price:
                new_selling_price = minimum_price
                at_minimum += 1

            adjustments[ean] = self.calculate_klantprijs_for_target_price(new_selling_price)

        if big_gap_steps_taken:
            print(f"Big-gap EUR10 steps taken this run: {big_gap_steps_taken}")
        self.upload_json_to_github(big_gap, "big_gap.json")

        print(f"Adjustments: {len(adjustments)} articles")
        print(f"At minimum price: {at_minimum} articles")
        if check_buybox_live:
            print(f"Buybox already won (held steady): {len(buybox_won)} articles")
            print(f"Buybox check failed (treated as not-won): {buybox_checks_failed} articles")

        self.audit_tracking_consistency(adjustments, frozen, big_gap, master_tracked)

        new_state = {"date": today_str}
        return adjustments, new_state, buybox_won

    def match_competitor_prices(self, undercut: float = 0.02) -> dict:
        """
        Morning fast-start (Peter's proposal, 19 July): instead of grinding
        down from the full price by EUR0.50/EUR10 steps over many hours,
        immediately match (just barely undercut) whoever currently holds the
        buybox for every active EAN, the moment a fresh CSV is uploaded.
        Peter's estimate: this alone should win the buybox on ~80% of
        articles immediately, since price was often the only disadvantage.

        Must run from a residential connection (same limitation as all
        buybox-checking) - not usable from the GitHub Actions cloud job.
        Meant to be run once each morning, right after Peter uploads a fresh
        CSV, before/instead of the regular hourly cloud iteration for that
        first cycle. The regular hourly automation then continues normally
        from wherever this leaves things (EUR0.50 fine-tuning for anything
        that still doesn't win even at the matched price, capped by the
        same minimum-price floor as always - never goes below it).

        Also covers EANs already in big_gap.json - matching directly can
        resolve a large gap in one shot instead of needing several EUR10
        steps, so those are checked here too and removed from big_gap.json
        if resolved.

        Returns a dict with counts: {'matched': int, 'already_won': int,
        'at_minimum': int, 'failed': int}.
        """
        frozen = self.load_frozen_eans()
        big_gap = self.load_big_gap()
        master_tracked = set(self.load_master_tracked())

        candidates = (set(self.products.keys()) | big_gap.keys() | master_tracked) - set(frozen.keys())
        candidates = {ean for ean in candidates if ean in self.bliving_klantprijzen}

        session = requests.Session()
        adjustments = {}
        newly_won = {}
        at_minimum = 0
        failed = 0

        print(f"\n[MATCH] Checking {len(candidates)} active EAN(s) for immediate price-matching...")

        for i, ean in enumerate(candidates):
            result = self.check_buybox(ean, session)
            if not result.get("found"):
                failed += 1
                time.sleep(0.3)
                continue

            if result.get("has_buybox"):
                # Already winning right now - freeze it instead of matching
                price = float(result.get("price"))
                newly_won[ean] = self.calculate_klantprijs_for_target_price(price)
                big_gap.pop(ean, None)
                time.sleep(0.3)
                continue

            competitor_price = float(result.get("price"))
            fresh_kp = self.bliving_klantprijzen[ean]
            minimum_price = self.calculate_minimum_price(fresh_kp)

            target_price = competitor_price - undercut
            if target_price < minimum_price:
                target_price = minimum_price
                at_minimum += 1

            adjustments[ean] = self.calculate_klantprijs_for_target_price(target_price)
            big_gap.pop(ean, None)  # resolved directly, no need for step-based tracking anymore
            time.sleep(0.3)

            if (i + 1) % 50 == 0:
                print(f"   {i+1}/{len(candidates)} checked...")

        # Frozen EANs still need to be included so the XML holds their price too
        for ean, kp in frozen.items():
            adjustments[ean] = kp

        output_dir = Path(__file__).resolve().parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        xml_path = str(output_dir / "repricing_current.xml")
        self.generate_reprice_xml(xml_path, adjustments)
        self.upload_to_github(xml_path, "repricing_current.xml")

        if newly_won:
            frozen.update(newly_won)
            self.upload_json_to_github(frozen, "frozen.json")

        self.upload_json_to_github(big_gap, "big_gap.json")

        from datetime import date
        self.upload_json_to_github({"date": date.today().isoformat()}, "state.json")

        print(f"\n[MATCH] Matched (undercut competitor): {len(adjustments) - len(frozen)}")
        print(f"[MATCH] Already winning (frozen now): {len(newly_won)}")
        print(f"[MATCH] Hit minimum price floor: {at_minimum}")
        print(f"[MATCH] Check failed: {failed}")

        return {
            "matched": len(adjustments) - len(frozen),
            "already_won": len(newly_won),
            "at_minimum": at_minimum,
            "failed": failed,
        }

    def run_iteration(self, iteration: int) -> dict:
        """
        Run one iteration of repricing.

        For each article without buybox: reduce SELLING PRICE by €0.50
        Never go below minimum (× 2.1 + 8.5)

        Returns: dict of EAN -> NEW_KLANTPRIJS (for XML, Channable will recalculate)
        """
        print(f"\n{'='*70}")
        print(f"ITERATION {iteration} - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*70}")

        adjustments = {}
        articles_to_adjust = 0
        at_minimum = 0

        for ean, product in self.products.items():
            if ean not in self.bliving_klantprijzen:
                continue

            klantprijs = self.bliving_klantprijzen[ean]
            normal_price = self.calculate_normal_price(klantprijs)
            minimum_price = self.calculate_minimum_price(klantprijs)

            # All articles in this list don't have buybox
            has_buybox = False

            if not has_buybox:
                # Calculate new SELLING PRICE: current - €0.50
                current_price = product.get('current_price') or normal_price
                new_selling_price = current_price - 0.50

                # Check minimum
                if new_selling_price < minimum_price:
                    new_selling_price = minimum_price
                    action = "AT_MINIMUM"
                    at_minimum += 1
                else:
                    action = "REDUCED"

                # INVERSE: calculate new klantprijs that produces this selling price
                new_klantprijs = self.calculate_klantprijs_for_target_price(new_selling_price)

                # Store NEW KLANTPRIJS for XML (Channable will recalculate price)
                adjustments[ean] = new_klantprijs

                product['current_price'] = new_selling_price
                articles_to_adjust += 1

                if articles_to_adjust <= 5:  # Show first 5
                    print(f"  {ean}: €{current_price:.2f} → €{new_selling_price:.2f} (klantprijs: {klantprijs:.2f} → {new_klantprijs:.2f})")

        print(f"\nAdjustments: {articles_to_adjust} articles")
        print(f"At minimum price: {at_minimum} articles")

        return adjustments

    def run_repricing_loop(self, max_iterations: int = 999):
        """
        Main loop: run repricing iterations until buybox or manual stop.

        Between iterations: wait 5 minutes (Bol.com processing time)
        """
        print("\n" + "="*70)
        print("FASE 2: REPRICING LOOP (Kat-en-Muis Spel)")
        print("="*70)
        print("\nInstructions:")
        print("  1. Each iteration generates an XML file")
        print("  2. Upload XML to GitHub")
        print("  3. Import in Channable (via GitHub raw URL)")
        print("  4. Wait 5 minutes for Bol.com to process")
        print("  5. Next iteration runs automatically")
        print("  6. Press Ctrl+C to stop")
        print("="*70)

        iteration = 0

        try:
            while iteration < max_iterations:
                iteration += 1

                # Generate adjustments
                adjustments = self.run_iteration(iteration)

                # Generate XML (always same local filename - no local clutter either)
                xml_path = "C:\\Users\\Avantius\\Documents\\bol-repricing-be\\output\\repricing_current.xml"

                # Create output dir if needed
                Path("C:\\Users\\Avantius\\Documents\\bol-repricing-be\\output").mkdir(exist_ok=True)

                self.generate_reprice_xml(xml_path, adjustments)

                # Auto-upload to GitHub (always same filename, Channable URL never changes)
                self.upload_to_github(xml_path, "repricing_current.xml")

                print(f"\n✓ XML ready: repricing_current.xml (iteration {iteration})")
                print(f"✓ Uploaded to GitHub as repricing_current.xml")
                print(f"✓ Next iteration in 80 minutes (1h 20m)...")
                print(f"\nWaiting... (press Ctrl+C to stop)")

                # Wait 80 minutes (1 hour 20 minutes = 4800 seconds)
                time.sleep(4800)  # 80 minutes

        except KeyboardInterrupt:
            print(f"\n\n[STOP] Repricing loop stopped by user")
            print(f"Total iterations: {iteration}")
            return True

        return True

if __name__ == "__main__":
    # GitHub raw URL for daily CSV (always the same filename - Peter overwrites this file each morning)
    csv_url = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/bolcom_productinformatie.csv"

    engine = RepricingEngine(csv_url)

    if not engine.products:
        print("\n[ERROR] No products loaded from CSV")
        sys.exit(1)

    if not engine.bliving_klantprijzen:
        print("\n[ERROR] No klantprijzen loaded from B-Living feed")
        sys.exit(1)

    # Count matching products
    matching = sum(1 for ean in engine.products if ean in engine.bliving_klantprijzen)

    print(f"\n[INFO] Loaded {len(engine.products)} products from CSV")
    print(f"[INFO] Loaded {len(engine.bliving_klantprijzen)} klantprijzen from B-Living")
    print(f"[INFO] Matching products: {matching}")

    # START REAL LOOP!
    print(f"\n[GO!] Starting repricing loop...")
    print(f"Iterations every 2 minutes until buybox or manual stop (Ctrl+C)")
    engine.run_repricing_loop()
