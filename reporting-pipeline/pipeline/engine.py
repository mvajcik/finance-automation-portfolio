#!/usr/bin/env python3
"""engine.py — profilový motor: jedna linka, firma = profil.

    engine.py --profile profiles/<firma> --input <priečinok dodávky> --out <výstup>
              [--truth <etalón.json>]

vstupy (súbory podľa profilu) → staging → kontroly (všetky, zbierajú nálezy) →
výsledovka + mesiace × predajne + plán vs. skutočnosť → verdikt (SEDÍ / SEDÍ
S VÝNIMKAMI / NESEDÍ) → výstup → výstup znovu načítaný z disku (od stroja X/N).
Pri NESEDÍ sa čísla boardu NEVYDAJÚ — vydá sa len protokol kontrol (stroj
nedá boardu čísla, o ktorých vie, že nesedia).

Exit: 0 = SEDÍ / SEDÍ S VÝNIMKAMI · 1 = NESEDÍ · 2 = chýba dodávka alebo profil.
"""
import os
import sys

_HERE_S = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path
               if p not in ("", _HERE_S) and os.path.abspath(p or ".") != _HERE_S]

import argparse                 # noqa: E402
import csv                      # noqa: E402
import datetime as dt           # noqa: E402
import importlib.util           # noqa: E402
import json                     # noqa: E402
import re                       # noqa: E402
from pathlib import Path        # noqa: E402

ROOT = Path(_HERE_S).resolve().parent               # koreň repa (kotva B zmluvy: tools/golden_nezavisly.py)

_spec = importlib.util.spec_from_file_location("zl_checks_engine", Path(_HERE_S) / "checks.py")
_checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_checks)
CHECKS = _checks.CHECKS
_spec_bp = importlib.util.spec_from_file_location("zl_boardpack_engine", Path(_HERE_S) / "boardpack.py")
_bp = importlib.util.module_from_spec(_spec_bp)
_spec_bp.loader.exec_module(_bp)

VERDICTS = ("SEDÍ", "SEDÍ S VÝNIMKAMI", "NESEDÍ")


def sk_eur(v: float, sign: bool = False) -> str:
    """Suma po slovensky: medzera na tisíce, bez desatinných, znamienko mínus (−)."""
    s = f"{abs(v):,.0f}".replace(",", "\u00a0")
    pre = "−" if v < 0 else ("+" if sign and v > 0 else "")
    return f"{pre}{s} €"


def sk_pct(v: float) -> str:
    """Percento po slovensky: desatinná čiarka, medzera pred %, znamienko."""
    s = f"{abs(v) * 100:.1f}".replace(".", ",")
    return f"{'−' if v < 0 else '+'}{s} %"


# ------------------------------------------------------------------ profil
def months_of(period: dict) -> list:
    y, m = map(int, period["start"].split("-"))
    out = []
    for _ in range(period["months"]):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def months_ext(profile: dict, spec: dict) -> list:
    """Mesiace zdroja: obdobie + `extra_months_before` (napr. úhrady za obdobie,
    zaplatené pred jeho začiatkom)."""
    k = int(spec.get("extra_months_before", 0))
    y, m = map(int, profile["period"]["start"].split("-"))
    m -= k
    while m < 1:
        y, m = y - 1, m + 12
    return months_of({"start": f"{y}-{m:02d}", "months": profile["period"]["months"] + k})


def expected_files(profile: dict) -> list:
    ms = months_of(profile["period"])
    y2 = profile["period"]["as_of"][:4]
    out = []
    for spec in profile["inputs"].values():
        if spec["per"] == "month":
            for cc in spec.get("cost_centers", [None]):             # súbor per stredisko × mesiac (pokladne)
                out += [spec["pattern"].format(ym=ym, cc=cc) for ym in months_ext(profile, spec)]
        else:
            out.append(spec["pattern"].format(y2=y2))
    return out


# ------------------------------------------------------------------ načítanie
def _bulk(con, table: str, types: list, rows: list) -> None:
    """Hromadný zápis do staging tabuľky cez dočasný CSV (executemany je
    riadok po riadku — 18 s z 19 s behu). Hodnoty idú ako text, typy z `types`;
    None → NULL (prázdny reťazec sa zachová ako '' vďaka úvodzovkám)."""
    import tempfile
    if not rows:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
        name = fh.name
    try:
        cols = ", ".join(f"'c{i}': 'VARCHAR'" for i in range(len(types)))
        casts = ", ".join(
            f"CASE WHEN c{i} IS NULL THEN NULL ELSE CAST(c{i} AS {ty}) END" for i, ty in enumerate(types))
        con.execute(f"INSERT INTO {table} SELECT {casts} FROM read_csv('{name}', header=false, "
                    f"columns={{{cols}}}, quote='\"', escape='\"', nullstr='')")
    finally:
        os.unlink(name)


def _cell(v):
    isnum = isinstance(v, (int, float)) and not isinstance(v, bool)
    return (None if v is None else str(v)), isnum, (float(v) if isnum else None)


def _read_gl_file(g: Path, spec: dict, gl_rows: list, gl_cells: list, issues: list) -> None:
    """Jedna mesačná predvaha (xlsx) → riadky + bunky súm (tak, ako sú)."""
    from openpyxl import load_workbook
    if not g.is_file():
        return
    ws = load_workbook(g, read_only=True, data_only=True)[spec["sheet"]]
    rows = ws.iter_rows(values_only=True)
    head = list(next(rows, []))
    if head != spec["header"]:
        issues.append(f"{g.name}: hlavička {head} ≠ profil {spec['header']}")
        return
    for i, r in enumerate(rows, start=2):
        r = (list(r) + [None] * 6)[:6]
        gl_rows.append((g.name, i, str(r[0]), str(r[1]), str(r[2])))
        for col, v in (("Obrat MD", r[4]), ("Obrat D", r[5])):
            gl_cells.append((g.name, i, col, *_cell(v)))


_GL_TABLES = """
CREATE TABLE gl AS SELECT r.ym, r.cc, r.account,
  (SELECT val FROM gl_cells c WHERE c.file = r.file AND c.line = r.line AND c.col = 'Obrat MD') AS debit,
  (SELECT val FROM gl_cells c WHERE c.file = r.file AND c.line = r.line AND c.col = 'Obrat D') AS credit
FROM gl_raw r"""


# ------------------------------------------------------------------ model retail_full
def _read_csv_export(f: Path, spec: dict, issues: list):
    """CSV export tak, ako ho posiela systém: kódovanie a oddeľovač z profilu, voliteľne úvodné
    riadky exportu pred hlavičkou, pätička (SPOLU) a riadky zostatkov. Vráti (riadky, meta, pätička)."""
    import csv as _csv
    b, enc = f.read_bytes(), spec.get("encoding", "utf-8")
    try:
        raw = b.decode(enc)
    except UnicodeDecodeError as e:
        issues.append(f"{f.name}: nedá sa prečítať v kódovaní {enc} (bajt {e.start}) — iný export alebo poškodený súbor")
        return [], {}, None
    if enc.lower() in ("cp1250", "windows-1250") and any(x > 127 for x in b):
        try:
            b.decode("utf-8")
            issues.append(f"{f.name}: súbor je v UTF-8, profil čaká {enc} — texty by sa rozsypali")
        except UnicodeDecodeError:
            pass
    lines = raw.splitlines()
    sep = spec["sep"]
    head = sep.join(spec["header"])
    meta, footer, rows = {}, None, []
    try:
        start = lines.index(head) if spec.get("skip_until_header") else 0
    except ValueError:
        issues.append(f"{f.name}: hlavička {spec['header']} sa v súbore nenašla")
        return [], meta, footer
    if not spec.get("skip_until_header") and lines[:1] != [head]:
        issues.append(f"{f.name}: hlavička {lines[:1]} ≠ profil {spec['header']}")
        return [], meta, footer
    for ln in lines[:start] + lines:
        for key, label in spec.get("meta", {}).items():
            if ln.startswith(label + sep):
                meta[key] = ln.split(sep, 1)[1]
    for i, r in enumerate(_csv.reader(lines[start + 1:], delimiter=sep), start=start + 2):
        if not r or all(x == "" for x in r):
            continue
        if spec.get("footer_prefix") and r[0] == spec["footer_prefix"]:
            footer = r
            continue
        if any(r[0] == lab for lab in spec.get("meta", {}).values()):
            continue
        if len(r) != len(spec["header"]):
            issues.append(f"{f.name} r{i}: {len(r)} polí ≠ {len(spec['header'])} podľa profilu")
        rows.append((f.name, i, *((r + [None] * len(spec["header"]))[:len(spec["header"])])))
    return rows, meta, footer


def _xlsx_table(f: Path, spec: dict, issues: list):
    """Tabuľka z xlsx: hlavička sa nájde v hárku (môže byť pod nadpisom); dátumy → ISO text."""
    from openpyxl import load_workbook
    ws = load_workbook(f, read_only=True, data_only=True)[spec["sheet"]]
    rows = list(ws.iter_rows(values_only=True))
    want = spec.get("header") or spec.get("header_first")
    hi = next((i for i, r in enumerate(rows) if list(r[:len(want)]) == want), None)
    if hi is None:
        issues.append(f"{f.name}: hlavička {want} sa v hárku {spec['sheet']} nenašla")
        return [], []
    head = [str(x) for x in rows[hi]]
    out = []
    for i, r in enumerate(rows[hi + 1:], start=hi + 2):
        if all(v is None for v in r):
            continue
        out.append((f.name, i, *[(v.isoformat()[:10] if hasattr(v, "isoformat") else (None if v is None else str(v)))
                                for v in r]))
    return head, out


