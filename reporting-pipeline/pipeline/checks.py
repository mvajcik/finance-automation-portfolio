#!/usr/bin/env python3
"""Kontroly linky — jediné miesto, kde kontroly žijú.

Každá kontrola je funkcia registrovaná dekorátorom @check("<id>") a vracia
(ok, detail, items): items = menovité nálezy (jeden reťazec na nález).
Volá ich profilový motor (pipeline/engine.py); profil vyberá, ktoré bežia,
model motora určuje, ktoré sú povinné.
"""
import re
from pathlib import Path

CHECKS: dict = {}


def check(cid: str):
    def deco(fn):
        CHECKS[cid] = fn
        return fn
    return deco


def _cents(v: float) -> int:
    return int(round(v * 100))


# ================================================================ PROFILOVÝ MOTOR
# Kontroly pre pipeline/engine.py. Kontrakt je
# rozšírený: vracajú (ok, detail, items) — items = menovité nálezy (jeden reťazec
# na nález), aby sa na ne dali viazať výnimky s platnosťou. Pracujú nad staging
# tabuľkami, ktoré engine naplní zo súborov: pos_raw, gl_raw, plan_raw (+ typované
# pos, gl, plan). Žiadna nevie o konkrétnej firme — všetko prichádza z profilu.

_POS_AMOUNT_RE = re.compile(r"-?(?:0|[1-9]\d*),\d{2}", re.ASCII)


def _fmt_items(items: list, n: int = 6) -> str:
    return "; ".join(items[:n]) + (f" … (+{len(items) - n})" if len(items) > n else "")


@check("profile_contract")
def profile_contract(profile: dict, models: dict):
    """Profil smie vybrať model motora a vymenovať kontroly — nesmie vynechať
    povinnú kontrolu modelu ani uviesť neznámu (profil nemôže potichu vypnúť
    kontrolu; force-function). Neznámy model = FAIL."""
    items = []
    mid = profile.get("model")
    if mid not in models:
        return False, f"unknown model '{mid}' (the engine knows: {', '.join(sorted(models))})", [f"model {mid}"]
    known, required = models[mid]
    listed = list(profile.get("checks") or [])
    if not listed:
        return False, "the profile lists no check — 0 is not evidence", ["checks empty"]
    items += [f"required check '{r}' is missing in the profile" for r in required if r not in listed]
    items += [f"check '{x}' is unknown to model '{mid}'" for x in listed if x not in known]
    items += [f"check '{x}' is in the profile {listed.count(x)}×" for x in sorted(set(listed)) if listed.count(x) > 1]
    if items:
        return False, f"the profile broke the contract of model '{mid}': {_fmt_items(items)}", items
    return True, f"model '{mid}', {len(listed)} checks in the profile (required: {len(required)}/{len(required)})", []


@check("inputs_contract")
def inputs_contract(files: list, expected: list, header_issues: tuple = ()):
    """Dodávka = presne očakávané súbory profilu (menovite chýba / navyše) a každý
    má hlavičku podľa profilu. Prázdny zoznam očakávaných = FAIL (0 nie je dôkaz)."""
    if not expected:
        return False, "the profile expects no file — 0 is not evidence", ["contract empty"]
    got, want = set(files), set(expected)
    items = [f"missing file {f}" for f in sorted(want - got)] + \
            [f"unexpected file {f}" for f in sorted(got - want)] + list(header_issues)
    if items:
        return False, f"the delivery does not match the contract: {_fmt_items(items)}", items
    return True, f"delivery = contract ({len(want)} files)", []


@check("numeric_contract")
def numeric_contract(con, account_pattern: str = "[0-9]{3}"):
    """Každá suma je číslo v dohodnutom tvare: pokladňa CSV '1234,56' (desatinná
    čiarka, 2 miesta), xlsx bunka typu číslo — text, ktorý len vyzerá ako číslo
    ('37 040,44'), je FAIL (Excel by ho ticho spočítal ako 0). Dátum pokladne je
    platný a patrí mesiacu súboru. Každý riadok predvahy má účet (tvar z profilu,
    napr. 3–6 číslic pre analytické účty),
    stredisko a obdobie = mesiac súboru — inak by potichu vypadol z výpočtu
    aj z kontrolných súčtov naraz."""
    items = []
    for f, line, col, val in con.execute(
            "SELECT file, line, 'amount', amount_txt FROM pos_raw ORDER BY file, line").fetchall():
        if val is None or not _POS_AMOUNT_RE.fullmatch(val):
            items.append(f"{f} r{line} {col}='{val}'")
    # dátum: platný a v mesiaci, ktorý nesie meno súboru
    for f, line, val, ok in con.execute(
            "SELECT file, line, date_txt, strftime(CAST(try_strptime(date_txt, '%d.%m.%Y') AS DATE), '%Y-%m') "
            "= regexp_extract(file, '([0-9]{4}-[0-9]{2})', 1) FROM pos_raw ORDER BY file, line").fetchall():
        if not ok:
            items.append(f"{f} r{line} date='{val}' (invalid or outside the month of the file)")
    # predvaha: účet = 3 číslice, stredisko vyplnené, obdobie = mesiac súboru (prázdny
    # účet, ' 518' alebo obdobie iného mesiaca by inak vypadli z výpočtu aj z kontroly)
    for f, line, ym, cc, acc in con.execute(
            "SELECT file, line, ym, cc, account FROM gl_raw WHERE NOT ("
            "regexp_full_match(coalesce(account, ''), ?) "
            "AND coalesce(cc, 'None') NOT IN ('', 'None') "
            "AND ym = regexp_extract(file, '([0-9]{4}-[0-9]{2})', 1)) ORDER BY file, line",
            [account_pattern]).fetchall():
        items.append(f"{f} r{line} trial balance row outside the contract (period='{ym}', cost centre='{cc}', account='{acc}')")
    for f, line, col, val, isnum in con.execute(
            "SELECT file, line, col, raw, is_num FROM gl_cells UNION ALL "
            "SELECT file, line, col, raw, is_num FROM plan_cells ORDER BY 1, 2").fetchall():
        if not isnum:
            items.append(f"{f} r{line} {col}='{val}' (text, not a number)")
    n = con.execute("SELECT (SELECT count(*) FROM pos_raw) + (SELECT count(*) FROM gl_cells)"
                    " + (SELECT count(*) FROM plan_cells)").fetchone()[0]
    if n == 0:
        return False, "no amount to check — 0 is not evidence", ["0 amounts"]
    if items:
        return False, f"{len(items)} amounts are not numbers in the agreed format: {_fmt_items(items)}", items
    return True, f"{n:,} amounts are numbers in the agreed format", []


def _gl_duplicate_items(con, mapping: dict = None) -> list:
    """Duplicity predvahy (spoločné pre všetky modely): kľúč mesiac × stredisko × účet,
    syntetický účet aj jeho analytika, zhodné MD/D dvoch účtov jedného riadku."""
    gl_dup = con.execute(
        "SELECT ym, cc, account, count(*) FROM gl GROUP BY 1, 2, 3 HAVING count(*) > 1 "
        "ORDER BY 1, 2, 3").fetchall()
    items = [f"trial balance: {ym} {cc} account {acc}: {n}× (expected 1×)" for ym, cc, acc, n in gl_dup]
    # účet a jeho analytika (504 aj 504001) v tom istom stredisku × mesiaci —
    # výpočet ich zaradí do jedného riadku cez predponu → dvojité zaúčtovanie
    mix = con.execute(
        "SELECT a.ym, a.cc, a.account, b.account FROM (SELECT DISTINCT ym, cc, account FROM gl) a "
        "JOIN (SELECT DISTINCT ym, cc, account FROM gl) b ON a.ym = b.ym AND a.cc = b.cc "
        "AND (length(a.account) = 3 OR list_contains(?::VARCHAR[], a.account)) "
        "AND b.account LIKE a.account || '%' AND b.account <> a.account "
        "ORDER BY 1, 2, 3, 4", [sorted(mapping or {})]).fetchall()
    # nadradený = syntetický účet (3 číslice) alebo účet z prevodníka profilu (5181 aj 51811);
    # 5040 + 504001 ostáva bez poplachu — 5040 nie je v prevodníku
    items += [f"trial balance: {ym} {cc} account {s} and its sub-account {an} — double posting"
              for ym, cc, s, an in mix]
    # dva rôzne účty toho istého riadku výsledovky v tom istom stredisku ×
    # mesiaci s PRESNE rovnakým MD aj D = podpis dvakrát nahratého riadku (konzervatívne:
    # radšej poplach, ktorý človek vysvetlí, než zlé číslo pre board)
    if mapping:
        seen = {}
        for ym, cc, acc, md, dal in con.execute(
                "SELECT ym, cc, account, debit, credit FROM gl WHERE debit IS NOT NULL AND credit IS NOT NULL "
                "AND (debit <> 0 OR credit <> 0) ORDER BY 1, 2, 3").fetchall():
            row = resolve_account(acc, mapping)
            if row is None:
                continue
            k = (ym, cc, row, round(md, 2), round(dal, 2))
            if k in seen and seen[k] != acc:
                items.append(f"trial balance: {ym} {cc} accounts {seen[k]} and {acc} (line {row}) have identical "
                             f"Dr {md:,.2f} / Cr {dal:,.2f} — suspected row loaded twice")
            seen.setdefault(k, acc)
    return items


def resolve_account(account: str, mapping: dict):
    """Riadok výsledovky pre účet: najdlhšia predpona z prevodníka (518001 → 518).
    Spoločná pre výpočet aj kontrolu úplnosti (vedome: jedno pravidlo zaradenia)."""
    best = None
    for k in mapping:
        if str(account).startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return None if best is None else mapping[best]


@check("account_mapping_complete")
def account_mapping_complete(con, mapping: dict, scope: list):
    """Každý výnosový/nákladový účet (triedy zo `scope`) má riadok vo výsledovke.
    Nový účet, ktorý nikto nezaradil = STOP menovite — náklad nesmie ticho
    vypadnúť z EBITDA."""
    accounts = [r[0] for r in con.execute(
        "SELECT DISTINCT account FROM gl ORDER BY 1").fetchall()]
    in_scope = [a for a in accounts if any(str(a).startswith(p) for p in scope)]
    if not in_scope:
        return False, "the books contain no income/expense account — 0 is not evidence", ["0 accounts"]
    items = []
    for a in in_scope:
        if resolve_account(a, mapping) is None:
            amt = con.execute("SELECT sum(debit) + sum(credit) FROM gl WHERE account = ?", [a]).fetchone()[0]
            items.append(f"account {a} not mapped to the P&L (turnover €{amt or 0:,.2f})")
    if items:
        return False, f"unmapped accounts: {_fmt_items(items)}", items
    return True, f"{len(in_scope)} income/expense accounts mapped to the P&L", []


@check("pl_control_total")
def pl_control_total(con, reported: dict, control_totals: dict, year: str, as_of: str,
                     tol: float = 0.01, required: tuple = (), full: list | None = None):
    """Každý kontrolný súčet výsledovky (EBITDA, Hrubá marža …), ktorý ide boardu,
    == priamo z predvahy: sum(Obrat D − Obrat MD) cez účty, ktoré do neho podľa
    ÚČTOVEJ POLITIKY profilu patria (`control_totals`: predpony účtov). Nepoužíva
    prevodník účet → riadok ani skladbu subtotalov výpočtu (inak by prešla
    Hrubá marža = len Tržby alebo odpisy/úroky vnútri EBITDA)."""
    if not control_totals:
        return False, "the profile has no control totals — 0 is not evidence", ["control_totals empty"]
    items, ok_txt = [], []
    for name in required:           # subtotal bez kontrolného súčtu = FAIL
        if name not in control_totals:
            items.append(f"{name}: goes to the board but has no control total in the profile (control_totals)")
    for name, prefixes in control_totals.items():
        got = reported.get(name)
        if got is None or not prefixes:
            items.append(f"{name}: reported value or account policy is missing")
            continue
        cond = " OR ".join(["account LIKE ?"] * len(prefixes))
        src = con.execute(f"SELECT sum(credit - debit) FROM gl WHERE ({cond}) AND ym LIKE ? AND ym <= ?",
                          [f"{p}%" for p in prefixes] + [f"{year}-%", as_of]).fetchone()[0]
        if src is None:
            items.append(f"{name}: YTD trial balance has no accounts {prefixes}")
        elif abs(got - src) > tol:
            # do súboru len smer — suma = číslo boardu, pri NESEDÍ sa nevydáva; plné hodnoty len na obrazovku (`full`)
            items.append(f"{name}: reported ≠ trial balance ({'higher' if got > src else 'lower'} than the trial balance)")
            if full is not None:
                full.append(f"{name}: reported {_money(got)} ≠ trial balance {_money(src)} (difference {_signed(got - src)})")
        else:
            ok_txt.append(name)     # bez sumy: čísla boardu len v Prehľade a len pri SEDÍ
    if items:
        return False, f"control totals do not tie: {_fmt_items(items)}", items
    return True, (f"reported totals == trial balance per the profile's accounting policy, to the cent: {', '.join(ok_txt)} "
                  f"(the amounts are in the Overview; on DOES NOT TIE they are not issued)"), []


