#!/usr/bin/env python3
"""Build the Demo Retail s.r.o. company in a fresh Odoo 17 Community database — over the ORM, via XML-RPC.

    python3 -m demo_retail_odoo.setup_demo [--url http://127.0.0.1:8071] [--db demo_retail]

Steps (each one idempotent — running twice changes nothing):
  1. database (country SK) · modules `account` (+ `l10n_sk` pulled in by the company country)
  2. company name, address, bank account on the bank journal
  3. analytic plan "Stores" with Store North / Centre / South / HQ         (decision 001)
  4. analytic distribution models: vendor -> store or HQ at 100 %        (decision 002)
  5. custom field x_payment_week on vendor bills + a line in the bill form (decision 003)
  6. 20 vendors, 11 with example IBANs
  7. 70 posted vendor bills for July–September 2026, payment week filled
  8. readback: what is in Odoo must equal the plan, to the cent — otherwise exit 1
"""
import argparse
import sys
from decimal import Decimal

from . import master_data as md
from .rpc import Odoo, ensure_database, install_modules, wait_ready


def log(msg):
    print(msg, flush=True)


def setup_admin_groups(o):
    """A fresh database gives the admin invoicing rights only; analytic plans, bank statements and full accounting need three groups."""
    groups = [o.ref(x) for x in ("analytic.group_analytic_accounting", "account.group_account_user",
                                 "account.group_account_manager")]
    o.write("res.users", [o.uid], {"groups_id": [(4, g) for g in groups if g]})


def setup_company(o):
    cid = o.one("res.company", [], ["id", "partner_id"])
    o.write("res.company", [cid["id"]], {"name": md.COMPANY["name"]})
    country = o.one("res.country", [("code", "=", md.COMPANY["country"])], ["id"])["id"]
    o.write("res.partner", [cid["partner_id"][0]], {"street": md.COMPANY["street"], "zip": md.COMPANY["zip"],
                                                    "city": md.COMPANY["city"], "country_id": country})
    bank = o.one("account.journal", [("type", "=", "bank")], ["id", "code", "bank_account_id"])
    if not bank["bank_account_id"]:
        o.write("account.journal", [bank["id"]], {"bank_acc_number": md.COMPANY["iban"]})
    return bank["id"]


def setup_analytic(o):
    # Odoo ships one analytic plan ("Default"); it is the one whose accounts land in `account_id` of the
    # analytic lines. Renaming it keeps the standard reports and the readback simple (decision 001).
    plan = o.one("account.analytic.plan", [("name", "=", md.ANALYTIC_PLAN)], ["id"]) \
        or o.search_read("account.analytic.plan", [], ["id"], order="id", limit=1)[0]
    plan_id = plan["id"]
    o.write("account.analytic.plan", [plan_id], {"name": md.ANALYTIC_PLAN})
    ids = {}
    for name in md.STORES + [md.HQ]:
        acc = o.one("account.analytic.account", [("name", "=", name), ("plan_id", "=", plan_id)], ["id"])
        ids[name] = acc["id"] if acc else o.create("account.analytic.account", {"name": name, "plan_id": plan_id})
    return ids


def setup_vendors(o, analytic):
    ids = {}
    for v in md.VENDOR.values():
        p = o.one("res.partner", [("name", "=", v["name"])], ["id"])
        if p:
            ids[v["key"]] = p["id"]
            continue
        country = o.one("res.country", [("code", "=", v["country"])], ["id"])["id"]
        vals = {"name": v["name"], "is_company": True, "supplier_rank": 1, "country_id": country}
        if v["iban"]:
            vals["bank_ids"] = [(0, 0, {"acc_number": v["iban"]})]
        ids[v["key"]] = o.create("res.partner", vals)
        if v["default_analytic"]:       # distribution model: this vendor's cost always lands here
            o.create("account.analytic.distribution.model",
                     {"partner_id": ids[v["key"]], "analytic_distribution": {str(analytic[v["default_analytic"]]): 100}})
    return ids


def setup_payment_week_field(o):
    model = o.one("ir.model", [("model", "=", "account.move")], ["id"])["id"]
    if not o.one("ir.model.fields", [("model", "=", "account.move"), ("name", "=", "x_payment_week")], ["id"]):
        o.create("ir.model.fields", {"name": "x_payment_week", "model_id": model, "ttype": "char", "state": "manual",
                                     "field_description": "Payment week", "index": "btree_not_null",
                                     "help": "ISO week in which the bill is due to be paid, e.g. 2026-W39. Filled by the "
                                             "import script, used to group the weekly payment run."})
    if not o.one("ir.ui.view", [("name", "=", "account.move.form.payment.week")], ["id"]):
        form = o.ref("account.view_move_form")
        o.create("ir.ui.view", {
            "name": "account.move.form.payment.week", "model": "account.move", "inherit_id": form, "type": "form",
            "arch": '<xpath expr="//field[@name=\'invoice_date_due\']" position="after">'
                    '<field name="x_payment_week" invisible="move_type not in (\'in_invoice\', \'in_refund\')"/>'
                    '</xpath>'})


