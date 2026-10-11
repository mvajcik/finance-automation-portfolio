"""Master data and the deterministic three-month plan of vendor bills for Demo Retail s.r.o.

Nothing here is real. Vendor names are built to read as fake. Eleven vendors carry an
official *example* IBAN from the SWIFT IBAN Registry (no account holder exists); the other
nine have no bank account on file — their payments show up in the statement without a
counterparty IBAN, which is what a real statement does for direct debits and card fees.

The plan is produced from a fixed seed, so every run of `setup_demo.py` books the same bills
and the regression tests can pin the totals.
"""
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

SEED = 2026
CENT = Decimal("0.01")
MONTHS = [(2026, 7), (2026, 8), (2026, 9)]

COMPANY = {
    "name": "Demo Retail s.r.o.",
    "street": "Ukážková 1", "zip": "811 01", "city": "Bratislava", "country": "SK",
    "iban": "SK3112000000198742637541",     # SWIFT registry example for SK
}

STORES = ["Store North", "Store Centre", "Store South"]
HQ = "HQ"
ANALYTIC_PLAN = "Stores"

# account codes from the Slovak chart (l10n_sk)
ACC = {"goods": "504000", "material": "501000", "energy": "502000", "repairs": "511000",
       "services": "518000", "insurance": "548000", "payable": "321000"}
# bank and suspense accounts are read from the bank journal at run time, not hard-coded

# key, display name, IBAN or None, default analytic (store name, HQ, or None = set per bill line)
VENDORS = [
    ("paper",     "Demo Paper Supply s.r.o.",            "CZ6508000000192000145399", None),
    ("packaging", "Mock Packaging Sp. z o.o.",           "PL61109010140000071219812874", None),
    ("logistics", "Sample Logistics GmbH",               "AT611904300234573201", HQ),
    ("energy",    "Example Energy AG",                   "DE89370400440532013000", None),
    ("furniture", "Fictional Office Furniture BV",       "NL91ABNA0417164300", None),
    ("cleaning",  "Placeholder Cleaning Kft.",           "HU42117730161111101800000000", None),
    ("rent_n",    "Test Rent d.o.o.",                    "SI56263300012039086", "Store North"),
    ("telecom",   "Dummy Telecom SA",                    "BE68539007547034", HQ),
    ("rent_c",    "Sample Properties s.r.o.",            "ES9121000418450200051332", "Store Centre"),
    ("rent_s",    "Mock Realty a.s.",                    "FR1420041010050500013M02606", "Store South"),
    ("security",  "Example Security Services s.r.l.",   "IT60X0542811101000000123456", None),
    ("water",     "Specimen Water Utility s.r.o.",       None, None),
    ("waste",     "Placeholder Waste Management s.r.o.", None, None),
    ("accounting","Demo Accounting Partners s.r.o.",     None, HQ),
    ("software",  "Sample Software Licences s.r.o.",     None, HQ),
    ("marketing", "Test Marketing Agency s.r.o.",        None, HQ),
    ("insurance", "Fictional Insurance a.s.",            None, HQ),
    ("repairs",   "Mock Maintenance Services s.r.o.",    None, None),
    ("pos",       "Example POS Terminals s.r.o.",        None, None),
    ("legal",     "Specimen Legal Advisory s.r.o.",      None, HQ),
]
VENDOR = {v[0]: {"key": v[0], "name": v[1], "iban": v[2], "default_analytic": v[3],
                 "country": (v[2][:2] if v[2] else "SK")} for v in VENDORS}

# vendors with a Slovak VAT invoice (23 %); foreign vendors are booked net (reverse charge left out on purpose)
def vat_rate(vendor_key):
    return Decimal("0.23") if VENDOR[vendor_key]["country"] == "SK" else Decimal("0")


def money(rng, lo, hi):
    return (Decimal(rng.randint(int(lo * 100), int(hi * 100))) / 100).quantize(CENT)