# ---------------------------------------------------------------- model retail_full: 9 zdrojov
# Kontroly pracujú nad SQL vrstvou (sql/<firma>/10_stg.sql …): stg_* = typované tabuľky, v ktorých SQL
# samo vyhlási nečitateľné polia do stĺpca `bad`. Každá kontrola páruje DVA nezávislé zdroje
# (iný systém, iný súbor) a pri nesúlade menuje súbor · riadok / deň · stredisko · účet.
def _money(v) -> str:
    x = float(v or 0)
    return f"{'-' if x < 0 else ''}€{abs(x):,.2f}"


def _signed(v) -> str:
    x = float(v or 0)
    return f"{'-' if x < 0 else '+'}€{abs(x):,.2f}"


def _fmt_num(v) -> str:
    """Číslo na obrazovku bez artefaktov float (103794.72999999994 → 103,794.73); text ostane textom."""
    return f"{v:,.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def _day(d) -> str:
    """Dátum pre správu; nečitateľný dátum (NULL) sa nesmie stratiť — menuje ho stg_parse_contract."""
    return d.strftime("%d.%m.%Y") if d is not None else "unreadable date"


@check("stg_parse_contract")
def stg_parse_contract(con, tables: list):
    """Každý riadok každého zdroja sa dal prečítať: SQL vrstva STG vyhlási v stĺpci `bad` polia, ktoré
    sa nedali previesť na typ (dátum, suma, sadzba DPH, mesiac súboru …). Neprázdny `bad` = FAIL
    menovite (súbor, riadok, pole); prázdny zdroj = FAIL (0 nie je dôkaz)."""
    items, n = [], 0
    for t in tables:
        k = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        n += k
        if k == 0:
            items.append(f"{t}: 0 rows — 0 is not evidence")
            continue
        for f, ln, bad in con.execute(f"SELECT file, line, bad FROM {t} WHERE coalesce(bad, '') <> '' ORDER BY 1, 2").fetchall():
            items.append(f"{f} r{ln}: unreadable {bad}")
    if items:
        return False, f"{len(items)} source rows could not be read: {_fmt_items(items)}", items
    return True, f"{n:,} rows from {len(tables)} source tables read without loss", []


@check("full_duplicate_keys")
def full_duplicate_keys(con, mapping: dict = None):
    """Nič nie je nahraté dvakrát: bloček len v jednom súbore a dni, riadok denníka ani bankový pohyb
    presne dvakrát, číslo faktúry a zamestnanec × mesiac raz; predvaha ako všade (mesiac × stredisko ×
    účet, syntetika aj analytika, zhodné MD/D)."""
    items = []
    q = {"receipt in 2 files/days": "SELECT doklad, count(DISTINCT file || day) FROM stg_pos GROUP BY 1 HAVING count(DISTINCT file || day) > 1",
         "journal row 2×": "SELECT doklad || ' ' || md || '/' || d || ' ' || amount || ' ' || cc || ' ' || text, count(*) FROM stg_journal GROUP BY 1 HAVING count(*) > 1",
         "invoice 2×": "SELECT invoice, count(*) FROM stg_invoices GROUP BY 1 HAVING count(*) > 1",
         "payroll row 2×": "SELECT employee || ' ' || ym, count(*) FROM stg_payroll GROUP BY 1 HAVING count(*) > 1",
         "bank movement 2×": "SELECT strftime(day, '%d.%m.%Y') || ' ' || counterparty || ' ' || amount || ' ' || text, count(*) FROM stg_bank GROUP BY 1 HAVING count(*) > 1"}
    for label, sql in q.items():
        items += [f"{label}: {k} ({n}×)" for k, n in con.execute(sql + " ORDER BY 1").fetchall()]
    items += _gl_duplicate_items(con, mapping)
    n = con.execute("SELECT (SELECT count(*) FROM stg_pos) + (SELECT count(*) FROM stg_journal)").fetchone()[0]
    if n == 0:
        return False, "POS and journal are both empty — 0 is not evidence", ["empty source"]
    if items:
        return False, f"duplicates: {_fmt_items(items)}", items
    return True, "receipts, journal, invoices, payroll, bank and trial balance without duplicates", []


@check("full_coverage")
def full_coverage(con, shops: list, months: list, pos_ccs: list):
    """Každý mesiac obdobia má denník, predvahu, banku, mzdy a faktúry; každá predajňa má pokladňu v
    každom mesiaci. Stredisko, ktoré nie je v zozname firmy (profil), = cudzie dáta = FAIL."""
    if not shops or not months:
        return False, "the profile has no cost centres or period — 0 is not evidence", ["profile empty"]
    ccs = {s["cost_center"] for s in shops}
    items = []
    for label, sql in (("journal", "SELECT DISTINCT ym FROM stg_journal"), ("trial balance", "SELECT DISTINCT ym FROM gl"),
                       ("bank", "SELECT DISTINCT ym FROM stg_bank_meta"), ("payroll", "SELECT DISTINCT ym FROM stg_payroll"),
                       ("invoices", "SELECT DISTINCT ym FROM stg_invoices"),
                       ("stock movements", "SELECT DISTINCT ym FROM stg_stock_moves"),
                       ("stock levels", "SELECT DISTINCT ym FROM stg_stock_state")):
        have = {r[0] for r in con.execute(sql).fetchall()}
        items += [f"{label}: {ym} without data" for ym in months if ym not in have]
    have = {tuple(r) for r in con.execute("SELECT DISTINCT cc, strftime(day, '%Y-%m') FROM stg_pos").fetchall()}
    items += [f"POS: {cc} {ym} without data" for cc in pos_ccs for ym in months if (cc, ym) not in have]
    for label, sql in (("journal", "SELECT DISTINCT cc FROM stg_journal"), ("POS", "SELECT DISTINCT cc FROM stg_pos"),
                       ("payroll", "SELECT DISTINCT cc FROM stg_payroll"), ("invoices", "SELECT DISTINCT cc FROM stg_invoices"),
                       ("trial balance", "SELECT DISTINCT cc FROM gl")):
        items += [f"{label}: unknown cost centre '{c}'" for (c,) in con.execute(sql).fetchall() if c not in ccs]
    if items:
        return False, f"coverage is incomplete: {_fmt_items(items)}", items
    return True, f"{len(months)} months × 7 sources and {len(pos_ccs)} POS × {len(months)} months without a gap", []


@check("pos_control_total")
def pos_control_total(con, tol: float = 0.01):
    """Export pokladne je celý: riadok SPOLU v každom súbore == súčet jeho bločkov (orezaný alebo
    ručne doplnený export sa prezradí). Súbor bez riadku SPOLU = FAIL."""
    rows = con.execute("""SELECT f.file, f.total, (SELECT sum(gross) FROM stg_pos p WHERE p.file = f.file) FROM stg_pos_footer f
                          ORDER BY 1""").fetchall()
    if not rows:
        return False, "no POS file with a TOTAL row — 0 is not evidence", ["0 files"]
    items = [f"{f}: TOTAL is missing" if t is None else f"{f}: TOTAL {_money(t)} ≠ receipts {_money(s)} (difference {_signed((s or 0) - t)})"
             for f, t, s in rows if t is None or abs(float((s or 0) - t)) > tol]
    if items:
        return False, f"the POS export is not complete: {_fmt_items(items)}", items
    return True, f"{len(rows)} POS exports: TOTAL == sum of receipts", []


@check("journal_tb_match")
def journal_tb_match(con, tol: float = 0.01):
    """Účtovný denník == predvaha: obraty MD aj D každého účtu v každom stredisku a mesiaci (predvaha je
    výstup iného modulu účtovníctva — ručná úprava alebo neúplný export sa prezradí)."""
    rows = con.execute("""
        WITH j AS (SELECT ym, cc, account, sum(md) AS md, sum(dd) AS dd FROM (
                     SELECT ym, cc, md AS account, amount AS md, 0 AS dd FROM stg_journal
                     UNION ALL SELECT ym, cc, d, 0, amount FROM stg_journal) GROUP BY 1, 2, 3),
             t AS (SELECT ym, cc, account, sum(coalesce(debit, 0)) AS md, sum(coalesce(credit, 0)) AS dd FROM gl GROUP BY 1, 2, 3)
        SELECT coalesce(j.ym, t.ym), coalesce(j.cc, t.cc), coalesce(j.account, t.account),
               coalesce(j.md, 0), coalesce(t.md, 0), coalesce(j.dd, 0), coalesce(t.dd, 0)
        FROM j FULL JOIN t ON j.ym = t.ym AND j.cc = t.cc AND j.account = t.account ORDER BY 1, 2, 3""").fetchall()
    if not rows:
        return False, "journal and trial balance are both empty — 0 is not evidence", ["0 rows"]
    items = [f"{ym} {cc} account {a}: journal Dr {_money(jm)} / Cr {_money(jd)} ≠ trial balance Dr {_money(tm)} / Cr {_money(td)}"
             for ym, cc, a, jm, tm, jd, td in rows if abs(float(jm) - float(tm)) > tol or abs(float(jd) - float(td)) > tol]
    if items:
        return False, f"journal ≠ trial balance ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows):,} turnovers month × cost centre × account: journal == trial balance to the cent", []


@check("pos_gl_match")
def pos_gl_match(con, tol: float = 0.01):
    """Pokladňa == účtovníctvo po predajni a dni (pokladničný softvér vs. denník): (a) súčet bločkov s DPH
    podľa spôsobu platby == zápisy 211 (hotovosť) / 315 (karta) proti 604 + 343; (b) tržby bez DPH z bločkov
    (po sadzbách) == celý účet 604 (D − MD) — zápis tržieb bez pokladne alebo presun z DPH do tržieb = FAIL."""
    a = con.execute("""
        WITH p AS (SELECT cc, day, payment, sum(gross) AS g FROM stg_pos GROUP BY 1, 2, 3),
             j AS (SELECT cc, day, CASE md WHEN '211' THEN 'cash' ELSE 'card' END AS payment, sum(amount) AS g
                   FROM stg_journal WHERE md IN ('211', '315') AND d IN ('604', '343') GROUP BY 1, 2, 3)
        SELECT coalesce(p.cc, j.cc), coalesce(p.day, j.day), coalesce(p.payment, j.payment), coalesce(p.g, 0), coalesce(j.g, 0)
        FROM p FULL JOIN j ON p.cc = j.cc AND p.day = j.day AND p.payment = j.payment
        ORDER BY 1, 2, 3 DESC""").fetchall()          # cash pred card — poradie nálezov ako doteraz (H < K)
    b = con.execute("""
        WITH p AS (SELECT cc, day, sum(net) AS n FROM (
                     SELECT cc, day, round(CAST(sum(gross) AS DOUBLE) / (1 + vat_rate / 100.0), 2) AS net
                     FROM stg_pos GROUP BY cc, day, payment, vat_rate) GROUP BY 1, 2),
             j AS (SELECT cc, day, sum(CASE WHEN d = '604' THEN amount ELSE -amount END) AS n
                   FROM stg_journal WHERE (d = '604' OR md = '604') AND doklad NOT LIKE 'PS%' GROUP BY 1, 2)
        SELECT coalesce(p.cc, j.cc), coalesce(p.day, j.day), coalesce(p.n, 0), coalesce(j.n, 0)
        FROM p FULL JOIN j ON p.cc = j.cc AND p.day = j.day ORDER BY 1, 2""").fetchall()
    if not a:
        return False, "no revenue — 0 is not evidence", ["0 days"]
    items = [f"{cc} {_day(d)} {'cash' if pay == 'cash' else 'card'}: POS {_money(p)} ≠ books {_money(j)} "
             f"(difference {_signed(p - j)})" for cc, d, pay, p, j in a if abs(float(p - j)) > tol]
    items += [f"{cc} {_day(d)}: revenue excl. VAT from receipts {_money(p)} ≠ account 604 {_money(j)} (difference {_signed(float(p) - float(j))})"
              for cc, d, p, j in b if abs(float(p) - float(j)) > 0.05]        # zaokrúhlenie DPH po sadzbách a platbe
    if items:
        return False, f"POS ↔ books do not tie ({len(items)}): {_fmt_items(items)}", items
    return True, (f"{len(b):,} sales days × store: receipts == 211/315 by payment method and revenue excl. VAT == the whole account 604"), []

