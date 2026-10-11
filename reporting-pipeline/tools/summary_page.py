#!/usr/bin/env python3
"""summary_page.py — jedna čitateľná strana pre manažéra z hotového prehlad.xlsx, po anglicky aj po slovensky.

Použitie: python tools/summary_page.py <prehlad.xlsx> [--out <priečinok>]
Výstup:   summary_en.html, summary_sk.html (samostatné súbory, otvoria sa v prehliadači, tlač = 1 strana A4 na šírku)

LEN ČÍTA hotový zošit — čísla berie z hárku Board pack, takže strana nemôže ukázať iné číslo než board pack.
Jediný výpočet: dva súčtové riadky (ostatné prevádzkové náklady; odpisy, úroky a daň), aby sa tabuľka dala
prepočítať od tržieb po EBITDA a po čistý zisk. Súčet sa robí z presných čísel zošita a až potom zaokrúhli.
Verdikt SEDÍ → výsledok, plán, odhad roka, tri najväčšie odchýlky, čo čaká na kontrolóra.
Verdikt NESEDÍ → board pack sa nevydal; strana povie prečo a kde (kontrola, počet nálezov, súbor).
Príčina odchýlky je VÝPOČET z mesačného priebehu (kedy vznikla), nie vysvetlenie — strana to tak aj označuje.
"""
import argparse
import html
import re
from pathlib import Path

from openpyxl import load_workbook

ROWS = {"Tržby": "Revenue", "Náklady na predaný tovar": "Cost of goods sold", "Hrubá marža": "Gross margin",
        "Personál": "Staff", "Nájom": "Rent", "Energie": "Energy", "Marketing": "Marketing", "Služby": "Services",
        "Ostatné": "Other", "EBITDA": "EBITDA", "Odpisy": "Depreciation", "EBIT": "EBIT",
        "Úroky a finančné": "Interest and financial", "Zisk pred zdanením": "Profit before tax",
        "Daň z príjmov": "Income tax", "Čistý zisk": "Net profit"}
WORDS = {"Predajňa": "Store", "Centrála": "Head office", "Papiernictvo": "Stationery", "Hračky": "Toys",
         "Knihy": "Books", "Sídlisko": "Sídlisko", "Mesto": "Mesto", "Centrum": "Centrum"}
# Riadky tabuľky zhora nadol; n-tica = súčet riadkov zošita. Medzisúčty (STRONG) = súčet riadkov od predošlého.
OTHER_OPEX = ("Energie", "Marketing", "Služby", "Ostatné")
BELOW = ("Odpisy", "Úroky a finančné", "Daň z príjmov")
TABLE = ["Tržby", "Náklady na predaný tovar", "Hrubá marža", "Personál", "Nájom", OTHER_OPEX, "EBITDA", BELOW,
         "Čistý zisk"]
STRONG = ("Hrubá marža", "EBITDA", "Čistý zisk")
COLS = (1, 2, 3, 6, 7, 8)   # stĺpce hárku Board pack: YTD skutočnosť, plán, rozdiel, odhad roka, plán roka, rozdiel

CHECKS = {  # kontrola: (SK, EN)
    "stg_parse_contract": ("Riadky vstupov sú čitateľné", "Input rows are readable"),
    "inputs_contract": ("Dodávka je úplná", "Delivery is complete"),
    "numeric_contract": ("Sumy sú čísla v dohodnutom tvare", "Amounts are numbers in the agreed format"),
    "full_duplicate_keys": ("Bez duplicít", "No duplicates"),
    "full_coverage": ("Žiadny mesiac ani zdroj nechýba", "No month or source is missing"),
    "pos_control_total": ("Pokladňa: riadok SPOLU = súčet bločkov", "Till: TOTAL line = sum of receipts"),
    "journal_tb_match": ("Denník = predvaha", "Journal = trial balance"),
    "pos_gl_match": ("Pokladňa = účtovníctvo", "Till = general ledger"),
    "bank_balance": ("Banka: počiatočný stav = konečný predchádzajúceho výpisu",
                     "Bank: opening balance = previous closing balance"),
    "bank_gl_match": ("Banka = účet 221", "Bank = ledger account 221"),
    "bank_ap_match": ("Úhrada z banky má faktúru", "Every bank payment has an invoice"),
    "payroll_gl_match": ("Mzdy = účet 521", "Payroll = ledger account 521"),
    "ap_gl_match": ("Faktúry dodávateľov sú zaúčtované", "Supplier invoices are posted"),
    "stock_consistency": ("Sklad: žiadna záporná zásoba, výdaj = predaný tovar",
                          "Stock: no negative stock, issues = cost of goods sold"),
    "liability_settlement": ("Úhrada záväzku = zostatok záväzku", "Liability paid = liability balance"),
    "card_settlement": ("Karty: poplatok = tržby kartou − pripísané bankou",
                        "Cards: fee = card sales − amount credited by the bank"),
    "pl_control_total": ("Výsledovka = predvaha", "P&L = trial balance"),
    "posting_policy": ("Každý zápis na povolenej predkontácii", "Every posting uses an allowed pattern"),
    "loan_schedule": ("Úver podľa zmluvy", "Loan follows the contract"),
    "account_mapping_complete": ("Všetky účty zaradené do výsledovky", "All accounts mapped to the P&L"),
    "boardpack_consistency": ("Board pack = druhá, nezávislá cesta výpočtu",
                              "Board pack = second, independent calculation"),
    "profile_contract": ("Profil firmy je úplný", "Company profile is complete"),
    "exceptions_contract": ("Výnimky v platnom tvare", "Exceptions are well-formed"),
}

