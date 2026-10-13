#!/usr/bin/env python3
"""Generátor fiktívnej firmy „Papiernictvo DEMO" — robustné vstupy (9 zdrojov), plná výsledovka.

Fiktívne, deterministické dáta (seed). Obdobie 2025-01 až 2026-09.
Zdroje, zámerne v nepohodlných formátoch, ako chodia z reálnych systémov:
  pos_<SS>_YYYY-MM.csv       bločky: hlavička exportu, `;`, desatinná čiarka, riadok TOTAL
  journal_YYYY-MM.csv        účtovný denník (MD/D, stredisko): `,`, BOM, dátum dd.mm.yyyy
  trial_balance_YYYY-MM.xlsx obraty MD/D stredisko × účet (vrátane súvahových účtov)
  invoices_YYYY-MM.xlsx      kniha došlých faktúr: nadpis nad tabuľkou, dátumy ako dátumy
  payroll_YYYY-MM.csv        mzdový export v kódovaní Windows-1250
  bank_YYYY-MM.csv           výpis: počiatočný / konečný zostatok v hlavičke a pätičke
  stock_moves_YYYY-MM.csv    príjemky a výdajky v nákupných cenách
  stock_levels_YYYY-MM.csv   stav zásob predajňa × kategória
  plan_2026.xlsx             plán výsledovky účet × stredisko × mesiac (celý rok 2026)
  master_data.xlsx           účtový rozvrh, strediská, kategórie, dodávatelia
Všetky sumy sa počítajú v centoch (int) — podvojnosť a súčty sedia presne.
Etalón (truth.json) a príbehy počíta TENTO kód, nie motor. Parametre: profiles/papiernictvo2/calibration.json.
Použitie: python3 tools/gen_papiernictvo2.py [--out DIR] [--seed 2026] [--no-stories]
"""
import argparse
import calendar
import datetime as dt
import hashlib
import io
import json
import random
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "papiernictvo2"
FIXED = dt.datetime(2026, 1, 1)

# účet: (názov, typ B=súvaha / E=náklad / R=výnos / C=závierkový, riadok výsledovky)
ACCOUNTS = {
    "022": ("Movable fixed assets", "B", None), "082": ("Accumulated depreciation — movable assets", "B", None),
    "132": ("Goods in stock", "B", None), "211": ("Cash on hand", "B", None), "221": ("Bank accounts", "B", None),
    "315": ("Card payment receivables", "B", None), "321": ("Trade payables", "B", None),
    "331": ("Employees", "B", None), "336": ("Social and health insurance", "B", None),
    "341": ("Income tax", "B", None), "342": ("Other direct taxes", "B", None), "343": ("VAT", "B", None),
    "461": ("Bank loans", "B", None), "411": ("Share capital", "B", None),
    "428": ("Retained earnings", "B", None), "701": ("Opening balance sheet account", "C", None),
    "501": ("Materials consumed", "E", "Other"), "502": ("Energy consumed", "E", "Energy"),
    "504": ("Goods sold", "E", "Cost of goods sold"), "511": ("Repairs and maintenance", "E", "Services"),
    "518100": ("Rent", "E", "Rent"), "518200": ("IT services", "E", "Services"),
    "518300": ("Accounting services", "E", "Services"), "518400": ("Telecommunications", "E", "Services"),
    "518500": ("Marketing", "E", "Marketing"), "521": ("Wages and salaries", "E", "Staff"),
    "524": ("Statutory social insurance", "E", "Staff"), "551": ("Depreciation", "E", "Depreciation"),
    "562": ("Interest", "E", "Interest and financial"), "568": ("Other financial costs — card fees", "E", "Other"),
    "591": ("Income tax — current", "E", "Income tax"), "604": ("Revenue from goods", "R", "Revenue"),
}
PL_ROWS = ["Revenue", "Cost of goods sold", "Gross margin", "Staff", "Rent", "Energy", "Marketing",
           "Services", "Other", "EBITDA", "Depreciation", "EBIT", "Interest and financial", "Profit before tax",
           "Income tax", "Net profit"]
PL_SUBTOTALS = {"Gross margin": ["Revenue", "Cost of goods sold"],
                "EBITDA": ["Revenue", "Cost of goods sold", "Staff", "Rent", "Energy", "Marketing", "Services", "Other"],
                "EBIT": ["EBITDA", "Depreciation"], "Profit before tax": ["EBIT", "Interest and financial"],
                "Net profit": ["Profit before tax", "Income tax"]}
SUPPLIERS = {  # fiktívni dodávatelia (IČO vymyslené)
    "Stationery": ("Paper Distribution DEMO s.r.o.", "90000011"), "Books": ("Book Wholesale DEMO a.s.", "90000022"),
    "Toys": ("Toys Import DEMO s.r.o.", "90000033"), "Gifts": ("Gift Trade DEMO s.r.o.", "90000044"),
    "518100": ("Real Estate DEMO s.r.o.", "90000055"), "502": ("Energy DEMO a.s.", "90000066"),
    "518200": ("IT Service DEMO s.r.o.", "90000077"), "518300": ("Accounting DEMO s.r.o.", "90000088"),
    "518400": ("Telecom DEMO a.s.", "90000099"), "518500": ("Advertising DEMO s.r.o.", "90000101"),
    "511": ("Maintenance DEMO s.r.o.", "90000112"), "501": ("Office Supplies DEMO s.r.o.", "90000123"),
}
# Poradie kategórií v súboroch = poradie spred prekladu (abecedne po slovensky: Darčeky, Hračky, Knihy,
# Papiernictvo). Triedenie podľa anglického mena by zmenilo poradie riadkov a poradie sčítania — čísla majú ostať.
CAT_ORDER = {"Gifts": 0, "Toys": 1, "Books": 2, "Stationery": 3}
PAY_WORD = {"H": "cash", "K": "card"}          # interný kód platby (H hotovosť / K karta) → slovo v súboroch


def cat_key(k):
    return (CAT_ORDER.get(k, len(CAT_ORDER)), k)


def months(start, n):
    y, m = map(int, start.split("-"))
    for _ in range(n):
        yield f"{y}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def c(x):
    """€ → centy (int)."""
    return int(round(x * 100))


def eur(cents, sep="."):
    s = f"{cents / 100:.2f}"
    return s.replace(".", sep)