@check("bank_balance")
def bank_balance(con, tol: float = 0.01):
    """Bankový výpis je celý: počiatočný zostatok + pohyby == konečný zostatok v každom výpise a
    konečný zostatok mesiaca == počiatočný zostatok nasledujúceho (vynechaný pohyb sa prezradí)."""
    rows = con.execute("""SELECT m.file, m.ym, m.opening, m.closing, coalesce((SELECT sum(amount) FROM stg_bank b WHERE b.file = m.file), 0)
                          FROM stg_bank_meta m ORDER BY m.ym""").fetchall()
    if not rows:
        return False, "no statement — 0 is not evidence", ["0 statements"]
    items = []
    for i, (f, ym, op, cl, s) in enumerate(rows):
        if op is None or cl is None:
            items.append(f"{f}: balance is missing")
            continue
        if abs(float(op + s - cl)) > tol:
            items.append(f"{f}: opening {_money(op)} + movements {_money(s)} ≠ closing {_money(cl)}")
        if i and rows[i - 1][3] is not None and abs(float(rows[i - 1][3] - op)) > tol:
            items.append(f"{f}: opening {_money(op)} ≠ closing of the previous statement {_money(rows[i - 1][3])}")
    if items:
        return False, f"the bank statements are not complete: {_fmt_items(items)}", items
    return True, f"{len(rows)} statements: balances carry forward and tie to the movements", []


@check("bank_gl_match")
def bank_gl_match(con, tol: float = 0.01):
    """Banka == účet 221 v účtovníctve po dňoch (bankový výpis vs. denník). Pri nesúlade menuje pohyby, ktoré
    nemajú náprotivok: zápis v denníku (doklad, stredisko, text) bez pohybu v banke a naopak."""
    rows = con.execute("""
        WITH b AS (SELECT day, sum(amount) AS s FROM stg_bank GROUP BY 1),
             j AS (SELECT day, sum(CASE WHEN md = '221' THEN amount ELSE -amount END) AS s FROM stg_journal
                   WHERE (md = '221' OR d = '221') AND doklad NOT LIKE 'PS%' GROUP BY 1)
        SELECT coalesce(b.day, j.day), coalesce(b.s, 0), coalesce(j.s, 0) FROM b FULL JOIN j ON b.day = j.day ORDER BY 1""").fetchall()
    if not rows:
        return False, "no bank movement — 0 is not evidence", ["0 days"]
    items = []
    for d, b, j in rows:
        if abs(float(b - j)) <= tol:
            continue
        items.append(f"{_day(d)}: bank {_money(b)} ≠ account 221 {_money(j)} (difference {_signed(b - j)})")
        bank = [float(x[0]) for x in con.execute("SELECT amount FROM stg_bank WHERE day = ?", [d]).fetchall()]
        for doc, cc, text, v in con.execute(
                "SELECT doklad, cc, text, CASE WHEN md = '221' THEN amount ELSE -amount END FROM stg_journal "
                "WHERE day = ? AND (md = '221' OR d = '221') AND doklad NOT LIKE 'PS%' ORDER BY 1", [d]).fetchall():
            if float(v) in bank:
                bank.remove(float(v))
            else:
                items.append(f"  {_day(d)}: in the journal {doc} {cc} “{text}” {_money(v)} — missing in the bank")
        items += [f"  {_day(d)}: in the bank {_money(v)} — missing in the journal" for v in bank]
    if items:
        return False, f"bank ↔ books do not tie: {_fmt_items(items)}", items
    return True, f"{len(rows)} bank days: statement == account 221 to the cent", []

@check("bank_ap_match")
def bank_ap_match(con, internal: list, direct_pl_allowed: list):
    """Každý pohyb v banke má podklad: úhrada faktúry z knihy (VS = číslo faktúry, IČO protistrany = IČO
    faktúry a v číselníku, suma = faktúra), alebo menovitá interná platba z profilu (karty, vklad hotovosti,
    mzdy, odvody, úver, DPH, daň, dividenda). Iný pohyb = FAIL. Náklad či výnos zaúčtovaný priamo proti banke
    (bez faktúry) = FAIL, okrem účtov povolených profilom (úroky)."""
    rows = con.execute("""
        SELECT b.file, b.line, b.day, b.counterparty, b.vs, b.amount, right(b.iban, 8),
               i.invoice, i.ico, i.total,
               EXISTS (SELECT 1 FROM raw_dims d WHERE d.sheet = 'Suppliers' AND d.k = right(b.iban, 8))
        FROM stg_bank b LEFT JOIN stg_invoices i ON regexp_replace(i.invoice, '[^0-9]', '', 'g') = b.vs
        ORDER BY b.day, b.line""").fetchall()
    if not rows:
        return False, "no bank movement — 0 is not evidence", ["0 movements"]
    items, n_inv, n_int = [], 0, 0
    for f, ln, d, who, vs, amt, ico, inv, inv_ico, total, known in rows:
        if any((who or "").startswith(x["counterparty_prefix"]) for x in internal):
            n_int += 1
            continue
        if inv is None:
            items.append(f"{f} r{ln} {_day(d)}: {who} {_money(amt)} (reference {vs}) — no invoice in the register and not an internal payment")
            continue
        n_inv += 1
        if ico != inv_ico or not known:
            items.append(f"{f} r{ln}: payment of invoice {inv} to company ID {ico}, the invoice has company ID {inv_ico}"
                         + ("" if known else " (the supplier is not in the master data)"))
        if abs(float(-amt) - float(total)) > 0.005:
            items.append(f"{f} r{ln}: payment {_money(-amt)} ≠ invoice {inv} {_money(total)}")
    for doc, d, md, dd, v, cc, text in con.execute(
            "SELECT doklad, day, md, d, amount, cc, text FROM stg_journal WHERE doklad NOT LIKE 'PS%' AND "
            "((d = '221' AND substr(md, 1, 1) IN ('5', '6')) OR (md = '221' AND substr(d, 1, 1) IN ('5', '6'))) ORDER BY 2, 1").fetchall():
        acc = md if dd == "221" else dd
        if not any(acc.startswith(a) for a in direct_pl_allowed):
            items.append(f"journal {doc} {_day(d)} {cc}: account {acc} directly against the bank {_money(v)} “{text}” — no invoice")
    if items:
        return False, f"movements without support ({len(items)}): {_fmt_items(items)}", items
    return True, f"{n_inv:,} invoice payments (reference, company ID, amount) and {n_int:,} named internal payments — no movement without support", []

@check("payroll_gl_match")
def payroll_gl_match(con, tol: float = 0.01):
    """Mzdy == účtovníctvo po stredisku a mesiaci: hrubé mzdy z mzdového systému == 521 (MD − D), odvody
    zamestnávateľa == 524 (MD − D) — aj zápis na strane D (storno) sa počíta."""
    rows = con.execute("""
        WITH p AS (SELECT ym, cc, sum(gross) AS g, sum(employer) AS e FROM stg_payroll GROUP BY 1, 2),
             j AS (SELECT ym, cc,
                          sum(CASE WHEN md = '521' THEN amount WHEN d = '521' THEN -amount ELSE 0 END) AS g,
                          sum(CASE WHEN md = '524' THEN amount WHEN d = '524' THEN -amount ELSE 0 END) AS e
                   FROM stg_journal WHERE md IN ('521', '524') OR d IN ('521', '524') GROUP BY 1, 2)
        SELECT coalesce(p.ym, j.ym), coalesce(p.cc, j.cc), coalesce(p.g, 0), coalesce(j.g, 0), coalesce(p.e, 0), coalesce(j.e, 0)
        FROM p FULL JOIN j ON p.ym = j.ym AND p.cc = j.cc ORDER BY 1, 2""").fetchall()
    if not rows:
        return False, "no payroll — 0 is not evidence", ["0 payroll rows"]
    items = []
    for ym, cc, pg, jg, pe, je in rows:
        if abs(float(pg - jg)) > tol:
            items.append(f"{ym} {cc}: gross pay {_money(pg)} ≠ 521 {_money(jg)} (difference {_signed(pg - jg)})")
        if abs(float(pe - je)) > tol:
            items.append(f"{ym} {cc}: contributions {_money(pe)} ≠ 524 {_money(je)}")
    if items:
        return False, f"payroll ↔ books do not tie: {_fmt_items(items)}", items
    return True, f"{len(rows)} cost centres × months: payroll == 521 and 524 (Dr − Cr) to the cent", []

@check("ap_gl_match")
def ap_gl_match(con, tol: float = 0.01):
    """Kniha došlých faktúr == denník: každá faktúra je zaúčtovaná pod svojím číslom na svojom účte,
    stredisku a v mesiaci svojho dátumu (náklad/tovar = základ, záväzok 321 = spolu) a každý zápis faktúry
    v denníku má faktúru v knihe (presun nákladu medzi strediskami alebo mesiacmi sa prezradí)."""
    rows = con.execute("""
        WITH j AS (SELECT doklad, sum(amount) FILTER (WHERE d = '321') AS total,
                          sum(amount) FILTER (WHERE md NOT IN ('343', '321')) AS base,
                          string_agg(DISTINCT md, '+') FILTER (WHERE md NOT IN ('343', '321')) AS acc,
                          string_agg(DISTINCT cc, '+') FILTER (WHERE md NOT IN ('343', '321')) AS cc,
                          string_agg(DISTINCT ym, '+') AS ym
                   FROM stg_journal WHERE doklad LIKE 'FD%' GROUP BY 1)
        SELECT coalesce(i.invoice, j.doklad), i.file, i.line, i.total, j.total, i.base, j.base, i.account, j.acc,
               i.cc, j.cc, i.ym, j.ym
        FROM stg_invoices i FULL JOIN j ON i.invoice = j.doklad ORDER BY 1""").fetchall()
    if not rows:
        return False, "no invoice — 0 is not evidence", ["0 invoices"]
    items = []
    for no, f, ln, it, jt, ib, jb, ia, ja, icc, jcc, iym, jym in rows:
        if jt is None:
            items.append(f"{f} r{ln}: invoice {no} ({_money(it)}) is not posted in the journal")
        elif it is None:
            items.append(f"journal: document {no} ({_money(jt)}) has no invoice in the register")
        else:
            if abs(float(it - jt)) > tol or abs(float((ib or 0) - (jb or 0))) > tol or ia != ja:
                items.append(f"invoice {no}: register {ia} {_money(ib)} / {_money(it)} ≠ journal {ja} {_money(jb)} / {_money(jt)}")
            if icc != jcc:
                items.append(f"invoice {no}: cost centre in the register {icc} ≠ in the journal {jcc}")
            if iym != jym:
                items.append(f"invoice {no}: invoice month {iym} ≠ posted in {jym}")
    if items:
        return False, f"invoices ↔ journal do not tie ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows):,} invoices posted under their own number to the right account, cost centre, month and amount", []

