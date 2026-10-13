#!/usr/bin/env python3
"""summary_page.py — jedna čitateľná strana pre manažéra z hotového overview.xlsx (po anglicky).

Použitie: python tools/summary_page.py <overview.xlsx> [--out <priečinok>]
Výstup:   summary.html (samostatný súbor, otvorí sa v prehliadači, tlač = 1 strana A4 na šírku)

LEN ČÍTA hotový zošit — čísla berie z hárku Board pack, takže strana nemôže ukázať iné číslo než board pack.
Jediný výpočet: dva súčtové riadky (ostatné prevádzkové náklady; odpisy, úroky a daň), aby sa tabuľka dala
prepočítať od tržieb po EBITDA a po čistý zisk. Súčet sa robí z presných čísel zošita a až potom zaokrúhli.
Verdikt TIES → výsledok, plán, odhad roka, tri najväčšie odchýlky, čo čaká na kontrolóra.
Verdikt DOES NOT TIE → board pack sa nevydal; strana povie prečo a kde (kontrola, počet nálezov, súbor).
Príčina odchýlky je VÝPOČET z mesačného priebehu (kedy vznikla), nie vysvetlenie — strana to tak aj označuje.
"""
import argparse
import html
from pathlib import Path

from openpyxl import load_workbook

# Riadky tabuľky zhora nadol; n-tica = súčet riadkov zošita. Medzisúčty (STRONG) = súčet riadkov od predošlého.
OTHER_OPEX = ("Energy", "Marketing", "Services", "Other")
BELOW = ("Depreciation", "Interest and financial", "Income tax")
TABLE = ["Revenue", "Cost of goods sold", "Gross margin", "Staff", "Rent", OTHER_OPEX, "EBITDA", BELOW,
         "Net profit"]
STRONG = ("Gross margin", "EBITDA", "Net profit")
COLS = (1, 2, 3, 6, 7, 8)   # stĺpce hárku Board pack: YTD skutočnosť, plán, rozdiel, odhad roka, plán roka, rozdiel

CHECKS = {
    "stg_parse_contract": "Input rows are readable",
    "inputs_contract": "Delivery is complete",
    "numeric_contract": "Amounts are numbers in the agreed format",
    "full_duplicate_keys": "No duplicates",
    "full_coverage": "No month or source is missing",
    "pos_control_total": "Till: TOTAL line = sum of receipts",
    "journal_tb_match": "Journal = trial balance",
    "pos_gl_match": "Till = general ledger",
    "bank_balance": "Bank: opening balance = previous closing balance",
    "bank_gl_match": "Bank = ledger account 221",
    "bank_ap_match": "Every bank payment has an invoice",
    "payroll_gl_match": "Payroll = ledger account 521",
    "ap_gl_match": "Supplier invoices are posted",
    "stock_consistency": "Stock: no negative stock, issues = cost of goods sold",
    "liability_settlement": "Liability paid = liability balance",
    "card_settlement": "Cards: fee = card sales − amount credited by the bank",
    "pl_control_total": "P&L = trial balance",
    "posting_policy": "Every posting uses an allowed pattern",
    "loan_schedule": "Loan follows the contract",
    "account_mapping_complete": "All accounts mapped to the P&L",
    "boardpack_consistency": "Board pack = second, independent calculation",
    "profile_contract": "Company profile is complete",
    "exceptions_contract": "Exceptions are well-formed",
}

T = dict(title="Management summary", title_err="Data check — report not released",
         other_opex="Other operating costs", below="Depreciation, interest and tax", computed="(computed)",
         round_note="Whole euros; a total may differ by €1 due to rounding.", more_fmt="and {n} more", asof="as of", ties="TIES", fails="DOES NOT TIE",
         ytd_rev="Revenue year to date",
         ytd_ebitda="EBITDA year to date", fy_ebitda="Full-year EBITDA forecast", plan="plan",
         vs_plan="vs plan", line="Line", act="Actual YTD", planc="Plan YTD", diff="Difference",
         fc="Full-year forecast", fyplan="Full-year plan", fcdiff="Forecast − plan", pl="Result vs plan (€)",
         var="Three largest variances vs plan", where="Where", impact="EBITDA impact", when="When it arose",
         when_note="“When it arose” is calculated from the monthly pattern. It is not an explanation of the cause.",
         open="Waiting for the finance manager",
         open_txt="{m} of {n} comments have no valid confirmation (machine-written), {c} confirmed by the controller. "
                  "Before this goes to management, each variance needs a cause and a decision.",
         risks="Risks and forecast sensitivity", risks_note="The items overlap — do not add them up.", cost_spike="cost spike in {q} may repeat",
         mix="category trend distorts the forecast", pace="revenue pace distorts the forecast",
         src="Source: overview.xlsx from this run. Fictional data (Papiernictvo DEMO).",
         blocked="Report NOT released", blocked_txt="The numbers do not tie to the sources, so management "
         "receives nothing. Below: which check failed and in which file.", passed="checks passed",
         failed="checks failed", findings="findings", check="Check that failed", n="Findings",
         file="File (row)", next="What happens next",
         steps=["Open the file and row from the table.", "Fix the error at the source (not in the report).",
                "Run again. The report is released only when everything ties."])


