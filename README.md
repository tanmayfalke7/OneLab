---
title: LedgerBridge Reconciliation
sdk: docker
app_port: 8000
---
# LedgerBridge

LedgerBridge is a stateless FastAPI reconciliation dashboard for comparing platform captures with delayed bank settlements. It uses `Decimal` with `ROUND_HALF_UP`, hash-map joins, and HTMX partial updates to keep reconciliation exact and responsive.

## Local run

```bash
python data/generate_data.py
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Run the verification suite with `pytest`.

## Architecture

Two CSV ledgers are parsed in memory and indexed by `transaction_id`, making matching O(N + M). The reconciler classifies timing rollover, duplicates, orphan refunds, missing/unrecorded records, payout mismatches, and aggregate rounding drift. FastAPI returns small Jinja/HTMX fragments; no database or uploaded-file persistence is involved.

## Deploy to Render or Railway

1. Push this directory to a Git repository and create a new Render Web Service or Railway service from it.
2. Select Docker deployment; the included `Dockerfile` starts four Uvicorn workers on port 8000.
3. Attach a public URL and use `/health` as the health-check path. Configure the platform to route its exposed port to container port 8000.

## What This Would Get Wrong in Production

In production, banks rarely settle transactions one-to-one with original `transaction_id` keys, instead sending lump-sum NEFT/RTGS payouts netted against multi-day chargebacks, rolling reserves, and GST on gateway fees that require many-to-one batch matching.

Stateless in-memory CSV reconciliation cannot track multi-month rolling state—meaning a transaction settled in November would still need a persistent ledger state store to confirm it actually cleared rather than silently vanishing after month-end.

Real-world payment gateways also handle partial captures, multi-currency FX conversion spreads, and asynchronous webhook out-of-order delivery, which would trigger false-positive amount mismatches and orphan refund alerts under single-currency exact-ID matching.
