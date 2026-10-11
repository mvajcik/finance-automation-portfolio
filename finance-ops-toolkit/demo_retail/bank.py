"""Bank reconciliation: bank statement vs. the bank account in the ledger.

Matching, in order of confidence:
  rule 1  same reference and same amount
  rule 2  same amount, dates at most 3 days apart, exactly one candidate
Whatever is left becomes an open item and must carry a reason. An open item
without a reason is a failed reconciliation, not a footnote.
"""
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .checks import Result

WINDOW_DAYS = 3
IN_TRANSIT_MAX_DAYS = 3


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["_id"] = i
        r["_amount"] = Decimal(r["amount"])
        r["_date"] = date.fromisoformat(r["date"])
    return rows


def match(bank, ledger):
    matches, used_l = [], set()
    by_ref = {}
    for l in ledger:
        by_ref.setdefault((l["reference"], l["_amount"]), []).append(l)
    for b in bank:
        cands = [l for l in by_ref.get((b["reference"], b["_amount"]), []) if l["_id"] not in used_l]
        if b["reference"] and cands:
            matches.append((b, cands[0], "rule 1: reference + amount"))
            used_l.add(cands[0]["_id"])
    used_b = {m[0]["_id"] for m in matches}
    for b in bank:
        if b["_id"] in used_b:
            continue
        cands = [l for l in ledger if l["_id"] not in used_l and l["_amount"] == b["_amount"]
                 and abs((l["_date"] - b["_date"]).days) <= WINDOW_DAYS]
        if len(cands) == 1:
            matches.append((b, cands[0], "rule 2: amount + date window"))
            used_l.add(cands[0]["_id"])
            used_b.add(b["_id"])
    open_bank = [b for b in bank if b["_id"] not in used_b]
    open_ledger = [l for l in ledger if l["_id"] not in used_l]
    return matches, open_bank, open_ledger


def reason_bank(b):
    if b["reference"].startswith("FEE-"):
        return "Bank fee not yet booked in the ledger"
    if b["_amount"] > 0 and not b["reference"]:
        return "Unidentified receipt: ask the bank for the sender"
    return ""


def reason_ledger(l, period_end):
    if (period_end - l["_date"]).days <= IN_TRANSIT_MAX_DAYS and l["_amount"] < 0:
        return "Payment booked, not yet debited by the bank (in transit)"
    return ""


def reconcile(statement_csv, statement_header, ledger_csv, ledger_header):
    sh = json.loads(Path(statement_header).read_text(encoding="utf-8"))
    lh = json.loads(Path(ledger_header).read_text(encoding="utf-8"))
    bank, ledger = _read(statement_csv), _read(ledger_csv)
    period_end = max(b["_date"] for b in bank)
    matches, open_bank, open_ledger = match(bank, ledger)

    r = Result()
    b_open, b_close = Decimal(sh["opening_balance"]), Decimal(sh["closing_balance"])
    b_sum = sum(b["_amount"] for b in bank)
    r.add("B1", "Statement is complete: opening + lines == closing",
          [] if b_open + b_sum == b_close else [f"{b_open} + {b_sum} != {b_close}"])
    l_open = Decimal(lh["opening_balance"])
    r.add("B2", "Ledger opening balance == bank opening balance",
          [] if l_open == b_open else [f"ledger {l_open} vs bank {b_open}"])
    ids_b = [m[0]["_id"] for m in matches] + [b["_id"] for b in open_bank]
    ids_l = [m[1]["_id"] for m in matches] + [l["_id"] for l in open_ledger]
    r.add("B3", "Every line used exactly once (matched or open)",
          [] if sorted(ids_b) == list(range(len(bank))) and sorted(ids_l) == list(range(len(ledger)))
          else ["a line is missing or used twice"])
    l_close = l_open + sum(l["_amount"] for l in ledger)
    adj = l_close + sum(b["_amount"] for b in open_bank) - sum(l["_amount"] for l in open_ledger)
    r.add("B4", "Ledger + open bank items - open ledger items == bank closing (to the cent)",
          [] if adj == b_close else [f"{adj} vs {b_close}"])
    unexplained = [f"bank {b['date']} {b['amount']} {b['text']}" for b in open_bank if not reason_bank(b)] + \
                  [f"ledger {l['date']} {l['amount']} {l['description']}" for l in open_ledger
                   if not reason_ledger(l, period_end)]
    r.add("B5", "Every open item has a reason", unexplained)

    report = {
        "bank_opening": b_open, "bank_closing": b_close, "ledger_closing": l_close,
        "matched": len(matches),
        "by_rule": {k: sum(1 for m in matches if m[2] == k) for k in sorted({m[2] for m in matches})},
        "open_bank": [(b["date"], b["_amount"], b["text"], reason_bank(b)) for b in open_bank],
        "open_ledger": [(l["date"], l["_amount"], l["description"], reason_ledger(l, period_end))
                        for l in open_ledger],
        "matches": matches,
    }
    return ("RECONCILED" if r.ok else "NOT RECONCILED"), r, report


def write_report(report, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "bank_reconciliation.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["status", "bank_date", "ledger_date", "amount", "bank_text", "ledger_text", "rule_or_reason"])
        for b, l, rule in report["matches"]:
            w.writerow(["matched", b["date"], l["date"], b["amount"], b["text"], l["description"], rule])
        for d, a, t, why in report["open_bank"]:
            w.writerow(["open (bank)", d, "", f"{a:.2f}", t, "", why])
        for d, a, t, why in report["open_ledger"]:
            w.writerow(["open (ledger)", "", d, f"{a:.2f}", "", t, why])
    return path
