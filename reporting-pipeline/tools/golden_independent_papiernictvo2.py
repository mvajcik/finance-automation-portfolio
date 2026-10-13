#!/usr/bin/env python3
"""Kotva B zmluvy reportu Papiernictvo 2 (profiles/papiernictvo2/contract.json, §5).

Nezávislý prepočet čísel P01–P16 PRIAMO zo vstupných súborov dodávky — bez kódu motora (pipeline/) aj
generátora, bez DuckDB, iná cesta: csv nad denníkom a pokladňou, openpyxl nad plánom, Decimal pre centy.
Definície (riadky výsledovky, metóda odhadu, pravidlá rizika a citlivosti) sú prepísané zo zmluvy §2–§3.

Motor ho volá NAŽIVO nad každou dodávkou (pipeline/engine.py _contract_state); nesmie importovať nič
z pipeline/ (gate test). Výstup: values (P01–P16) + odtlačok dodávky + obdobie.
Použitie: python3 tools/golden_independent_papiernictvo2.py [--input DIR] [--out FILE]
"""
import argparse
import csv
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "papiernictvo2"
Y2, Y1, AS_OF_M, RR = "2026", "2025", 9, 3                  # zmluva §1: k 2026-09, tempo posledných 3 mesiacov
TAX = Decimal("0.21")                                       # zmluva §2: daň z príjmov 21 %
TAX_CC = "C00"
# zmluva §2 — riadky výsledovky: účty (presne, s analytikami podľa zápisu v denníku)
ROWS = {"Revenue": ["604"], "Cost of goods sold": ["504"], "Staff": ["521", "524"], "Rent": ["518100"],
        "Energy": ["502"], "Marketing": ["518500"], "Services": ["511", "518200", "518300", "518400"],
        "Other": ["501", "568"], "Depreciation": ["551"], "Interest and financial": ["562"], "Income tax": ["591"]}
EBITDA = ["Revenue", "Cost of goods sold", "Staff", "Rent", "Energy", "Marketing", "Services", "Other"]
PBT = EBITDA + ["Depreciation", "Interest and financial"]
NET = PBT + ["Income tax"]
ACC_ROW = {a: r for r, accs in ROWS.items() for a in accs}