def _col(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def load_full(con, inp: Path, profile: dict) -> list:
    """Model retail_full: 9 zdrojov → raw tabuľky (text TAK, AKO PRIŠIEL) → SQL vrstvy stg/core/mart
    zo súborov profilu (`sql_dir`). Typy a tvar overí stg_parse_contract (SQL vyhlási, čo sa nedalo prečítať)."""
    ins = profile["inputs"]
    issues = []
    # predvaha → gl (zdieľané kontroly numeric_contract, account_mapping_complete, pl_control_total)
    con.execute("CREATE TABLE pos_raw (file TEXT, line INT, date_txt TEXT, shop TEXT, category TEXT, amount_txt TEXT)")
    con.execute("CREATE TABLE plan_cells (file TEXT, line INT, col TEXT, raw TEXT, is_num BOOLEAN, val DOUBLE, shop TEXT, month INT)")
    con.execute("CREATE TABLE gl_raw (file TEXT, line INT, ym TEXT, cc TEXT, account TEXT)")
    con.execute("CREATE TABLE gl_cells (file TEXT, line INT, col TEXT, raw TEXT, is_num BOOLEAN, val DOUBLE)")
    gl_rows, gl_cells = [], []
    for ym in months_ext(profile, ins["gl"]):
        _read_gl_file(inp / ins["gl"]["pattern"].format(ym=ym), ins["gl"], gl_rows, gl_cells, issues)
    _bulk(con, "gl_raw", ["TEXT", "INT", "TEXT", "TEXT", "TEXT"], gl_rows)
    _bulk(con, "gl_cells", ["TEXT", "INT", "TEXT", "TEXT", "BOOLEAN", "DOUBLE"], gl_cells)
    con.execute(_GL_TABLES)
    # CSV exporty
    for src in ("pos", "journal", "payroll", "bank", "stock_moves", "stock_state"):
        spec = ins[src]
        cols = [_col(h) for h in spec["header"]]
        con.execute(f"CREATE TABLE raw_{src} (file TEXT, line INT, " + ", ".join(f"{c} TEXT" for c in cols) + ")")
        rows, metas, footers = [], [], []
        for cc in spec.get("cost_centers", [None]):
            for ym in months_ext(profile, spec):
                f = inp / spec["pattern"].format(ym=ym, cc=cc)
                if not f.is_file():
                    continue
                r, meta, footer = _read_csv_export(f, spec, issues)
                rows += r
                if spec.get("meta"):
                    metas.append((f.name, meta.get("opening"), meta.get("closing")))
                if spec.get("footer_prefix"):
                    footers.append((f.name, None if footer is None else footer[-2]))
        _bulk(con, f"raw_{src}", ["TEXT", "INT"] + ["TEXT"] * len(cols), rows)
        if spec.get("meta"):
            con.execute(f"CREATE TABLE raw_{src}_meta (file TEXT, opening TEXT, closing TEXT)")
            _bulk(con, f"raw_{src}_meta", ["TEXT", "TEXT", "TEXT"], metas)
        if spec.get("footer_prefix"):
            con.execute(f"CREATE TABLE raw_{src}_footer (file TEXT, total TEXT)")
            _bulk(con, f"raw_{src}_footer", ["TEXT", "TEXT"], footers)
    # xlsx: faktúry (mesačne), plán, číselníky
    spec = ins["invoices"]
    cols = [_col(h) for h in spec["header"]]
    con.execute("CREATE TABLE raw_invoices (file TEXT, line INT, " + ", ".join(f"{c} TEXT" for c in cols) + ")")
    rows = []
    for ym in months_ext(profile, spec):
        f = inp / spec["pattern"].format(ym=ym)
        if f.is_file():
            head, r = _xlsx_table(f, spec, issues)
            rows += [x[:2 + len(cols)] for x in r]
    _bulk(con, "raw_invoices", ["TEXT", "INT"] + ["TEXT"] * len(cols), rows)
    y2 = profile["period"]["as_of"][:4]
    f = inp / ins["plan"]["pattern"].format(y2=y2)
    con.execute("CREATE TABLE raw_plan (file TEXT, line INT, ucet TEXT, stredisko TEXT, mesiac TEXT, suma TEXT)")
    if f.is_file():
        head, r = _xlsx_table(f, ins["plan"], issues)
        _bulk(con, "raw_plan", ["TEXT", "INT", "TEXT", "TEXT", "TEXT", "TEXT"],
              [(x[0], x[1], x[2], x[3], head[j], x[j + 2]) for x in r for j in range(2, len(head))])
    f = inp / ins["dims"]["pattern"]
    con.execute("CREATE TABLE raw_dims (sheet TEXT, line INT, k TEXT, v1 TEXT, v2 TEXT, v3 TEXT)")
    if f.is_file():
        from openpyxl import load_workbook
        wb = load_workbook(f, read_only=True, data_only=True)
        rows = []
        for sh in ins["dims"]["sheets"]:
            if sh not in wb.sheetnames:
                issues.append(f"{f.name}: chýba hárok {sh}")
                continue
            for i, r in enumerate(list(wb[sh].iter_rows(values_only=True))[1:], start=2):
                r = [None if v is None else str(v) for v in (list(r) + [None] * 4)[:4]]
                rows.append((sh, i, *r))
        _bulk(con, "raw_dims", ["TEXT", "INT", "TEXT", "TEXT", "TEXT", "TEXT"], rows)
    # SQL vrstvy
    con.execute("CREATE TABLE pl_map (account TEXT, row TEXT)")
    accs = [r[0] for r in con.execute("SELECT DISTINCT md FROM raw_journal UNION SELECT DISTINCT d FROM raw_journal "
                                      "UNION SELECT DISTINCT ucet FROM raw_plan").fetchall() if r[0]]
    pm = [(a, _checks.resolve_account(a, profile["pl_mapping"])) for a in accs]
    con.executemany("INSERT INTO pl_map VALUES (?, ?)", [x for x in pm if x[1]] or [("-", "-")])
    con.execute("CREATE TABLE cost_centers (cc TEXT, shop TEXT)")
    con.executemany("INSERT INTO cost_centers VALUES (?, ?)", [(s["cost_center"], s["name"]) for s in profile["shops"]])
    bpc = profile.get("board_pack")
    if bpc:                         # vstup pre sql/<firma>/40_boardpack.sql: štruktúra výsledovky a parametre z profilu
        con.execute("CREATE TABLE bp_var_rows (row TEXT)")
        con.executemany("INSERT INTO bp_var_rows VALUES (?)", [(r,) for r in bpc["variance_rows"]])
        con.execute("CREATE TABLE pl_struct (row TEXT, part TEXT)")
        con.executemany("INSERT INTO pl_struct VALUES (?, ?)", _bp.pl_struct(profile))
        as_of = profile["period"]["as_of"]
        tax_shop = next(s["name"] for s in profile["shops"] if s["cost_center"] == bpc["tax_cost_center"])
        con.execute("CREATE TABLE bp_params AS SELECT ?::VARCHAR AS y2, ?::VARCHAR AS y1, ?::INT AS as_of_m, "
                    "?::INT AS runrate_months, ?::DOUBLE AS tax_rate, ?::VARCHAR AS tax_row, ?::VARCHAR AS tax_shop, "
                    "?::VARCHAR AS pbt_row, ?::VARCHAR AS ebitda_row",
                    [as_of[:4], str(int(as_of[:4]) - 1), int(as_of[5:]), bpc["runrate_months"], bpc["tax_rate"],
                     bpc["tax_row"], tax_shop, bpc["pbt_row"], bpc["ebitda_row"]])
    for f in sorted((ROOT / profile["sql_dir"]).glob("*.sql")):
        con.execute(f.read_text(encoding="utf-8"))
    return issues


# ------------------------------------------------------------------ marty
def _marts_from_pl_base(con, profile: dict) -> dict:
    """Spoločná časť modelov: z martu pl_base (ym, shop, row, amount) výsledovka YTD / minulý rok,
    mesiace × strediská, plán vs. skutočnosť, čísla pre meter a board."""
    as_of = profile["period"]["as_of"]
    y2 = as_of[:4]
    y1 = str(int(y2) - 1)
    m_as_of = as_of[5:]
    shops = [s["name"] for s in profile["shops"]]
    base_rows = [r for r in profile["pl_rows"] if r not in profile["pl_subtotals"]]

    def pl(year, upto_month=None):
        q = ("SELECT shop, row, sum(amount) FROM pl_base WHERE ym LIKE ? "
             + ("AND substr(ym, 6, 2) <= ? " if upto_month else "") + "GROUP BY 1, 2")
        args = [f"{year}-%"] + ([upto_month] if upto_month else [])
        t = {(s, r): 0.0 for s in shops for r in base_rows}
        for s, r, v in con.execute(q, args).fetchall():
            t[(s, r)] = v or 0.0          # nečitateľná bunka (NULL) → 0; verdikt ju už menuje
        for sub, parts in profile["pl_subtotals"].items():
            for s in shops:
                t[(s, sub)] = sum(t[(s, p)] for p in parts)
        for r in profile["pl_rows"]:
            t[("Spolu", r)] = sum(t[(s, r)] for s in shops)
        return t

    ytd, ytd_prev = pl(y2, m_as_of), pl(y1, m_as_of)
    rev = {(ym, s): (v or 0.0) for ym, s, v in con.execute(
        "SELECT ym, shop, amount FROM pl_base WHERE row = 'Tržby'").fetchall()}
    months = months_of(profile["period"])
    plan = {(s, m): a for s, m, a in con.execute("SELECT shop, month, amount FROM plan").fetchall()}
    plan_ytd = {s: sum(plan.get((s, m), 0.0) or 0.0 for m in range(1, int(m_as_of) + 1)) for s in shops}
    wages_row = profile.get("wages_row", "Mzdy")
    res = {
        "pos_rows": con.execute("SELECT count(*) FROM pos_raw").fetchone()[0],
        "revenue_net_y1": sum(v for (ym, _), v in rev.items() if ym.startswith(y1)),
        "revenue_net_y2": sum(v for (ym, _), v in rev.items() if ym.startswith(y2)),
        "revenue_net_y2_by_shop": {s: sum(v for (ym, s2), v in rev.items() if s2 == s and ym.startswith(y2))
                                   for s in shops},
        "revenue_net_dec_y2": sum(v for (ym, _), v in rev.items() if ym == f"{y2}-12"),
        "ytd_revenue_net": ytd[("Spolu", "Tržby")],
        "ytd_ebitda_total": ytd[("Spolu", "EBITDA")],
        "ytd_ebitda_by_shop": {s: ytd[(s, "EBITDA")] for s in shops},
        "ytd_wages_total": -ytd.get(("Spolu", wages_row), 0.0),
        "ytd_pl_by_row": {r: ytd[("Spolu", r)] for r in profile["pl_rows"]},
    }
    return {"ytd": ytd, "ytd_prev": ytd_prev, "rev": rev, "months": months, "shops": shops,
            "plan_ytd": plan_ytd, "results": res, "y1": y1, "y2": y2, "as_of": as_of}


# ------------------------------------------------------------------ board
def board_findings(con, profile: dict, m: dict) -> list:
    """Zistenia pre board — pravidlá s prahmi z profilu, žiadne natvrdo písané firmy."""
    b = profile["board"]
    out = []
    rows = [r for r in profile["pl_rows"] if r not in profile["pl_subtotals"] and r != "Tržby"]
    r1 = b["ebitda_vs_revenue"]
    for s in m["shops"]:
        rv0, rv1 = m["ytd_prev"][(s, "Tržby")], m["ytd"][(s, "Tržby")]
        e0, e1 = m["ytd_prev"][(s, "EBITDA")], m["ytd"][(s, "EBITDA")]
        if not rv0 and not rv1:
            continue                    # nákladové stredisko bez tržieb (centrála) — pravidlo sa naň nevzťahuje
        if not rv0 or not e0:
            out.append({"rule": "ebitda_vs_revenue", "key": s,
                        "text": f"{s}: medziročné porovnanie nemožné — nulový základ minulého roka"})
            continue
        ry, ey = rv1 / rv0 - 1, e1 / abs(e0) - (1 if e0 > 0 else -1)
        if ry > r1["min_revenue_yoy"] and ey < r1["max_ebitda_yoy"]:
            # dôvod = zmena riadku NAD RÁMEC rastu tržieb (náklad, ktorý rastie s tržbami,
            # nie je vysvetlenie poklesu)
            k = rv1 / rv0
            deltas = {r: m["ytd"][(s, r)] - m["ytd_prev"][(s, r)] * k for r in rows}
            drv = min(deltas, key=deltas.get)
            out.append({"rule": "ebitda_vs_revenue", "key": s,
                        "text": f"{s}: tržby {sk_pct(ry)}, ale EBITDA {sk_pct(ey)} medziročne — hlavný dôvod: "
                                f"{drv} {sk_eur(deltas[drv], True)} nad rámec rastu tržieb"})
    r2 = b["month_concentration"]
    mon = {}
    ebitda_parts = [r for r in profile["pl_subtotals"].get("EBITDA", []) if r not in profile["pl_subtotals"]]
    for ym, s, v in con.execute(                  # len zložky EBITDA — nie odpisy, úroky, daň
            "SELECT ym, shop, sum(amount) FROM pl_base WHERE list_contains(?::VARCHAR[], row) GROUP BY 1, 2",
            [ebitda_parts]).fetchall():
        if ym.startswith(m["y2"]) and ym <= m["as_of"]:
            mon[ym] = mon.get(ym, 0.0) + (v or 0.0)
    total = sum(mon.values())
    if total <= 0 and mon:
        out.append({"rule": "month_concentration", "key": "strata",
                    "text": f"YTD EBITDA {sk_eur(total)} — firma je v strate, koncentrácia mesiacov sa nepočíta"})
    if total > 0:
        n = len(mon)
        limit = r2["min_multiple_of_average"] / n          # 3× priemer: 12 mes. → 25 %, 6 mes. → 50 %
        span = "ročnej" if n == 12 else f"YTD ({n} mes.)"
        for ym, v in sorted(mon.items()):
            if v / total >= limit:
                out.append({"rule": "month_concentration", "key": ym,
                            "text": f"{ym}: {f'{v / total * 100:.1f}'.replace('.', ',')} % {span} EBITDA v jednom mesiaci "
                                    f"({f'{v / total * n:.1f}'.replace('.', ',')}× priemer) — "
                                    f"slabý {ym[5:]}. mesiac ohrozí celý rok"})
    r3 = b["category_decline"]
    q = {}
    for cat, y, qq, v in con.execute(
            "SELECT category, year(day), quarter(day), sum(gross) FROM pos GROUP BY 1, 2, 3").fetchall():
        q[(cat, str(y), qq)] = v
    last_q = (int(m["as_of"][5:]) - 1) // 3 + 1
    for cat in sorted({k[0] for k in q}):
        yoy = []
        for qq in range(1, last_q + 1):
            a, c = q.get((cat, m["y1"], qq)), q.get((cat, m["y2"], qq))
            yoy.append(None if not a or c is None else c / a - 1)
        n = r3["consecutive_quarters"]
        tail = yoy[-n:]
        if len(tail) == n and all(x is not None and x < 0 for x in tail):
            qs = ", ".join(f"Q{last_q - n + 1 + i} {sk_pct(x)}" for i, x in enumerate(tail))
            out.append({"rule": "category_decline", "key": cat,
                        "text": f"{cat}: medziročný pokles {n} štvrťroky po sebe ({qs})"})
    return out


# ------------------------------------------------------------------ výnimky + verdikt
def apply_exceptions(results: list, exc: list, as_of: str) -> tuple:
    """(verdikt, riadky protokolu). Výnimka kryje PRÁVE JEDEN nález svojej
    kontroly — ak jej `match` sedí na viac nálezov, je príliš široká a nekryje
    nič. Expirovaná výnimka nekryje (menovite)."""
    hits = {}
    for cid, ok, detail, items in results:
        if ok:
            continue
        for it in items or [detail]:
            for i, e in enumerate(exc):
                if e["check"] == cid and e["match"] in it:
                    hits[i] = hits.get(i, 0) + 1
    hard, covered, lines = 0, 0, []
    for cid, ok, detail, items in results:
        if ok:
            lines.append(("PASS", cid, detail))
            continue
        left = []
        for it in items or [detail]:
            idx = next((i for i, e in enumerate(exc) if e["check"] == cid and e["match"] in it), None)
            ex = exc[idx] if idx is not None else None
            if ex and hits[idx] == 1 and as_of <= ex["valid_until"]:
                covered += 1
                lines.append(("VÝNIMKA", cid, f"{it} — {ex['reason']} (platí do {ex['valid_until']})"))
                continue
            if ex and hits[idx] > 1:
                it += f" — výnimka '{ex['match']}' je príliš široká (sedí na {hits[idx]} nálezov), nekryje"
            elif ex:
                it += f" — výnimka expirovala {ex['valid_until']}"
            left.append(it)
        if left:
            hard += 1
            lines.append(("FAIL", cid, "; ".join(left)))
    verdict = VERDICTS[2] if hard else (VERDICTS[1] if covered else VERDICTS[0])
    return verdict, lines


# ------------------------------------------------------------------ výstup
def write_outputs(out: Path, profile: dict, verdict: str, lines: list, m: dict | None,
                  findings: list, truth_used: bool, outside: tuple = None, contract_note: str = None,
                  panel: dict = None) -> dict:
    """Zapíše prehlad.xlsx + report.md. Vráti očakávané čísla hárkov pre spätné
    načítanie (sheet, riadok, stĺpec) → hodnota. `panel` = riadky
    kontrolného panelu, chybné riadky a zdroje z `panel_model()` → hárky Kontrolný panel + Chybné riadky
    (overuje ich control_panel_readback, nie xlsx_readback)."""
    from openpyxl import Workbook
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 1, 1)
    ws = wb.active
    ws.title = "Prehľad"
    expected = {}
    headers = {}                    # hlavičky dátových hárkov (pre spätné načítanie)
    texts = []                      # texty Prehľadu v poradí zápisu (pre spätné načítanie)
    _append = ws.append

    def put(row):
        _append(row)
        texts.extend(str(v) for v in row if v is not None and not isinstance(v, (int, float)))
    ws_append = put
    nv = list(profile["not_verified"]) + ([] if truth_used else ["etalón neaplikovaný na túto dodávku"])
    if outside:
        nv.append(f"{outside[0]} riadkov predvahy mimo výsledovky (triedy mimo {'/'.join(profile['account_scope'])}, "
                  f"obraty {outside[1]:,.2f} €) — do výsledovky nevstupujú a neoverovali sa")
    ws_append([profile["company"], f"stav k {profile['period']['as_of']}"])
    ws_append(["Verdikt", verdict])
    if contract_note:
        ws_append(["Zmluva reportu", contract_note])
    md = [f"# {profile['company']} — prehľad k {profile['period']['as_of']}", "", f"**Verdikt: {verdict}**", ""]
    if m is not None:
        ytd = m["ytd"]
        ws_append(["YTD EBITDA (€)", round(ytd[("Spolu", "EBITDA")], 2)])
        ws_append(["YTD tržby (€)", round(ytd[("Spolu", "Tržby")], 2)])
        expected[("Prehľad", "YTD EBITDA (€)", "B")] = ytd[("Spolu", "EBITDA")]
        expected[("Prehľad", "YTD tržby (€)", "B")] = ytd[("Spolu", "Tržby")]
        md += [f"**YTD EBITDA: {ytd[('Spolu', 'EBITDA')]:,.2f} €** · YTD tržby: {ytd[('Spolu', 'Tržby')]:,.2f} €", ""]
        exc_lines = [d for st, _, d in lines if st == "VÝNIMKA"]
        if exc_lines:
            ws_append([])
            ws_append(["Schválené výnimky"])
            md += ["## Schválené výnimky", ""]
            for d in exc_lines:
                ws_append(["•", d])
                md.append(f"- {d}")
            md.append("")
        ws_append([])
        ws_append(["Zistenia pre board"])
        md += ["## Zistenia pre board", ""]
        for f in findings or [{"text": "stroj nenašiel zistenie nad prahmi profilu"}]:
            ws_append(["•", f["text"]])
            md.append(f"- {f['text']}")
        md.append("")
        pk = m.get("pack")
        if pk:
            ebitda = pk["rows"][("Spolu", profile["board_pack"]["ebitda_row"])]
            ws_append([])
            ws_append(["Odhad EBITDA roka (€)", round(ebitda["fy_est"], 2)])
            ws_append(["Plán EBITDA roka (€)", round(ebitda["fy_plan"], 2)])
            expected[("Prehľad", "Odhad EBITDA roka (€)", "B")] = ebitda["fy_est"]
            expected[("Prehľad", "Plán EBITDA roka (€)", "B")] = ebitda["fy_plan"]
            ws_append(["Metóda odhadu", pk["method"]])
            md += ["## Board pack", "", f"*{pk['method']}*", ""]
            final = {c["key"]: c for c in pk["comments"]}
            for title, items in (("Odhad roka", pk["fy"]), ("Najväčšie odchýlky voči plánu", pk["variance"]),
                                 ("Riziká a príležitosti", [x for x in pk["ro"] if x["group"] != "citlivosť"]),
                                 ("Citlivosť odhadu na metódu (položky sa prekrývajú — nesčítavať)",
                                  [x for x in pk["ro"] if x["group"] == "citlivosť"])):
                ws_append([])
                ws_append([title])
                md += [f"### {title}", ""]
                for it in items or [{"key": None}]:
                    c = final.get(it["key"])
                    txt = c["final"] if c else "stroj nenašiel položku nad prahmi profilu"
                    ws_append(["•", txt])
                    md.append(f"- {c['final_md'] if c else txt}")
                md.append("")
            if pk["comment_warnings"]:
                ws_append([])
                ws_append(["Komentáre — upozornenia"])
                md += ["### Komentáre — upozornenia", ""]
                for w_ in pk["comment_warnings"]:
                    ws_append(["⚠", w_])
                    md.append(f"- ⚠ {w_}")
                md.append("")
    else:
        ws_append(["Čísla pre board", "NEVYDANÉ — kontroly nesedia, viď hárok Kontroly"])
        md += ["**Čísla pre board NEVYDANÉ — kontroly nesedia (protokol nižšie).**", ""]
    ws_append([])
    ws_append(["Čo som neoveroval"])
    md += ["## Čo som neoveroval", ""]
    for x in nv:
        ws_append(["•", x])
        md.append(f"- {x}")
    md.append("")

    if m is not None:
        shops = m["shops"] + ["Spolu"]
        w = wb.create_sheet("P&L YTD")
        w.append(["Riadok"] + shops)
        headers["P&L YTD"] = ["Riadok"] + shops
        for r in profile["pl_rows"]:
            w.append([r] + [round(m["ytd"][(s, r)], 2) for s in shops])
            for s in shops:
                expected[("P&L YTD", r, s)] = m["ytd"][(s, r)]
        month_sheet = f"Mesiace x {profile.get('entity_label', 'predajne')}"
        w = wb.create_sheet(month_sheet)
        w.append(["Mesiac"] + shops)
        headers[month_sheet] = ["Mesiac"] + shops
        for ym in m["months"]:
            vals = [m["rev"].get((ym, s), 0.0) for s in m["shops"]]
            w.append([ym] + [round(v, 2) for v in vals] + [round(sum(vals), 2)])
            for s, v in zip(shops, vals + [sum(vals)]):
                expected[(month_sheet, ym, s)] = v
        if "plan" in profile["inputs"]:
            w = wb.create_sheet("Plán vs skutočnosť")
            w.append(["Predajňa", "Plán YTD", "Skutočnosť YTD", "Rozdiel", "Plnenie"])
            headers["Plán vs skutočnosť"] = ["Predajňa", "Plán YTD", "Skutočnosť YTD", "Rozdiel", "Plnenie"]
            for s in m["shops"]:
                p, a = m["plan_ytd"][s], m["ytd"][(s, "Tržby")]
                row = [s, round(p, 2), round(a, 2), round(a - p, 2), round(a / p, 4) if p else None]
                w.append(row)
                for col, v in zip(["Plán YTD", "Skutočnosť YTD", "Rozdiel", "Plnenie"], row[1:]):
                    if v is not None:
                        expected[("Plán vs skutočnosť", s, col)] = v
        for name, head, rows in m.get("extra_sheets", []):
            w = wb.create_sheet(name)
            w.append(head)
            headers[name] = head
            for r in rows:
                w.append([(round(v, 4) if (name, j + 1) in m.get("pct_cols", ()) else round(v, 2))
                          if isinstance(v, float) else v for j, v in enumerate(r)])
                for col, v in zip(head[1:], r[1:]):
                    expected[(name, r[0], col)] = v if isinstance(v, str) else float(v)
        if m.get("pack"):
            _write_pack_sheets(wb, profile, m, expected, headers)
        md += ["## Výsledovka YTD (€)", "", "| Riadok | " + " | ".join(shops) + " |",
               "|---|" + "---:|" * len(shops)]
        for r in profile["pl_rows"]:
            md.append(f"| {r} | " + " | ".join(f"{m['ytd'][(s, r)]:,.2f}" for s in shops) + " |")
        md.append("")
    w = wb.create_sheet("Kontroly")
    w.append(["Stav", "Kontrola", "Detail"])
    md += ["## Kontroly", "", "| Stav | Kontrola | Detail |", "|---|---|---|"]
    for st, cid, d in lines:
        w.append([st, cid, d])
        md.append(f"| {st} | {cid} | {d.replace('|', '/')} |")
    if panel:
        _write_panel_sheets(wb, profile, verdict, panel)
        md += ["", "## Kontrolný panel", "", "| Semafor | Oblasť | Kontrola | Nálezov |", "|---|---|---|---:|"]
        md += [f"| {r['light']} | {r['group']} | {r['cid']} | {r['n']} |" for r in panel["rows"]]
        md.append("")
    for w in wb.worksheets:                      # čitateľnosť: formát čísel, šírky stĺpcov
        for row in w.iter_rows():
            for c in row:
                if isinstance(c.value, float):
                    pct = (w.title == "Plán vs skutočnosť" and c.column == 5) or \
                        (m is not None and (w.title, c.column) in m.get("pct_cols", ()))   # podiel → board vidí %
                    c.number_format = "0.0%" if pct else "#,##0.00"
        for col in w.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            w.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 90)
    wb.save(out / "prehlad.xlsx")
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return expected, texts, headers


