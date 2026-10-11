"""Generate the fictional input files in data/ (deterministic: same seed, same files).

One month (October 2026) of Demo Retail s.r.o.:
  payments.csv + payments_approval.json   -> (a) SEPA
  bank_statement.csv + ledger_bank.csv    -> (b) bank reconciliation, (d) cash report
  attendance.csv + payroll_tape.csv + payroll_report.csv  -> (c) payroll (September 2026)

The data is clean except for the deliberate reconciling items a real month has
(bank fees not yet booked, an unidentified receipt, a payment in transit).
"""
import calendar
import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from demo_retail.company import COMPANY, EMPLOYEES, STORES, SUPPLIERS

DATA = Path(__file__).parent / "data"
SEED = 2026
CENT = Decimal("0.01")
OPENING_BALANCE = Decimal("85000.00")
EXEC_DATE = date(2026, 10, 13)


def money(rng, lo, hi):
    return Decimal(rng.randint(int(lo * 100), int(hi * 100))) / 100


def write(name, rows):
    with open(DATA / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def business_days(year, month):
    n = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, n + 1) if date(year, month, d).weekday() < 5]


def payments(rng):
    rows = []
    for i in range(24):
        s = SUPPLIERS[i] if i < len(SUPPLIERS) else rng.choice(SUPPLIERS)  # every supplier at least once
        rows.append({"name": s["name"], "iban": s["iban"], "amount": f"{money(rng, 40, 9500):.2f}",
                     "currency": "EUR", "reference": f"INV-D{i + 1:02d}", "category": s["category"]})
    return rows


def payroll(rng):
    """September 2026: attendance per day, the provider's payroll tape, the management report."""
    attendance, tape = [], []
    days = [date(2026, 9, d) for d in range(1, 31)]
    for e in EMPLOYEES:
        rate = Decimal(e["hourly_rate"])
        worked = rng.sample(days, 20)
        hours = sunday = Decimal(0)
        for d in sorted(worked):
            h = Decimal(rng.choice([4, 6, 7.5, 8, 8, 8]))
            attendance.append({"employee_id": e["id"], "date": d.isoformat(), "hours": f"{h:.1f}"})
            hours += h
            if d.weekday() == 6:
                sunday += h
        gross = (hours * rate + sunday * rate * Decimal("0.5")).quantize(CENT, ROUND_HALF_UP)
        deductions = (gross * Decimal("0.234")).quantize(CENT, ROUND_HALF_UP)
        tape.append({"employee_id": e["id"], "name": e["name"], "store": e["store"],
                     "hourly_rate": e["hourly_rate"], "hours": f"{hours:.1f}", "sunday_hours": f"{sunday:.1f}",
                     "gross": f"{gross:.2f}", "deductions": f"{deductions:.2f}",
                     "net": f"{gross - deductions:.2f}"})
    report = []
    for s in STORES:
        mine = [t for t in tape if t["store"] == s]
        report.append({"store": s, "headcount": len(mine),
                       "hours": f"{sum(Decimal(t['hours']) for t in mine):.1f}",
                       "gross": f"{sum(Decimal(t['gross']) for t in mine):.2f}"})
    return attendance, tape, report