def save_xlsx(wb, path: Path):
    """Deterministický xlsx: pevný čas v docProps aj v zipe (bajtovo rovnaký výstup pri každom behu)."""
    buf = io.BytesIO()
    wb.save(buf)
    zin = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in sorted(zin.infolist(), key=lambda i: i.filename):
            data = zin.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:(created|modified)[^>]*>)[^<]*", rb"\g<1>2026-01-01T00:00:00Z", data)
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zo.writestr(zi, data)
    path.write_bytes(out.getvalue())


class Books:
    """Podvojné účtovníctvo v centoch + banka + sklad + faktúry + mzdy."""

    def __init__(self):
        self.journal = []      # (doklad, date, md, d, cents, cc, text)
        self.bank = []         # (date, protistrana, iban, vs, cents(+/-), popis)
        self.invoices = []     # dict
        self.payroll = []      # dict
        self.stock_moves = []  # (doklad, date, typ, cc, cat, cents)
        self.seq = {}

    def doc(self, prefix, date):
        k = (prefix, date.year)
        self.seq[k] = self.seq.get(k, 0) + 1
        return f"{prefix}{date.year}{self.seq[k]:05d}"

    def post(self, doklad, date, md, d, cents, cc, text):
        if cents == 0:
            return
        if cents < 0:
            md, d, cents = d, md, -cents
        self.journal.append((doklad, date, md, d, cents, cc, text))


def open_days(cal):
    closed = set(cal["closed_days"])
    return lambda day: cal["weekday"][day.weekday()] > 0 and day.isoformat() not in closed


def bank_day(day, is_open_bank):
    d = day + dt.timedelta(days=1)
    while not is_open_bank(d):
        d += dt.timedelta(days=1)
    return d