@check("stock_consistency")
def stock_consistency(con, tol: float = 0.01):
    """Sklad je konzistentný: žiadna záporná zásoba; stav = počiatočný + príjem − výdaj; počiatočný stav
    mesiaca == konečný predchádzajúceho; príjem a výdaj v stave == súčet pohybov; príjem == účet 132 (MD)
    a výdaj == predaný tovar 504 (MD − D) po stredisku a mesiaci — aj stredisko bez skladu (centrála)."""
    items = []
    for f, cc, cat, cl in con.execute("SELECT file, cc, category, closing FROM stg_stock_state WHERE closing < 0 ORDER BY 1").fetchall():
        items.append(f"{f}: negative stock {cc} {cat} {_money(cl)}")
    for f, cc, cat in con.execute("""SELECT file, cc, category FROM stg_stock_state
                                     WHERE abs(opening + received - issued - closing) > 0.005 ORDER BY 1""").fetchall():
        items.append(f"{f}: {cc} {cat} closing ≠ opening + received − issued")
    for f, cc, cat, op, prev in con.execute("""
            SELECT s.file, s.cc, s.category, s.opening, p.closing FROM stg_stock_state s JOIN stg_stock_state p
            ON p.cc = s.cc AND p.category = s.category
            AND p.ym = strftime(CAST(s.ym || '-01' AS DATE) - INTERVAL 1 MONTH, '%Y-%m')
            WHERE abs(s.opening - p.closing) > 0.005 ORDER BY 1""").fetchall():
        items.append(f"{f}: {cc} {cat} opening {_money(op)} ≠ closing of the previous month {_money(prev)}")
    for f, cc, cat, sr, si, mr, mi in con.execute("""
            WITH mv AS (SELECT ym, cc, category, sum(value) FILTER (WHERE kind = 'receipt') AS r,
                               sum(value) FILTER (WHERE kind = 'issue') AS i FROM stg_stock_moves GROUP BY 1, 2, 3)
            SELECT s.file, s.cc, s.category, s.received, s.issued, coalesce(mv.r, 0), coalesce(mv.i, 0)
            FROM stg_stock_state s LEFT JOIN mv USING (ym, cc, category)
            WHERE abs(s.received - coalesce(mv.r, 0)) > 0.005 OR abs(s.issued - coalesce(mv.i, 0)) > 0.005 ORDER BY 1""").fetchall():
        items.append(f"{f}: {cc} {cat} levels received/issued {_money(sr)}/{_money(si)} ≠ movements {_money(mr)}/{_money(mi)}")
    rows = con.execute("""
        WITH mv AS (SELECT ym, cc, sum(value) FILTER (WHERE kind = 'receipt') AS r, sum(value) FILTER (WHERE kind = 'issue') AS i
                    FROM stg_stock_moves GROUP BY 1, 2),
             j AS (SELECT ym, cc, sum(CASE WHEN md = '132' THEN amount WHEN d = '132' AND md <> '504' THEN -amount ELSE 0 END)
                                  FILTER (WHERE doklad NOT LIKE 'PS%') AS r,
                          sum(CASE WHEN md = '504' THEN amount WHEN d = '504' THEN -amount ELSE 0 END) AS i
                   FROM stg_journal WHERE md IN ('132', '504') OR d IN ('132', '504') GROUP BY 1, 2)
        SELECT coalesce(mv.ym, j.ym), coalesce(mv.cc, j.cc), coalesce(mv.r, 0), coalesce(j.r, 0), coalesce(mv.i, 0), coalesce(j.i, 0)
        FROM mv FULL JOIN j ON mv.ym = j.ym AND mv.cc = j.cc ORDER BY 1, 2""").fetchall()
    if not rows:
        return False, "no stock movement — 0 is not evidence", ["0 movements"]
    for ym, cc, mr, jr, mi, ji in rows:
        if abs(float(mr - jr)) > tol:
            items.append(f"{ym} {cc}: stock received {_money(mr)} ≠ 132 {_money(jr)}")
        if abs(float(mi - ji)) > tol:
            items.append(f"{ym} {cc}: stock issued {_money(mi)} ≠ goods sold 504 {_money(ji)}")
    if items:
        return False, f"stock does not tie ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows)} cost centres × months: stock non-negative and carried forward, levels == movements, received == 132, issued == 504", []


@check("posting_policy")
def posting_policy(con, policy: list):
    """Predkontácie: každý riadok denníka zodpovedá povolenej kombinácii
    typ dokladu × MD × D z účtovej politiky profilu. Náklad cez medziúčet bez dokladu (518/379,
    501/211, 518/331) inak prejde všetkými párovaniami zdroj ↔ zdroj — tu padne menovite."""
    if not policy:
        return False, "the profile has no accounting policy of posting patterns — 0 is not evidence", ["posting_policy empty"]
    con.execute("CREATE OR REPLACE TEMP TABLE _policy (doc VARCHAR, md VARCHAR, d VARCHAR)")
    con.executemany("INSERT INTO _policy VALUES (?, ?, ?)", [tuple(p) for p in policy])
    rows = con.execute("""
        SELECT j.file, j.line, j.doklad, j.md, j.d, j.amount, j.cc
        FROM stg_journal j LEFT JOIN _policy p
          ON p.doc = regexp_extract(j.doklad, '^[A-Z]+') AND p.md = j.md AND p.d = j.d
        WHERE p.doc IS NULL ORDER BY j.file, j.line""").fetchall()
    total = con.execute("SELECT count(*) FROM stg_journal").fetchone()[0]
    if not total:
        return False, "empty journal — 0 is not evidence", ["0 journal rows"]
    items = [f"{f} r{ln}: {doc} {md}/{d} {_money(a)} {cc} — posting pattern is not in the accounting policy"
             for f, ln, doc, md, d, a, cc in rows]
    if items:
        return False, f"postings outside the accounting policy ({len(items)}): {_fmt_items(items)}", items
    return True, f"{total:,} journal rows: each on an allowed posting pattern ({len(policy)} patterns from the profile)", []


@check("liability_settlement")
def liability_settlement(con, accounts: dict, tol: float = 0.01):
    """Úhrady záväzkov: úhrada z banky na účet záväzku (331 mzdy, 336 odvody,
    342 daň zo mzdy, 341 preddavky dane, 343 DPH) v mesiaci == záväzok predchádzajúceho mesiaca; kladný
    záväzok bez úhrady = FAIL. Pravidlo z profilu: 'accrual' = pohyb účtu mimo banky za predchádzajúci mesiac
    (záporný → 0, preplatok sa neprenáša), 'balance' = zostatok ku koncu predchádzajúceho mesiaca (s prenosom
    nároku, DPH). Rozsah: po stredisku ('cc') alebo za firmu ('company')."""
    if not accounts:
        return False, "the profile has no liability accounts to settle — 0 is not evidence", ["settlement_accounts empty"]
    months = [r[0] for r in con.execute("SELECT DISTINCT ym FROM stg_journal WHERE ym IS NOT NULL ORDER BY 1").fetchall()]
    items, n = [], 0
    for acc, rule in accounts.items():
        key = "cc" if rule["scope"] == "cc" else "'company'"
        mov = con.execute(f"""
            SELECT ym, {key} AS k,
                   sum(CASE WHEN md = '221' OR d = '221' THEN 0 WHEN d = ? THEN amount ELSE -amount END) AS accr,
                   sum(CASE WHEN md = ? AND d = '221' THEN amount WHEN d = ? AND md = '221' THEN -amount ELSE 0 END) AS paid
            FROM stg_journal WHERE md = ? OR d = ? GROUP BY 1, 2""", [acc, acc, acc, acc, acc]).fetchall()
        by = {(ym, k): (float(a), float(p)) for ym, k, a, p in mov}
        for k in sorted({k for _, k in by}):
            bal, prev = 0.0, 0.0
            for ym in months:
                accr, paid = by.get((ym, k), (0.0, 0.0))
                base = bal if rule["rule"] == "balance" else prev
                due = base if base > tol else 0.0
                refund = rule["rule"] == "balance" and base < -tol and abs(paid - base) <= tol   # vrátenie nároku
                if paid or due:
                    n += 1
                    if abs(paid - due) > tol and not refund:
                        what = "balance at the end of" if rule["rule"] == "balance" else "liability for"
                        items.append(f"{ym} {k} account {acc}: payment in the bank {_money(paid)} ≠ {what} "
                                     f"the previous month {_money(due)}")
                bal += accr - paid
                prev = accr
    if not n and not items:
        return False, "no liability payment — 0 is not evidence", ["0 payments"]
    if items:
        return False, f"liability payments do not tie ({len(items)}): {_fmt_items(items)}", items
    return True, f"{n} liability payments ({', '.join(accounts)}) == liability of the previous month", []


@check("card_settlement")
def card_settlement(con, tol: float = 0.01):
    """Zúčtovanie kariet: poplatok za karty 568 po predajni a mesiaci == tržby kartou
    z pokladne za zúčtované dni − pripísané bankou; zostatok 315 == tržby kartou, ktoré banka ešte nepripísala.
    Poplatok ani odpis pohľadávky sa nedá pridať bez stopy v banke a pokladni."""
    rows = con.execute("""
        WITH pos AS (SELECT cc, day, sum(gross) AS g FROM stg_pos WHERE payment = 'card' GROUP BY 1, 2),
             st AS (SELECT regexp_extract(text, '^Settlement (\\S+) ', 1) AS cc,
                           CAST(try_strptime(regexp_extract(text, '(\\d{2}\\.\\d{2}\\.\\d{4})$', 1), '%d.%m.%Y') AS DATE) AS sale,
                           max(strftime(day, '%Y-%m')) AS ym, sum(amount) AS paid
                    FROM stg_bank WHERE text LIKE 'Settlement %' GROUP BY 1, 2),
             fee AS (SELECT st.cc, st.ym, sum(coalesce(pos.g, 0) - st.paid) AS f
                     FROM st LEFT JOIN pos ON pos.cc = st.cc AND pos.day = st.sale GROUP BY 1, 2),
             j AS (SELECT cc, ym, sum(CASE WHEN md = '568' THEN amount ELSE -amount END) AS f
                   FROM stg_journal WHERE md = '568' OR d = '568' GROUP BY 1, 2)
        SELECT coalesce(fee.cc, j.cc), coalesce(fee.ym, j.ym), coalesce(fee.f, 0), coalesce(j.f, 0)
        FROM fee FULL JOIN j ON fee.cc = j.cc AND fee.ym = j.ym ORDER BY 1, 2""").fetchall()
    if not rows:
        return False, "no card settlement — 0 is not evidence", ["0 settlements"]
    items = [f"{ym} {cc}: fee 568 {_money(jf)} ≠ card sales − credited by the bank {_money(pf)} "
             f"(difference {_signed(jf - pf)})" for cc, ym, pf, jf in rows if abs(float(pf - jf)) > tol]
    open_ = con.execute("""
        WITH pos AS (SELECT cc, day, sum(gross) AS g FROM stg_pos WHERE payment = 'card' GROUP BY 1, 2),
             st AS (SELECT DISTINCT regexp_extract(text, '^Settlement (\\S+) ', 1) AS cc,
                           CAST(try_strptime(regexp_extract(text, '(\\d{2}\\.\\d{2}\\.\\d{4})$', 1), '%d.%m.%Y') AS DATE) AS sale
                    FROM stg_bank WHERE text LIKE 'Settlement %'),
             un AS (SELECT pos.cc, sum(pos.g) AS g FROM pos LEFT JOIN st ON st.cc = pos.cc AND st.sale = pos.day
                    WHERE st.cc IS NULL GROUP BY 1),
             b AS (SELECT cc, sum(CASE WHEN md = '315' THEN amount ELSE -amount END) AS bal
                   FROM stg_journal WHERE md = '315' OR d = '315' GROUP BY 1)
        SELECT coalesce(b.cc, un.cc), coalesce(un.g, 0), coalesce(b.bal, 0)
        FROM b FULL JOIN un ON b.cc = un.cc ORDER BY 1""").fetchall()
    items += [f"{cc}: balance 315 {_money(bal)} ≠ card sales not yet credited by the bank {_money(g)}"
              for cc, g, bal in open_ if abs(float(g - bal)) > tol]
    if items:
        return False, f"card settlement does not tie ({len(items)}): {_fmt_items(items)}", items
    return True, (f"{len(rows)} stores × months: fee 568 == card sales − credited by the bank; "
                  f"balance 315 == sales not yet credited"), []