def payment_week(d):
    """ISO week of a date as text, e.g. 2026-W39. This is the value of the custom field x_payment_week."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _bill(rng, counter, vendor, inv_date, due_days, lines, ref_prefix):
    counter[vendor] = counter.get(vendor, 0) + 1
    return {
        "vendor": vendor,
        "ref": f"{ref_prefix}-{inv_date:%Y%m}-{counter[vendor]:03d}",
        "invoice_date": inv_date,
        "due_date": inv_date + timedelta(days=due_days),
        # (account key, label, net amount, analytic: store / HQ / None = let the distribution model decide)
        "lines": [(a, label, Decimal(str(amt)).quantize(CENT), an) for a, label, amt, an in lines],
    }


def bills_plan(seed=SEED):
    """The three months of vendor bills, deterministic for a seed."""
    rng = random.Random(seed)
    counter, plan = {}, []
    rent = {"rent_n": (1850, "RENT-N"), "rent_c": (2400, "RENT-C"), "rent_s": (1620, "RENT-S")}
    for (y, m) in MONTHS:
        d = lambda day: date(y, m, day)
        month = f"{date(y, m, 1):%B %Y}"
        for v, (amt, prefix) in rent.items():             # rent: one vendor per store, analytic by distribution model
            plan.append(_bill(rng, counter, v, d(1), 14, [("services", f"Rent {month}", amt, None)], prefix))
        for s in STORES:                                  # energy: one bill per store, store set on the line
            plan.append(_bill(rng, counter, "energy", d(8), 14,
                              [("energy", f"Electricity {month} {s}", money(rng, 380, 720), s)], "EN"))
            plan.append(_bill(rng, counter, "water", d(18), 14,
                              [("energy", f"Water {month} {s}", money(rng, 60, 140), s)], "WAT"))
        plan.append(_bill(rng, counter, "cleaning", d(5), 30,     # one bill, three lines, one per store
                          [("services", f"Cleaning {month} {s}", a, s) for s, a in zip(STORES, (240, 260, 220))], "CLN"))
        plan.append(_bill(rng, counter, "security", d(10), 30,
                          [("services", f"Security {month} {s}", 310, s) for s in STORES], "SEC"))
        plan.append(_bill(rng, counter, "pos", d(12), 14,
                          [("services", f"POS terminal fees {month} {s}", a, s) for s, a in zip(STORES, (45, 55, 40))], "POS"))
        plan.append(_bill(rng, counter, "waste", d(25), 14,
                          [("services", f"Waste collection {month} {s}", 70, s) for s in STORES], "WST"))
        plan.append(_bill(rng, counter, "telecom", d(15), 14, [("services", f"Telecom {month}", 149.90, None)], "TEL"))
        plan.append(_bill(rng, counter, "accounting", d(20), 14, [("services", f"Bookkeeping {month}", 650, None)], "ACC"))
        plan.append(_bill(rng, counter, "software", d(3), 14, [("services", f"Software licences {month}", 89, None)], "SW"))
        plan.append(_bill(rng, counter, "logistics", d(rng.randint(6, 24)), 14,
                          [("services", f"Store deliveries {month}", money(rng, 410, 890), None)], "LOG"))
        for _ in range(rng.randint(2, 3)):                # goods for resale, store chosen per delivery
            s = rng.choice(STORES)
            plan.append(_bill(rng, counter, "paper", d(rng.randint(2, 26)), 30,
                              [("goods", f"Goods delivery {s}", money(rng, 2500, 7800), s)], "DPS"))
        s = rng.choice(STORES)
        plan.append(_bill(rng, counter, "packaging", d(rng.randint(4, 22)), 30,
                          [("material", f"Packaging {s}", money(rng, 320, 640), s)], "PKG"))
    # one-offs
    plan.append(_bill(rng, counter, "insurance", date(2026, 7, 1), 30, [("insurance", "Shop insurance Q3 2026", 1980, None)], "INS"))
    plan.append(_bill(rng, counter, "repairs", date(2026, 7, 14), 14, [("repairs", "Door repair Store South", 480, "Store South")], "REP"))
    plan.append(_bill(rng, counter, "repairs", date(2026, 9, 9), 14, [("repairs", "Lighting repair Store North", 760, "Store North")], "REP"))
    plan.append(_bill(rng, counter, "furniture", date(2026, 8, 11), 30, [("material", "Shelving Store Centre", 3400, "Store Centre")], "FUR"))
    plan.append(_bill(rng, counter, "marketing", date(2026, 8, 19), 14, [("services", "Back-to-school campaign", 1200, None)], "MKT"))
    plan.append(_bill(rng, counter, "marketing", date(2026, 9, 16), 14, [("services", "Autumn campaign", 2350, None)], "MKT"))
    plan.append(_bill(rng, counter, "legal", date(2026, 9, 2), 14, [("services", "Lease review", 1500, None)], "LEG"))
    plan.sort(key=lambda b: (b["invoice_date"], b["ref"]))
    refs = [b["ref"] for b in plan]
    assert len(refs) == len(set(refs)), "vendor references must be unique (the bank matches on them)"
    return plan


def bill_net(bill):
    return sum(l[2] for l in bill["lines"])


def bill_total(bill):
    """Gross amount as Odoo will compute it: net + VAT per line, rounded per line."""
    rate = vat_rate(bill["vendor"])
    return sum((l[2] + (l[2] * rate).quantize(CENT, ROUND_HALF_UP)) for l in bill["lines"])


def line_analytic(bill, line):
    """Where a line's cost lands: explicit store on the line, else the vendor's default (distribution model)."""
    return line[3] or VENDOR[bill["vendor"]]["default_analytic"]
