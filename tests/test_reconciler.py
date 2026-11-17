import csv
import subprocess
import sys
import time
from pathlib import Path

from app.reconciler import reconcile

ROOT = Path(__file__).parents[1]

def rows(name):
    with (ROOT / "data" / name).open(encoding="utf-8") as f: return list(csv.DictReader(f))

def test_planted_cases_and_balance_proof():
    subprocess.run([sys.executable, "data/generate_data.py"], cwd=ROOT, check=True, capture_output=True)
    result = reconcile(rows("platform_ledger.csv"), rows("bank_settlements.csv"))
    assert result.unexplained_variance == 0
    assert result.counts["Next-month rollover"] == 5
    assert result.counts["Platform duplicate"] == 1
    assert result.counts["Bank duplicate"] == 1
    assert result.counts["Orphan refund"] == 2
    assert result.counts["Missing settlement"] == 1
    assert result.counts["Amount mismatch"] == 1
    assert result.rounding_drift != 0

def test_ten_thousand_rows_under_quarter_second():
    platform, bank = rows("platform_ledger.csv"), rows("bank_settlements.csv")
    platform = (platform * 9)[:10_000]
    bank = (bank * 9)[:10_000]
    started = time.perf_counter(); reconcile(platform, bank); elapsed = time.perf_counter() - started
    assert elapsed < .25