T = {
    "sk": dict(lang="sk", title="Manažérsky súhrn", title_err="Kontrola dát — report sa nevydal",
               other_opex="Ostatné prevádzkové náklady", below="Odpisy, úroky a daň", computed="(výpočet)",
               round_note="Celé eurá; súčet sa môže líšiť o 1 € zaokrúhlením.", more_fmt="a ďalšie {n}", asof="stav k", ties="SEDÍ", fails="NESEDÍ",
               ytd_rev="Tržby od začiatku roka",
               ytd_ebitda="EBITDA od začiatku roka", fy_ebitda="Odhad EBITDA za celý rok", plan="plán",
               vs_plan="voči plánu", line="Riadok", act="Skutočnosť YTD", planc="Plán YTD", diff="Rozdiel",
               fc="Odhad roka", fyplan="Plán roka", fcdiff="Odhad − plán", pl="Výsledok voči plánu (€)",
               var="Tri najväčšie odchýlky voči plánu", where="Kde", impact="Vplyv na EBITDA", when="Kedy vznikla",
               when_note="Stĺpec „Kedy vznikla“ je výpočet z mesačného priebehu. Nie je to vysvetlenie príčiny.",
               open="Čaká na finančného manažéra",
               open_txt="{m} z {n} komentárov je bez platného potvrdenia (vetu napísal stroj), {c} potvrdil kontrolór. "
                        "Pred odoslaním vedeniu treba ku každej odchýlke doplniť príčinu a rozhodnutie.",
               risks="Riziká a citlivosť odhadu", risks_note="Položky sa prekrývajú — nesčítavať.", cost_spike="skok nákladu v {q} sa môže zopakovať",
               mix="trend kategórie skresľuje odhad", pace="tempo tržieb skresľuje odhad",
               src="Zdroj: prehlad.xlsx z tohto behu. Vymyslené dáta (Papiernictvo DEMO).",
               blocked="Report sa NEVYDAL", blocked_txt="Čísla nesedia so zdrojmi, preto vedenie nedostane nič. "
               "Nižšie je, ktorá kontrola zlyhala a v ktorom súbore.", passed="kontrol prešlo", failed="kontrol zlyhalo",
               findings="nálezov", check="Kontrola, ktorá zlyhala", n="Nálezov", file="Súbor (riadok)",
               first="Prvý nález", next="Čo ďalej", steps=["Otvor súbor a riadok z tabuľky.",
               "Oprav chybu v zdroji (nie v reporte).", "Pusti beh znova. Report sa vydá, až keď všetko sedí."],
               since="od {m}, každý mesiac {v}", mainly="najmä v {q} ({v})",
               spread="rozložené počas roka (priemer {v} mesačne)"),
    "en": dict(lang="en", title="Management summary", title_err="Data check — report not released",
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
               src="Source: prehlad.xlsx from this run. Fictional data (Papiernictvo DEMO).",
               blocked="Report NOT released", blocked_txt="The numbers do not tie to the sources, so management "
               "receives nothing. Below: which check failed and in which file.", passed="checks passed",
               failed="checks failed", findings="findings", check="Check that failed", n="Findings",
               file="File (row)", first="First finding", next="What happens next",
               steps=["Open the file and row from the table.", "Fix the error at the source (not in the report).",
                      "Run again. The report is released only when everything ties."],
               since="since {m}, every month {v}", mainly="mainly in {q} ({v})",
               spread="spread across the year (average {v} per month)"),
}


def num(v, lang, sign=False):
    if v is None:
        return ""
    s = f"{abs(round(v)):,}".replace(",", " " if lang == "sk" else ",")
    pre = "−" if round(v) < 0 else ("+" if sign and round(v) > 0 else "")
    return f"{pre}{s}"