def _write_pack_sheets(wb, profile: dict, m: dict, expected: dict, headers: dict) -> None:
    """Hárky board packu (čísla zo SQL, texty z pravidiel) + očakávania pre spätné načítanie (čísla aj texty)."""
    pk = m["pack"]

    def sheet(name, head, rows):
        w = wb.create_sheet(name)
        w.append(head)
        headers[name] = head
        for r in rows:
            w.append([None if v == "" else (round(v, 2) if isinstance(v, float) else v) for v in r])
            for col, v in zip(head[1:], r[1:]):
                if v is None or v == "":
                    continue
                expected[(name, r[0], col)] = v if isinstance(v, str) else float(v)

    bp = pk["rows"]
    head = ["Riadok", "YTD skutočnosť", "YTD plán", "Rozdiel voči plánu", "YTD minulý rok",
            "Rozdiel voči minulému roku", "Odhad roka", "Plán roka", "Odhad − plán roka", "Minulý rok celý"]
    sheet("Board pack", head, [
        [r, x["ytd_act"], x["ytd_plan"], x["ytd_act"] - x["ytd_plan"], x["ytd_ly"], x["ytd_act"] - x["ytd_ly"],
         x["fy_est"], x["fy_plan"], x["fy_est"] - x["fy_plan"], x["fy_ly"]]
        for r in profile["pl_rows"] for x in [bp[("Spolu", r)]]])
    shops = m["shops"] + ["Spolu"]
    sheet("Odhad roka", ["Riadok"] + shops, [[r] + [bp[(s, r)]["fy_est"] for s in shops] for r in profile["pl_rows"]])
    sheet("Odchýlky", ["Stredisko · riadok", "YTD skutočnosť", "YTD plán", "Vplyv na EBITDA voči plánu",
                       "Vplyv voči minulému roku", "Príčina"],
          [[f"{v['shop']} · {v['row']}", v["act"], v["plan"], v["d_plan"], v["d_ly"], v["cause"]] for v in pk["variance"]])
    sheet("Riziká a príležitosti", ["Kľúč", "Typ", "Vplyv na EBITDA", "Popis"],       # kľúč = stabilné meno (zmluva)
          [[x["key"], x["kind"], x["number"], x["text"]] for x in pk["ro"]])
    sheet("Komentáre", ["Kľúč", "Číslo", "Komentár stroja", "Komentár kontrolóra", "Platný komentár", "Stav"],
          [[c["key"], c["number"], c["auto"], c["kontrolor"], c["final"], c["status"]] for c in pk["comments"]])