def fingerprint(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")):
        h.update(f"{f.name}:{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode("utf-8"))
    return h.hexdigest()


def read_journal(d: Path) -> dict:
    """(stredisko, riadok, rok, mesiac) → Σ (D − MD) v Decimal; bez dokladov počiatočného stavu (PS)."""
    out = {}
    for f in sorted(d.glob("journal_*.csv")):
        with f.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["Document"].startswith("PS"):
                    continue
                dd, mm, yy = r["Date"].split(".")
                amt = Decimal(r["Amount"])
                for acc, sgn in ((r["Dr"], -1), (r["Cr"], 1)):
                    row = ACC_ROW.get(acc)
                    if row:
                        k = (r["Cost centre"], row, yy, int(mm))
                        out[k] = out.get(k, Decimal(0)) + sgn * amt
    return out


def read_plan(d: Path) -> dict:
    """(stredisko, riadok, mesiac) → plán so znamienkom (výnos +, náklad −); daň plánu = −21 % × plán zisku pred
    zdanením mesiaca za firmu, na centy od nuly, na centrálu (zmluva §2)."""
    from openpyxl import load_workbook
    ws = load_workbook(d / f"plan_{Y2}.xlsx", read_only=True, data_only=True)["Plan 2026"]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Account")
    head = rows[hi]
    out = {}
    for r in rows[hi + 1:]:
        if not r or r[0] is None or str(r[0]) not in ACC_ROW:
            continue
        acc, cc, row = str(r[0]), str(r[1]), ACC_ROW[str(r[0])]
        for j in range(2, len(head)):
            mo = int(str(head[j])[5:7])
            v = Decimal(str(r[j] or 0))
            k = (cc, row, mo)
            out[k] = out.get(k, Decimal(0)) + (v if acc.startswith("6") else -v)
    for mo in range(1, 13):
        pbt = sum((v for (cc, row, m), v in out.items() if m == mo and row in PBT), Decimal(0))
        out[(TAX_CC, "Income tax", mo)] = (-TAX * pbt).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return out


def read_pos(d: Path) -> list:
    """(rok, mesiac, kategória, s DPH, bez DPH) z každého riadku bločku; hlavička exportu a riadok SPOLU sa preskočia."""
    out = []
    for f in sorted(d.glob("pos_*.csv")):
        lines = f.read_text(encoding="utf-8").splitlines()
        hi = next(i for i, x in enumerate(lines) if x.startswith("receipt;"))
        for r in csv.DictReader(lines[hi:], delimiter=";"):
            if r["receipt"] == "TOTAL" or not r["datetime"]:
                continue
            dd, mm, rest = r["datetime"].split(".")
            g = float(r["total_incl_vat"].replace(",", "."))
            out.append((rest[:4], int(mm), r["category"], g, g / (1 + int(r["vat_rate"]) / 100)))
    return out


def compute(inp: Path) -> dict:
    inp = Path(inp)
    act, plan, pos = read_journal(inp), read_plan(inp), read_pos(inp)
    ccs = sorted({k[0] for k in act} | {k[0] for k in plan})
    ytd, rest, rr = range(1, AS_OF_M + 1), range(AS_OF_M + 1, 13), range(AS_OF_M - RR + 1, AS_OF_M + 1)
    A = lambda cc, row, y, ms: float(sum((act.get((cc, row, y, m), Decimal(0)) for m in ms), Decimal(0)))  # noqa: E731
    P = lambda cc, row, ms: float(sum((plan.get((cc, row, m), Decimal(0)) for m in ms), Decimal(0)))  # noqa: E731
    # odhad zvyšku roka (zmluva §2): plán mesiaca × (skutočnosť ÷ plán za posledné 3 mesiace); bez plánu priemer
    fc = {}
    for cc in ccs:
        for row in ROWS:
            if row == "Income tax":
                continue
            a, p = A(cc, row, Y2, rr), P(cc, row, rr)
            for m in rest:
                fc[(cc, row, m)] = P(cc, row, [m]) * a / p if p else a / RR
    for m in rest:
        fc[(TAX_CC, "Income tax", m)] = -float(TAX) * sum(v for (cc, row, mm), v in fc.items() if mm == m and row in PBT)
    F = lambda row: sum(v for (cc, r, m), v in fc.items() if r == row)  # noqa: E731
    tot_a = lambda rows, y=Y2, ms=ytd: sum(A(cc, r, y, ms) for cc in ccs for r in rows)  # noqa: E731
    tot_p = lambda rows, ms: sum(P(cc, r, ms) for cc in ccs for r in rows)  # noqa: E731
    tot_f = lambda rows: sum(F(r) for r in rows)  # noqa: E731
    v = {}
    for base, rows in ((1, ["Revenue"]), (5, EBITDA), (9, NET)):
        v[f"P{base:02d}"] = tot_a(rows)                       # YTD skutočnosť
        v[f"P{base + 1:02d}"] = tot_p(rows, ytd)              # YTD plán
        v[f"P{base + 2:02d}"] = tot_a(rows) + tot_f(rows)     # odhad roka
        v[f"P{base + 3:02d}"] = tot_p(rows, range(1, 13))     # plán roka
    v["P13"] = A("S03", "Rent", Y2, ytd) - P("S03", "Rent", ytd)    # Predajňa OC · Nájom voči plánu
    # P14 energie: skok v Q1 zopakovaný vo zvyšku roka
    q1 = range(1, 4)
    yoy = tot_a(["Energy"], Y2, q1) / tot_a(["Energy"], Y1, q1)
    v["P14"] = tot_a(["Energy"], Y1, rest) * yoy - tot_f(["Energy"])
    # P15 papiernictvo: oprava odhadu na sezónny podiel kategórie
    net = {}
    for y, m, cat, g, n in pos:
        net[(y, m, cat)] = net.get((y, m, cat), 0.0) + n
    cn = lambda cat, y, ms: sum(net.get((y, m, cat), 0.0) for m in ms)  # noqa: E731
    tn = lambda y, ms: sum(x for (yy, m, _), x in net.items() if yy == y and m in ms)  # noqa: E731
    q3 = range(7, 10)
    yoy_p = cn("Stationery", Y2, q3) / cn("Stationery", Y1, q3) - 1
    share_rr = cn("Stationery", Y1, rr) / tn(Y1, rr)
    gm = tot_a(["Revenue", "Cost of goods sold"]) / tot_a(["Revenue"])
    v["P15"] = yoy_p * (cn("Stationery", Y1, rest) - tn(Y1, rest) * share_rr) * gm
    # P16 hračky: medziročná zmena Q3 tržieb s DPH (v %)
    gross = lambda cat, y, ms: sum(g for yy, m, c, g, _ in pos if yy == y and c == cat and m in ms)  # noqa: E731
    v["P16"] = (gross("Toys", Y2, q3) / gross("Toys", Y1, q3) - 1) * 100
    v["P17"] = (v["P07"] - v["P08"]) / abs(v["P08"]) * 100          # EBITDA odhad voči plánu roka v %
    return {"_meta": {"anchor": "B — independent recalculation from the inputs (no engine, no generator)",
                      "contract": "profiles/papiernictvo2/contract.json", "as_of": f"{Y2}-{AS_OF_M:02d}",
                      "delivery_sha256": fingerprint(inp)},
            "values": {k: round(x, 4 if k in ("P16", "P17") else 2) for k, x in sorted(v.items())}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(PROFILE / "data" / "clean"))
    ap.add_argument("--out")
    a = ap.parse_args()
    res = compute(Path(a.input))
    txt = json.dumps(res, ensure_ascii=False, indent=2) + "\n"
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