def bank_and_ledger(rng, pays, tape):
    """October 2026 bank statement and the bank account (221) in the general ledger."""
    bank, ledger = [], []

    def both(d, amount, ref, text, category, store="HQ", bank_d=None, bank_ref=None, iban=""):
        ledger.append({"date": d.isoformat(), "amount": f"{amount:.2f}", "reference": ref,
                       "description": text, "category": category, "store": store})
        bank.append({"date": (bank_d or d).isoformat(), "amount": f"{amount:.2f}",
                     "reference": ref if bank_ref is None else bank_ref, "counterparty_iban": iban,
                     "text": text.upper()})

    for d in business_days(2026, 10):
        for s in STORES:
            amt = money(rng, 800, 4000)
            both(d, amt, f"CARD-{s.split()[1].upper()}-{d:%d%b}".upper(), f"Card settlement {s}", "Card receipts", s,
                 bank_d=d + timedelta(days=1) if d.weekday() < 4 else d)
        if d.weekday() == 4:
            for s in STORES:
                amt = money(rng, 1500, 6000)
                both(d, amt, f"CASH-{s.split()[1].upper()}-{d:%d%b}".upper(), f"Cash deposit {s}", "Cash receipts", s)

    for i, p in enumerate(pays):
        # banks shorten or drop the remittance text; the matcher has to cope
        bank_ref = "" if i % 6 == 5 else None
        both(EXEC_DATE, -Decimal(p["amount"]), p["reference"], f"Supplier {p['name']}", p["category"],
             bank_d=EXEC_DATE + timedelta(days=1 if i % 4 == 0 else 0), bank_ref=bank_ref, iban=p["iban"])

    net = sum(Decimal(t["net"]) for t in tape)
    both(date(2026, 10, 15), -net, "PAYROLL-2026-09", "Net payroll September 2026", "Payroll")

    # reconciling items a real month has
    bank.append({"date": "2026-10-15", "amount": "-3.84", "reference": "FEE-SEPA",
                 "counterparty_iban": "", "text": "SEPA TRANSFER FEES"})
    bank.append({"date": "2026-10-30", "amount": "-12.50", "reference": "FEE-ACCOUNT",
                 "counterparty_iban": "", "text": "ACCOUNT MAINTENANCE FEE"})
    bank.append({"date": "2026-10-22", "amount": "250.00", "reference": "",
                 "counterparty_iban": "ES9121000418450200051332", "text": "TRANSFER RECEIVED"})
    ledger.append({"date": "2026-10-30", "amount": "-1465.90", "reference": "INV-D99",
                   "description": "Supplier Test Rent d.o.o. (November rent)", "category": "Rent", "store": "HQ"})

    bank.sort(key=lambda r: (r["date"], r["reference"]))
    ledger.sort(key=lambda r: (r["date"], r["reference"]))
    closing = OPENING_BALANCE + sum(Decimal(b["amount"]) for b in bank)
    header = {"account_iban": COMPANY["iban"], "period": "2026-10", "currency": "EUR",
              "opening_balance": f"{OPENING_BALANCE:.2f}", "closing_balance": f"{closing:.2f}"}
    return bank, ledger, header


def main():
    rng = random.Random(SEED)
    DATA.mkdir(exist_ok=True)
    pays = payments(rng)
    write("payments.csv", [{k: v for k, v in p.items() if k != "category"} for p in pays])
    total = sum(Decimal(r["amount"]) for r in pays)
    (DATA / "payments_approval.json").write_text(json.dumps(
        {"approved_total": f"{total:.2f}", "execution_date": EXEC_DATE.isoformat(),
         "approved_by": "Finance manager (role)"}, indent=2) + "\n", encoding="utf-8")

    attendance, tape, report = payroll(rng)
    write("attendance.csv", attendance)
    write("payroll_tape.csv", tape)
    write("payroll_report.csv", report)

    bank, ledger, header = bank_and_ledger(rng, pays, tape)
    write("bank_statement.csv", bank)
    (DATA / "bank_statement_header.json").write_text(json.dumps(header, indent=2) + "\n", encoding="utf-8")
    write("ledger_bank.csv", ledger)
    (DATA / "ledger_header.json").write_text(json.dumps(
        {"account": "221 Bank", "period": "2026-10", "opening_balance": f"{OPENING_BALANCE:.2f}"},
        indent=2) + "\n", encoding="utf-8")

    print(f"payments {len(pays)} ({total:.2f} EUR) · attendance {len(attendance)} rows · "
          f"bank {len(bank)} lines · ledger {len(ledger)} lines")


if __name__ == "__main__":
    main()