def eur(v, lang, sign=False):
    n = num(v, lang, sign)
    if lang == "sk":
        return f"{n}\u00a0€"
    return f"{n[0]}€{n[1:]}" if n[:1] in "−+" else f"€{n}"


def pct(a, b, lang):
    if not b:
        return ""
    p = f"{abs(a / abs(b)) * 100:.1f}"
    return f"{'−' if a < 0 else '+'}{p.replace('.', ',') if lang == 'sk' else p} %"


def name(s, lang):
    """Názov riadku / strediska / kategórie; po anglicky cez slovník, neznáme slovo ostáva."""
    if lang == "sk":
        return s
    s = ROWS.get(s, s)
    for sk, en in WORDS.items():
        s = re.sub(rf"\b{sk}\b", en, s)
    return s


def money_txt(s, lang):
    """'−2 600 €' zo zošita → zápis v jazyku strany."""
    v = float(re.sub(r"[^\d,.\-−+]", "", s).replace("−", "-").replace(",", "."))
    return eur(v, lang, True)


def cause(s, t):
    """Tri tvary príčiny z pipeline/boardpack.py; iný tvar ostáva v origináli."""
    lang = t["lang"]
    if m := re.fullmatch(r"od (\d{4}-\d{2}) mesačne (.+ €)", s):
        return t["since"].format(m=m[1], v=money_txt(m[2], lang))
    if m := re.fullmatch(r"najmä v (Q\d) \((.+ €)\)", s):
        return t["mainly"].format(q=m[1], v=money_txt(m[2], lang))
    if m := re.fullmatch(r"rozložené počas roka \(priemer (.+ €) mesačne\)", s):
        return t["spread"].format(v=money_txt(m[1], lang))
    return s


def risk_label(key, t):
    p = key.split("|")
    if p[1] == "skok_nakladu":
        return f"{name(p[2], t['lang'])}: {t['cost_spike'].format(q=p[3])}"
    return f"{name(p[2], t['lang'])}: {t['mix'] if p[1] == 'mix_kategorie' else t['pace']}"


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


def table_rows(bp, t):
    """[(názov, {stĺpec: hodnota}, je_medzisúčet)] — čísla zo zošita, súčtové riadky z presných hodnôt."""
    out = []
    for k in TABLE:
        if isinstance(k, tuple):
            label = t["other_opex"] if k is OTHER_OPEX else t["below"]
            out.append((label, {c: sum(bp[r][c] for r in k) for c in COLS}, False))
        else:
            out.append((name(k, t["lang"]), {c: bp[k][c] for c in COLS}, k in STRONG))
    return out


def page(t, company, asof, ok, body):
    badge = f'<span class="badge {"ok" if ok else "bad"}">{"✓" if ok else "✗"} {t["ties"] if ok else t["fails"]}</span>'
    return (f'<!doctype html><html lang="{t["lang"]}"><meta charset="utf-8"><title>{t["title"]}</title>'
            f'<style>{CSS}</style><header><div><h1>{t["title"] if ok else t["title_err"]}</h1>'
            f'<div class="sub">{html.escape(company)} · {t["asof"]} {asof}</div></div>{badge}</header>{body}'
            f'<footer>{t["src"]}</footer></html>')