def gen(cal, seed, stories):
    rng = random.Random(seed)
    per = cal["period"]
    ms = list(months(per["start"], per["months"]))
    first = dt.date.fromisoformat(ms[0] + "-01")
    y_last, m_last = map(int, ms[-1].split("-"))
    last = dt.date(y_last, m_last, calendar.monthrange(y_last, m_last)[1])
    y1 = first.year
    is_open = open_days(cal)
    closed = set(cal["closed_days"])
    is_bank = lambda d: d.weekday() < 5 and d.isoformat() not in closed  # noqa: E731
    cats = cal["categories"]
    cat_names = list(cats)
    shops = [x for x in cal["cost_centers"] if x["daily_gross"] > 0]
    st = cal["stories"]
    B = Books()
    pos = {}              # (cc, ym) → [riadky bločkov]
    pos_total = {}        # (cc, ym) → centy
    # počiatočné stavy
    stock = {(s["code"], k): c(s["daily_gross"] * 26 * cats[k]["share"] / (1 + cats[k]["vat"]) * (1 - cats[k]["margin"])
                               * cal["stock"]["cover_months"]) for s in shops for k in cat_names}
    open_doc = B.doc("PS", first)
    for (cc, k), v in sorted(stock.items(), key=lambda x: (x[0][0], cat_key(x[0][1]))):
        B.post(open_doc, first, "132", "701", v, cc, f"Opening stock {k}")
    B.post(open_doc, first, "221", "701", c(cal["opening"]["bank"]), "C00", "Opening bank balance")
    B.post(open_doc, first, "701", "461", c(cal["loan"]["principal"]), "C00", "Opening loan balance")
    for cc, dep in cal["fixed_assets"]["depreciation_monthly"].items():
        B.post(open_doc, first, "022", "701", c(dep * 60), cc, "Opening fixed assets")
    op = cal["opening"]
    B.post(open_doc, first, "701", "321", c(op["payables_321"]), "C00", "Opening trade payables")
    B.post(open_doc, first, "701", "411", c(op["equity_411"]), "C00", "Share capital")
    plug = sum(v if dd == "701" else -v for _, _, md, dd, v, _, _ in B.journal if "701" in (md, dd))
    B.post(open_doc, first, "701", "428", plug, "C00", "Retained earnings")
    loan = c(cal["loan"]["principal"])
    cash_box = {s["code"]: 0 for s in shops}
    card_pending = []      # (settle_day, cc, gross_cents, sale_day)
    receipt_no = {}
    rev_month = {}         # (cc, ym) → čisté tržby centy (pre marketing a plán)
    cost_month = {}        # (cc, cat, ym) → výdaj v nákupných cenách
    purchase_due = {}      # faktúry na úhradu: day → list
    state_due = [(dt.date(first.year, 1, 15), "Payment of liabilities as at 2024-12-31", c(cal["opening"]["payables_321"]),
                  "Payment of liabilities as at 2024-12-31", "PS2024", "321")]
    dv = cal["dividend"]
    state_due.append((dt.date.fromisoformat(dv["month"] + "-20"), "Dividend payout", c(dv["amount"]),
                      "Shareholder DEMO", "DIV" + dv["month"][:4], "428"))
    day = first
    while day <= last:
        ym = day.strftime("%Y-%m")
        y, m = day.year, day.month
        # ---- predaj
        if is_open(day):
            for s in shops:
                cc = s["code"]
                growth = (1 + s["growth_y2"]) if y > y1 else 1.0
                mix = {}
                for k in cat_names:
                    f = cats[k]["share"] * (cats[k]["season"][m - 1] if stories else 1.0)   # bez príbehov vyrovnaná sezóna
                    if stories and y > y1 and k == st["S2_toys_decline"]["category"]:
                        f *= 1 + st["S2_toys_decline"]["yoy_by_quarter_y2"][min((m - 1) // 3, 2)]
                    if stories and k == st["S4_school_boost"]["category"] and ym in st["S4_school_boost"]["months"]:
                        f *= st["S4_school_boost"]["factor"]
                    mix[k] = f
                target = s["daily_gross"] * cal["weekday"][day.weekday()] * growth * sum(mix.values())
                # mix = podiel na TRŽBÁCH; riadok sa vyberá váhou mix ÷ cena položky (lacný papier = viac riadkov)
                lw = {k: mix[k] / cats[k]["unit_price"] for k in cat_names}
                avg_line = sum(lw[k] * cats[k]["unit_price"] * 1.6 for k in cat_names) / sum(lw.values())
                n_lines = max(0, int(rng.gauss(target / avg_line, (target / avg_line) ** 0.5)))
                agg = {}      # (vat, pay) → gross
                cat_gross = {k: 0 for k in cat_names}
                regs = cal["pos"]["registers"][cc]
                made = 0
                while made < n_lines:
                    k_lines = rng.choices([1, 2, 3], cal["pos"]["lines_per_receipt"])[0]
                    reg = rng.randint(1, regs)
                    receipt_no[(cc, reg)] = receipt_no.get((cc, reg), 0) + 1
                    rid = f"{cc}-{reg}-{receipt_no[(cc, reg)]:07d}"
                    t = dt.datetime.combine(day, dt.time(9, 0)) + dt.timedelta(minutes=rng.randint(0, 540))
                    pay = "K" if rng.random() < cal["pos"]["card_share"] else "H"
                    for _ in range(k_lines):
                        k = rng.choices(cat_names, [lw[x] for x in cat_names])[0]
                        qty = rng.choices([1, 2, 3], [0.7, 0.2, 0.1])[0]
                        unit = c(max(0.5, rng.lognormvariate(0, 0.45) * cats[k]["unit_price"]))
                        g = unit * qty
                        vat = cats[k]["vat"]
                        pos.setdefault((cc, ym), []).append((rid, t, reg, k, qty, unit, int(vat * 100), g, pay))
                        agg[(vat, pay)] = agg.get((vat, pay), 0) + g
                        cat_gross[k] += g
                        made += 1
                d_pos = B.doc("PK", day)
                for (vat, pay), g in sorted(agg.items()):
                    net = int(round(g / (1 + vat)))
                    acc = "211" if pay == "H" else "315"
                    B.post(d_pos, day, acc, "604", net, cc, f"Revenue {PAY_WORD[pay]} {int(vat * 100)}%")
                    B.post(d_pos, day, acc, "343", g - net, cc, f"VAT {PAY_WORD[pay]} {int(vat * 100)}%")
                    rev_month[(cc, ym)] = rev_month.get((cc, ym), 0) + net
                    if pay == "H":
                        cash_box[cc] += g
                    else:
                        card_pending.append((bank_day(day, is_bank), cc, g, day))
                for k in cat_names:
                    if cat_gross[k]:
                        cost = int(round(cat_gross[k] / (1 + cats[k]["vat"]) * (1 - cats[k]["margin"])))
                        B.stock_moves.append((B.doc("VY", day), day, "issue", cc, k, cost))
                        stock[(cc, k)] -= cost
                        cost_month[(cc, k, ym)] = cost_month.get((cc, k, ym), 0) + cost
        # ---- banka: pripísanie kariet, vklad hotovosti, úhrady
        if is_bank(day):
            for item in [x for x in card_pending if x[0] == day]:
                _, cc, g, sale = item
                fee = int(round(g * cal["pos"]["card_fee"]))
                dk = B.doc("BV", day)
                B.post(dk, day, "221", "315", g - fee, cc, f"Cards {sale:%d.%m.}")
                B.post(dk, day, "568", "315", fee, cc, f"Card fee {sale:%d.%m.}")
                B.bank.append((day, "Card Centre DEMO", "SK0000000000000000000001", sale.strftime("%d%m"),
                               g - fee, f"Settlement {cc} {sale:%d.%m.%Y}"))
            card_pending = [x for x in card_pending if x[0] != day]
            if day.weekday() == 0:
                for cc in sorted(cash_box):
                    if cash_box[cc]:
                        dk = B.doc("BV", day)
                        B.post(dk, day, "221", "211", cash_box[cc], cc, "Cash deposit")
                        B.bank.append((day, f"Cash deposit {cc}", "", "", cash_box[cc], "Takings deposit"))
                        cash_box[cc] = 0
            for inv in purchase_due.pop(day, []):
                dk = B.doc("BV", day)
                for acct, v in inv.get("lines", [("321", inv["total"])]):
                    B.post(dk, day, acct, "221", v, inv["cc"], f"Payment {inv['cislo']}")
                B.bank.append((day, inv["dodavatel"], f"SK00000000000000{inv['ico']}", re.sub(r"\D", "", inv["cislo"])[-10:],
                               -inv["total"], f"Payment {inv['cislo']}"))

        def invoice(acct, cc, base, vat_rate, due_days, text, cat=None):
            sup, ico = SUPPLIERS[cat or acct]
            vat = int(round(base * vat_rate))
            cislo = B.doc("FD", day)
            inv = {"cislo": cislo, "dodavatel": sup, "ico": ico, "datum": day, "splatnost": day + dt.timedelta(days=due_days),
                   "ucet": acct, "cc": cc, "zaklad": base, "dph": vat, "total": base + vat, "text": text}
            B.invoices.append(inv)
            B.post(cislo, day, acct, "321", base, cc, text)
            B.post(cislo, day, "343", "321", vat, cc, f"VAT {text}")
            pay_day = inv["splatnost"]
            while not is_bank(pay_day):
                pay_day += dt.timedelta(days=1)
            purchase_due.setdefault(pay_day, []).append(inv)
            return inv
        # ---- úhrady voči štátu a spoločníkovi (vždy na nasledujúci bankový deň od termínu)
        if is_bank(day):
            for due, kind, amt, who, vs, acct in [x for x in state_due if x[0] <= day]:
                dk = B.doc("BV", day)
                B.post(dk, day, acct, "221", amt, "C00", kind)
                B.bank.append((day, who, "", vs, -amt, kind))
            state_due[:] = [x for x in state_due if x[0] > day]
        # ---- nákup tovaru (týždenne, pondelok)
        if day.weekday() == 0 and is_bank(day):
            for s in shops:
                for k in cat_names:
                    need = c(s["daily_gross"] * 26 * cats[k]["share"] * (cats[k]["season"][m - 1] if stories else 1.0)
                             / (1 + cats[k]["vat"])
                             * (1 - cats[k]["margin"]) * cal["stock"]["cover_months"]) - stock[(s["code"], k)]
                    if need > 0:
                        inv = invoice("132", s["code"], need, cats[k]["vat"], 30, f"Goods {k}", cat=k)
                        B.stock_moves.append((inv["cislo"], day, "receipt", s["code"], k, need))
                        stock[(s["code"], k)] += need
        # ---- mesačné služby (1. deň) a mesačná závierka (posledný deň)
        if day.day == 1:
            sv = cal["services"]
            for cc_ in [x["code"] for x in cal["cost_centers"]]:
                rent = sv["rent"][cc_]
                if stories and cc_ == st["S1_rent_jump"]["cost_center"] and ym >= st["S1_rent_jump"]["from"]:
                    rent = st["S1_rent_jump"]["new_rent"]
                invoice("518100", cc_, c(rent), 0.23, 14, f"Rent {ym}")
                invoice("518400", cc_, c(sv["telecom"][cc_]), 0.23, 14, f"Telecom {ym}")
            invoice("518200", "C00", c(sv["it"]["C00"]), 0.23, 14, f"IT services {ym}")
            invoice("518300", "C00", c(sv["accounting"]["C00"]), 0.23, 14, f"Accounting {ym}")
        if day == dt.date(y, m, calendar.monthrange(y, m)[1]):
            sv = cal["services"]
            prev = sum(v for (cc_, ym_), v in rev_month.items() if ym_ == ym)
            invoice("518500", "C00", int(round(prev * sv["marketing_share"])), 0.23, 30, f"Marketing {ym}")
            for cc_ in [x["code"] for x in cal["cost_centers"]]:
                e = sv["energy"][cc_] * sv["season_energy"][m - 1]
                s3 = st["S3_energy_spike"]
                if stories and s3["from"] <= ym <= s3["to"]:
                    e *= s3["factor"]
                invoice("502", cc_, c(e), 0.23, 14, f"Energy {ym}")
                invoice("501", cc_, c(rng.uniform(40, 140)), 0.23, 14, f"Materials {ym}")
                if rng.random() < 0.4:
                    invoice("511", cc_, c(rng.uniform(80, sv["repairs_max"])), 0.23, 14, f"Repairs {ym}")
            # COGS: výdaj zo skladu → 504/132 (stredisko × kategória)
            dk = B.doc("ID", day)
            for s in shops:
                for k in cat_names:
                    B.post(dk, day, "504", "132", cost_month.get((s["code"], k, ym), 0), s["code"], f"Goods sold {k} {ym}")
            # mzdy
            pr = cal["payroll"]
            dk = B.doc("MZ", day)
            per_cc = {}
            emp_no = 0
            for x in cal["cost_centers"]:
                for pos_name, n in x["staff"].items():
                    for i in range(n):
                        emp_no += 1
                        gross = pr["gross"][pos_name] * ((1 + pr["raise_y2"]) if y > y1 else 1.0)
                        gross *= 1 + rng.uniform(-0.02, 0.06)
                        if m == 12:
                            gross *= 1 + pr["december_bonus"]
                        g = c(gross)
                        er, ee = int(round(g * pr["employer"])), int(round(g * pr["employee"]))
                        tax = max(0, int(round((g - ee - c(pr["allowance"])) * pr["tax"])))
                        net = g - ee - tax
                        B.payroll.append({"os": f"Z{emp_no:03d}", "cc": x["code"], "pozicia": pos_name, "ym": ym,
                                          "hruba": g, "odvody_zamestnavatel": er, "odvody_zamestnanec": ee, "dan": tax,
                                          "cista": net})
                        a = per_cc.setdefault(x["code"], [0, 0, 0, 0, 0])
                        for j, v in enumerate((g, er, ee, tax, net)):
                            a[j] += v
            pay_day = dt.date(y + (m == 12), m % 12 + 1, 10)
            while not is_bank(pay_day):
                pay_day += dt.timedelta(days=1)
            for cc_, (g, er, ee, tax, net) in sorted(per_cc.items()):
                B.post(dk, day, "521", "331", g, cc_, f"Gross pay {ym}")
                B.post(dk, day, "524", "336", er, cc_, f"Employer contributions {ym}")
                B.post(dk, day, "331", "336", ee, cc_, f"Employee contributions {ym}")
                B.post(dk, day, "331", "342", tax, cc_, f"Payroll tax {ym}")
                purchase_due.setdefault(pay_day, []).append(
                    {"cislo": f"PAYROLL{ym.replace('-', '')}{cc_}", "dodavatel": f"Payroll payout {cc_}", "ico": "00000000",
                     "cc": cc_, "total": net, "lines": [("331", net)]})
                purchase_due[pay_day].append({"cislo": f"CONTRIB{ym.replace('-', '')}{cc_}", "dodavatel": "Insurers and Tax Office DEMO",
                                              "ico": "00000001", "cc": cc_, "total": er + ee + tax,
                                              "lines": [("336", er + ee), ("342", tax)]})
            # odpisy, úver
            dk = B.doc("OD", day)
            for cc_, dep in cal["fixed_assets"]["depreciation_monthly"].items():
                B.post(dk, day, "551", "082", c(dep), cc_, f"Depreciation {ym}")
            interest = int(round(loan * cal["loan"]["rate"] / 12))
            dk = B.doc("BV", day)
            B.post(dk, day, "562", "221", interest, "C00", f"Interest {ym}")
            B.post(dk, day, "461", "221", c(cal["loan"]["monthly_repayment"]), "C00", f"Loan repayment {ym}")
            B.bank.append((day, "Bank DEMO — loan", "", "LOAN", -interest, f"Interest {ym}"))
            B.bank.append((day, "Bank DEMO — loan", "", "LOAN", -c(cal["loan"]["monthly_repayment"]), f"Loan repayment {ym}"))
            loan -= c(cal["loan"]["monthly_repayment"])
            # daň z príjmov: priebežný odhad 21 % z YTD zisku pred zdanením
            ytd = 0                                   # zisk pred zdanením od začiatku roka: výnosy (D 6xx) − náklady (MD 5xx)
            for doc_, d_, md, dd, v, cc_, _ in B.journal:
                if d_.year == y:
                    if md[0] in "56" and md != "591":
                        ytd -= v
                    if dd[0] in "56" and dd != "591":
                        ytd += v
            accrued = sum(v for _, d_, md, dd, v, _, _ in B.journal if d_.year == y and md == "591") - \
                sum(v for _, d_, md, dd, v, _, _ in B.journal if d_.year == y and dd == "591")
            tax_m = int(round(max(0, ytd) * cal["income_tax"]["rate"])) - accrued
            B.post(B.doc("DZ", day), day, "591", "341", tax_m, "C00", f"Income tax — interim {ym}")
            nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
            if tax_m > 0:                                      # preddavok dane nasledujúci mesiac
                state_due.append((nxt.replace(day=20), f"Income tax advance payment {ym}", tax_m,
                                  "Tax Office DEMO — income tax", "CIT" + ym.replace("-", ""), "341"))
            vat = sum(v for _, d_, md, dd, v, _, _ in B.journal if dd == "343") - \
                sum(v for _, d_, md, dd, v, _, _ in B.journal if md == "343") - \
                sum(x[2] for x in state_due if x[5] == "343")   # otvorený záväzok DPH (nadmerný odpočet sa prenáša)
            if vat > 0:                                         # DPH za mesiac splatná 25. nasledujúceho
                state_due.append((nxt.replace(day=25), f"VAT {ym}", vat, "Tax Office DEMO — VAT",
                                  "VAT" + ym.replace("-", ""), "343"))
        day += dt.timedelta(days=1)
    # úhrady miezd/odvodov ležia v purchase_due: prehrať tie, čo padli do obdobia (kvôli jednoduchosti druhý prechod)
    return B, pos, stock, ms, rev_month


# ------------------------------------------------------------------ zápis súborov
def write_set(cal, out: Path, B, pos, ms, plan_rows, errors=None):
    from openpyxl import Workbook
    errors = errors or {}
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    names = {x["code"]: x["name"] for x in cal["cost_centers"]}
    for (cc, ym), rows in sorted(pos.items()):
        y, m = map(int, ym.split("-"))
        total = sum(r[7] for r in rows)
        rows_out = rows[:-15] if errors.get("E6") == (cc, ym) else rows          # E6: orezaný export, SPOLU ostáva
        lines = [f"POS export v2.3;{names[cc]} ({cc})",
                 f"Period;01.{m:02d}.{y} - {calendar.monthrange(y, m)[1]:02d}.{m:02d}.{y}",
                 f"Created;{dt.date(y + (m == 12), m % 12 + 1, 1):%d.%m.%Y} 06:00", "",
                 "receipt;datetime;till;category;quantity;unit_price_incl_vat;vat_rate;total_incl_vat;payment"]
        lines += [f"{rid};{t:%d.%m.%Y %H:%M};{reg};{k};{q};{eur(u, ',')};{v};{eur(g, ',')};{PAY_WORD[p]}"
                  for rid, t, reg, k, q, u, v, g, p in rows_out]
        lines.append(f"TOTAL;;;;;;;{eur(total, ',')};")
        (out / f"pos_{cc}_{ym}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    journal = [j for j in B.journal if not (errors.get("E1") and j[0] == errors["E1"])]
    for ym in ms:
        rows = [j for j in journal if j[1].strftime("%Y-%m") == ym]
        txt = "Document,Date,Dr,Cr,Amount,Cost centre,Description\n" + "".join(
            f'{d},{t:%d.%m.%Y},{md},{dd},{eur(v)},{cc},"{txt}"\n' for d, t, md, dd, v, cc, txt in rows)
        (out / f"journal_{ym}.csv").write_bytes(b"\xef\xbb\xbf" + txt.encode("utf-8"))
        # predvaha = obraty z denníka (stredisko × účet)
        tb = {}
        for d, t, md, dd, v, cc, _ in rows:
            tb.setdefault((cc, md), [0, 0])[0] += v
            tb.setdefault((cc, dd), [0, 0])[1] += v
        if errors.get("E5") and errors["E5"][0] == ym:
            tb[(errors["E5"][1], errors["E5"][2])][0] += c(250)                 # E5: ručná úprava predvahy
        wb = Workbook(); ws = wb.active; ws.title = "Trial balance"
        ws.append(["Period", "Cost centre", "Account", "Account name", "Debit turnover", "Credit turnover"])
        for (cc, acc), (md, dd) in sorted(tb.items()):
            ws.append([ym, cc, acc, ACCOUNTS[acc][0], md / 100, dd / 100])
        save_xlsx(wb, out / f"trial_balance_{ym}.xlsx")
        # kniha došlých faktúr
        wb = Workbook(); ws = wb.active; ws.title = "Received invoices"
        ws.append([f"Received invoice register — Papiernictvo DEMO s.r.o. — {ym}"]); ws.append([])
        ws.append(["Number", "Supplier", "Company ID", "Issue date", "Due date", "Account", "Cost centre", "Text",
                   "Net", "VAT", "Total"])
        for inv in B.invoices:
            if inv["datum"].strftime("%Y-%m") == ym:
                ws.append([inv["cislo"], inv["dodavatel"], inv["ico"], inv["datum"], inv["splatnost"], inv["ucet"],
                           inv["cc"], inv["text"], inv["zaklad"] / 100, inv["dph"] / 100, inv["total"] / 100])
        save_xlsx(wb, out / f"invoices_{ym}.xlsx")
        # mzdy (Windows-1250)
        pr = [p for p in B.payroll if p["ym"] == ym]
        txt = "employee_no;cost_centre;position;gross_pay;employer_contributions;employee_contributions;tax;net_pay\n"
        e2 = next((p for p in pr if errors.get("E2") == (ym, p["cc"])), None)   # E2: jedna mzda iná než v 521
        for p in pr:
            h = p["hruba"] + (c(150) if p is e2 else 0)
            txt += (f"{p['os']};{p['cc']};{p['pozicia']};{eur(h, ',')};{eur(p['odvody_zamestnavatel'], ',')};"
                    f"{eur(p['odvody_zamestnanec'], ',')};{eur(p['dan'], ',')};{eur(p['cista'], ',')}\n")
        (out / f"payroll_{ym}.csv").write_bytes(txt.encode("cp1250"))
        # banka
        bl = [b for b in B.bank if b[0].strftime("%Y-%m") == ym]
        if errors.get("E7") and errors["E7"][0] == ym:
            drop = next(b for b in bl if b[1] == "Card Centre DEMO" and errors["E7"][1] in b[5])
            bl = [b for b in bl if b is not drop]
        if errors.get("E3") and errors["E3"] == ym:
            bl.append((bl[-1][0], "Unknown Supplier DEMO s.r.o.", "SK0000000000000090009999", "2026999999", -c(1830.50),
                       "Invoice payment"))
        opening = c(45000) + sum(b[4] for b in B.bank if b[0].strftime("%Y-%m") < ym)
        closing = opening + sum(b[4] for b in bl)
        y, m = map(int, ym.split("-"))
        txt = (f"Account statement;SK99 9900 0000 0012 3456 7890\nPeriod;01.{m:02d}.{y} - "
               f"{calendar.monthrange(y, m)[1]:02d}.{m:02d}.{y}\nOpening balance;{eur(opening, ',')}\n\n"
               "Date;Counterparty;Counterparty IBAN;Reference;Amount;Currency;Description\n")
        txt += "".join(f"{d:%d.%m.%Y};{who};{iban};{vs};{eur(v, ',')};EUR;{pop}\n" for d, who, iban, vs, v, pop in bl)
        txt += f"\nClosing balance;{eur(closing, ',')}\n"
        (out / f"bank_{ym}.csv").write_text(txt, encoding="utf-8")
        # sklad
        mv = [x for x in B.stock_moves if x[1].strftime("%Y-%m") == ym]
        if errors.get("E4") and errors["E4"][0] == ym:
            _, cc4, k4 = errors["E4"]
            have = sum(v if t == "receipt" else -v for _, d_, t, cc_, k_, v in B.stock_moves
                       if cc_ == cc4 and k_ == k4 and d_.strftime("%Y-%m") <= ym) + \
                next(x[4] for x in B.journal if x[0].startswith("PS") and x[2] == "132" and x[5] == cc4 and x[6].endswith(k4))
            mv = mv + [(f"VY{ym[:4]}99999", mv[-1][1], "issue", cc4, k4, have + c(350))]   # výdaj o 350 € nad zásobu
        txt = "document;date;type;store;category;cost_value\n" + "".join(
            f"{d};{t:%Y-%m-%d};{typ};{cc};{k};{v / 100:.2f}\n" for d, t, typ, cc, k, v in mv)
        (out / f"stock_moves_{ym}.csv").write_text(txt, encoding="utf-8")
    # stav zásob po mesiacoch (z pohybov v zapísanom súbore — konzistentné aj pri E4)
    bal = {}
    for x in B.journal:
        if x[0].startswith("PS") and x[2] == "132":
            bal[(x[5], x[6].replace("Opening stock ", ""))] = x[4]
    for ym in ms:
        mv = [l.split(";") for l in (out / f"stock_moves_{ym}.csv").read_text(encoding="utf-8").splitlines()[1:]]
        txt = "store;category;opening;received;issued;closing\n"
        for key in sorted(bal, key=lambda x: (x[0], cat_key(x[1]))):
            pr_ = sum(c(float(r[5])) for r in mv if (r[3], r[4]) == key and r[2] == "receipt")
            vy_ = sum(c(float(r[5])) for r in mv if (r[3], r[4]) == key and r[2] == "issue")
            end = bal[key] + pr_ - vy_
            txt += f"{key[0]};{key[1]};{bal[key] / 100:.2f};{pr_ / 100:.2f};{vy_ / 100:.2f};{end / 100:.2f}\n"
            bal[key] = end
        (out / f"stock_levels_{ym}.csv").write_text(txt, encoding="utf-8")
    # plán 2026
    wb = Workbook(); ws = wb.active; ws.title = "Plan 2026"
    ws.append(["Account", "Cost centre"] + [f"2026-{m:02d}" for m in range(1, 13)])
    for (acc, cc), vals in sorted(plan_rows.items()):
        ws.append([acc, cc] + [v / 100 for v in vals])
    save_xlsx(wb, out / "plan_2026.xlsx")
    # číselníky
    wb = Workbook(); ws = wb.active; ws.title = "Accounts"
    ws.append(["Account", "Name", "Type", "P&L line"])
    for a, (n, t, r) in sorted(ACCOUNTS.items()):
        ws.append([a, n, t, r])
    ws = wb.create_sheet("Cost centres"); ws.append(["Code", "Name"])
    for x in cal["cost_centers"]:
        ws.append([x["code"], x["name"]])
    ws = wb.create_sheet("Categories"); ws.append(["Category", "VAT rate"])
    for k, v in cal["categories"].items():
        ws.append([k, int(v["vat"] * 100)])
    ws = wb.create_sheet("Suppliers"); ws.append(["Company ID", "Name"])
    for n, ico in sorted(set(SUPPLIERS.values()), key=lambda x: x[1]):
        ws.append([ico, n])
    save_xlsx(wb, out / "master_data.xlsx")


def plan_of(cal, B, ms):
    """Plán 2026 = skutočnosť 2025 rovnakého mesiaca × ambícia (tržby) / zmluvy (nájom, služby);
    vedenie o príbehoch 2026 pri plánovaní nevedelo."""
    y1 = ms[0][:4]
    act = {}
    for d, t, md, dd, v, cc, _ in B.journal:
        if t.strftime("%Y") != y1:
            continue
        for acc, sgn in ((md, 1), (dd, -1)):
            if ACCOUNTS[acc][1] in "ER" and acc != "591":
                k = (acc, cc)
                act.setdefault(k, [0] * 12)[t.month - 1] += sgn * v
    amb = 1 + cal["plan_2026"]["revenue_ambition"]
    plan = {}
    for (acc, cc), vals in act.items():
        f = amb if acc in ("604", "504", "568", "518500") else (1 + cal["payroll"]["raise_y2"] if acc in ("521", "524") else 1.0)
        plan[(acc, cc)] = [int(round(abs(v) * f)) for v in vals]
    return plan


def pl_of(cal, journal, year, upto="12"):
    """Výsledovka (znamienková: výnosy +, náklady −) po strediskách a riadkoch z denníka generátora."""
    t = {}
    for d, dt_, md, dd, v, cc, _ in journal:
        if dt_.strftime("%Y") != year or dt_.strftime("%m") > upto:
            continue
        for acc, sgn in ((md, -1), (dd, 1)):
            row = ACCOUNTS[acc][2]
            if row:
                t[(cc, row)] = t.get((cc, row), 0) + sgn * v
    ccs = sorted({x["code"] for x in cal["cost_centers"]})
    for sub, parts in PL_SUBTOTALS.items():
        for cc in ccs:
            t[(cc, sub)] = sum(t.get((cc, p), 0) for p in parts)
    for r in PL_ROWS:
        t[("Total", r)] = sum(t.get((cc, r), 0) for cc in ccs)
    return t


def boardpack_truth(cal, B, plan):
    """Kotva A board packu — vlastným kódom generátora z jeho denníka a plánu (nie z motora ani jeho SQL):
    plán a odhad roka po riadkoch výsledovky. Metóda (parametre z profilu → board_pack): mesiac zvyšku roka =
    plán × (skutočnosť ÷ plán za posledné N mesiacov) po stredisku a riadku, bez plánu priemer N mesiacov;
    daň (aj v pláne) = −sadzba × zisk pred zdanením mesiaca, na centrálu."""
    cfg = json.loads((PROFILE / "profile.json").read_text(encoding="utf-8"))["board_pack"]
    as_of = cal["period"]["as_of"]
    y2, am, n = as_of[:4], int(as_of[5:]), cfg["runrate_months"]
    rate, tax_row, tax_cc = cal["income_tax"]["rate"], "Income tax", cfg["tax_cost_center"]
    ccs = sorted({x["code"] for x in cal["cost_centers"]})
    base = [r for r in PL_ROWS if r not in PL_SUBTOTALS]

    def parts(r):
        return [x for p in PL_SUBTOTALS[r] for x in parts(p)] if r in PL_SUBTOTALS else [r]
    pbt = parts("Profit before tax")
    act, pl, ly = {}, {}, {}
    y1 = str(int(y2) - 1)
    for d, t, md, dd, v, cc, _ in B.journal:
        if d.startswith("PS") or t.strftime("%Y") not in (y1, y2):
            continue
        tgt = act if t.strftime("%Y") == y2 else ly
        for acc, sgn in ((md, -1), (dd, 1)):
            row = ACCOUNTS[acc][2]
            if row:
                tgt[(cc, row, t.month)] = tgt.get((cc, row, t.month), 0) + sgn * v
    for (acc, cc), vals in plan.items():
        row = ACCOUNTS[acc][2]
        for i, v in enumerate(vals):
            pl[(cc, row, i + 1)] = pl.get((cc, row, i + 1), 0) + (v if acc.startswith("6") else -v)
    from decimal import ROUND_HALF_UP, Decimal
    for mo in range(1, 13):                  # daň plánu v celých centoch, zaokrúhlenie od nuly
        pl[(tax_cc, tax_row, mo)] = int((-Decimal(str(rate)) * sum(pl.get((cc, r, mo), 0) for cc in ccs for r in pbt))
                                        .quantize(Decimal(1), ROUND_HALF_UP))
    fc = {}
    rr = range(am - n + 1, am + 1)
    for cc in ccs:
        for r in base:
            if r == tax_row:
                continue
            a = sum(act.get((cc, r, mo), 0) for mo in rr)
            p = sum(pl.get((cc, r, mo), 0) for mo in rr)
            for mo in range(am + 1, 13):
                fc[(cc, r, mo)] = pl.get((cc, r, mo), 0) * a / p if p else a / n
    for mo in range(am + 1, 13):
        fc[(tax_cc, tax_row, mo)] = -rate * sum(fc.get((cc, r, mo), 0) for cc in ccs for r in pbt)

    def total(src, months):
        return {r: sum(src.get((cc, p, mo), 0) for cc in ccs for p in parts(r) for mo in months) / 100 for r in PL_ROWS}
    ytd_act, rest = total(act, range(1, am + 1)), total(fc, range(am + 1, 13))

    def cell(src, cc, r, months):
        return sum(src.get((cc, p, mo), 0) for p in parts(r) for mo in months) / 100
    names = {x["code"]: x["name"] for x in cal["cost_centers"]}
    ytdm, restm, rrm = range(1, am + 1), range(am + 1, 13), range(am - n + 1, am + 1)
    # odchýlky: stredisko × riadok odchýlok, skutočnosť − plán YTD, top N podľa vplyvu (profil → board_pack)
    var = sorted(((names[cc], r, cell(act, cc, r, ytdm) - cell(pl, cc, r, ytdm)) for cc in ccs
                  for r in cfg["variance_rows"]), key=lambda x: (-abs(x[2]), x[0], x[1]))
    var = [x for x in var[:cfg["variance_top"]] if abs(x[2]) >= cfg["variance_min_eur"]]
    # riziká a citlivosť — pravidlá revenue_pace a cost_spike_repeat vlastným kódom
    ro, mn = {}, cfg["ro_min_eur"]
    for cc in sorted(ccs, key=lambda c: names[c]):
        a, p = cell(act, cc, "Revenue", rrm), cell(pl, cc, "Revenue", rrm)
        ay, py = cell(act, cc, "Revenue", ytdm), cell(pl, cc, "Revenue", ytdm)
        if not p or not py or not ay or abs(a / p - ay / py) < cfg["ro"]["revenue_pace"]["min_gap"]:
            continue
        gm = cell(act, cc, "Gross margin", ytdm) / ay
        imp = (cell(pl, cc, "Revenue", restm) * ay / py - cell(fc, cc, "Revenue", restm)) * gm
        if abs(imp) >= mn:
            ro[f"sensitivity|revenue_pace|{names[cc]}"] = round(imp, 2)
    cs = cfg["ro"]["cost_spike_repeat"]
    tot = lambda src, r, months: sum(cell(src, cc, r, months) for cc in ccs)  # noqa: E731
    for r in [x for x in parts("EBITDA") if x not in cs["exclude"] and x != "Revenue"]:
        lr = tot(ly, r, rrm)
        rr_yoy = tot(act, r, rrm) / lr - 1 if lr else 0.0
        for q in range(1, (am - n) // 3 + 1):
            qm = range(3 * q - 2, 3 * q + 1)
            lq = tot(ly, r, qm)
            if not lq:
                continue
            yoy = tot(act, r, qm) / lq - 1
            if yoy >= cs["min_yoy"] and rr_yoy < cs["min_yoy"] / 2:
                imp = tot(ly, r, restm) * (1 + yoy) - tot(fc, r, restm)
                if abs(imp) >= mn:
                    ro[f"ro|cost_spike|{r}|Q{q}"] = round(imp, 2)
    return {"ytd_plan_by_row": {r: round(v, 2) for r, v in total(pl, range(1, am + 1)).items()},
            "fy_plan_by_row": {r: round(v, 2) for r, v in total(pl, range(1, 13)).items()},
            "fy_est_by_row": {r: round(ytd_act[r] + rest[r], 2) for r in PL_ROWS},
            "fy_ebitda_by_cc": {names[cc]: round(cell(act, cc, "EBITDA", ytdm) + cell(fc, cc, "EBITDA", restm), 2)
                                for cc in ccs},
            "variance_top_vs_ly": {f"{s_} · {r}": round(cell(act, c_, r, ytdm) - cell(ly, c_, r, ytdm), 2)
                                   for s_, r, _ in var for c_ in ccs if names[c_] == s_},
            "variance_top": {f"{s_} · {r}": round(d, 2) for s_, r, d in var}, "variance_top_count": len(var),
            "ro_anchored": ro, "ro_anchored_count": len(ro)}


def golden_of(cal, pos, truth: dict, delivery: Path) -> dict:
    """Kotva A zmluvy reportu (profiles/papiernictvo2/contract.json): čísla P01–P16 z etalónu generátora (jeho denník,
    plán, odhad) a z jeho bločkov (kategórie) — vlastným kódom, nie z motora. Viazaná na dodávku (odtlačok) a obdobie."""
    as_of = cal["period"]["as_of"]
    y2, am = as_of[:4], int(as_of[5:])
    y1 = str(int(y2) - 1)
    v = {}
    for base, row in ((1, "Revenue"), (5, "EBITDA"), (9, "Net profit")):
        v[f"P{base:02d}"] = truth["ytd_pl_by_row"][row]
        v[f"P{base + 1:02d}"] = truth["ytd_plan_by_row"][row]
        v[f"P{base + 2:02d}"] = truth["fy_est_by_row"][row]
        v[f"P{base + 3:02d}"] = truth["fy_plan_by_row"][row]
    v["P13"] = truth["variance_top"]["Store OC · Rent"]
    v["P14"] = truth["ro_anchored"]["ro|cost_spike|Energy|Q1"]
    net, gross = {}, {}                              # bločky: (rok, mesiac, kategória) → bez DPH / s DPH (centy)
    for (cc, ym), lines in pos.items():
        for rid, t, reg, k, qty, unit, vat, g, pay in lines:
            key = (ym[:4], int(ym[5:]), k)
            net[key] = net.get(key, 0) + g / (1 + vat / 100)
            gross[key] = gross.get(key, 0) + g
    cats = sorted({k[2] for k in net}, key=cat_key)
    q3, rest, rr = range(7, 10), range(am + 1, 13), range(am - 2, am + 1)
    cs = lambda src, c, y, ms: sum(src.get((y, m, c), 0) for m in ms)  # noqa: E731
    ts = lambda y, ms: sum(cs(net, c, y, ms) for c in cats)  # noqa: E731
    yoy = cs(net, "Stationery", y2, q3) / cs(net, "Stationery", y1, q3) - 1
    share_rr = cs(net, "Stationery", y1, rr) / ts(y1, rr)
    gm = truth["ytd_pl_by_row"]["Gross margin"] / truth["ytd_pl_by_row"]["Revenue"]
    v["P15"] = yoy * (cs(net, "Stationery", y1, rest) - ts(y1, rest) * share_rr) / 100 * gm
    v["P16"] = (cs(gross, "Toys", y2, q3) / cs(gross, "Toys", y1, q3) - 1) * 100
    v["P17"] = (v["P07"] - v["P08"]) / abs(v["P08"]) * 100          # EBITDA odhad voči plánu roka v %
    h = hashlib.sha256()
    for f in sorted(p for p in delivery.iterdir() if p.is_file() and not p.name.startswith(".")):
        h.update(f"{f.name}:{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode("utf-8"))
    return {"_meta": {"anchor": "A — generator (internal data, independent of the engine)",
                      "contract": "profiles/papiernictvo2/contract.json", "delivery": "clean", "as_of": as_of,
                      "delivery_sha256": h.hexdigest()},
            "values": {k: round(x, 4 if k in ("P16", "P17") else 2) for k, x in sorted(v.items())}}


def truth_of(cal, B, pos, ms):
    as_of = cal["period"]["as_of"]
    y2, y1 = as_of[:4], ms[0][:4]
    p2, p1 = pl_of(cal, B.journal, y2, as_of[5:]), pl_of(cal, B.journal, y1)
    names = {x["code"]: x["name"] for x in cal["cost_centers"]}
    r = lambda v: round(v / 100, 2)  # noqa: E731
    return {"_meta": "Generator reference for papiernictvo2 (clean data): P&L 2026 YTD and 2025 from the generator's journal.",
            "ytd_pl_by_row": {row: r(p2[("Total", row)]) for row in PL_ROWS},
            "pl_y1_by_row": {row: r(p1[("Total", row)]) for row in PL_ROWS},
            "ytd_ebitda_by_cc": {names[cc]: r(p2[(cc, "EBITDA")]) for cc in sorted(names)},
            "ytd_net_profit": r(p2[("Total", "Net profit")]),
            "rows": {"pos_rows": sum(len(v) for v in pos.values()), "journal_rows": len(B.journal),
                     "invoices": len(B.invoices), "bank_rows": len(B.bank), "payroll_rows": len(B.payroll),
                     "stock_moves": len(B.stock_moves)}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PROFILE / "data"))
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-stories", action="store_true")
    a = ap.parse_args()
    cal = json.loads((PROFILE / "calibration.json").read_text(encoding="utf-8"))
    out = Path(a.out)
    stories = not a.no_stories
    B, pos, stock, ms, rev = gen(cal, a.seed, stories)
    plan = plan_of(cal, B, ms)
    write_set(cal, out / "clean", B, pos, ms, plan)
    meta = PROFILE if (out.resolve() == (PROFILE / "data").resolve() and stories) else out
    truth = {**truth_of(cal, B, pos, ms), **boardpack_truth(cal, B, plan)}
    (meta / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if stories:                                      # kotva A zmluvy len pre dodávku s príbehmi (tú zmluva viaže)
        (meta / "golden_generator.json").write_text(
            json.dumps(golden_of(cal, pos, truth, out / "clean"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if stories:
        pe = cal["planted_errors"]
        e1_doc = next(i["cislo"] for i in B.invoices if i["datum"].strftime("%Y-%m") == pe["E1"]["month"] and i["ucet"] == "511")
        errs = {"E1": e1_doc, "E2": (pe["E2"]["month"], pe["E2"]["cost_center"]), "E3": pe["E3"]["month"],
                "E4": (pe["E4"]["month"], pe["E4"]["cost_center"], pe["E4"]["category"]),
                "E5": (pe["E5"]["month"], pe["E5"]["cost_center"], "518100"),
                "E6": (pe["E6"]["cost_center"], pe["E6"]["month"]), "E7": (pe["E7"]["month"], pe["E7"]["cost_center"])}
        write_set(cal, out / "with_errors", B, pos, ms, plan, errs)
        log = [{"id": k, "what": pe[k]["what"], "where": (list(v) if isinstance(v, tuple) else v)} for k, v in errs.items()]
        (meta / "planted_errors.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    t = truth_of(cal, B, pos, ms)
    print(f"GEN papiernictvo2: {t['rows']} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
