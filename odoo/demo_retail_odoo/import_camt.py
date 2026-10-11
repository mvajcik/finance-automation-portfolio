#!/usr/bin/env python3
"""Import a CAMT.053 statement into Odoo 17 Community and match its lines to vendor bills — over the ORM.

    python3 -m demo_retail_odoo.import_camt out/camt053-2026-07.xml out/camt053-2026-08.xml out/camt053-2026-09.xml

Honest note: Odoo 17 *Community* has bank statements but no CAMT import and no reconciliation
screen — both are Enterprise. This script does the two things by hand:
  1. statement + lines are created through the ORM (`account.bank.statement.line`);
  2. a matched line is reconciled the way the Enterprise widget does it internally: the line's
     counterpart (the journal's suspense account) is re-pointed to the vendor's payable account and reconciled
     with the bill's payable line through the standard `account.move.line.reconcile()`.

Matching rules, in this order, no guessing:
  R1 reference: the bill reference appears in EndToEndId or remittance text, and the amount equals
     the bill's open amount to the cent;
  R2 amount + counterparty: no usable reference; exactly ONE open bill of the counterparty with the
     same amount due within 5 days of the statement date. Two candidates = open item, not a match.
  Everything else is an open item and must carry a reason. Verdict RECONCILED only when the statement
  is complete (opening + lines = closing), every line is matched or explained, and Odoo shows the
  same closing balance as the file.
"""
import argparse
import json
import re
import sys
import xmlrpc.client
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import master_data as md
from .camt import parse_camt053
from .rpc import Odoo

RECONCILE_CTX = {"skip_invoice_sync": True, "skip_account_move_synchronization": True, "force_delete": True}


def dec(x):
    return Decimal(str(x)).quantize(md.CENT)


def open_bills(o):
    rows = o.search_read("account.move", [("move_type", "=", "in_invoice"), ("state", "=", "posted"),
                                          ("payment_state", "in", ("not_paid", "partial"))],
                         ["ref", "partner_id", "amount_residual", "invoice_date_due", "line_ids"])
    for r in rows:
        r["amount_residual"] = dec(r["amount_residual"])
        r["due"] = date.fromisoformat(r["invoice_date_due"])
    return rows


def propose_reason(line):
    """A proposed reason for an open item from its shape. A person still has to accept it."""
    text = line["text"].upper()
    if line["amount"] < 0 and "FEE" in text:
        return "Bank fee: book to 568000 (other financial costs), no bill expected"
    if line["amount"] > 0 and line["name"]:
        return f"Receipt from a vendor ({line['name']}): refund — credit note not yet in Odoo"
    if line["amount"] > 0:
        return "Unidentified receipt: ask the bank for the sender"
    return "Payment without a matching open bill: check for a missing or duplicated bill"


def match(lines, bills):
    """Pure function: statement lines x open bills -> (matches, open items). Testable without Odoo."""
    by_ref = {b["ref"]: b for b in bills}
    refs_re = re.compile("|".join(re.escape(r) for r in sorted(by_ref, key=len, reverse=True))) if by_ref else None
    used, matches, open_items = set(), [], []
    for l in lines:
        amount = dec(l["amount"])
        hit = refs_re.search(f"{l['end_to_end']} {l['text']}") if refs_re else None
        if hit and hit.group(0) not in used and by_ref[hit.group(0)]["amount_residual"] == -amount:
            b = by_ref[hit.group(0)]
            used.add(b["ref"]); matches.append((l, b, "R1 reference + amount")); continue
        d = date.fromisoformat(l["date"])
        cands = [b for b in bills if b["ref"] not in used and b["partner_id"][1] == l["name"]
                 and b["amount_residual"] == -amount and abs((b["due"] - d).days) <= 5]
        if len(cands) == 1:
            used.add(cands[0]["ref"]); matches.append((l, cands[0], "R2 counterparty + amount + date")); continue
        reason = propose_reason(l) if not cands else f"{len(cands)} bills of {l['name']} fit — a person decides"
        open_items.append((l, reason))
    return matches, open_items


def ensure_statement(o, header, lines, journal):
    name = f"STMT {header['id']}"
    st = o.one("account.bank.statement", [("name", "=", name)], ["id", "line_ids"])
    if st:
        return st["id"], False
    st_id = o.create("account.bank.statement", {"name": name, "journal_id": journal["id"], "date": header["to"],
                                                 "balance_start": float(header["opening"]),
                                                 "balance_end_real": float(header["closing"])})
    for l in lines:
        o.create("account.bank.statement.line", {
            "statement_id": st_id, "journal_id": journal["id"], "date": l["date"], "ref": l["ref"],
            "payment_ref": f"{l['text']} / {l['end_to_end']}", "amount": float(l["amount"]),
            "partner_name": l["name"] or False, "account_number": l["iban"] or False})
    return st_id, True