def accounts(o):
    rows = o.search_read("account.account", [("code", "in", list(md.ACC.values()))], ["code"])
    by_code = {r["code"]: r["id"] for r in rows}
    missing = [c for c in md.ACC.values() if c not in by_code]
    if missing:
        raise SystemExit(f"accounts missing in the chart: {missing}")
    return {k: by_code[c] for k, c in md.ACC.items()}


def purchase_tax(o):
    t = o.one("account.tax", [("type_tax_use", "=", "purchase"), ("amount", "=", 23), ("name", "=", "23%")], ["id"])
    return t["id"]


def create_bills(o, vendors, analytic, acc, tax_id):
    existing = {r["ref"] for r in o.search_read("account.move", [("move_type", "=", "in_invoice")], ["ref"])}
    created = 0
    for b in md.bills_plan():
        if b["ref"] in existing:
            continue
        lines = []
        for account_key, label, net, store in b["lines"]:
            line = {"account_id": acc[account_key], "name": label, "quantity": 1, "price_unit": float(net),
                    "tax_ids": [(6, 0, [tax_id])] if md.vat_rate(b["vendor"]) else [(6, 0, [])]}
            if store:                                                   # explicit store on the line
                line["analytic_distribution"] = {str(analytic[store]): 100}
            lines.append((0, 0, line))                                  # otherwise the distribution model decides
        move_id = o.create("account.move", {
            "move_type": "in_invoice", "partner_id": vendors[b["vendor"]], "ref": b["ref"],
            "invoice_date": b["invoice_date"].isoformat(), "invoice_date_due": b["due_date"].isoformat(),
            "invoice_line_ids": lines})
        o.call("account.move", "action_post", [move_id])
        o.write("account.move", [move_id], {"x_payment_week": md.payment_week(b["due_date"])})
        created += 1
    return created


def readback(o, analytic):
    """What Odoo holds must equal the plan: count, every bill's total, every line's analytic account."""
    plan = {b["ref"]: b for b in md.bills_plan()}
    bills = o.search_read("account.move", [("move_type", "=", "in_invoice"), ("state", "=", "posted")],
                          ["ref", "amount_total", "x_payment_week", "invoice_date_due", "invoice_line_ids"])
    problems = []
    if len(bills) != len(plan):
        problems.append(f"bills in Odoo {len(bills)} != plan {len(plan)}")
    by_id = {v: k for k, v in analytic.items()}
    for b in bills:
        p = plan.get(b["ref"])
        if not p:
            problems.append(f"{b['ref']} not in plan"); continue
        if Decimal(str(b["amount_total"])).quantize(md.CENT) != md.bill_total(p):
            problems.append(f"{b['ref']} total {b['amount_total']} != plan {md.bill_total(p)}")
        if b["x_payment_week"] != md.payment_week(p["due_date"]):
            problems.append(f"{b['ref']} payment week {b['x_payment_week']} != {md.payment_week(p['due_date'])}")
        lines = o.read("account.move.line", b["invoice_line_ids"], ["name", "analytic_distribution"])
        for pl in p["lines"]:
            ol = next((l for l in lines if l["name"] == pl[1]), None)
            want = md.line_analytic(p, pl)
            got = [by_id.get(int(k)) for k in (ol["analytic_distribution"] or {})] if ol else None
            if got != [want]:
                problems.append(f"{b['ref']} line '{pl[1]}' analytic {got} != {want}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8071")
    ap.add_argument("--db", default="demo_retail")
    a = ap.parse_args(argv)
    log(f"Odoo {wait_ready(a.url)} at {a.url}")
    if ensure_database(a.url, a.db):
        log(f"database {a.db} created (country SK, no demo data)")
    o = Odoo(a.url, a.db)
    log("modules installed: " + ", ".join(install_modules(o, ["account", "l10n_sk"])))
    setup_admin_groups(o)
    setup_company(o)
    analytic = setup_analytic(o)
    vendors = setup_vendors(o, analytic)
    setup_payment_week_field(o)
    n = create_bills(o, vendors, analytic, accounts(o), purchase_tax(o))
    log(f"company {md.COMPANY['name']} · stores {len(md.STORES)} + HQ · vendors {len(vendors)} · bills created now {n}")
    problems = readback(o, analytic)
    for p in problems:
        log("  FAIL " + p)
    total = sum(md.bill_total(b) for b in md.bills_plan())
    log(f"readback: {len(md.bills_plan())} bills, {total:.2f} EUR gross — {'PASS' if not problems else 'FAIL'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