def write_comment_template(out: Path, pack: dict) -> None:
    """Šablóna pre kontrolóra: prepíše stĺpec „Komentár kontrolóra" a uloží ako profiles/<firma>/komentare.xlsx (vstup motora)."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 1, 1)
    ws = wb.active
    ws.title = "Komentáre"
    ws.append(["Kľúč", "Číslo pri písaní", "Komentár kontrolóra", "Komentár stroja (pre porovnanie)"])
    for c in pack["comments"]:
        ws.append([c["key"], round(c["number"], 2), c["kontrolor"] or None, c["auto"]])
    for col, wd in zip("ABCD", (34, 16, 90, 90)):
        ws.column_dimensions[col].width = wd
    wb.save(out / "komentare_sablona.xlsx")


# ------------------------------------------------------------------ kontrolný panel + pivotka
PANEL_LIGHT = {"PASS": "🟢 PASS", "FAIL": "🔴 FAIL", "VÝNIMKA": "🟡 VÝNIMKA"}
PANEL_HEAD = ["Semafor", "Oblasť", "Kontrola", "Výsledok", "Nálezov", "Chybné riadky"]
ERR_HEAD = ["#", "Kontrola", "Súbory (miesto detekcie)", "Riadok", "Nález", "Otvoriť 1", "Otvoriť 2", "Otvoriť 3"]
PANEL_FOOTNOTE = ("Nad hotovým súborom bežia ešte xlsx_readback, control_panel_readback a pivot_pl_match — ich FAIL súbory zmaže;"
                  " tento súbor existuje = prešli (výsledok na obrazovke behu a v logu).")
SRC_HEAD = ["Zdroj", "Súbory očakávané", "Súbory prišli", "Riadky načítané", "Nečitateľné riadky", "Semafor"]
_ERR_RE = re.compile(r"([A-Za-z0-9_\-]+\.(?:csv|xlsx))(?:\s+r(\d+))?")


def _files_of_input(profile: dict, key: str) -> list:
    spec = profile["inputs"][key]
    if spec["per"] != "month":
        return [spec["pattern"].format(y2=profile["period"]["as_of"][:4])]
    return [spec["pattern"].format(ym=ym, cc=cc) for cc in spec.get("cost_centers", [None])
            for ym in months_ext(profile, spec)]


_YM_RE = re.compile(r"(20[0-9]{2}-[0-9]{2})|[0-9]{2}\.([0-9]{2})\.(20[0-9]{2})")
_CC_RE = re.compile(r"\b([A-Z][0-9]{2})\b")


def _infer_files(profile: dict, cfg: dict, cid: str, text: str, files: set) -> list:
    """Nález bez mena súboru (napr. „2026-08 S01 účet 518100“): súbory dodávky, v ktorých nález leží — zdroje kontroly
    z profilu (control_panel.check_sources) × mesiac z textu (rrrr-mm alebo dd.mm.rrrr) × stredisko pri súboroch
    na stredisko. Bez mesiaca v texte → súbory zdroja „once“ (plán, číselníky), inak nič (žiadny hádaný odkaz)."""
    mt = _YM_RE.search(text)
    ym = (mt.group(1) or f"{mt.group(3)}-{mt.group(2)}") if mt else None
    cc = _CC_RE.search(text)
    out = []
    for key in cfg.get("check_sources", {}).get(cid, []):
        spec = profile["inputs"][key]
        for f in _files_of_input(profile, key):
            if f not in files or f in out:
                continue
            if spec["per"] != "month":
                out.append(f)
            elif ym and ym in f and (not spec.get("cost_centers") or (cc and cc.group(1) in f)):
                out.append(f)
    return out


def panel_model(con, profile: dict, inp: Path, out: Path, results: list, lines: list, verdict: str) -> dict:
    """Kontrolný panel: každá kontrola behu v presne jednej skupine profilu (control_panel.groups)
    so semaforom z protokolu; chybné riadky = nálezy kontrol so súborom a riadkom vstupu (preklik na súbor dodávky);
    zdroje = čo prišlo (súbory, riadky, nečitateľné) z tabuliek stg. Kontrola bez skupiny sa menuje — panel nesmie
    kontrolu ticho vynechať (overí control_panel_readback)."""
    cfg = profile["control_panel"]
    group_of = {cid: g for g, ids in cfg["groups"].items() for cid in ids}
    st = {}
    for s, cid, d in lines:
        cur = st.get(cid)
        st[cid] = (s, d) if cur is None or (s == "FAIL") or (s == "VÝNIMKA" and cur[0] == "PASS") else cur
    items_of = {cid: (items or ([detail] if not ok else [])) for cid, ok, detail, items in results}
    rows, err, ungrouped = [], [], []
    files = {p.name for p in Path(inp).iterdir() if p.is_file()} if Path(inp).is_dir() else set()
    rel = os.path.relpath(Path(inp).resolve(), Path(out).resolve())
    for g, ids in cfg["groups"].items():
        for cid in ids:
            if cid not in st:
                continue                                 # kontrola skupiny, ktorá v tomto behu nebežala (iný profil/verdikt)
            s, d = st[cid]
            its = items_of.get(cid, []) if s != "PASS" else []
            rows.append({"light": PANEL_LIGHT[s], "status": s, "group": g, "cid": cid, "detail": d, "n": len(its)})
            for it in its:
                mt = _ERR_RE.search(it)
                f, ln = (mt.group(1), mt.group(2)) if mt else (None, None)
                fs = [f] if f in files else _infer_files(profile, cfg, cid, it, files)
                err.append({"cid": cid, "file": "; ".join(fs) or None, "line": int(ln) if ln and f in files else None,
                            "text": it, "hrefs": [f"{rel}/{x}" for x in fs[:3]]})
    ungrouped = sorted(cid for cid in st if cid not in group_of)
    srcs = []
    for key, sp in cfg["sources"].items():
        exp = _files_of_input(profile, key)
        got = sum(1 for f in exp if f in files)
        cols = {c[0] for c in con.execute(f"SELECT * FROM {sp['table']} LIMIT 0").description}
        n, bad = con.execute(f"SELECT count(*), count(*) FILTER (WHERE {'bad <> \'\'' if 'bad' in cols else 'false'}) "
                             f"FROM {sp['table']}").fetchone()
        srcs.append({"label": sp["label"], "expected": len(exp), "got": got, "rows": int(n), "bad": int(bad),
                     "light": PANEL_LIGHT["PASS" if got == len(exp) and bad == 0 else "FAIL"]})
    return {"rows": rows, "err": err, "sources": srcs, "ungrouped": ungrouped, "inp_rel": rel, "verdict": verdict,
            "company": profile["company"], "as_of": profile["period"]["as_of"], "footnote": PANEL_FOOTNOTE,
            "panel_head": PANEL_HEAD, "err_head": ERR_HEAD}


def _write_panel_sheets(wb, profile: dict, verdict: str, panel: dict) -> None:
    """Hárky Kontrolný panel (semafor po skupinách + zdroje) a Chybné riadky (preklik sem z panelu, odtiaľ na súbor)."""
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.hyperlink import Hyperlink
    w = wb.create_sheet("Kontrolný panel")
    e = wb.create_sheet("Chybné riadky")
    e.append(ERR_HEAD)
    first_row = {}
    for i, x in enumerate(panel["err"], start=1):
        e.append([i, x["cid"], x["file"], x["line"], x["text"]] + [h.rsplit("/", 1)[-1] for h in x["hrefs"]])
        first_row.setdefault(x["cid"], e.max_row)
        for k, h in enumerate(x["hrefs"]):
            e.cell(e.max_row, 6 + k).hyperlink = h
            e.cell(e.max_row, 6 + k).font = Font(color="0563C1", underline="single")
    if not panel["err"]:
        e.append([None, None, None, None, "žiadne nálezy — všetky kontroly prešli"])
    w.append(["Kontrolný panel", profile["company"], f"stav k {profile['period']['as_of']}", f"Verdikt: {verdict}"])
    w.append([])
    w.append(PANEL_HEAD)
    fill = {"PASS": "C6EFCE", "FAIL": "FFC7CE", "VÝNIMKA": "FFEB9C"}
    last = None
    for r in panel["rows"]:
        if r["group"] != last:
            w.append([None, r["group"]])
            w.cell(w.max_row, 2).font = Font(bold=True)
            last = r["group"]
        w.append([r["light"], r["group"], r["cid"], r["detail"], r["n"], "→ chybné riadky" if r["n"] else None])
        w.cell(w.max_row, 1).fill = PatternFill("solid", fgColor=fill[r["status"]])
        if r["n"]:
            c = w.cell(w.max_row, 6)
            c.hyperlink = Hyperlink(ref=c.coordinate, location=f"'Chybné riadky'!A{first_row[r['cid']]}")
            c.font = Font(color="0563C1", underline="single")
    w.append([])
    w.append([PANEL_FOOTNOTE])
    w.append([])
    w.append(["Vstupy — čo prišlo"])
    w.cell(w.max_row, 1).font = Font(bold=True)
    w.append(SRC_HEAD)
    for s in panel["sources"]:
        w.append([s["label"], s["expected"], s["got"], s["rows"], s["bad"], s["light"]])
        w.cell(w.max_row, 6).fill = PatternFill("solid", fgColor=fill["PASS" if s["light"] == PANEL_LIGHT["PASS"] else "FAIL"])
    if panel["ungrouped"]:
        w.append([])
        w.append(["⚠ kontroly bez skupiny v profile (panel ich nezobrazuje):", ", ".join(panel["ungrouped"])])
    for col, wd in zip("ABCDEF", (12, 28, 26, 100, 10, 18)):
        w.column_dimensions[col].width = wd
    for col, wd in zip("ABCDEFGH", (6, 24, 44, 8, 110, 26, 26, 26)):
        e.column_dimensions[col].width = wd


PIVOT_NOTE = [
    ["Pivotka — plochá tabuľka faktov pre kontingenčnú tabuľku"],
    ["Hárok Fakty je tabuľka Excelu s menom Fakty: jeden riadok = mesiac × stredisko × účet × druh (skutočnosť / plán)."],
    ["Kontingenčná tabuľka: klikni do tabuľky Fakty → Vložiť → Kontingenčná tabuľka → riadky: Riadok výsledovky,"
     " stĺpce: Mesiac, hodnoty: Suma (€), filter: Druh."],
    ["Znamienko ako vo výsledovke: výnosy +, náklady −. Skutočnosť = účtovný denník, plán = súbor plánu;"
     " prevodník účet → riadok je ten istý (profil)."],
    ["Hárky Pivot skutočnosť a Pivot plán sú tie isté fakty zoskupené strojom (riadok × mesiac bežného roka),"
     " aby bolo s čím porovnať tvoju kontingenčnú tabuľku."],
    ["Natívnu kontingenčnú tabuľku stroj nevyrába — vložíš si ju 2 klikmi z tabuľky Fakty."],
]


def write_pivot(out: Path, profile: dict, m: dict) -> tuple:
    """pivotka.xlsx: Fakty (tabuľka Excelu) + Pivot skutočnosť / Pivot plán (riadok výsledovky × mesiac bežného roka,
    medzisúčty z profilu) + Návod. Vráti (očakávania pre spätné načítanie, hlavičky)."""
    from openpyxl import Workbook
    from openpyxl.worksheet.table import Table, TableStyleInfo
    wb = Workbook()
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 1, 1)
    ws = wb.active
    ws.title = "Fakty"
    head = ["Kľúč", "Druh", "Mesiac", "Rok", "Kód strediska", "Stredisko", "Účet", "Názov účtu", "Riadok výsledovky",
            "Suma (€)", "Zápisov"]
    ws.append(head)
    expected, headers = {}, {"Fakty": head}
    for kind, ym, cc, shop, acc, name, row, amount, n in m["facts"]:
        key = f"{kind} {ym} {cc} {acc}"
        ws.append([key, kind, ym, int(ym[:4]), cc, shop, acc, name, row, round(amount, 2), int(n)])
        for col, v in zip(head[1:], (kind, ym, int(ym[:4]), cc, shop, acc, name, row, amount, int(n))):
            expected[("Fakty", key, col)] = v if isinstance(v, str) else float(v)
    ws.add_table(Table(displayName="Fakty", ref=f"A1:{chr(64 + len(head))}{ws.max_row}",
                       tableStyleInfo=TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)))
    y2, am = m["y2"], int(m["as_of"][5:])
    base = [r for r in profile["pl_rows"] if r not in profile["pl_subtotals"]]
    for title, kind, months in (("Pivot skutočnosť", "skutočnosť", range(1, am + 1)), ("Pivot plán", "plán", range(1, 13))):
        w = wb.create_sheet(title)
        cols = [f"{y2}-{mo:02d}" for mo in months]
        w.append(["Riadok"] + cols + ["Spolu"])
        headers[title] = ["Riadok"] + cols + ["Spolu"]
        t = {(r, c): 0.0 for r in base for c in cols}
        for k, ym, _, _, _, _, row, amount, _ in m["facts"]:
            if k == kind and (row, ym) in t:
                t[(row, ym)] += amount
        for sub, parts in profile["pl_subtotals"].items():
            for c in cols:
                t[(sub, c)] = sum(t[(p, c)] for p in parts)
        for r in profile["pl_rows"]:
            vals = [t[(r, c)] for c in cols]
            w.append([r] + [round(v, 2) for v in vals] + [round(sum(vals), 2)])
            for c, v in zip(cols + ["Spolu"], vals + [sum(vals)]):
                expected[(title, r, c)] = v
    n = wb.create_sheet("Návod")
    for line in PIVOT_NOTE:
        n.append(line)
    n.column_dimensions["A"].width = 120
    for w in wb.worksheets:
        for row in w.iter_rows():
            for c in row:
                if isinstance(c.value, float):
                    c.number_format = "#,##0.00"
        if w.title != "Návod":
            for col in w.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                w.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)
    wb.save(out / "pivotka.xlsx")
    return expected, headers


# ------------------------------------------------------------------ modely (motor = registre)
# Model = ako firma vyzerá: načítanie zdrojov, kontroly (s fázou pred/po martoch),
# stavba martov a pravidlá boardu. Profil si model VYBERIE a vymenuje kontroly;
# povinné kontroly modelu nesmie vynechať (profile_contract). Nový biznis = nový
# model v motore (schopnosť pre všetky profily), nie kópia linky.

def _retail_checks():
    def pl_ct(c, p, x):
        m = x["m"]
        return (c, {k: m["ytd"][("Spolu", k)] for k in p["control_totals"]}, p["control_totals"],
                m["y2"], m["as_of"], 0.01, tuple(["Tržby"] + list(p["pl_subtotals"])),
                x.setdefault("pl_ct_full", []))
    return {
        "inputs_contract": ("pre", lambda c, p, x: (x["files"], expected_files(p), tuple(x["header_issues"]))),
        "numeric_contract": ("pre", lambda c, p, x: (c, p.get("account_pattern", "[0-9]{3}"))),
        "account_mapping_complete": ("pre", lambda c, p, x: (c, p["pl_mapping"], p["account_scope"])),
        "pl_control_total": ("post", pl_ct),
    }


def _retail_outside(con, profile):
    scope = profile["account_scope"]
    cond = " AND ".join(["account NOT LIKE ?"] * len(scope))
    n, s = con.execute(f"SELECT count(*), coalesce(sum(abs(coalesce(debit,0)) + abs(coalesce(credit,0))), 0) "
                       f"FROM gl WHERE {cond}", [f"{x}%" for x in scope]).fetchone()
    return (n, s) if n else None


def build_marts_full(con, profile: dict) -> dict:
    """Model retail_full: výsledovka z martu pl_base (SQL vrstva, denník) + celý minulý rok + počty riadkov."""
    m = _marts_from_pl_base(con, profile)
    base = [r for r in profile["pl_rows"] if r not in profile["pl_subtotals"]]
    t = {r: 0.0 for r in base}
    for r, v in con.execute("SELECT row, sum(amount) FROM pl_base WHERE ym LIKE ? GROUP BY 1", [f"{m['y1']}-%"]).fetchall():
        t[r] = v or 0.0
    for sub, parts in profile["pl_subtotals"].items():
        t[sub] = sum(t[x] for x in parts)
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    m["results"].update({
        "pl_y1_by_row": {r: t[r] for r in profile["pl_rows"]},
        "ytd_ebitda_by_cc": {s: m["ytd"][(s, "EBITDA")] for s in m["shops"]},
        "ytd_net_profit": m["ytd"][("Spolu", "Čistý zisk")],
        "rows": {"pokladna_riadky": q("SELECT count(*) FROM stg_pos"), "dennik_riadky": q("SELECT count(*) FROM stg_journal"),
                 "faktury": q("SELECT count(*) FROM stg_invoices"), "banka_riadky": q("SELECT count(*) FROM stg_bank"),
                 "mzdy_riadky": q("SELECT count(*) FROM stg_payroll"), "sklad_pohyby": q("SELECT count(*) FROM stg_stock_moves")},
    })
    if profile.get("board_pack"):   # čísla board packu zo SQL (40_boardpack.sql) — do etalónu a výstupu
        bp = _bp.rows_of(con)
        m["results"].update({f"{k}_by_row": {r: bp[("Spolu", r)][src] for r in profile["pl_rows"]}
                             for k, src in (("ytd_plan", "ytd_plan"), ("fy_plan", "fy_plan"), ("fy_est", "fy_est"))})
        bpc = profile["board_pack"]
        var = {f"{s} · {r}": d for s, r, d in con.execute(
            "SELECT shop, row, d_plan FROM bp_variance WHERE rk <= ? AND abs(d_plan) >= ? ORDER BY rk",
            [bpc["variance_top"], bpc["variance_min_eur"]]).fetchall()}
        m["bp_ro"] = _bp.ro_items(con, profile, bp)       # jeden výpočet: etalón, kontrola aj board pack
        ro = {x["key"]: x["number"] for x in m["bp_ro"]
              if x["rule"] in ("revenue_pace", "cost_spike_repeat")}          # kotvené pravidlá (etalón generátora)
        var_ly = {f"{s} · {r}": dl for s, r, dl in con.execute(
            "SELECT shop, row, d_ly FROM bp_variance WHERE rk <= ? AND abs(d_plan) >= ? ORDER BY rk",
            [bpc["variance_top"], bpc["variance_min_eur"]]).fetchall()}
        m["results"].update({"fy_ebitda_by_cc": {s: bp[(s, bpc["ebitda_row"])]["fy_est"] for s in m["shops"]},
                             "variance_top_vs_ly": var_ly,
                             "variance_top": var, "variance_top_count": len(var),
                             "ro_anchored": ro, "ro_anchored_count": len(ro)})
        m["bp_rows"] = bp
    if profile.get("pivot"):        # pivotka: fakty z martu mart_facts (50_pivot.sql) — len čítané, nie počítané tu
        m["facts"] = [tuple(r) for r in con.execute(
            "SELECT kind, ym, cc, shop, account, account_name, row, CAST(amount AS DOUBLE), postings "
            "FROM mart_facts ORDER BY kind, ym, cc, account").fetchall()]
    return m


_STG_TABLES = ["stg_pos", "stg_pos_footer", "stg_journal", "stg_invoices", "stg_payroll", "stg_bank", "stg_bank_meta",
               "stg_stock_moves", "stg_stock_state", "stg_plan"]


def _full_checks():
    r = _retail_checks()
    tol = lambda c, p, x: (c, p["reconciliation_tolerance_eur"])  # noqa: E731
    return {
        "inputs_contract": r["inputs_contract"],
        "stg_parse_contract": ("pre", lambda c, p, x: (c, _STG_TABLES)),
        "numeric_contract": r["numeric_contract"],
        "full_duplicate_keys": ("pre", lambda c, p, x: (c, p["pl_mapping"])),
        "full_coverage": ("pre", lambda c, p, x: (c, p["shops"], x["months"], p["inputs"]["pos"]["cost_centers"])),
        "pos_control_total": ("pre", tol), "journal_tb_match": ("pre", tol), "pos_gl_match": ("pre", tol),
        "bank_balance": ("pre", tol), "bank_gl_match": ("pre", tol),
        "bank_ap_match": ("pre", lambda c, p, x: (c, p["bank_internal"], p["bank_direct_pl_allowed"])),
        "payroll_gl_match": ("pre", tol), "ap_gl_match": ("pre", tol), "stock_consistency": ("pre", tol),
        "posting_policy": ("pre", lambda c, p, x: (c, p["posting_policy"])),
        "liability_settlement": ("pre", lambda c, p, x: (c, p["settlement_accounts"], p["reconciliation_tolerance_eur"])),
        "card_settlement": ("pre", tol),
        "loan_schedule": ("pre", lambda c, p, x: (c, p["loan_contract"], p["reconciliation_tolerance_eur"])),
        "boardpack_consistency": ("post", lambda c, p, x: (c, x["m"]["ytd"], x["m"]["ytd_prev"], p, x["m"]["bp_ro"],
                                                          p["reconciliation_tolerance_eur"])),
        "account_mapping_complete": r["account_mapping_complete"],
        "pl_control_total": r["pl_control_total"],
    }


MODELS = {
    "retail_full": {
        "load": load_full, "marts": build_marts_full, "board": board_findings, "outside": _retail_outside,
        "checks": _full_checks(),
        "required": ["inputs_contract", "stg_parse_contract", "numeric_contract", "full_duplicate_keys", "full_coverage",
                     "pos_control_total", "journal_tb_match", "pos_gl_match", "bank_balance", "bank_gl_match",
                     "bank_ap_match", "payroll_gl_match", "ap_gl_match", "stock_consistency",
                     "posting_policy", "liability_settlement", "card_settlement", "loan_schedule",
                     "account_mapping_complete", "pl_control_total", "boardpack_consistency"],
    },
}


# ------------------------------------------------------------------ zmluva reportu
def delivery_fingerprint(d: Path) -> str:
    """sha256 cez (meno súboru, sha256 obsahu) zoradené — kotva zmluvy platí len pre túto dodávku."""
    import hashlib
    h = hashlib.sha256()
    for f in sorted(p for p in Path(d).iterdir() if p.is_file() and not p.name.startswith(".")):
        h.update(f"{f.name}:{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode("utf-8"))
    return h.hexdigest()


def _gl_detail(con, year: str):
    """Čo stroj prečítal z predvahy po mesiacoch pre bod zmluvy (cesta k vstupu pri nesúlade)."""
    def fn(p):
        src = p.get("source", {})
        acc = src.get("accounts")
        if not acc:
            return None
        cond = " OR ".join(["account LIKE ?"] * len(acc))
        q = (f"SELECT ym, sum(coalesce(credit, 0) - coalesce(debit, 0)) FROM gl WHERE ({cond}) AND ym LIKE ?"
             + (" AND cc = ?" if src.get("cost_center") else "") + " GROUP BY 1")
        args = [f"{a}%" for a in acc] + [f"{year}-%"] + ([src["cost_center"]] if src.get("cost_center") else [])
        return {ym: v or 0.0 for ym, v in con.execute(q, args).fetchall()}
    return fn


def anchor_imports_forbidden(f: Path) -> list:
    """Moduly, ktoré skript kotvy B nesmie importovať (kód motora, DuckDB) — kontrola pri KAŽDOM behu, nie len gate
    testom. Vráti zakázané importy (prázdne = v poriadku)."""
    import ast
    tree = ast.parse(f.read_text(encoding="utf-8"))
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
        {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    return sorted(m for m in mods if m.split(".")[0] in ("pipeline", "engine", "checks", "boardpack", "duckdb"))


def _contract_state(profile_dir: Path, profile: dict, inp: Path):
    """(zmluva, kotvy) alebo (None, None), ak profil zmluvu nemá. Kotva „.json" = súbor
    v profile; kotva „.py" = nezávislý skript, ktorý sa spustí NAŽIVO nad touto dodávkou
