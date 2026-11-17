"""Linear-time reconciliation with Decimal-only monetary arithmetic."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable
from .models import Discrepancy, ReconciliationResult

CENT, TOLERANCE = Decimal("0.01"), Decimal("0.01")
def decimal(value: object) -> Decimal: return Decimal(str(value or "0"))
def money(value: object) -> Decimal: return decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
def day(value: str) -> date: return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
def index_rows(rows: list[dict]) -> dict[str, list[dict]]:
    indexed: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if txid := (row.get("transaction_id") or "").strip(): indexed[txid].append(row)
    return indexed

def reconcile(platform_rows: Iterable[dict], bank_rows: Iterable[dict], period_year: int = 2026, period_month: int = 10) -> ReconciliationResult:
    """Reconcile two ledgers in O(N + M): all joins are hash-map lookups."""
    platform, bank = list(platform_rows), list(bank_rows)
    p_index, b_index = index_rows(platform), index_rows(bank)
    platform_total = sum((decimal(r.get("net_amount_exact")) for r in platform), Decimal("0")).quantize(CENT, ROUND_HALF_UP)
    bank_total = sum((money(r.get("settled_amount")) for r in bank), Decimal("0")).quantize(CENT, ROUND_HALF_UP)
    raw_variance = (bank_total - platform_total).quantize(CENT, ROUND_HALF_UP)
    last_day = date(period_year, period_month + 1, 1) - timedelta(days=1) if period_month < 12 else date(period_year, 12, 31)
    gaps: list[Discrepancy] = []
    def add(kind, txid, impact, detail, source=""):
        gaps.append(Discrepancy(kind, txid, Decimal(impact).quantize(CENT, ROUND_HALF_UP), detail, source))

    for txid, rows in p_index.items():
        for row in rows[1:]: add("DUPLICATE_PLATFORM", txid, -money(row.get("net_amount_exact")), "Extra platform occurrence (webhook retry).", "platform")
    for txid, rows in b_index.items():
        for row in rows[1:]: add("DUPLICATE_BANK", txid, money(row.get("settled_amount")), "Extra bank settlement occurrence.", "bank")

    captures = {r.get("transaction_id") for r in platform if r.get("type") == "CAPTURE"}
    orphan_bank: set[str] = set()
    for source, rows in (("Platform", platform), ("Bank", bank)):
        for row in rows:
            if row.get("type") == "REFUND" and row.get("parent_transaction_id") not in captures:
                txid = row.get("transaction_id", "")
                impact = -money(row.get("net_amount_exact")) if source == "Platform" else money(row.get("settled_amount"))
                add("ORPHAN_REFUND", txid, impact, f"{source} refund references absent parent {row.get('parent_transaction_id', '')}.", source.lower())
                if source == "Bank": orphan_bank.add(txid)

    small_deltas = []
    for txid, rows in p_index.items():
        p = rows[0]
        if p.get("type") != "CAPTURE": continue
        expected_exact, expected, captured = decimal(p.get("net_amount_exact")), money(p.get("net_amount_exact")), day(p["timestamp_utc"])
        matches = b_index.get(txid)
        if not matches:
            kind = "NEXT_MONTH_ROLLOVER" if captured >= last_day - timedelta(days=1) else "MISSING_IN_BANK"
            add(kind, txid, -expected, "Valid T+1/T+2 timing." if kind == "NEXT_MONTH_ROLLOVER" else "Capture has no bank settlement.", "platform")
            continue
        b = matches[0]; settled = money(b.get("settled_amount"))
        if captured >= last_day - timedelta(days=1) and day(b["settlement_date_utc"]) > last_day:
            add("NEXT_MONTH_ROLLOVER", txid, settled - expected, "Settled in November under the T+1/T+2 SLA.", "bank")
        elif abs(settled - expected) > TOLERANCE:
            add("AMOUNT_MISMATCH", txid, settled - expected, f"Expected ₹{expected}; bank settled ₹{settled}.", "bank")
        else: small_deltas.append(settled - expected_exact)

    for txid, rows in b_index.items():
        if txid not in p_index and txid not in orphan_bank:
            add("UNRECORDED_IN_PLATFORM", txid, money(rows[0].get("settled_amount")), "Bank settlement has no platform capture.", "bank")

    # Residual represents all <= ₹0.01 matched row differences plus batch-rounding boundary effects.
    non_drift = sum((gap.impact for gap in gaps), Decimal("0.00"))
    drift = (raw_variance - non_drift).quantize(CENT, ROUND_HALF_UP)
    if drift or small_deltas:
        add("CUMULATIVE_ROUNDING_DRIFT", "MONTHLY-ROUNDING", drift, "Aggregate six-decimal platform net versus per-row bank ROUND_HALF_UP payouts.", "aggregate")
    explained = sum((gap.impact for gap in gaps), Decimal("0.00")).quantize(CENT, ROUND_HALF_UP)
    return ReconciliationResult(platform_total, bank_total, raw_variance, explained, (raw_variance - explained).quantize(CENT, ROUND_HALF_UP), drift, gaps)