def num(v, sign=False):
    if v is None:
        return ""
    s = f"{abs(round(v)):,}"
    pre = "−" if round(v) < 0 else ("+" if sign and round(v) > 0 else "")
    return f"{pre}{s}"


def eur(v, sign=False):
    n = num(v, sign)
    return f"{n[0]}€{n[1:]}" if n[:1] in "−+" else f"€{n}"


def pct(a, b):
    if not b:
        return ""
    return f"{'−' if a < 0 else '+'}{abs(a / abs(b)) * 100:.1f}%"


def risk_label(key):
    p = key.split("|")
    if p[1] == "cost_spike":
        return f"{p[2]}: {T['cost_spike'].format(q=p[3])}"
    return f"{p[2]}: {T['mix'] if p[1] == 'category_mix' else T['pace']}"


def rows(ws, start=2):
    return [r for r in ws.iter_rows(min_row=start, values_only=True) if r[0] is not None]


CSS = """
@page{size:A4 landscape;margin:11mm}
*{box-sizing:border-box}
body{font:12.5px/1.45 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#1c2430;background:#fff;margin:0 auto;
     max-width:1050px;padding:8px 16px}
header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #1c2430;
       padding-bottom:8px;margin-bottom:12px}
h1{font-size:21px;margin:0}.sub{color:#5b6675;font-size:12.5px}
.badge{font-weight:700;font-size:14px;padding:5px 12px;border-radius:4px;color:#fff;white-space:nowrap}
.ok{background:#1b7a43}.bad{background:#b3261e}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px}
.tile{border:1px solid #d5dae1;border-radius:6px;padding:7px 12px}
.tile .l{color:#5b6675;font-size:12px}.tile .v{font-size:23px;font-weight:700;letter-spacing:-.3px}
.tile .d{font-size:12.5px}.neg{color:#b3261e}.pos{color:#1b7a43}
.cols{display:grid;grid-template-columns:1.15fr 1fr;gap:16px}
h2{font-size:13.5px;margin:0 0 5px;text-transform:uppercase;letter-spacing:.4px;color:#39424f}
table{border-collapse:collapse;width:100%;margin-bottom:10px}
th,td{padding:3px 6px;border-bottom:1px solid #e3e7ec;text-align:right;font-variant-numeric:tabular-nums}
th{font-weight:600;color:#5b6675;font-size:11.5px;border-bottom:1px solid #1c2430}
th:first-child,td:first-child{text-align:left}td.t,th.t{text-align:left}
tr.strong td{font-weight:700}.nw{white-space:nowrap}
table.err td{padding:2.5px 6px}td.cut{max-width:330px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.note{color:#5b6675;font-size:11.5px;margin:-4px 0 10px}
.box{border-left:4px solid #b7791f;background:#fbf6ea;padding:7px 11px;margin-bottom:10px}
.box.red{border-color:#b3261e;background:#fbeeed}
ol{margin:4px 0 0;padding-left:20px}footer{color:#5b6675;font-size:11px;margin-top:6px}
"""


def table_rows(bp):
    """[(názov, {stĺpec: hodnota}, je_medzisúčet)] — čísla zo zošita, súčtové riadky z presných hodnôt."""
    out = []
    for k in TABLE:
        if isinstance(k, tuple):
            label = T["other_opex"] if k is OTHER_OPEX else T["below"]
            out.append((label, {c: sum(bp[r][c] for r in k) for c in COLS}, False))
        else:
            out.append((k, {c: bp[k][c] for c in COLS}, k in STRONG))
    return out


def page(company, asof, ok, body):
    badge = f'<span class="badge {"ok" if ok else "bad"}">{"✓" if ok else "✗"} {T["ties"] if ok else T["fails"]}</span>'
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{T["title"]}</title>'
            f'<style>{CSS}</style><header><div><h1>{T["title"] if ok else T["title_err"]}</h1>'
            f'<div class="sub">{html.escape(company)} · {T["asof"]} {asof}</div></div>{badge}</header>{body}'
            f'<footer>{T["src"]}</footer></html>')


