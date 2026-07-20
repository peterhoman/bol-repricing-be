#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Morning fast-start: match (slightly undercut) whoever currently holds the
buybox for every active EAN, right after a fresh CSV is uploaded - instead
of waiting hours for the normal EUR0.50/EUR10 grind to close the gap.

Must run from a residential connection (bol.com blocks buybox checks from
cloud/datacenter IPs) - run this manually each morning after uploading the
day's CSV, before/instead of the first regular cloud cycle.

Usage:
    python src/match_prices.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase2_repricing import RepricingEngine

from dotenv import load_dotenv
load_dotenv()

CSV_URL = "https://raw.githubusercontent.com/peterhoman/bol-repricing-be/main/bolcom_productinformatie.csv"

if __name__ == "__main__":
    engine = RepricingEngine(CSV_URL)

    if not engine.products:
        print("\n[ERROR] No products loaded from CSV")
        sys.exit(1)

    engine.match_competitor_prices()
