#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eenmalig setup-script: uploadt alle projectbestanden naar de (verse) GitHub-repo
via de Contents API - zelfde architectuur als het originele NL-project (geen
lokale git nodig).

Vereist: .env met GITHUB_TOKEN (fine-grained PAT voor deze repo) en
GITHUB_REPO (peterhoman/bol-repricing-be), en een bestaande LEGE public repo.

Gebruik:
    python setup_upload.py
"""
import os
import sys
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

FILES = [
    "README.md",
    "requirements.txt",
    ".gitignore",
    ".env.example",
    ".github/workflows/reprice.yml",
    "src/__init__.py",
    "src/phase2_repricing.py",
    "src/github_action_reprice.py",
    "src/sync_buybox.py",
    "src/probe_recovery.py",
    "src/match_prices.py",
    "bolcom_productinformatie.csv",
    "state.json",
    "frozen.json",
    "big_gap.json",
    "master_tracked.json",
]

def upload(rel_path: str) -> bool:
    local = Path(__file__).resolve().parent / rel_path
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{rel_path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}",
               "Accept": "application/vnd.github+json"}

    content_b64 = base64.b64encode(local.read_bytes()).decode("utf-8")

    sha = None
    get_r = requests.get(api_url, headers=headers, timeout=15)
    if get_r.status_code == 200:
        sha = get_r.json().get("sha")

    payload = {"message": f"Setup: add {rel_path}", "content": content_b64}
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload, timeout=30)
    ok = r.status_code in (200, 201)
    print(f"  {'OK ' if ok else 'FOUT'} {rel_path}" + ("" if ok else f" -> {r.status_code}: {r.text[:200]}"))
    return ok

if __name__ == "__main__":
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("FOUT: GITHUB_TOKEN of GITHUB_REPO ontbreekt in .env")
        sys.exit(1)

    print(f"Uploaden naar {GITHUB_REPO}...")
    failed = [f for f in FILES if not upload(f)]

    if failed:
        print(f"\n{len(failed)} bestand(en) mislukt: {failed}")
        sys.exit(1)
    print(f"\nKlaar - alle {len(FILES)} bestanden staan op GitHub.")
    print("Vaste Channable-URL (verandert nooit meer):")
    print(f"  https://raw.githubusercontent.com/{GITHUB_REPO}/main/repricing_current.xml")