def clean_body(wb):
    bp = {r[0]: r for r in rows(wb["Board pack"])}
    cls = lambda v: "neg" if round(v) < 0 else "pos"  # noqa: E731

    def tile(label, v, plan):
        d = v - plan
        return (f'<div class="tile"><div class="l">{label}</div><div class="v">{eur(v)}</div>'
                f'<div class="d">{T["plan"]} {eur(plan)} · <span class="{cls(d)}">{eur(d, True)} '
                f'({pct(d, plan)})</span> {T["vs_plan"]}</div></div>')

    r, e = bp["Revenue"], bp["EBITDA"]
    out = [f'<div class="tiles">{tile(T["ytd_rev"], r[1], r[2])}{tile(T["ytd_ebitda"], e[1], e[2])}'
           f'{tile(T["fy_ebitda"], e[6], e[7])}</div><div class="cols"><div>']
    out.append(f'<h2>{T["pl"]}</h2><table><tr><th>{T["line"]}</th><th>{T["act"]}</th><th>{T["planc"]}</th>'
               f'<th>{T["diff"]}</th><th>{T["fc"]}</th><th>{T["fyplan"]}</th><th>{T["fcdiff"]}</th></tr>')
    for label, x, strong in table_rows(bp):
        out.append(f'<tr{" class=strong" if strong else ""}><td>{label}</td><td>{num(x[1])}</td>'
                   f'<td>{num(x[2])}</td><td class="{cls(x[3])}">{num(x[3], True)}</td>'
                   f'<td>{num(x[6])}</td><td>{num(x[7])}</td>'
                   f'<td class="{cls(x[8])}">{num(x[8], True)}</td></tr>')
    out.append(f'</table><p class="note">{T["round_note"]}</p>')
    kom = rows(wb["Comments"])
    confirmed = sum(1 for x in kom if x[5] == "controller")   # zastaraný komentár kontrolóra potvrdením NIE JE
    out.append(f'<div class="box"><h2>{T["open"]}</h2>'
               f'{T["open_txt"].format(m=len(kom) - confirmed, n=len(kom), c=confirmed)}</div>')
    out.append(f'</div><div><h2>{T["var"]}</h2><table><tr><th>{T["where"]}</th><th>{T["impact"]}</th>'
               f'<th class="t">{T["when"]}</th></tr>')
    for x in rows(wb["Variances"])[:3]:
        out.append(f'<tr><td>{html.escape(x[0])}</td><td class="{cls(x[3])}">'
                   f'{eur(x[3], True)}</td><td class="t nw">{html.escape(x[5])}</td></tr>')
    out.append(f'</table><p class="note">{T["when_note"]}</p>')
    ro = rows(wb["Risks and opportunities"])
    if ro:
        out.append(f'<h2>{T["risks"]}</h2><table><tr><th></th><th>{T["impact"]}</th></tr>')
        out += [f'<tr><td>{html.escape(risk_label(x[0]))}</td><td class="{cls(x[2])}">{eur(x[2], True)}</td></tr>'
                for x in ro[:3]]
        out.append(f'</table><p class="note">{T["risks_note"]}</p>')
    out.append("</div></div>")
    return "".join(out)


def error_body(wb):
    checks = rows(wb["Checks"])
    failed = [c[1] for c in checks if c[0] == "FAIL"]
    bad = {}
    for x in rows(wb["Failed rows"]):
        bad.setdefault(x[1], []).append(x)
    total = sum(len(v) for v in bad.values())
    out = [f'<div class="box red"><h2>{T["blocked"]}</h2>{T["blocked_txt"]}</div><div class="tiles">'
           f'<div class="tile"><div class="v pos">{len(checks) - len(failed)}</div><div class="l">{T["passed"]}</div></div>'
           f'<div class="tile"><div class="v neg">{len(failed)}</div><div class="l">{T["failed"]}</div></div>'
           f'<div class="tile"><div class="v">{total}</div><div class="l">{T["findings"]}</div></div></div>'
           f'<table class="err"><tr><th>{T["check"]}</th><th>{T["n"]}</th><th class="t">{T["file"]}</th></tr>']
    for c in failed:
        f = bad.get(c, [])
        files = sorted({(name_, x[3]) for x in f for name_ in x[5:8] if name_}, key=lambda p: (p[0], str(p[1])))
        where = ", ".join(f"{a}{f' (r{b})' if b else ''}" for a, b in files[:2])
        where += f" {T['more_fmt'].format(n=len(files) - 2)}" if len(files) > 2 else ""
        out.append(f'<tr><td class="nw">{CHECKS.get(c, c)}</td><td>{len(f)}</td>'
                   f'<td class="t nw">{html.escape(where) or T["computed"]}</td></tr>')
    out.append(f'</table><h2>{T["next"]}</h2><ol>' + "".join(f"<li>{s}</li>" for s in T["steps"]) + "</ol>")
    return "".join(out)


def build(xlsx: Path, out: Path) -> Path:
    wb = load_workbook(xlsx, data_only=True)
    head = [r for r in wb["Overview"].iter_rows(min_row=1, max_row=2, values_only=True)]
    company, asof, ok = head[0][0], head[0][1].replace("as of ", ""), head[1][1] == "TIES"
    out.mkdir(parents=True, exist_ok=True)
    p = out / "summary.html"
    p.write_text(page(company, asof, ok, clean_body(wb) if ok else error_body(wb)), encoding="utf-8")
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out")
    a = ap.parse_args()
    print(f"   summary: {build(Path(a.xlsx), Path(a.out) if a.out else Path(a.xlsx).parent)}")