@check("loan_schedule")
def loan_schedule(con, loan: dict, tol: float = 0.01):
    """Úver podľa zmluvy: úrok 562 v mesiaci == zostatok úveru na začiatku mesiaca ×
    ročná sadzba / 12 a splátka istiny == mesačná splátka zo zmluvy (údaje zmluvy v profile, nie z generátora)."""
    if not loan:
        return False, "the profile has no loan agreement — 0 is not evidence", ["loan_contract empty"]
    acc, ia = loan["account"], loan["interest_account"]
    opening = float(con.execute("SELECT coalesce(sum(CASE WHEN d = ? THEN amount ELSE -amount END), 0) FROM stg_journal "
                                "WHERE (d = ? OR md = ?) AND doklad LIKE 'PS%'", [acc, acc, acc]).fetchone()[0])
    rows = con.execute("""
        SELECT ym, sum(CASE WHEN d = ? THEN amount WHEN md = ? THEN -amount ELSE 0 END) AS net,
               sum(CASE WHEN md = ? THEN amount ELSE 0 END) AS repaid,
               sum(CASE WHEN md = ? THEN amount WHEN d = ? THEN -amount ELSE 0 END) AS interest
        FROM stg_journal WHERE (md IN (?, ?) OR d IN (?, ?)) AND doklad NOT LIKE 'PS%'
        GROUP BY 1 ORDER BY 1""", [acc, acc, acc, ia, ia, acc, ia, acc, ia]).fetchall()
    if not rows:
        return False, "no loan movement — 0 is not evidence", ["0 movements"]
    items, bal = [], opening
    for ym, net, repaid, interest in rows:
        exp_i = round(bal * loan["rate_pa"] / 12, 2)
        if abs(float(interest) - exp_i) > tol:
            items.append(f"{ym}: interest {ia} {_money(interest)} ≠ agreement {_money(exp_i)} "
                         f"(balance {_money(bal)} × {loan['rate_pa'] * 100:.2f}% / 12)")
        due = min(loan["monthly_repayment"], bal) if bal > tol else 0.0     # posledná splátka = zvyšok
        if abs(float(repaid) - due) > tol:
            items.append(f"{ym}: principal repayment {_money(repaid)} ≠ agreement {_money(due)}")
        bal += float(net)
    if items:
        return False, f"the loan does not tie to the agreement ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows)} months: interest == balance × rate / 12 and repayment == agreement", []


# ---------------------------------------------------------------- board pack