."""
    if not profile.get("contract"):
        return None, None
    c = json.loads((profile_dir / profile["contract"]).read_text(encoding="utf-8"))
    anchors = {}
    for name in c.get("anchors", []):
        try:
            if name.endswith(".py"):
                f = (ROOT / name).resolve()
                if f.parent != (ROOT / "tools").resolve():      # kód kotvy len z tools/ repa
                    raise ValueError(f"skript kotvy mimo tools/: {name}")
                bad_imp = anchor_imports_forbidden(f)
                if bad_imp:                                      # kotva, ktorá počíta kódom motora, nie je kotva
                    raise ValueError(f"skript kotvy importuje kód motora alebo DuckDB: {', '.join(bad_imp)}")
                import importlib.util
                spec = importlib.util.spec_from_file_location("zl_anchor_live", f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                anchors[name] = mod.compute(Path(inp))
            else:
                f = profile_dir / name
                anchors[name] = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
        except Exception as e:  # noqa: BLE001 — kotva, ktorá sa nedá spočítať = neplatná, menovite
            print(f"   · kotva {name} sa nedala získať: {type(e).__name__}: {e}")
            anchors[name] = None
    return c, anchors


def contract_signature(profile_dir: Path, contract: dict) -> str:
    """sha256 podpisovaného obsahu: zmluva (bez poľa `signed`) + súbory kotiev a skript kotvy.
    Akákoľvek zmena po podpise → podpis neplatí → odoslanie nepovolené."""
    import hashlib
    body = {k: v for k, v in contract.items() if k != "signed"}
    h = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for name in contract.get("anchors", []):
        f = (ROOT / name) if name.endswith(".py") else (profile_dir / name)
        h.update(name.encode("utf-8") + (f.read_bytes() if f.is_file() else b"<chyba>"))
    return h.hexdigest()


# ------------------------------------------------------------------ viditeľná SQL vrstva
def persist_run(con, profile: dict, verdict: str, lines: list, note: str, m: dict | None, findings: list = (),
                panel: dict | None = None) -> None:
    """Do DB behu zapíše to, čo nie je v SQL martoch: verdikt a protokol kontrol (run_meta, check_results), zistenia boardu,
    riziká a komentáre board packu (Python) — Evidence číta len DB. Pri NESEDÍ ostávajú marty v DB (SQL vrstva je viditeľná),
    ale Evidence podľa run_meta.verdict čísla boardu nezobrazí — rovnaké pravidlo ako prehlad.xlsx."""
    con.execute("CREATE OR REPLACE TABLE run_meta AS SELECT ?::VARCHAR AS company, ?::VARCHAR AS as_of, ?::VARCHAR AS verdict, "
                "?::VARCHAR AS contract_note, ?::VARCHAR AS model, ?::VARCHAR AS git_commit, now()::VARCHAR AS run_at",
                [profile["company"], profile["period"]["as_of"], verdict, note, profile["model"], _git_head()])
    con.execute("CREATE OR REPLACE TABLE check_results (seq INT, status VARCHAR, check_id VARCHAR, detail VARCHAR)")
    _many(con, "INSERT INTO check_results VALUES (?, ?, ?, ?)", [(i, s, c, d) for i, (s, c, d) in enumerate(lines, 1)])
    con.execute("CREATE OR REPLACE TABLE board_findings (seq INT, rule VARCHAR, key VARCHAR, text VARCHAR)")
    if findings and verdict != VERDICTS[2]:
        _many(con, "INSERT INTO board_findings VALUES (?, ?, ?, ?)",
                        [(i, f.get("rule"), str(f.get("key")), f["text"]) for i, f in enumerate(findings, 1)])
    con.execute("CREATE OR REPLACE TABLE bp_ro_items (key VARCHAR, kind VARCHAR, grp VARCHAR, number DOUBLE, text VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE bp_comments (key VARCHAR, number DOUBLE, auto VARCHAR, kontrolor VARCHAR, final VARCHAR, status VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE bp_variance_items (key VARCHAR, shop VARCHAR, row VARCHAR, act DOUBLE, plan DOUBLE, "
                "d_plan DOUBLE, d_ly DOUBLE, cause VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE pl_rows (ord INT, row VARCHAR, is_subtotal BOOLEAN)")
    _many(con, "INSERT INTO pl_rows VALUES (?, ?, ?)",
                    [(i, r, r in profile["pl_subtotals"]) for i, r in enumerate(profile["pl_rows"], 1)])
    con.execute("CREATE OR REPLACE TABLE panel_rows (seq INT, light VARCHAR, status VARCHAR, grp VARCHAR, check_id VARCHAR, "
                "detail VARCHAR, n_items INT)")
    con.execute("CREATE OR REPLACE TABLE panel_errors (seq INT, check_id VARCHAR, files VARCHAR, line INT, text VARCHAR)")
    con.execute("CREATE OR REPLACE TABLE panel_sources (seq INT, label VARCHAR, files_expected INT, files_got INT, rows_loaded INT, "
                "rows_bad INT, light VARCHAR)")
    if panel:
        _many(con, "INSERT INTO panel_rows VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(i, r["light"], r["status"], r["group"], r["cid"], r["detail"], r["n"]) for i, r in enumerate(panel["rows"], 1)])
        _many(con, "INSERT INTO panel_errors VALUES (?, ?, ?, ?, ?)",
                        [(i, x["cid"], x["file"], x["line"], x["text"]) for i, x in enumerate(panel["err"], 1)])
        _many(con, "INSERT INTO panel_sources VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(i, s["label"], s["expected"], s["got"], s["rows"], s["bad"], s["light"]) for i, s in enumerate(panel["sources"], 1)])
    pk = (m or {}).get("pack") if verdict != VERDICTS[2] else None
    if pk:
        _many(con, "INSERT INTO bp_ro_items VALUES (?, ?, ?, ?, ?)",
                        [(x["key"], x["kind"], x["group"], x["number"], x["text"]) for x in pk["ro"]])
        _many(con, "INSERT INTO bp_comments VALUES (?, ?, ?, ?, ?, ?)",
                        [(c["key"], c["number"], c["auto"], c["kontrolor"], c["final"], c["status"]) for c in pk["comments"]])
        _many(con, "INSERT INTO bp_variance_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [(v["key"], v["shop"], v["row"], v["act"], v["plan"], v["d_plan"], v["d_ly"], v["cause"]) for v in pk["variance"]])


def _many(con, sql: str, rows: list) -> None:
    """executemany s prázdnym zoznamom DuckDB odmieta — prázdna tabuľka je platný stav (0 nálezov, 0 rizík)."""
    if rows:
        con.executemany(sql, rows)


def _git_head() -> str:
    import subprocess
    try:
        h = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return (h or "?") + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "?"


# ------------------------------------------------------------------ beh
def run(profile_dir: Path, inp: Path, out: Path, truth_path: Path | None = None, db: Path | None = None) -> int:
    import duckdb
    profile_dir, inp, out = Path(profile_dir), Path(inp), Path(out)
    if db is not None:                      # viditeľná SQL vrstva: DB je recept, stavia sa nanovo pri každom behu
        db = Path(db)
        db.parent.mkdir(parents=True, exist_ok=True)
        for f in (db, Path(str(db) + ".wal")):
            f.unlink(missing_ok=True)
    for f in ("prehlad.xlsx", "report.md", "komentare_sablona.xlsx", "pivotka.xlsx"):   # starý výstup nikdy neprežije beh
        (out / f).unlink(missing_ok=True)
    pf = profile_dir / "profile.json"
    if not pf.is_file() or not inp.is_dir():
        print(f"ENGINE: STOP — chýba profil ({pf}) alebo dodávka ({inp}), beh KONČÍ")
        return 2
    profile = json.loads(pf.read_text(encoding="utf-8"))
    ok, detail, items = CHECKS["profile_contract"](profile, {k: (list(v["checks"]), v["required"])
                                                            for k, v in MODELS.items()})
    print(f"[{'PASS' if ok else 'FAIL'}] profile_contract — {detail}")
    if not ok:
        print("ENGINE: STOP — profil porušil kontrakt motora, beh KONČÍ (VERDIKT: NESEDÍ)")
        return 1
    model = MODELS[profile["model"]]
    exc = json.loads((profile_dir / profile["exceptions"]).read_text(encoding="utf-8"))["exceptions"]
    print(f"== profilový motor — {profile['company']} · model {profile['model']} · dodávka {inp.name} ==")
    con = duckdb.connect(str(db)) if db is not None else duckdb.connect()
    ctx = {"files": sorted(p.name for p in inp.iterdir() if p.is_file() and not p.name.startswith(".")),
           "months": months_of(profile["period"])}
    ctx["header_issues"] = model["load"](con, inp, profile)
    results = [("profile_contract", ok, detail, items)]

    def run_check(cid, *args):
        ok, detail, items = CHECKS[cid](*args)
        print(f"[{'PASS' if ok else 'FAIL'}] {cid} — {detail}")
        results.append((cid, ok, detail, items))
        return ok

    for phase in ("pre", "post"):
        if phase == "post":
            ctx["m"] = model["marts"](con, profile)
        for cid in profile["checks"]:
            ph, argfn = model["checks"][cid]
            if ph == phase:
                run_check(cid, *argfn(con, profile, ctx))
    for it in ctx.get("pl_ct_full", []):         # sumy kontrolných súčtov len na obrazovku, nie do súboru
        print(f"   · {it}")
    m = ctx["m"]
    truth_used = truth_path is not None
    if truth_used:
        tfull = []
        if not run_check("truth_meter", m["results"], json.loads(Path(truth_path).read_text(encoding="utf-8")), tfull):
            for it in tfull:
                print(f"   · {it}")
    if not run_check("exceptions_contract", exc, {r[0] for r in results}, profile["period"]["as_of"]):
        exc = []                    # neplatné výnimky nekryjú nič
    verdict, lines = apply_exceptions(results, exc, profile["period"]["as_of"])
    findings = model["board"](con, profile, m) if verdict != VERDICTS[2] else []
    if verdict != VERDICTS[2] and profile.get("board_pack"):   # board pack len pri SEDÍ (čísla sa inak nevydajú)
        m["pack"] = _bp.build(con, profile, profile_dir, findings, m["bp_ro"])
        for w_ in m["pack"]["comment_warnings"]:
            print(f"[KOMENTÁR] {w_}")
    contract = json.loads((profile_dir / profile["contract"]).read_text(encoding="utf-8")) \
        if profile.get("contract") else None
    note = ("žiadna — report nie je určený na odoslanie (profil nemá zmluvu)" if contract is None
            else "overuje sa" if verdict == VERDICTS[0] else f"ODOSLANIE ZAMIETNUTÉ — verdikt {verdict}")

    def emit(verdict, lines, note, quiet=False):
        panel = panel_model(con, profile, inp, out, results, lines, verdict) if profile.get("control_panel") else None
        ctx["panel"] = panel
        exp, texts, heads = write_outputs(out, profile, verdict, lines, m if verdict != VERDICTS[2] else None,
                                          findings, truth_used, model["outside"](con, profile), note, panel)
        ok, detail, _ = CHECKS["xlsx_readback"](out / "prehlad.xlsx", exp, texts, expected_headers=heads)
        if not quiet or not ok:
            print(f"[{'PASS' if ok else 'FAIL'}] xlsx_readback — {detail}")
        if ok and panel is not None:      # panel z HOTOVÉHO súboru = protokol kontrol; kontrola bez skupiny = FAIL
            ok, detail, _ = CHECKS["control_panel_readback"](out / "prehlad.xlsx", panel, results)
            if not quiet or not ok:
                print(f"[{'PASS' if ok else 'FAIL'}] control_panel_readback — {detail}")
        (out / "pivotka.xlsx").unlink(missing_ok=True)
        if ok and verdict != VERDICTS[2] and profile.get("pivot") and "facts" in m:   # pivotka len pri vydaných číslach
            exp_p, heads_p = write_pivot(out, profile, m)
            ok, detail, _ = CHECKS["xlsx_readback"](out / "pivotka.xlsx", exp_p, None, unchecked_sheets=("Návod",),
                                                   expected_headers=heads_p, main_sheet=None)
            if not quiet or not ok:
                print(f"[{'PASS' if ok else 'FAIL'}] xlsx_readback — pivotka: {detail}")
            if ok:
                ok, detail, _ = CHECKS["pivot_pl_match"](out / "pivotka.xlsx", m["ytd"], m.get("bp_rows"), profile)
                if not quiet or not ok:
                    print(f"[{'PASS' if ok else 'FAIL'}] pivot_pl_match — {detail}")
        if not ok:
            for f in ("prehlad.xlsx", "report.md", "pivotka.xlsx"):
                (out / f).unlink(missing_ok=True)
            print("ENGINE: STOP — hotový výstup nesedí s výpočtom, súbory zmazané.")
        if ok and verdict != VERDICTS[2] and m.get("pack"):
            write_comment_template(out, m["pack"])
        else:
            (out / "komentare_sablona.xlsx").unlink(missing_ok=True)
        return ok

    if not emit(verdict, lines, note):
        persist_run(con, profile, VERDICTS[2], lines, "výstup zamietnutý spätným načítaním", m, panel=ctx.get("panel"))
        return 1
    if contract is not None and verdict == VERDICTS[0]:          # §4.1: len SEDÍ
        # zmluva reportu: čísla z HOTOVÉHO súboru vs. kotvy mimo motora
        contract, anchors = _contract_state(profile_dir, profile, inp)
        rc_args = (contract, anchors, delivery_fingerprint(inp), {r[0]: r[1] for r in results},
                   _gl_detail(con, m["y2"]), profile["period"]["as_of"])
        full = []
        if not run_check("report_contract", out / "prehlad.xlsx", *rc_args, full):
            for it in full:                           # plné hodnoty len na obrazovku, nie do súboru
                print(f"   · {it}")
            verdict, lines = apply_exceptions(results, exc, profile["period"]["as_of"])
            findings = []
            m.pop("pack", None)             # zmluva nesplnená → board pack sa nevydá (ako zistenia)
            if not emit(verdict, lines, "ODOSLANIE ZAMIETNUTÉ — zmluva reportu nesplnená (pozri Kontroly)"):
                return 1
            print(f"VERDIKT: {verdict} — zmluva reportu nesplnená, vydaný len protokol ({out / 'prehlad.xlsx'})")
            persist_run(con, profile, verdict, lines, "ODOSLANIE ZAMIETNUTÉ — zmluva reportu nesplnená", m, panel=ctx.get("panel"))
            return 1
        verdict, lines = apply_exceptions(results, exc, profile["period"]["as_of"])
        sig = contract.get("signed") or {}
        if sig and sig.get("sha256") == contract_signature(profile_dir, contract):
            note = f"ODOSLANIE POVOLENÉ — {results[-1][2]} · zmluvu podpísal {sig.get('by')} {sig.get('date')}"
        elif sig:
            note = (f"PODPIS NEPLATNÝ — zmluva alebo kotvy sa po podpise zmenili; ODOSLANIE AŽ PO NOVOM PODPISE KONTROLÓRA"
                    f" — {results[-1][2]}")
        else:
            note = f"ZMLUVA SPLNENÁ, ODOSLANIE AŽ PO PODPISE KONTROLÓRA — {results[-1][2]}"
        if not emit(verdict, lines, note, quiet=True):
            return 1
        ok, detail, _ = CHECKS["report_contract"](out / "prehlad.xlsx", *rc_args)   # finálny súbor znova
        if not ok:
            for f in ("prehlad.xlsx", "report.md", "pivotka.xlsx"):
                (out / f).unlink(missing_ok=True)
            print(f"ENGINE: STOP — finálny výstup porušil zmluvu ({detail}); súbory zmazané.")
            return 1
    print(f"ZMLUVA: {note}")
    for f in findings:
        print(f"[BOARD] {f['text']}")
    print(f"VERDIKT: {verdict} — výstup {out / 'prehlad.xlsx'}")
    persist_run(con, profile, verdict, lines, note, m, findings, panel=ctx.get("panel"))
    return 1 if verdict == VERDICTS[2] else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--truth")
    ap.add_argument("--db", help="súbor DuckDB s vrstvami raw/stg/core/mart (viditeľná SQL vrstva, stavia sa nanovo)")
    a = ap.parse_args()
    try:
        return run(Path(a.profile), Path(a.input), Path(a.out), Path(a.truth) if a.truth else None,
                   Path(a.db) if a.db else None)
    except Exception as e:  # noqa: BLE001 — výnimka = menovitý STOP, nie traceback bez verdiktu
        out = Path(a.out)
        for f in ("prehlad.xlsx", "report.md", "pivotka.xlsx"):
            (out / f).unlink(missing_ok=True)
        print(f"ENGINE: STOP — výnimka v behu ({type(e).__name__}: {e}); výstup zmazaný, VERDIKT: NESEDÍ")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
