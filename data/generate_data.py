"""Create deterministic October 2026 sample files with planted reconciliation anomalies."""
import csv, json, random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).parent
random.seed(42)
FEE = Decimal("0.0175")

PLATFORM_FIELDS = ["transaction_id", "timestamp_utc", "customer_id", "payment_method", "type", "parent_transaction_id", "gross_amount", "platform_fee_exact", "net_amount_exact"]
BANK_FIELDS = ["settlement_id", "transaction_id", "settlement_date_utc", "type", "parent_transaction_id", "gross_amount", "bank_fee_rounded", "settled_amount"]

def q(value, places="0.01"): return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)
def capture(txid, when, gross, customer="CUST-001"):
    gross = q(gross); fee = q(gross * FEE, "0.000001"); net = gross - fee
    return {"transaction_id":txid,"timestamp_utc":when.isoformat().replace("+00:00","Z"),"customer_id":customer,"payment_method":random.choice(["UPI","Card","NetBanking"]),"type":"CAPTURE","parent_transaction_id":"","gross_amount":str(gross),"platform_fee_exact":str(fee),"net_amount_exact":str(net)}
def settlement(row, sid, days=1):
    gross = Decimal(row["gross_amount"]); fee=q(gross * FEE); net=q(gross-fee)
    d=datetime.fromisoformat(row["timestamp_utc"].replace("Z","+00:00"))+timedelta(days=days)
    return {"settlement_id":sid,"transaction_id":row["transaction_id"],"settlement_date_utc":d.isoformat().replace("+00:00","Z"),"type":"CAPTURE","parent_transaction_id":"","gross_amount":str(gross),"bank_fee_rounded":str(fee),"settled_amount":str(net)}

platform=[]; bank=[]
base=datetime(2026,10,1,tzinfo=timezone.utc)
for i in range(1180):
    d=base+timedelta(days=i % 28, hours=(i*7)%23, minutes=(i*13)%59)
    gross=Decimal(random.choice(["149.33","899.75","2450.19","511.17","76.63"])) + Decimal(i % 9)
    row=capture(f"TXN-202610-{i:04d}",d,gross,f"CUST-{i:04d}"); platform.append(row); bank.append(settlement(row,f"SET-{i:04d}",1+(i%2)))

# Five valid rollovers, deliberately left out of the October bank source.
for i in range(1,6):
    row=capture(f"TXN-202610-ROLL{i:02d}", datetime(2026,10,31,18+i,tzinfo=timezone.utc), "899.75"); platform.append(row); bank.append(settlement(row,f"SET-ROLL{i:02d}", 1+(i%2)))
# Platform duplicate and bank duplicate.
dupp=capture("TXN-202610-DUPPLAT1",base+timedelta(days=10),"350.55"); platform += [dupp, dupp.copy()]; bank.append(settlement(dupp,"SET-DUPPLAT",1))
dupb=capture("TXN-202610-DUPBANK1",base+timedelta(days=11),"700.77"); platform.append(dupb); bank += [settlement(dupb,"SET-DUPBANK-A",1),settlement(dupb,"SET-DUPBANK-B",1)]
# Missing and mismatched.
miss=capture("TXN-202610-MISS01",base+timedelta(days=14),"999.99"); platform.append(miss)
mism=capture("TXN-202610-MISM01",base+timedelta(days=17),"1200.00"); platform.append(mism); bad=settlement(mism,"SET-MISM",1); bad["settled_amount"]=str(q(Decimal(bad["settled_amount"])-50)); bank.append(bad)
# Orphan refunds.
platform.append({"transaction_id":"RFN-202610-ORPH02","timestamp_utc":"2026-10-20T12:00:00Z","customer_id":"CUST-R","payment_method":"UPI","type":"REFUND","parent_transaction_id":"TXN-202609-NONEXIST2","gross_amount":"-640.00","platform_fee_exact":"0.000000","net_amount_exact":"-640.00"})
bank.append({"settlement_id":"SET-ORPH01","transaction_id":"RFN-202610-ORPH01","settlement_date_utc":"2026-10-21T00:00:00Z","type":"REFUND","parent_transaction_id":"TXN-202609-NONEXIST1","gross_amount":"-1250.00","bank_fee_rounded":"0.00","settled_amount":"-1250.00"})

with (ROOT/"platform_ledger.csv").open("w",newline="",encoding="utf-8") as f: csv.DictWriter(f,PLATFORM_FIELDS).writeheader(); csv.DictWriter(f,PLATFORM_FIELDS).writerows(platform)
with (ROOT/"bank_settlements.csv").open("w",newline="",encoding="utf-8") as f: csv.DictWriter(f,BANK_FIELDS).writeheader(); csv.DictWriter(f,BANK_FIELDS).writerows(bank)
print(json.dumps({"platform_rows":len(platform),"bank_rows":len(bank),"rollovers":5,"platform_duplicates":1,"bank_duplicates":1,"orphan_refunds":2,"missing":1,"mismatches":1},indent=2))