@check("boardpack_consistency")
def boardpack_consistency(con, ytd: dict, ytd_prev: dict, profile: dict, ro: list = (), tol: float = 0.01):
    """Board pack == druhá cesta v Pythone na cent — nezávislé od SQL
    board packu (bp_*): mesačná mriežka skutočnosť / plán / minulý rok z pl_base a zo zdroja plánu stg_plan (daň
    plánu = sadzba × plán zisku pred zdanením); ODHAD zvyšku roka po stredisku × riadku × mesiaci (plán × tempo
    posledných N mesiacov, bez plánu priemer, daň sadzbou); riadky YTD, minulý rok YTD aj celý, plán, odhad roka so
    medzisúčtami z pl_subtotals; odchýlky voči plánu aj minulému roku a ich poradie; pravidlá tempo tržieb a nákladový
    skok (€); každý účet plánu zaradený, súčet plánu == zdroj. Mimo: mix kategórie."""
    bpc, subs = profile["board_pack"], profile["pl_subtotals"]
    as_of = profile["period"]["as_of"]
    y2, y1, am, n = as_of[:4], str(int(as_of[:4]) - 1), int(as_of[5:]), bpc["runrate_months"]
    shops = [s["name"] for s in profile["shops"]]
    tax_row, tax_shop = bpc["tax_row"], next(s["name"] for s in profile["shops"] if s["cost_center"] == bpc["tax_cost_center"])
    base = [r for r in profile["pl_rows"] if r not in subs]

    def parts(r):
        return [x for p in subs[r] for x in parts(p)] if r in subs else [r]
    pbt = parts(bpc["pbt_row"])

    def compose(b: dict) -> dict:
        t = {(s, r): sum(b.get((s, p), 0.0) for p in parts(r)) for s in shops for r in profile["pl_rows"]}
        t.update({("Total", r): sum(t[(s, r)] for s in shops) for r in profile["pl_rows"]})
        return t

    def cell(src, s, r, months):
        return sum(src.get((s, p, mo), 0.0) for p in parts(r) for mo in months)
    if not con.execute("SELECT count(*) FROM bp_rows").fetchone()[0]:
        return False, "board pack is empty — 0 is not evidence", ["bp_rows empty"]
    act, ly, pm = {}, {}, {}
    for s, r, ym, v in con.execute("SELECT shop, row, ym, sum(amount) FROM pl_base GROUP BY 1, 2, 3").fetchall():
        mo = int(ym[5:])
        if ym[:4] == y2 and mo <= am:
            act[(s, r, mo)] = float(v or 0)
        elif ym[:4] == y1:
            ly[(s, r, mo)] = float(v or 0)
    from decimal import ROUND_HALF_UP, Decimal
    pdec = {}
    for s, r, mo, v in con.execute("""
            SELECT c.shop, m.row, CAST(substr(p.ym, 6, 2) AS INT),
                   sum(CASE WHEN p.account LIKE '6%' THEN p.amount ELSE -p.amount END)
            FROM stg_plan p JOIN pl_map m USING (account) JOIN cost_centers c USING (cc) GROUP BY 1, 2, 3""").fetchall():
        pdec[(s, r, mo)] = Decimal(str(v or 0))
        pm[(s, r, mo)] = float(v or 0)
    for mo in range(1, 13):                  # daň plánu presne na centy, od nuly (ako SQL a generátor)
        pm[(tax_shop, tax_row, mo)] = float((-Decimal(str(bpc["tax_rate"])) * sum(
            (v for (s, r, m_), v in pdec.items() if m_ == mo and r in pbt), Decimal(0))).quantize(Decimal("0.01"), ROUND_HALF_UP))
    rr, rest, ytdm = range(am - n + 1, am + 1), range(am + 1, 13), range(1, am + 1)
    fc = {}
    for s in shops:
        for r in base:
            if r == tax_row:
                continue
            a, p = sum(act.get((s, r, mo), 0.0) for mo in rr), sum(pm.get((s, r, mo), 0.0) for mo in rr)
            for mo in rest:
                fc[(s, r, mo)] = pm.get((s, r, mo), 0.0) * a / p if p else a / n
    for mo in rest:
        fc[(tax_shop, tax_row, mo)] = -bpc["tax_rate"] * sum(v for (s, r, m_), v in fc.items() if m_ == mo and r in pbt)
    items = []

    def diff(label, got, want):
        if abs(float(got or 0) - float(want or 0)) > tol:
            items.append(f"{label}: board pack ≠ second path ({'higher' if float(got or 0) > float(want or 0) else 'lower'})")
    # 1. mesačná mriežka
    grid = con.execute("SELECT shop, row, mo, actual, plan, ly FROM bp_grid").fetchall()
    for s, r, mo, a, p, l_ in grid:
        diff(f"{s} · {r} · month {mo} actual", a, act.get((s, r, mo), 0.0) if mo <= am else 0.0)
        diff(f"{s} · {r} · month {mo} plan", p, pm.get((s, r, mo), 0.0))
        diff(f"{s} · {r} · month {mo} last year", l_, ly.get((s, r, mo), 0.0))
    if len(grid) != len(shops) * len(base) * 12:
        items.append(f"grid: {len(grid)} cells ≠ {len(shops) * len(base) * 12}")
    # 2. odhad po stredisku × riadku × mesiaci
    got_fc = {(s, r, mo): float(v or 0) for s, r, mo, v in con.execute(
        "SELECT shop, row, mo, sum(amount) FROM bp_forecast GROUP BY 1, 2, 3").fetchall()}
    for k in sorted(set(got_fc) | set(fc)):
        diff(f"{k[0]} · {k[1]} · month {k[2]} forecast", got_fc.get(k, 0.0), fc.get(k, 0.0))
    # 3. riadky board packu so medzisúčtami
    want = {"ytd_act": ytd, "ytd_ly": ytd_prev,
            "ytd_plan": compose({(s, r): cell(pm, s, r, ytdm) for s in shops for r in base}),
            "fy_plan": compose({(s, r): cell(pm, s, r, range(1, 13)) for s in shops for r in base}),
            "fy_ly": compose({(s, r): cell(ly, s, r, range(1, 13)) for s in shops for r in base}),
            "rest_fc": compose({(s, r): cell(fc, s, r, rest) for s in shops for r in base})}
    want["fy_est"] = {k: ytd[k] + want["rest_fc"][k] for k in ytd}
    cols = list(want)
    rows = {(s, r): dict(zip(cols, v)) for s, r, *v in con.execute(
        f"SELECT shop, row, {', '.join(cols)} FROM bp_rows").fetchall()}
    for (s, r) in sorted(ytd):
        if (s, r) not in rows:
            items.append(f"{s} · {r}: is in the P&L, missing in the board pack")
            continue
        for c in cols:
            diff(f"{s} · {r} · {c}", rows[(s, r)][c], want[c][(s, r)])
    items += [f"{s} · {r}: extra in the board pack (the P&L does not have it)" for s, r in rows if (s, r) not in ytd]
    # 4. odchýlky voči plánu aj minulému roku a poradie
    var = con.execute("SELECT shop, row, d_plan, d_ly FROM bp_variance ORDER BY rk").fetchall()
    want_var = sorted(((s, r, ytd[(s, r)] - want["ytd_plan"][(s, r)], ytd[(s, r)] - ytd_prev[(s, r)])
                       for s in shops for r in bpc["variance_rows"]), key=lambda x: (-abs(x[2]), x[0], x[1]))
    for (s, r, d, dl), (ws, wr, wd, wdl) in zip(var[:bpc["variance_top"]], want_var[:bpc["variance_top"]]):
        if (s, r) != (ws, wr) or abs(float(d) - wd) > tol or abs(float(dl) - wdl) > tol:
            items.append(f"variances: order or amount does not tie ({s} · {r} vs second path {ws} · {wr})")
            break
    if len(var) != len(want_var):
        items.append(f"variances: {len(var)} rows ≠ {len(want_var)} (cost centre × variance line)")
    # 5. pravidlá rizík a citlivosti s €: tempo tržieb, nákladový skok (mix kategórie = limit)
    want_ro, mn = {}, bpc["ro_min_eur"]
    for s in sorted(shops):
        a, p = cell(act, s, "Revenue", rr), cell(pm, s, "Revenue", rr)
        ay, py = cell(act, s, "Revenue", ytdm), cell(pm, s, "Revenue", ytdm)
        if p and py and ay and abs(a / p - ay / py) >= bpc["ro"]["revenue_pace"]["min_gap"]:
            imp = (cell(pm, s, "Revenue", rest) * ay / py - cell(fc, s, "Revenue", rest)) * cell(act, s, "Gross margin", ytdm) / ay
            if abs(imp) >= mn:
                want_ro[f"sensitivity|revenue_pace|{s}"] = imp
    cs = bpc["ro"]["cost_spike_repeat"]
    tot = lambda src, r, ms: sum(cell(src, s, r, ms) for s in shops)  # noqa: E731
    for r in [x for x in parts(bpc["ebitda_row"]) if x not in cs.get("exclude", []) and x != "Revenue"]:
        lr = tot(ly, r, rr)
        rr_yoy = tot(act, r, rr) / lr - 1 if lr else 0.0
        for q in range(1, (am - n) // 3 + 1):
            lq = tot(ly, r, range(3 * q - 2, 3 * q + 1))
            if lq and tot(act, r, range(3 * q - 2, 3 * q + 1)) / lq - 1 >= cs["min_yoy"] and rr_yoy < cs["min_yoy"] / 2:
                imp = tot(ly, r, rest) * (tot(act, r, range(3 * q - 2, 3 * q + 1)) / lq) - tot(fc, r, rest)
                if abs(imp) >= mn:
                    want_ro[f"ro|cost_spike|{r}|Q{q}"] = imp
    got_ro = {x["key"]: x["number"] for x in ro if x["rule"] in ("revenue_pace", "cost_spike_repeat")}
    for k in sorted(set(got_ro) | set(want_ro)):
        if k not in got_ro or k not in want_ro:
            items.append(f"risks: item {k} is {'missing' if k not in got_ro else 'extra'} vs the second path")
        else:
            diff(f"risks: {k}", got_ro[k], want_ro[k])
    # 6. plán úplný
    unmapped = [r[0] for r in con.execute(
        "SELECT DISTINCT account FROM stg_plan WHERE amount <> 0 AND account NOT IN (SELECT account FROM pl_map) "
        "ORDER BY 1").fetchall()]
    items += [f"plan: account {a} is not mapped to the P&L — the plan would be lost" for a in unmapped]
    src, got = con.execute("""
        SELECT (SELECT sum(CASE WHEN account LIKE '6%' THEN amount ELSE -amount END) FROM stg_plan
                WHERE cc IN (SELECT cc FROM cost_centers)),
               (SELECT sum(plan) FROM bp_grid_raw)""").fetchone()
    if abs(float(src or 0) - float(got or 0)) > tol:
        items.append(f"plan: board pack {float(got or 0):,.2f} ≠ plan source {float(src or 0):,.2f} (rows were lost)")
    lost = con.execute("SELECT count(*) FROM stg_plan WHERE cc NOT IN (SELECT cc FROM cost_centers) AND amount <> 0").fetchone()[0]
    if lost:
        items.append(f"plan: {lost} rows with an unknown cost centre")
    if items:
        return False, f"board pack ≠ second path ({len(items)}): {_fmt_items(items)}", items
    return True, (f"board pack == second path to the cent: {len(grid)} grid cells, {len(fc)} forecast cells, "
                  f"{len(rows)} lines (YTD, plan, last year, full-year forecast), variances and their order, {len(want_ro)} "
                  f"risk rules with €; plan complete"), []

# ---------------------------------------------------------------- zmluva reportu
def _pct_after(text: str, after: str):
    """Prvé percento v texte za slovom `after` ('' = prvé v texte): '−34,3 %' → -34.3."""
    i = text.find(after) if after else 0
    if i < 0:
        return None
    mt = re.search(r"([+−-]?\d+(?:,\d{3})*(?:\.\d+)?)\s*%", text[i + len(after):])
    return float(mt.group(1).replace("−", "-").replace(",", "")) if mt else None


def _contract_cell(wb, loc: dict):
    """Hodnota bunky zmluvy z hotového xlsx podľa NÁZVOV (nie súradníc): (hodnota, adresa) alebo
    (None, dôvod). Vzorec v bunke = nie hodnota (výstup pre board je bez vzorcov)."""
    if loc["sheet"] not in wb.sheetnames:
        return None, f"sheet '{loc['sheet']}' is missing"
    ws = wb[loc["sheet"]]
    rows = list(ws.iter_rows())
    if "text_prefix" in loc:
        for r in rows:
            for c in r:
                if isinstance(c.value, str) and c.value.startswith(loc["text_prefix"]):
                    v = _pct_after(c.value, loc["after"])
                    return (v, c.coordinate) if v is not None else (None, f"{c.coordinate}: no percentage in the text")
        return None, f"finding row starting with '{loc['text_prefix']}' is missing"
    if "label" in loc:
        for r in rows:
            if r and r[0].value == loc["label"] and len(r) > 1:
                return r[1].value, r[1].coordinate
        return None, f"row '{loc['label']}' is missing"
    head = [c.value for c in rows[0]] if rows else []
    if loc["col"] not in head:
        return None, f"column '{loc['col']}' is missing"
    ci = head.index(loc["col"])
    for r in rows[1:]:
        if r[0].value == loc["row"]:
            return r[ci].value, r[ci].coordinate
    return None, f"row '{loc['row']}' is missing"


@check("report_contract")
def report_contract(xlsx: Path, contract: dict, anchors: dict, delivery_sha: str,
                    check_status: dict, engine_detail=None, as_of: str = None, full_out: list = None):
    """Zmluva reportu (podmienky odoslania): každé číslo zmluvy prečítané z HOTOVÉHO xlsx
    (podľa názvov, bez vzorcov) sedí s KAŽDOU kotvou mimo motora — suma ±tolerancia €,
    percento = správne zaokrúhlená kotva (|zobrazené − kotva| ≤ 0,05 p. b.); kotvy sa zhodujú
    navzájom a patria tejto dodávke (odtlačok) aj obdobiu; kontroly menované pri čísle
    prešli. Číslo bez platnej kotvy = FAIL, nie SKIP. Detail aj položky (idú do súboru protokolu)
    NENESÚ čísla boardu — len ID, bunku, kotvu, rozdiel a cestu k vstupu; plné hodnoty
    pre obrazovku sa pridajú do `full_out`."""
    from openpyxl import load_workbook
    pts = contract.get("points") or []
    if not pts:
        return False, "the contract has no figure — 0 is not evidence", ["contract empty"]
    safe, full = [], []

    def bad(s_txt, f_txt=None):
        safe.append(s_txt)
        full.append(f_txt or s_txt)
    want_anchors = contract.get("anchors") or []
    if sorted(want_anchors) != sorted(anchors):
        bad(f"anchors of the run {sorted(anchors)} ≠ anchors of the contract {sorted(want_anchors)}")
    valid = {}
    for name in want_anchors:
        a = anchors.get(name)
        if not a:
            bad(f"anchor {name} is missing")
        elif a.get("_meta", {}).get("delivery_sha256") != delivery_sha:
            bad(f"anchor {name} is not for this delivery (different fingerprint) — no golden exists for it")
        elif as_of and a.get("_meta", {}).get("as_of") != as_of:
            bad(f"anchor {name} is for period {a['_meta'].get('as_of')}, the report is as of {as_of} — no golden exists for it")
        else:
            valid[name] = a
    if len(want_anchors) < 2:
        bad(f"the contract names {len(want_anchors)} anchor — condition 2 requires both (generator and independent recalculation)")
    if want_anchors and len(valid) < len(want_anchors):
        bad(f"valid anchors {len(valid)}/{len(want_anchors)} — {len(pts)} contract figures have no check, the report is not issued")
        if full_out is not None:
            full_out.extend(full)
        return False, f"report contract not met: {_fmt_items(safe)}", safe
    tol = contract["tolerance"]
    if not (0 < tol.get("eur", 0) and 0 < tol.get("pct_display", 0)):
        return False, "the contract has no eur and pct_display tolerance", ["tolerance missing"]
    wb = load_workbook(xlsx)                                   # bez data_only: vzorec ostane textom
    n_ok = 0
    fmt_ok = {"eur": "#,##0.00", "fraction": "0.0%"}          # zobrazenie bunky = to, čo board vidí
    for p in pts:
        pid, unit, lab = p["id"], p["unit"], p["label"]
        if unit not in ("eur", "pct", "fraction"):
            bad(f"{pid} {lab}: unknown unit '{unit}' (allowed: eur, pct, fraction)")
            continue
        for c in p.get("checks", []):
            if not check_status.get(c):
                bad(f"{pid} {lab}: check {c} did not run or FAIL")
        want = {n: a["values"].get(pid) for n, a in valid.items()}
        if any(w is None for w in want.values()):
            bad(f"{pid} {lab}: no value in the anchor — the figure has no check")
            continue
        if unit in ("pct", "fraction"):
            same = lambda shown, w: abs(shown - w) <= tol["pct_display"] + 1e-9  # noqa: E731  správne zaokrúhlená kotva
            agree = lambda a, b: abs(a - b) <= 0.01  # noqa: E731
        else:
            same = lambda shown, w: abs(shown - w) <= tol["eur"] + 1e-9  # noqa: E731
            agree = lambda a, b: abs(a - b) <= 0.01  # noqa: E731
        wv = list(want.items())
        if any(not agree(wv[0][1], w) for _, w in wv[1:]):
            bad(f"{pid} {lab}: the anchors do not agree with each other ({', '.join(n for n, _ in wv)})",
                f"{pid} {lab}: the anchors do not agree ({', '.join(f'{n} {w}' for n, w in wv)})")
        ok_here = True
        for loc in [p["locate"]] + p.get("also", []):
            lu = loc.get("unit", unit)                      # umiestnenie môže niesť vlastnú jednotku (G16: text + KPI)
            if lu not in ("eur", "pct", "fraction") or (lu == "pct") != ("text_prefix" in loc) or \
                    (lu == "eur") != (unit == "eur"):
                ok_here = False
                bad(f"{pid} {lab}: unit '{lu}' does not fit the location {loc.get('sheet')} (allowed: pct = finding text,"
                    f" fraction = share cell, eur = amount cell)")
                continue
            scale = 100.0 if lu == "fraction" else 1.0      # bunka ako podiel (0,25) vs. kotva v % (25,0)
            v, where = _contract_cell(wb, loc)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and lu in fmt_ok and \
                    wb[loc["sheet"]][where].number_format != fmt_ok[lu]:
                ok_here = False
                bad(f"{pid} {lab}: {loc['sheet']}!{where} has a format other than the agreed '{fmt_ok[lu]}' — the board would see "
                    f"a different figure")                           # podstrčený formát sa nevypisuje
                continue
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
                ok_here = False
                bad(f"{pid} {lab}: {where if v is None else f'{where} is not a number'}",
                    f"{pid} {lab}: {where if v is None else f'{where} is not a number ({v!r})'}")
                continue
            if lu == "fraction":                            # porovnáva sa ZOBRAZENÉ: × 100, 1 desatinné miesto
                from decimal import ROUND_HALF_UP, Decimal
                v = float((Decimal(str(v)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            else:
                v = float(v) * scale
            for n, w in want.items():
                if not same(float(v), w):
                    ok_here = False
                    u = "EUR" if unit == "eur" else "pp"
                    ls, lf = _lineage(p, valid, engine_detail)
                    smer = "higher" if float(v) > w else "lower"
                    bad(f"{pid} {lab}: report {loc['sheet']}!{where} {smer} than anchor {n}{ls}",
                        f"{pid} {lab}: report {loc['sheet']}!{where} = {float(v):,.2f} ≠ anchor {n} {w:,.2f} "
                        f"(difference {float(v) - w:+,.2f} {u}){lf}")
        n_ok += ok_here
    if safe:
        if full_out is not None:
            full_out.extend(full)
        return False, f"report contract not met ({len(safe)}): {_fmt_items(safe)}", safe
    return True, (f"{n_ok}/{len(pts)} contract figures from the finished {Path(xlsx).name} tie to {len(valid)} anchors outside "
                  f"the engine (±€{tol['eur']:.0f}; percentages = correctly rounded anchor)"), []


def _lineage(p: dict, anchors: dict, engine_detail) -> tuple:
    """Cesta k vstupu: (text pre súbor bez súm, text so sumami pre obrazovku). Keď odtlačok
    sedí, vstup je ten istý — rozdiel po mesiacoch znamená, že ho STROJ prečítal inak."""
    src = p.get("source", {})
    if "text" in src:
        t = f" — input: {src['text']}"
        return t, t
    det = next((a["detail"].get(p["id"]) for a in anchors.values() if a.get("detail")), None)
    cc = src.get("cost_center") or "all"
    base = f"{src.get('files')} · cost centre {cc} · accounts {', '.join(src.get('accounts', []))}"
    if det is None or engine_detail is None:
        return f" — input: {base}", f" — input: {base}"
    eng = engine_detail(p) or {}
    diff = [(ym, eng.get(ym, 0.0), det.get(ym, 0.0)) for ym in sorted(set(eng) | set(det))
            if abs(eng.get(ym, 0.0) - det.get(ym, 0.0)) > 0.005]
    if not diff:
        t = f" — input read the same as the anchor month by month ({base}); the difference arose in the calculation or in writing the report"
        return t, t
    more = f" … (+{len(diff) - 3} months)" if len(diff) > 3 else ""
    s_txt = " — the machine read " + "; ".join(f"trial_balance_{ym}.xlsx · cost centre {cc} differently from the anchor"
                                            for ym, e, d in diff[:3]) + more
    f_txt = " — the machine read " + "; ".join(f"trial_balance_{ym}.xlsx · cost centre {cc}: €{e:,.2f} ≠ anchor €{d:,.2f}"
                                            for ym, e, d in diff[:3]) + more
    return s_txt, f_txt


# VÝNIMKY SÚ VYPNUTÉ, kým vedenie nerozhodne, ktoré odchýlky smie board vedome prijať
# (biznisové rozhodnutie). Aj úzka výnimka na kontrolu integrity by pustila boardu
# zlú EBITDA a výnimka na párovanie pokladňa ↔ účtovníctvo by skryla jediný signál,
# že je zlé účtovníctvo. Premisa „párovanie čísla boardu nemení" bola nepravdivá.
EXCEPTABLE: set = set()
MAX_EXCEPTION_MONTHS = 12


def _months_between(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


@check("exceptions_contract")
def exceptions_contract(exceptions: list, known_checks: set, as_of: str = None):
    """Súbor výnimiek je platný: každá výnimka menuje existujúcu kontrolu,
    `match` má aspoň 5 znakov (prázdny by kryl všetko), `valid_until` je RRRR-MM
    (porovnáva sa s as_of) najviac 12 mesiacov dopredu, `reason` nie je prázdny
    a menuje kontrolu zo zoznamu EXCEPTABLE — ten je PRÁZDNY do rozhodnutia vedenia
    (každá výnimka je dnes neplatná). Či výnimka kryje PRÁVE JEDEN nález,
    overí motor pri použití (príliš široká výnimka nekryje nič). Neplatná
    výnimka = FAIL (všeobecný match „pokladňa“ a platnosť 2099
    by pustili boardu čísla zo sady s chybami)."""
    import re as _r
    items = []
    for i, e in enumerate(exceptions, start=1):
        if e.get("check") not in known_checks:
            items.append(f"exception #{i}: unknown check '{e.get('check')}'")
        if len(str(e.get("match", "")).strip()) < 5:
            items.append(f"exception #{i}: match '{e.get('match', '')}' is shorter than 5 characters")
        if not _r.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(e.get("valid_until", "")), _r.ASCII):
            items.append(f"exception #{i}: valid_until '{e.get('valid_until')}' is not YYYY-MM")
        if not str(e.get("reason", "")).strip():
            items.append(f"exception #{i}: reason is missing")
        if e.get("check") in known_checks and e.get("check") not in EXCEPTABLE:
            items.append(f"exception #{i}: check '{e.get('check')}' must not be covered by an exception — exceptions are "
                         f"switched off until management decides which variances the board may accept")
        vu = str(e.get("valid_until", ""))
        if as_of and _r.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", vu, _r.ASCII) \
                and _months_between(as_of, vu) > MAX_EXCEPTION_MONTHS:
            items.append(f"exception #{i}: validity {vu} is more than {MAX_EXCEPTION_MONTHS} months after {as_of}")
    if items:
        return False, f"invalid exceptions: {_fmt_items(items)}", items
    return True, f"{len(exceptions)} exceptions in a valid form", []


@check("truth_meter")
def truth_meter(results: dict, truth: dict, full_out: list = None):
    """Meter proti etalónu generátora (truth.json, počítaný nezávislým kódom
    z čistých dát). Každé číslo na cent."""
    items, n = [], 0

    def cmp(name, got, want):
        nonlocal n
        n += 1
        if got is None or abs(float(got) - float(want)) > 0.005:
            # do súboru protokolu bez hodnôt; plné hodnoty len na obrazovku
            items.append(f"{name}: pipeline {'value missing, expected as in' if got is None else ('higher than' if float(got) > float(want) else 'lower than')}"
                         f" the reference")
            if full_out is not None:
                full_out.append(f"{name}: pipeline {_fmt_num(got)} vs reference {_fmt_num(want)}")
    for k, v in truth.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                cmp(f"{k}[{kk}]", results.get(k, {}).get(kk), vv)
        else:
            cmp(k, results.get(k), v)
    if n == 0:
        return False, "reference is empty — 0 is not evidence", ["reference empty"]
    if items:
        return False, f"{len(items)} of {n} figures do not tie to the reference: {_fmt_items(items)}", items
    return True, f"{n}/{n} figures tie to the reference to the cent", []


@check("xlsx_readback")
def xlsx_readback(path: Path, expected: dict, expected_texts: list = None,
                  unchecked_sheets: tuple = ("Checks", "Control panel", "Failed rows"), expected_headers: dict = None,
                  main_sheet: str | None = "Overview"):
    """Hotový overview.xlsx sa znovu NAČÍTA Z DISKU (nie premenná writera):
    každé číslo vo VŠETKÝCH hárkoch (okrem protokolu kontrol) = výpočet na cent,
    žiadne navyše ani chýbajúce; hlavičky a popisy riadkov = výpočet; VŠETKY
    texty hárku Prehľad (aj stĺpec A) = presne to, čo motor vyrobil; vzorec
    kdekoľvek = FAIL (číslo, ktoré nevyrobil stroj); hárok navyše = FAIL.
    Porovnáva s hodnotami výpočtu — chytí chybu ZÁPISU, nie chybu výpočtu
. Hárky kontrolného panelu
 overuje control_panel_readback; pivot.xlsx sa overuje tou istou kontrolou s main_sheet=None."""
    from openpyxl import load_workbook
    path = Path(path)
    if not path.is_file():
        return False, f"output is missing: {path.name}", [f"missing {path.name}"]
    try:
        wb = load_workbook(path, data_only=False)
    except Exception as e:  # noqa: BLE001
        return False, f"output cannot be opened ({type(e).__name__})", [str(e)]
    want_sheets = {k[0] for k in expected} | ({main_sheet} if main_sheet else set()) | set(expected_headers or {})   # prázdny hárok s hlavičkou
    rows_ok = {sh: {k[1] for k in expected if k[0] == sh} for sh in want_sheets}
    cols_ok = {sh: {k[2] for k in expected if k[0] == sh} for sh in want_sheets}
    got, foreign, owned, texts = {}, [], 0, []
    for sh in wb.sheetnames:
        if sh in unchecked_sheets:
            continue
        if sh not in want_sheets:
            foreign.append(f"unexpected sheet '{sh}'")
            continue
        ws = wb[sh]
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" or (isinstance(c.value, str) and c.value.startswith("=")):
                    foreign.append(f"{sh}!{c.coordinate} formula '{c.value}'")
        rows = [tuple(c.value for c in r) for r in ws.iter_rows()]
        if sh == main_sheet:
            for r in rows:
                for ci, v in enumerate(r):
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        got[(sh, r[0], "B" if ci == 1 else chr(65 + ci))] = v
                    elif v is not None:
                        texts.append(str(v))
            continue
        head = rows[0] if rows else ()
        declared = set((expected_headers or {}).get(sh, [])[1:])     # hlavička sa overuje presne nižšie
        extra_cols = [h for h in head[1:] if h is not None and h not in cols_ok[sh] | declared]
        if head[:1] != (None,) and extra_cols:
            foreign.append(f"{sh}: unexpected columns {extra_cols}")
        if expected_headers is not None and list(head) != list(expected_headers.get(sh, [])):
            foreign.append(f"{sh}: header {list(head)} ≠ calculation {expected_headers.get(sh)}")
        for r in rows[1:]:
            if r[0] not in rows_ok[sh]:
                if any(v is not None for v in r):
                    foreign.append(f"{sh}: row '{r[0]}' was not set by the calculation")
                continue
            for col, v in zip(head[1:], r[1:]):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    got[(sh, r[0], col)] = v
                elif v is not None and isinstance(expected.get((sh, r[0], col)), str):
                    got[(sh, r[0], col)] = str(v)      # text, ktorý výpočet určil (board pack: príčina, komentár)
                elif v is not None:
                    foreign.append(f"{sh}/{r[0]}/{col}='{v}' (not a number)")
    for sh in want_sheets - set(wb.sheetnames):
        foreign.append(f"sheet '{sh}' is missing")
    n_txt = 0
    for k, v in got.items():
        want = expected.get(k)
        if want is None:
            foreign.append(f"{k[0]}/{k[1]}/{k[2]}={v} (not set by the calculation)")
        elif isinstance(want, str) or isinstance(v, str):
            if str(v) != str(want):
                foreign.append(f"{k[0]}/{k[1]}/{k[2]}: text '{str(v)[:60]}' ≠ calculation '{str(want)[:60]}'")
            else:
                n_txt += 1
        elif round(float(v) * 100) != round(float(want) * 100):
            foreign.append(f"{k[0]}/{k[1]}/{k[2]}={v} vs calculation {want:.2f}")
        else:
            owned += 1
    missing = [f"{k[0]}/{k[1]}/{k[2]} is missing" for k in expected if k not in got]
    if expected_texts is not None and texts != list(expected_texts):
        extra = [x for x in texts if x not in expected_texts][:3]
        lost = [x for x in expected_texts if x not in texts][:3]
        foreign.append(f"Overview texts do not tie (extra {extra}, missing {lost})")
    items = foreign + missing
    n = len(expected) - sum(isinstance(v, str) for v in expected.values())
    if items:
        return False, f"machine-made {owned}/{n}, {len(items)} do not tie: {_fmt_items(items)}", items
    if n == 0:
        return True, "output without figures for the board (verdict DOES NOT TIE — only the check log was issued); texts tie", []
    return True, (f"machine-made {owned}/{n} figures" + (f" + {len(texts)} texts of {main_sheet}" if main_sheet else "")
                  + (f" + {n_txt} texts of {'the board pack' if main_sheet else 'the data sheets'}" if n_txt else "") + f" in {path.name} "
                  f"(read back from disk, to the cent, no formulas; the check log is not verified)"), []


# ------------------------------------------------------------------ pivotka + kontrolný panel
_PANEL_LIGHT = {"PASS": "🟢 PASS", "FAIL": "🔴 FAIL", "EXCEPTION": "🟡 EXCEPTION"}


@check("pivot_pl_match")
def pivot_pl_match(path: Path, ytd: dict, bp_rows: dict | None, profile: dict):
    """Pivotka z HOTOVÉHO pivot.xlsx (hárok Fakty, po účtoch) sa sčíta druhou cestou — po stredisku a riadku
    výsledovky s medzisúčtami profilu — a musí sedieť na cent: skutočnosť YTD bežného roka s výsledovkou motora
    (všetky strediská aj Spolu, všetky riadky), skutočnosť celého minulého roka a plán celého roka s board packom
    (bp_rows fy_ly / fy_plan; plán bez riadku dane a čistého zisku — daň plánu dopočítava board pack sadzbou, plán ju
    nemá). Každý fakt: účet patrí do svojho riadku podľa prevodníka profilu, mesiac v období, suma je číslo. Hárky
    Pivot = tie isté fakty zoskupené: každá bunka vrátane Spolu = súčet faktov, prázdna bunka = FAIL. Bez board packu
    niet kotvy pre minulý rok a plán = FAIL. Chýbajúci súbor, hárok alebo riadok = FAIL, nie SKIP.
    Hárky Pivot majú riadky presne v poradí výsledovky profilu, bez duplicít. Limit: presun sumy medzi dvoma účtami toho
    istého riadku a strediska alebo medzi mesiacmi toho istého roka kotvu nemá."""
    from openpyxl import load_workbook
    path = Path(path)
    if not path.is_file():
        return False, f"pivot is missing: {path.name}", [f"missing {path.name}"]
    if bp_rows is None:
        return False, "a pivot without the board pack has no anchor for last year and the plan", ["bp_rows missing"]
    wb = load_workbook(path, data_only=False)
    if "Facts" not in wb.sheetnames:
        return False, "pivot without the Facts sheet", ["Facts sheet missing"]
    rows = list(wb["Facts"].iter_rows(values_only=True))
    head = list(rows[0]) if rows else []
    need = ["Kind", "Month", "Cost centre", "Account", "P&L line", "Amount (€)"]
    if any(h not in head for h in need):
        return False, f"Facts: header {head} lacks {need}", ["Facts header"]
    ix = {h: head.index(h) for h in need}
    as_of, y2 = profile["period"]["as_of"], profile["period"]["as_of"][:4]
    y1 = str(int(y2) - 1)
    shops = [s["name"] for s in profile["shops"]]
    base = [r for r in profile["pl_rows"] if r not in profile["pl_subtotals"]]
    acc = {(k, s, r): 0.0 for k in ("ytd", "ly", "plan") for s in shops for r in base}
    by_month = {}
    items, n_rows = [], 0
    for i, r in enumerate(rows[1:], start=2):
        if all(v is None for v in r):
            continue
        n_rows += 1
        k, ym, s, account, row, v = (r[ix[h]] for h in need)
        ym = str(ym)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            items.append(f"Facts r{i}: amount '{v}' is not a number")
            continue
        if s not in shops or row not in base or k not in ("actual", "plan"):
            items.append(f"Facts r{i}: unknown kind/cost centre/line {k}/{s}/{row}")
            continue
        if resolve_account(str(account), profile["pl_mapping"]) != row:
            items.append(f"Facts r{i}: account {account} does not belong to line {row} per the profile")
            continue
        if ym[:4] not in (y1, y2) or (k == "actual" and ym > as_of) or (k == "plan" and ym[:4] != y2):
            items.append(f"Facts r{i}: month {ym} outside the period ({k})")
            continue
        if ym[:4] == y2:
            by_month[(k, row, ym)] = by_month.get((k, row, ym), 0.0) + float(v)
        if k == "plan":
            acc[("plan", s, row)] += float(v)
        elif ym[:4] == y1:
            acc[("ly", s, row)] += float(v)
        elif ym <= as_of:
            acc[("ytd", s, row)] += float(v)
    if items:
        return False, f"pivot does not tie ({len(items)}): {_fmt_items(items)}", items
    if n_rows == 0:
        return False, "pivot without facts — 0 rows is not a result", ["0 facts"]
    for k in ("ytd", "ly", "plan"):
        for sub, parts in profile["pl_subtotals"].items():
            for s in shops:
                acc[(k, s, sub)] = sum(acc[(k, s, p)] for p in parts)
        for r in profile["pl_rows"]:
            acc[(k, "Total", r)] = sum(acc[(k, s, r)] for s in shops)
    tax = profile.get("board_pack", {}).get("tax_row")
    tax_rows = {r for r, parts in profile["pl_subtotals"].items() if tax in parts} | {tax}
    n = 0
    for s in shops + ["Total"]:
        for r in profile["pl_rows"]:
            n += 1
            if _cents(acc[("ytd", s, r)]) != _cents(ytd[(s, r)]):
                items.append(f"actual YTD {s} · {r}: pivot {acc[('ytd', s, r)]:,.2f} ≠ P&L {ytd[(s, r)]:,.2f}")
            n += 1
            if _cents(acc[("ly", s, r)]) != _cents(bp_rows[(s, r)]["fy_ly"]):
                items.append(f"last year {s} · {r}: pivot {acc[('ly', s, r)]:,.2f} ≠ board pack {bp_rows[(s, r)]['fy_ly']:,.2f}")
            if r in tax_rows:
                continue
            n += 1
            if _cents(acc[("plan", s, r)]) != _cents(bp_rows[(s, r)]["fy_plan"]):
                items.append(f"full-year plan {s} · {r}: pivot {acc[('plan', s, r)]:,.2f} ≠ board pack {bp_rows[(s, r)]['fy_plan']:,.2f}")
    n_piv = 0
    for title, kind in (("Pivot actual", "actual"), ("Pivot plan", "plan")):
        if title not in wb.sheetnames:
            items.append(f"sheet {title} is missing")
            continue
        prow = list(wb[title].iter_rows(values_only=True))
        cols = list(prow[0][1:]) if prow else []
        labels = [r[0] for r in prow[1:] if r[0] is not None]
        if labels != profile["pl_rows"]:            # poradie výsledovky a žiadny riadok dvakrát
            items.append(f"{title}: lines {labels} ≠ P&L of the profile (order, duplicate or extra)")
        seen = set()
        for r in prow[1:]:
            if r[0] is None:
                continue
            seen.add(r[0])
            parts = [r[0]] if r[0] not in profile["pl_subtotals"] else _flat_parts(profile, r[0])
            tot = 0.0
            for c, v in zip(cols, r[1:]):
                n_piv += 1
                if c == "Total":
                    want = tot
                else:
                    want = sum(by_month.get((kind, p, str(c)), 0.0) for p in parts)
                    tot += want
                if not isinstance(v, (int, float)) or isinstance(v, bool) or _cents(float(v)) != _cents(want):
                    items.append(f"{title} {r[0]} {c}: {v} ≠ facts {want:,.2f}")
        missing = [r for r in profile["pl_rows"] if r not in seen]
        if missing:
            items.append(f"{title}: lines missing {missing}")
    if items:
        return False, f"pivot does not tie to the P&L ({len(items)}): {_fmt_items(items)}", items
    return True, (f"pivot == P&L to the cent: {n_rows} facts (account → line per the profile) → {n} cells (actual YTD "
                  f"by cost centre and line, last year and full-year plan vs board pack excluding tax) + {n_piv} cells of the Pivot sheets "
                  f"including Total == facts; read from the finished file"), []


def _flat_parts(profile: dict, row: str) -> list:
    subs = profile["pl_subtotals"]
    return [x for p in subs[row] for x in _flat_parts(profile, p)] if row in subs else [row]


@check("control_panel_readback")
def control_panel_readback(path: Path, panel: dict, results: list):
    """Kontrolný panel z HOTOVÉHO overview.xlsx: každá kontrola behu (results) je na paneli práve raz, v skupine
    profilu, so semaforom = protokol; kontrola bez skupiny = FAIL menovite (panel nesmie kontrolu ticho vynechať);
    riadok s nálezmi má preklik na hárok Chybné riadky, kde je presne toľko riadkov tej kontroly, koľko je nálezov,
    text nálezu = protokol, odkazy (až 3 súbory miesta detekcie) vedú na existujúce súbory dodávky, riadok s kontrolou,
    ktorá nebežala = FAIL; hlavička (firma, obdobie, verdikt) a veta o kontrolách nad hotovým súborom = beh;
    tabuľka zdrojov (súbory, riadky, nečitateľné) = model.
    Vlastný výsledok tejto kontroly na paneli nie je (beží až nad hotovým súborom). Neoveruje farbu výplne (semafor
    je text) ani stĺpec Výsledok iného riadku než kontrol."""
    from openpyxl import load_workbook
    path = Path(path)
    items = []
    if panel["ungrouped"]:
        items.append(f"checks without a group in the profile (control_panel.groups): {', '.join(panel['ungrouped'])}")
    if not path.is_file():
        return False, f"output is missing: {path.name}", items + [f"missing {path.name}"]
    wb = load_workbook(path, data_only=False)
    for sh in ("Control panel", "Failed rows"):
        if sh not in wb.sheetnames:
            items.append(f"sheet {sh} is missing")
    if items:
        return False, f"control panel does not tie ({len(items)}): {_fmt_items(items)}", items
    wp, we = wb["Control panel"], wb["Failed rows"]
    ran = {cid for cid, *_ in results}
    if [c.value for c in wp[3]] != panel["panel_head"] or [c.value for c in we[1]] != panel["err_head"]:
        items.append("headers of the Control panel / Failed rows sheets ≠ contract")
    head = [c.value for c in wp[1]]
    if head[:4] != ["Control panel", panel["company"], f"as of {panel['as_of']}", f"Verdict: {panel['verdict']}"]:
        items.append(f"panel: header {head[:4]} ≠ company / period / verdict of the run ({panel['verdict']})")
    foot = [c.value for row in wp.iter_rows(values_only=False) for c in row[:1] if isinstance(c.value, str) and c.value.startswith("On the finished file")]
    if foot != [panel["footnote"]]:
        items.append("panel: the sentence about the checks on the finished file is missing or changed")
    expected = {r["cid"]: r for r in panel["rows"]}
    got, links = {}, {}
    for row in wp.iter_rows(min_row=4):
        a, g, cid, detail, n, link = (row[i].value if i < len(row) else None for i in range(6))
        if cid in expected and a in _PANEL_LIGHT.values():
            if cid in got:
                items.append(f"panel: check {cid} twice")
            got[cid] = (a, g, detail, n)
            links[cid] = row[5].hyperlink.location if row[5].hyperlink else None
    err_rows = {}
    for i, row in enumerate(we.iter_rows(min_row=2, values_only=False), start=2):
        cid = row[1].value
        if cid is None:
            continue
        if cid not in ran:
            items.append(f"failed rows r{i}: check '{cid}' did not run in this run")
            continue
        err_rows.setdefault(cid, []).append((i, row[2].value, row[3].value, row[4].value,
                                             [row[5 + k].hyperlink.target if row[5 + k].hyperlink else None for k in range(3)]))
        for k in range(3):                      # text odkazu = meno súboru cieľa
            h = row[5 + k].hyperlink.target if row[5 + k].hyperlink else None
            if (h.rsplit("/", 1)[-1] if h else None) != row[5 + k].value:
                items.append(f"failed rows r{i}: link text '{row[5 + k].value}' ≠ target {h}")
    for cid in sorted(ran - {"control_panel_readback"}):
        if cid not in expected:
            if cid not in panel["ungrouped"]:
                items.append(f"check {cid} ran, but the panel model does not have it")
            continue
        r = expected[cid]
        if cid not in got:
            items.append(f"panel: check {cid} is missing")
            continue
        a, g, detail, n = got[cid]
        if a != r["light"] or g != r["group"] or n != r["n"] or detail != r["detail"]:
            items.append(f"panel: {cid} has {a}/{g}/{n} ≠ check log {r['light']}/{r['group']}/{r['n']}")
        rows_c = err_rows.get(cid, [])
        if len(rows_c) != r["n"]:               # aj 0 nálezov = 0 riadkov
            items.append(f"failed rows: {cid} has {len(rows_c)} rows ≠ {r['n']} findings")
        if r["n"]:
            loc = links.get(cid)
            if not loc or not rows_c or loc != f"'Failed rows'!A{rows_c[0][0]}":
                items.append(f"panel: {cid} has no link to its failed rows ({loc})")
    for cid in got:
        if cid not in ran:
            items.append(f"panel: check {cid} is on the panel but did not run")
    want_err = {}
    for x in panel["err"]:
        want_err.setdefault(x["cid"], []).append(x)
    for cid, rows_c in err_rows.items():
        for (i, f, ln, txt, hrefs), x in zip(rows_c, want_err.get(cid, [])):
            want_h = (x["hrefs"] + [None] * 3)[:3]
            if f != x["file"] or ln != x["line"] or hrefs != want_h:
                items.append(f"failed rows r{i}: {f}/{ln}/{hrefs} ≠ model {x['file']}/{x['line']}/{want_h}")
            if txt != x["text"]:
                items.append(f"failed rows r{i}: finding text ≠ check log ('{str(txt)[:50]}')")
            for href in hrefs:
                if href and not (path.parent / href).is_file():
                    items.append(f"failed rows r{i}: the link to file {href} does not lead to an existing file")
    src = {}
    for row in wp.iter_rows(min_row=4, values_only=True):
        if row[0] in {s["label"] for s in panel["sources"]} and isinstance(row[1], (int, float)):
            src[row[0]] = tuple(row[1:6])
    for s in panel["sources"]:
        want = (s["expected"], s["got"], s["rows"], s["bad"], s["light"])
        if src.get(s["label"]) != want:
            items.append(f"sources: {s['label']} {src.get(s['label'])} ≠ model {want}")
    if items:
        return False, f"control panel does not tie ({len(items)}): {_fmt_items(items)}", items
    n_fail = sum(1 for r in panel["rows"] if r["status"] != "PASS")
    return True, (f"panel == check log: {len(got)} checks in {len({r['group'] for r in panel['rows']})} groups, "
                  f"{n_fail} with a status other than PASS, {len(panel['err'])} failed rows with a link, "
                  f"{len(panel['sources'])} sources; read from the finished file"), []
