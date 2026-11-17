"""Typed, Decimal-native result objects for the reconciliation service."""
from dataclasses import dataclass, field
from decimal import Decimal

@dataclass(frozen=True)
class Discrepancy:
    gap_type: str
    transaction_id: str
    impact: Decimal
    detail: str
    source: str = ""
    @property
    def category(self) -> str: return self.gap_type
    @property
    def amount(self) -> Decimal: return self.impact

@dataclass
class ReconciliationResult:
    platform_total_net: Decimal
    bank_total_settled: Decimal
    raw_variance: Decimal
    explained_variance: Decimal
    unexplained_variance: Decimal
    cumulative_rounding_drift: Decimal
    discrepancies: list[Discrepancy] = field(default_factory=list)
    @property
    def platform_net_total(self) -> Decimal: return self.platform_total_net
    @property
    def bank_settled_total(self) -> Decimal: return self.bank_total_settled
    @property
    def adjustments(self) -> Decimal: return self.explained_variance
    @property
    def rounding_drift(self) -> Decimal: return self.cumulative_rounding_drift
    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        aliases = {"NEXT_MONTH_ROLLOVER":"Next-month rollover", "DUPLICATE_PLATFORM":"Platform duplicate", "DUPLICATE_BANK":"Bank duplicate", "ORPHAN_REFUND":"Orphan refund", "MISSING_IN_BANK":"Missing settlement", "AMOUNT_MISMATCH":"Amount mismatch", "CUMULATIVE_ROUNDING_DRIFT":"Cumulative rounding drift"}
        for item in self.discrepancies:
            counts[item.gap_type] = counts.get(item.gap_type, 0) + 1
            if item.gap_type in aliases:
                alias = aliases[item.gap_type]; counts[alias] = counts.get(alias, 0) + 1
        return counts
    def by_category(self) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for item in self.discrepancies:
            totals[item.gap_type] = totals.get(item.gap_type, Decimal("0.00")) + item.impact
        return totals