def clean_body(wb, t):
    lang = t["lang"]
    bp = {r[0]: r for r in rows(wb["Board pack"])}
    cls = lambda v: "neg" if round(v) < 0 else "pos"  # noqa: E731

    def tile(label, v, plan):
        d = v - plan
        return (f'<div class="tile"><div class="l">{label}</div><div class="v">{eur(v, lang)}</div>'
                f'<div class="d">{t["plan"]} {eur(plan, lang)} · <span class="{cls(d)}">{eur(d, lang, True)} '
                f'({pct(d, plan, lang)})</span> {t["vs_plan"]}</div></div>')

    r, e = bp["Tržby"], bp["EBITDA"]
    out = [f'<div class="tiles">{tile(t["ytd_rev"], r[1], r[2])}{tile(t["ytd_ebitda"], e[1], e[2])}'
           f'{tile(t["fy_ebitda"], e[6], e[7])}</div><div class="cols"><div>']
    out.append(f'<h2>{t["pl"]}</h2><table><tr><th>{t["line"]}</th><th>{t["act"]}</th><th>{t["planc"]}</th>'
               f'<th>{t["diff"]}</th><th>{t["fc"]}</th><th>{t["fyplan"]}</th><th>{t["fcdiff"]}</th></tr>')
    for label, x, strong in table_rows(bp, t):
        out.append(f'<tr{" class=strong" if strong else ""}><td>{label}</td><td>{num(x[1], lang)}</td>'
                   f'<td>{num(x[2], lang)}</td><td class="{cls(x[3])}">{num(x[3], lang, True)}</td>'
                   f'<td>{num(x[6], lang)}</td><td>{num(x[7], lang)}</td>'
                   f'<td class="{cls(x[8])}">{num(x[8], lang, True)}</td></tr>')
    out.append(f'</table><p class="note">{t["round_note"]}</p>')
    kom = rows(wb["Komentáre"])
    confirmed = sum(1 for x in kom if x[5] == "kontrolór")   # zastaraný komentár kontrolóra potvrdením NIE JE
    out.append(f'<div class="box"><h2>{t["open"]}</h2>'
               f'{t["open_txt"].format(m=len(kom) - confirmed, n=len(kom), c=confirmed)}</div>')
    out.append(f'</div><div><h2>{t["var"]}</h2><table><tr><th>{t["where"]}</th><th>{t["impact"]}</th>'
               f'<th class="t">{t["when"]}</th></tr>')
    for x in rows(wb["Odchýlky"])[:3]:
        shop, row = x[0].split(" · ")
        out.append(f'<tr><td>{name(shop, lang)} · {name(row, lang)}</td><td class="{cls(x[3])}">'
                   f'{eur(x[3], lang, True)}</td><td class="t nw">{html.escape(cause(x[5], t))}</td></tr>')
    out.append(f'</table><p class="note">{t["when_note"]}</p>')
    ro = rows(wb["Riziká a príležitosti"])
    if ro:
        out.append(f'<h2>{t["risks"]}</h2><table><tr><th></th><th>{t["impact"]}</th></tr>')
        out += [f'<tr><td>{html.escape(risk_label(x[0], t))}</td><td class="{cls(x[2])}">{eur(x[2], lang, True)}</td></tr>'
                for x in ro[:3]]
        out.append(f'</table><p class="note">{t["risks_note"]}</p>')
    out.append("</div></div>")
    return "".join(out)


def error_body(wb, t):
    lang = t["lang"]
    checks = rows(wb["Kontroly"])
    failed = [c[1] for c in checks if c[0] == "FAIL"]
    bad = {}
    for x in rows(wb["Chybné riadky"]):
        bad.setdefault(x[1], []).append(x)
    total = sum(len(v) for v in bad.values())
    out = [f'<div class="box red"><h2>{t["blocked"]}</h2>{t["blocked_txt"]}</div><div class="tiles">'
           f'<div class="tile"><div class="v pos">{len(checks) - len(failed)}</div><div class="l">{t["passed"]}</div></div>'
           f'<div class="tile"><div class="v neg">{len(failed)}</div><div class="l">{t["failed"]}</div></div>'
           f'<div class="tile"><div class="v">{total}</div><div class="l">{t["findings"]}</div></div></div>'
           f'<table class="err"><tr><th>{t["check"]}</th><th>{t["n"]}</th><th class="t">{t["file"]}</th>'
           + (f'<th class="t">{t["first"]}</th>' if lang == "sk" else "") + "</tr>"]
    for c in failed:
        f = bad.get(c, [])
        files = sorted({(name_, x[3]) for x in f for name_ in x[5:8] if name_}, key=lambda p: (p[0], str(p[1])))
        where = ", ".join(f"{a}{f' (r{b})' if b else ''}" for a, b in files[:2])
        where += f" {t['more_fmt'].format(n=len(files) - 2)}" if len(files) > 2 else ""
        label = CHECKS.get(c, (c, c))[0 if lang == "sk" else 1]
        first = f'<td class="t cut">{html.escape(f[0][4].strip())}</td>' if lang == "sk" and f else (
            '<td></td>' if lang == "sk" else "")
        out.append(f'<tr><td class="nw">{label}</td><td>{len(f)}</td><td class="t nw">{html.escape(where) or t["computed"]}</td>{first}</tr>')
    out.append(f'</table><h2>{t["next"]}</h2><ol>' + "".join(f"<li>{s}</li>" for s in t["steps"]) + "</ol>")
    return "".join(out)


def build(xlsx: Path, out: Path):
    wb = load_workbook(xlsx, data_only=True)
    head = [r for r in wb["Prehľad"].iter_rows(min_row=1, max_row=2, values_only=True)]
    company, asof, ok = head[0][0], head[0][1].replace("stav k ", ""), head[1][1] == "SEDÍ"
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for lang, t in T.items():
        p = out / f"summary_{lang}.html"
        p.write_text(page(t, company, asof, ok, clean_body(wb, t) if ok else error_body(wb, t)), encoding="utf-8")
        made.append(p)
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out")
    a = ap.parse_args()
    for p in build(Path(a.xlsx), Path(a.out) if a.out else Path(a.xlsx).parent):
        print(f"   súhrn: {p}")
