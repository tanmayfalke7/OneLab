# Reconciliation assumptions

- Amounts are INR (₹) and timestamps are ISO-8601 UTC.
- Cleared bank settlements arrive one to two calendar days after a capture.
- Captures dated October 30–31, 2026 that are absent from the October bank period are valid next-month rollovers, not missing funds.
- The platform applies a 1.75% fee at six decimal places and rounds after aggregation. The bank applies that fee per transaction and rounds each payout to two decimals using `ROUND_HALF_UP`.
- Captures match by `transaction_id`; refunds match their original capture by `parent_transaction_id`.
- An amount delta of up to ₹0.01 is ordinary row-level rounding. Larger deltas are amount mismatches.
