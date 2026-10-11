"""Run every tool of the toolkit on the fictional company data and print the verdicts.

After each clean run, one tamper is applied live to show the check is real.
"""
import csv
import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

from demo_retail import bank, cash_report, payroll, sepa
from demo_retail.checks import print_report
from demo_retail.company import STORES

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "out"


def tamper_line(text):
    print(f"  TAMPER  {text}")


def demo_sepa():
    approval = json.loads((DATA / "payments_approval.json").read_text(encoding="utf-8"))
    exec_date = date.fromisoformat(approval["execution_date"])
    status, inp, rb, xml = sepa.run(DATA / "payments.csv", approval["approved_total"], exec_date, OUT)
    print_report("(a) Payment list -> SEPA XML", status, inp, rb)
    print(f"  file: {xml.relative_to(HERE)}")
    # live tamper: someone adds 1 cent to one payment in the finished file
    t = OUT / "tamper" / xml.name
    t.parent.mkdir(parents=True, exist_ok=True)
    x = xml.read_text(encoding="utf-8")
    i = x.index("<InstdAmt")
    j = x.index("</InstdAmt>", i)
    amt = Decimal(x[x.index(">", i) + 1:j]) + Decimal("0.01")
    t.write_text(x[:x.index(">", i) + 1] + f"{amt:.2f}" + x[j:], encoding="utf-8")
    caught = sepa.check_readback(t, sepa.read_payments(DATA / "payments.csv"), exec_date).failed()
    tamper_line(f"+0.01 EUR on one payment in the finished XML -> caught by {', '.join(sorted(caught))}")
    return status == "RELEASED" and caught


def demo_bank():
    status, res, rep = bank.reconcile(DATA / "bank_statement.csv", DATA / "bank_statement_header.json",
                                      DATA / "ledger_bank.csv", DATA / "ledger_header.json")
    print_report("(b) Bank reconciliation", status, res)
    print(f"  matched {rep['matched']} lines · " +
          " · ".join(f"{k}: {v}" for k, v in rep["by_rule"].items()))
    for d, a, t, why in rep["open_bank"] + rep["open_ledger"]:
        print(f"  open item  {d}  {a:>10.2f}  {t[:40]:<40}  {why}")
    print(f"  file: {bank.write_report(rep, OUT).relative_to(HERE)}")
    # live tamper: one ledger line booked 1 cent off
    tdir = OUT / "tamper"
    rows = list(csv.DictReader(open(DATA / "ledger_bank.csv", encoding="utf-8")))
    rows[10]["amount"] = f"{Decimal(rows[10]['amount']) + Decimal('0.01'):.2f}"
    with open(tdir / "ledger_bank.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    _, tres, _ = bank.reconcile(DATA / "bank_statement.csv", DATA / "bank_statement_header.json",
                                tdir / "ledger_bank.csv", DATA / "ledger_header.json")
    tamper_line(f"one ledger line booked 0.01 EUR off -> caught by {', '.join(sorted(tres.failed()))}")
    return status == "RECONCILED" and tres.failed(), rep


def demo_payroll():
    status, res, totals = payroll.check(DATA / "attendance.csv", DATA / "payroll_tape.csv",
                                        DATA / "payroll_report.csv")
    print_report("(c) Payroll: attendance x tape x report (September 2026)", status, res)
    print(f"  {totals['employees']} employees · {totals['hours']} h · gross {totals['gross']:.2f} · "
          f"net {totals['net']:.2f} EUR")
    tdir = OUT / "tamper"
    rows = list(csv.DictReader(open(DATA / "attendance.csv", encoding="utf-8")))
    rows[0]["hours"] = f"{Decimal(rows[0]['hours']) + Decimal('0.5'):.1f}"
    with open(tdir / "attendance.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    _, tres, _ = payroll.check(tdir / "attendance.csv", DATA / "payroll_tape.csv", DATA / "payroll_report.csv")
    tamper_line(f"half an hour added to one shift -> caught by {', '.join(sorted(tres.failed()))}")
    return status == "APPROVE" and tres.failed(), totals


def demo_cash(rep, totals):
    lh = json.loads((DATA / "ledger_header.json").read_text(encoding="utf-8"))
    model = cash_report.compute(DATA / "ledger_bank.csv", lh["opening_balance"], STORES)
    recon = {"bank_closing": rep["bank_closing"],
             "open_bank_sum": sum(a for _, a, _, _ in rep["open_bank"]),
             "open_ledger_sum": sum(a for _, a, _, _ in rep["open_ledger"])}
    xlsx = cash_report.write_xlsx(model, recon, OUT / "cash_report.xlsx")
    res = cash_report.readback(xlsx, model, recon, totals["net"])
    status = "TIES TO THE CENT" if res.ok else "DOES NOT TIE"
    print_report("(d) Cash report (October 2026)", status, res)
    print(f"  closing ledger {model['closing']:.2f} · bank {rep['bank_closing']:.2f} EUR")
    print(f"  file: {xlsx.relative_to(HERE)}")
    t = OUT / "tamper" / "cash_report.xlsx"
    shutil.copy(xlsx, t)
    from openpyxl import load_workbook
    wb = load_workbook(t)
    ws = wb[cash_report.SHEET]
    for row in ws.iter_rows(min_row=4):
        if row[0].value and row[0].value.strip() == "Goods":
            c = row[0].offset(column=len(STORES) + 1)
            c.value = (c.value or 0) + 100
    wb.save(t)
    tres = cash_report.readback(t, model, recon, totals["net"])
    tamper_line(f"100 EUR typed over one cell in the finished Excel -> caught by {', '.join(sorted(tres.failed()))}")
    return res.ok and tres.failed()


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "tamper").mkdir(parents=True)
    ok_a = demo_sepa()
    ok_b, rep = demo_bank()
    ok_c, totals = demo_payroll()
    ok_d = demo_cash(rep, totals)
    results = [bool(x) for x in (ok_a, ok_b, ok_c, ok_d)]
    print(f"\nTOOLKIT: {sum(results)}/{len(results)} tools PASS, every live tamper caught")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
