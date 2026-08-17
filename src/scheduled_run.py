#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper for the Windows Task Scheduler jobs (set up 17 August 2026).

Runs one step of the daily routine, captures everything it printed, and writes
the result to two places:

  logs/automation-YYYY-MM.log   locally, full output, for reading back
  automation_log.json           on GitHub, last 60 runs, compact

The GitHub copy is what matters: it is the only part a fresh chat session can
read without access to this machine, so that's where the morning check looks.

Why a wrapper instead of scheduling the scripts directly: a scheduled task that
fails silently is worse than no scheduled task at all. This records the exit
code and the last lines of output for every run, including crashes, so a failed
night is visible the next morning instead of showing up as "the numbers look
odd".

Usage (called by Task Scheduler, not by hand):
    python src/scheduled_run.py morning|probe_start|probe_check|sync|selftest
"""
import os
import sys
import json
import base64
import subprocess
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

GITHUB_REPO = os.getenv("GITHUB_REPO")
LOG_DIR = BASE / "logs"
MAX_ENTRIES = 60

# Each task is (script, args). Kept here rather than in the scheduled task
# itself so the schedule never has to be re-registered when a command changes.
TASKS = {
    "morning":     ("match_prices.py", []),
    "probe_start": ("probe_recovery.py", ["auto", "15"]),
    "probe_check": ("probe_recovery.py", ["check"]),
    "sync":        ("sync_buybox.py", []),
}


def github_headers():
    return {"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
            "Accept": "application/vnd.github+json"}


def push_log_entry(entry):
    """Append one entry to automation_log.json on GitHub, keeping the last MAX_ENTRIES."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/automation_log.json"
    headers = github_headers()
    try:
        r = requests.get(api_url, headers=headers, timeout=20)
        if r.status_code == 200:
            sha = r.json()["sha"]
            entries = json.loads(base64.b64decode(r.json()["content"]))
            if not isinstance(entries, list):
                entries = []
        else:
            sha, entries = None, []

        entries.append(entry)
        entries = entries[-MAX_ENTRIES:]

        payload = {
            "message": f"Automation log: {entry['task']} {entry['result']}",
            "content": base64.b64encode(
                json.dumps(entries, indent=2).encode("utf-8")).decode("utf-8"),
        }
        if sha:
            payload["sha"] = sha
        put = requests.put(api_url, headers=headers, json=payload, timeout=30)
        return put.status_code in (200, 201)
    except Exception as exc:
        # Never let logging failure mask the actual run - the local log still has it.
        print(f"[LOG] Could not push automation_log.json: {exc}")
        return False


def run(task_name):
    if task_name == "selftest":
        entry = {
            "task": "selftest",
            "started": datetime.now().isoformat(timespec="seconds"),
            "duration_s": 0,
            "exit_code": 0,
            "result": "ok",
            "summary": ["selftest - scheduler reached the script"],
        }
        LOG_DIR.mkdir(exist_ok=True)
        with open(LOG_DIR / f"automation-{datetime.now():%Y-%m}.log", "a", encoding="utf-8") as fh:
            fh.write(f"\n{'='*70}\n{entry['started']}  SELFTEST ok\n")
        push_log_entry(entry)
        print("selftest ok")
        return 0

    if task_name not in TASKS:
        print(f"Unknown task: {task_name}. Choose from: {', '.join(TASKS)}, selftest")
        return 2

    script, args = TASKS[task_name]
    started = datetime.now()
    cmd = [sys.executable, str(BASE / "src" / script)] + args

    try:
        proc = subprocess.run(cmd, cwd=str(BASE), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=45 * 60)
        output = (proc.stdout or "") + (proc.stderr or "")
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        output = "TIMEOUT: script ran longer than 45 minutes and was killed"
        exit_code = -1
    except Exception as exc:
        output = f"CRASH: {exc}"
        exit_code = -2

    duration = int((datetime.now() - started).total_seconds())

    # Keep the lines that actually say something - the [MATCH]/[DONE]/[PROBE]
    # style result lines - so a fresh session can read the outcome without the
    # progress noise.
    interesting = [ln.strip() for ln in output.splitlines()
                   if ln.strip().startswith(("[MATCH]", "[DONE]", "[PROBE]", "[KEPT]",
                                             "[REVERTED]", "[AUTO]", "[ERROR]", "[STOP]",
                                             "[GEWEIGERD]", "[LET OP]", "[AUDIT]",
                                             "[FLOOR]", "[WARN]", "TIMEOUT", "CRASH"))]

    entry = {
        "task": task_name,
        "started": started.isoformat(timespec="seconds"),
        "duration_s": duration,
        "exit_code": exit_code,
        "result": "ok" if exit_code == 0 else "FAILED",
        "summary": interesting[-25:],
    }

    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / f"automation-{started:%Y-%m}.log", "a", encoding="utf-8") as fh:
        fh.write(f"\n{'='*70}\n{entry['started']}  {task_name}  "
                 f"exit={exit_code}  {duration}s\n{'='*70}\n{output}\n")

    push_log_entry(entry)
    print(f"[{task_name}] exit={exit_code} in {duration}s")
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(run(sys.argv[1]))