def reconcile_line(o, st_line, bill, payable_account, suspense_account):
    """Re-point the statement line's suspense counterpart to payables and reconcile it with the bill."""
    counterpart = o.one("account.move.line", [("move_id", "=", st_line["move_id"][0]),
                                              ("account_id", "=", suspense_account)], ["id"])
    bill_line = o.one("account.move.line", [("move_id", "=", bill["id"]), ("account_id", "=", payable_account),
                                            ("reconciled", "=", False)], ["id"])
    o.write("account.move", [st_line["move_id"][0]],
            # analytic_distribution must be cleared explicitly: with the partner set, Odoo would apply the vendor's
            # distribution model to this payable line and write analytic lines for a payment (caught by check W3)
            {"line_ids": [(1, counterpart["id"], {"account_id": payable_account, "partner_id": bill["partner_id"][0],
                                                  "analytic_distribution": False})]},
            context=RECONCILE_CTX)
    o.write("account.bank.statement.line", [st_line["id"]], {"partner_id": bill["partner_id"][0]}, context=RECONCILE_CTX)
    try:
        o.call("account.move.line", "reconcile", [counterpart["id"], bill_line["id"]])
    except xmlrpc.client.Fault as e:
        # reconcile() returns None; XML-RPC cannot marshal None after the work is already committed
        if "cannot marshal None" not in str(e):
            raise
    flags = o.read("account.move.line", [counterpart["id"], bill_line["id"]], ["reconciled"])
    if not all(f["reconciled"] for f in flags):
        raise RuntimeError(f"reconcile of statement line {st_line['ref']} with {bill['ref']} did not stick")


def run(o, camt_path, out_dir):
    header, lines = parse_camt053(Path(camt_path).read_bytes())
    journal = o.one("account.journal", [("type", "=", "bank")], ["id", "code", "suspense_account_id", "default_account_id"])
    st_id, created = ensure_statement(o, header, lines, journal)
    st_lines = {l["ref"]: l for l in o.search_read("account.bank.statement.line", [("statement_id", "=", st_id)],
                                                   ["ref", "move_id", "is_reconciled", "amount", "date"])}
    todo = [l for l in lines if not st_lines[l["ref"]]["is_reconciled"]]
    matches, open_items = match(todo, open_bills(o))
    payable = o.one("account.account", [("code", "=", md.ACC["payable"])], ["id"])["id"]
    for l, b, rule in matches:
        reconcile_line(o, st_lines[l["ref"]], b, payable, journal["suspense_account_id"][0])
    for l, reason in open_items:
        o.write("account.bank.statement.line", [st_lines[l["ref"]]["id"]], {"narration": f"OPEN ITEM — {reason}"})

    # checks, each against an independent source
    checks = []
    file_sum = sum(dec(l["amount"]) for l in lines)
    checks.append(("B1 statement complete: opening + lines = closing (file)",
                   header["opening"] + file_sum == header["closing"],
                   f"{header['opening']:.2f} + {file_sum:.2f} vs {header['closing']:.2f}"))
    st = o.read("account.bank.statement", [st_id], ["balance_start", "balance_end", "balance_end_real"])[0]
    checks.append(("B2 Odoo statement closing = file closing", dec(st["balance_end"]) == header["closing"],
                   f"Odoo {st['balance_end']:.2f} vs file {header['closing']:.2f}"))
    now = o.search_read("account.bank.statement.line", [("statement_id", "=", st_id)], ["ref", "is_reconciled", "narration"])
    unexplained = [l["ref"] for l in now if not l["is_reconciled"] and not (l["narration"] or "").startswith("<p>OPEN ITEM")]
    checks.append(("B3 every line matched or an open item with a reason", not unexplained, f"unexplained: {unexplained}"))
    paid = o.search_read("account.move", [("id", "in", [b["id"] for _, b, _ in matches])], ["ref", "payment_state"])
    not_paid = [p["ref"] for p in paid if p["payment_state"] not in ("paid", "in_payment")]
    checks.append(("B4 every matched bill is paid in Odoo", not not_paid and len(paid) == len(matches), f"not paid: {not_paid}"))
    bank_acc = journal["default_account_id"]
    gl = o.search_read("account.move.line", [("account_id", "=", bank_acc[0]), ("parent_state", "=", "posted")], ["balance"])
    gl_bal = sum(dec(x["balance"]) for x in gl)
    all_lines = o.search_read("account.bank.statement.line", [("journal_id", "=", journal["id"])], ["amount"])
    movements = sum(dec(x["amount"]) for x in all_lines)
    checks.append((f"B5 bank account {bank_acc[1]} in the ledger = all statement movements imported so far (no opening entry booked)",
                   gl_bal == movements, f"ledger {gl_bal:.2f} vs statements {movements:.2f}"))
    verdict = "RECONCILED" if all(c[1] for c in checks) else "NOT RECONCILED"

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    report = [f"CAMT.053 import — statement {header['id']} ({header['from']} .. {header['to']}) — {'created' if created else 'already imported'}",
              f"lines {len(lines)} · matched now {len(matches)} · open items {len(open_items)} · "
              f"already reconciled before this run {len(lines) - len(todo)}", ""]
    for l, b, rule in matches:
        report.append(f"matched    {l['date']} {dec(l['amount']):>10.2f}  {b['ref']:<18} {rule}")
    for l, reason in open_items:
        report.append(f"open item  {l['date']} {dec(l['amount']):>10.2f}  {l['text'][:34]:<34} {reason}")
    report.append("")
    for name, ok, detail in checks:
        report.append(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    report.append(f"VERDICT: {verdict}")
    (out / f"import-log-{header['id']}.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    (out / f"open-items-{header['id']}.json").write_text(json.dumps(
        [{"date": l["date"], "amount": f"{dec(l['amount']):.2f}", "text": l["text"], "reason": r} for l, r in open_items],
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n".join(report))
    return verdict == "RECONCILED"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("camt", nargs="+", help="CAMT.053 files, oldest first")
    ap.add_argument("--url", default="http://127.0.0.1:8071")
    ap.add_argument("--db", default="demo_retail")
    ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    o = Odoo(a.url, a.db)
    ok = [run(o, path, a.out) for path in a.camt]
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
