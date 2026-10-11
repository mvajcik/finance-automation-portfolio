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
        return False, f"neznámy model '{mid}' (motor pozná: {', '.join(sorted(models))})", [f"model {mid}"]
    known, required = models[mid]
    listed = list(profile.get("checks") or [])
    if not listed:
        return False, "profil nevymenoval žiadnu kontrolu — 0 nie je dôkaz", ["checks prázdne"]
    items += [f"povinná kontrola '{r}' v profile chýba" for r in required if r not in listed]
    items += [f"kontrola '{x}' model '{mid}' nepozná" for x in listed if x not in known]
    items += [f"kontrola '{x}' je v profile {listed.count(x)}×" for x in sorted(set(listed)) if listed.count(x) > 1]
    if items:
        return False, f"profil porušil kontrakt modelu '{mid}': {_fmt_items(items)}", items
    return True, f"model '{mid}', {len(listed)} kontrol profilu (povinné: {len(required)}/{len(required)})", []


@check("inputs_contract")
def inputs_contract(files: list, expected: list, header_issues: tuple = ()):
    """Dodávka = presne očakávané súbory profilu (menovite chýba / navyše) a každý
    má hlavičku podľa profilu. Prázdny zoznam očakávaných = FAIL (0 nie je dôkaz)."""
    if not expected:
        return False, "profil neočakáva žiadny súbor — 0 nie je dôkaz", ["kontrakt prázdny"]
    got, want = set(files), set(expected)
    items = [f"chýba súbor {f}" for f in sorted(want - got)] + \
            [f"navyše súbor {f}" for f in sorted(got - want)] + list(header_issues)
    if items:
        return False, f"dodávka nesedí s kontraktom: {_fmt_items(items)}", items
    return True, f"dodávka = kontrakt ({len(want)} súborov)", []


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
            "SELECT file, line, 'trzba', amount_txt FROM pos_raw ORDER BY file, line").fetchall():
        if val is None or not _POS_AMOUNT_RE.fullmatch(val):
            items.append(f"{f} r{line} {col}='{val}'")
    # dátum: platný a v mesiaci, ktorý nesie meno súboru
    for f, line, val, ok in con.execute(
            "SELECT file, line, date_txt, strftime(CAST(try_strptime(date_txt, '%d.%m.%Y') AS DATE), '%Y-%m') "
            "= regexp_extract(file, '([0-9]{4}-[0-9]{2})', 1) FROM pos_raw ORDER BY file, line").fetchall():
        if not ok:
            items.append(f"{f} r{line} datum='{val}' (neplatný alebo mimo mesiaca súboru)")
    # predvaha: účet = 3 číslice, stredisko vyplnené, obdobie = mesiac súboru (prázdny
    # účet, ' 518' alebo obdobie iného mesiaca by inak vypadli z výpočtu aj z kontroly)
    for f, line, ym, cc, acc in con.execute(
            "SELECT file, line, ym, cc, account FROM gl_raw WHERE NOT ("
            "regexp_full_match(coalesce(account, ''), ?) "
            "AND coalesce(cc, 'None') NOT IN ('', 'None') "
            "AND ym = regexp_extract(file, '([0-9]{4}-[0-9]{2})', 1)) ORDER BY file, line",
            [account_pattern]).fetchall():
        items.append(f"{f} r{line} riadok predvahy mimo kontraktu (obdobie='{ym}', stredisko='{cc}', účet='{acc}')")
    for f, line, col, val, isnum in con.execute(
            "SELECT file, line, col, raw, is_num FROM gl_cells UNION ALL "
            "SELECT file, line, col, raw, is_num FROM plan_cells ORDER BY 1, 2").fetchall():
        if not isnum:
            items.append(f"{f} r{line} {col}='{val}' (text, nie číslo)")
    n = con.execute("SELECT (SELECT count(*) FROM pos_raw) + (SELECT count(*) FROM gl_cells)"
                    " + (SELECT count(*) FROM plan_cells)").fetchone()[0]
    if n == 0:
        return False, "žiadna suma na kontrolu — 0 nie je dôkaz", ["0 súm"]
    if items:
        return False, f"{len(items)} súm nie je číslo v dohodnutom tvare: {_fmt_items(items)}", items
    return True, f"{n:,} súm je číslo v dohodnutom tvare", []


def _gl_duplicate_items(con, mapping: dict = None) -> list:
    """Duplicity predvahy (spoločné pre všetky modely): kľúč mesiac × stredisko × účet,
    syntetický účet aj jeho analytika, zhodné MD/D dvoch účtov jedného riadku."""
    gl_dup = con.execute(
        "SELECT ym, cc, account, count(*) FROM gl GROUP BY 1, 2, 3 HAVING count(*) > 1 "
        "ORDER BY 1, 2, 3").fetchall()
    items = [f"predvaha: {ym} {cc} účet {acc}: {n}× (čakaný 1×)" for ym, cc, acc, n in gl_dup]
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
    items += [f"predvaha: {ym} {cc} účet {s} aj jeho analytika {an} — dvojité zaúčtovanie"
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
                items.append(f"predvaha: {ym} {cc} účty {seen[k]} a {acc} (riadok {row}) majú zhodné "
                             f"MD {md:,.2f} / D {dal:,.2f} — podozrenie na dvakrát nahratý riadok")
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
        return False, "v účtovníctve nie je žiadny výnosový/nákladový účet — 0 nie je dôkaz", ["0 účtov"]
    items = []
    for a in in_scope:
        if resolve_account(a, mapping) is None:
            amt = con.execute("SELECT sum(debit) + sum(credit) FROM gl WHERE account = ?", [a]).fetchone()[0]
            items.append(f"účet {a} nezaradený do výsledovky (obrat {amt or 0:,.2f} €)")
    if items:
        return False, f"nezaradené účty: {_fmt_items(items)}", items
    return True, f"{len(in_scope)} výnosových/nákladových účtov zaradených do výsledovky", []


@check("pl_control_total")
def pl_control_total(con, reported: dict, control_totals: dict, year: str, as_of: str,
                     tol: float = 0.01, required: tuple = (), full: list | None = None):
    """Každý kontrolný súčet výsledovky (EBITDA, Hrubá marža …), ktorý ide boardu,
    == priamo z predvahy: sum(Obrat D − Obrat MD) cez účty, ktoré do neho podľa
    ÚČTOVEJ POLITIKY profilu patria (`control_totals`: predpony účtov). Nepoužíva
    prevodník účet → riadok ani skladbu subtotalov výpočtu (inak by prešla
    Hrubá marža = len Tržby alebo odpisy/úroky vnútri EBITDA)."""
    if not control_totals:
        return False, "profil nemá kontrolné súčty — 0 nie je dôkaz", ["control_totals prázdne"]
    items, ok_txt = [], []
    for name in required:           # subtotal bez kontrolného súčtu = FAIL
        if name not in control_totals:
            items.append(f"{name}: ide boardu, ale v profile nemá kontrolný súčet (control_totals)")
    for name, prefixes in control_totals.items():
        got = reported.get(name)
        if got is None or not prefixes:
            items.append(f"{name}: vykázaná hodnota alebo politika účtov chýba")
            continue
        cond = " OR ".join(["account LIKE ?"] * len(prefixes))
        src = con.execute(f"SELECT sum(credit - debit) FROM gl WHERE ({cond}) AND ym LIKE ? AND ym <= ?",
                          [f"{p}%" for p in prefixes] + [f"{year}-%", as_of]).fetchone()[0]
        if src is None:
            items.append(f"{name}: predvaha za YTD bez účtov {prefixes}")
        elif abs(got - src) > tol:
            # do súboru len smer — suma = číslo boardu, pri NESEDÍ sa nevydáva; plné hodnoty len na obrazovku (`full`)
            items.append(f"{name}: vykázaná ≠ predvaha ({'vyššia' if got > src else 'nižšia'} ako predvaha)")
            if full is not None:
                full.append(f"{name}: vykázaná {got:,.2f} € ≠ predvaha {src:,.2f} € (rozdiel {got - src:+,.2f} €)")
        else:
            ok_txt.append(name)     # bez sumy: čísla boardu len v Prehľade a len pri SEDÍ
    if items:
        return False, f"kontrolné súčty nesedia: {_fmt_items(items)}", items
    return True, (f"vykázané súčty == predvaha podľa účtovej politiky profilu na cent: {', '.join(ok_txt)} "
                  f"(sumy sú v Prehľade, pri NESEDÍ sa nevydávajú)"), []


# ---------------------------------------------------------------- model retail_full: 9 zdrojov
# Kontroly pracujú nad SQL vrstvou (sql/<firma>/10_stg.sql …): stg_* = typované tabuľky, v ktorých SQL
# samo vyhlási nečitateľné polia do stĺpca `bad`. Každá kontrola páruje DVA nezávislé zdroje
# (iný systém, iný súbor) a pri nesúlade menuje súbor · riadok / deň · stredisko · účet.
def _money(v) -> str:
    return f"{float(v or 0):,.2f} €"


def _fmt_num(v) -> str:
    """Číslo na obrazovku bez artefaktov float (103794.72999999994 → 103,794.73); text ostane textom."""
    return f"{v:,.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def _day(d) -> str:
    """Dátum pre správu; nečitateľný dátum (NULL) sa nesmie stratiť — menuje ho stg_parse_contract."""
    return d.strftime("%d.%m.%Y") if d is not None else "nečitateľný dátum"


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
            items.append(f"{t}: 0 riadkov — 0 nie je dôkaz")
            continue
        for f, ln, bad in con.execute(f"SELECT file, line, bad FROM {t} WHERE coalesce(bad, '') <> '' ORDER BY 1, 2").fetchall():
            items.append(f"{f} r{ln}: nečitateľné {bad}")
    if items:
        return False, f"{len(items)} riadkov zdrojov sa nedalo prečítať: {_fmt_items(items)}", items
    return True, f"{n:,} riadkov z {len(tables)} tabuliek zdrojov prečítaných bez straty", []


@check("full_duplicate_keys")
def full_duplicate_keys(con, mapping: dict = None):
    """Nič nie je nahraté dvakrát: bloček len v jednom súbore a dni, riadok denníka ani bankový pohyb
    presne dvakrát, číslo faktúry a zamestnanec × mesiac raz; predvaha ako všade (mesiac × stredisko ×
    účet, syntetika aj analytika, zhodné MD/D)."""
    items = []
    q = {"bloček v 2 súboroch/dňoch": "SELECT doklad, count(DISTINCT file || day) FROM stg_pos GROUP BY 1 HAVING count(DISTINCT file || day) > 1",
         "riadok denníka 2×": "SELECT doklad || ' ' || md || '/' || d || ' ' || amount || ' ' || cc || ' ' || text, count(*) FROM stg_journal GROUP BY 1 HAVING count(*) > 1",
         "faktúra 2×": "SELECT invoice, count(*) FROM stg_invoices GROUP BY 1 HAVING count(*) > 1",
         "mzda 2×": "SELECT employee || ' ' || ym, count(*) FROM stg_payroll GROUP BY 1 HAVING count(*) > 1",
         "bankový pohyb 2×": "SELECT strftime(day, '%d.%m.%Y') || ' ' || counterparty || ' ' || amount || ' ' || text, count(*) FROM stg_bank GROUP BY 1 HAVING count(*) > 1"}
    for label, sql in q.items():
        items += [f"{label}: {k} ({n}×)" for k, n in con.execute(sql + " ORDER BY 1").fetchall()]
    items += _gl_duplicate_items(con, mapping)
    n = con.execute("SELECT (SELECT count(*) FROM stg_pos) + (SELECT count(*) FROM stg_journal)").fetchone()[0]
    if n == 0:
        return False, "pokladňa aj denník sú prázdne — 0 nie je dôkaz", ["prázdny zdroj"]
    if items:
        return False, f"duplicity: {_fmt_items(items)}", items
    return True, "bločky, denník, faktúry, mzdy, banka aj predvaha bez duplicít", []


@check("full_coverage")
def full_coverage(con, shops: list, months: list, pos_ccs: list):
    """Každý mesiac obdobia má denník, predvahu, banku, mzdy a faktúry; každá predajňa má pokladňu v
    každom mesiaci. Stredisko, ktoré nie je v zozname firmy (profil), = cudzie dáta = FAIL."""
    if not shops or not months:
        return False, "profil nemá strediská alebo obdobie — 0 nie je dôkaz", ["profil prázdny"]
    ccs = {s["cost_center"] for s in shops}
    items = []
    for label, sql in (("denník", "SELECT DISTINCT ym FROM stg_journal"), ("predvaha", "SELECT DISTINCT ym FROM gl"),
                       ("banka", "SELECT DISTINCT ym FROM stg_bank_meta"), ("mzdy", "SELECT DISTINCT ym FROM stg_payroll"),
                       ("faktúry", "SELECT DISTINCT ym FROM stg_invoices"),
                       ("sklad pohyby", "SELECT DISTINCT ym FROM stg_stock_moves"),
                       ("sklad stav", "SELECT DISTINCT ym FROM stg_stock_state")):
        have = {r[0] for r in con.execute(sql).fetchall()}
        items += [f"{label}: {ym} bez dát" for ym in months if ym not in have]
    have = {tuple(r) for r in con.execute("SELECT DISTINCT cc, strftime(day, '%Y-%m') FROM stg_pos").fetchall()}
    items += [f"pokladňa: {cc} {ym} bez dát" for cc in pos_ccs for ym in months if (cc, ym) not in have]
    for label, sql in (("denník", "SELECT DISTINCT cc FROM stg_journal"), ("pokladňa", "SELECT DISTINCT cc FROM stg_pos"),
                       ("mzdy", "SELECT DISTINCT cc FROM stg_payroll"), ("faktúry", "SELECT DISTINCT cc FROM stg_invoices"),
                       ("predvaha", "SELECT DISTINCT cc FROM gl")):
        items += [f"{label}: neznáme stredisko '{c}'" for (c,) in con.execute(sql).fetchall() if c not in ccs]
    if items:
        return False, f"pokrytie nesedí: {_fmt_items(items)}", items
    return True, f"{len(months)} mesiacov × 7 zdrojov a {len(pos_ccs)} pokladne × {len(months)} mesiacov bez medzery", []


@check("pos_control_total")
def pos_control_total(con, tol: float = 0.01):
    """Export pokladne je celý: riadok SPOLU v každom súbore == súčet jeho bločkov (orezaný alebo
    ručne doplnený export sa prezradí). Súbor bez riadku SPOLU = FAIL."""
    rows = con.execute("""SELECT f.file, f.total, (SELECT sum(gross) FROM stg_pos p WHERE p.file = f.file) FROM stg_pos_footer f
                          ORDER BY 1""").fetchall()
    if not rows:
        return False, "žiadny súbor pokladne s riadkom SPOLU — 0 nie je dôkaz", ["0 súborov"]
    items = [f"{f}: SPOLU chýba" if t is None else f"{f}: SPOLU {_money(t)} ≠ bločky {_money(s)} (rozdiel {float((s or 0) - t):+,.2f} €)"
             for f, t, s in rows if t is None or abs(float((s or 0) - t)) > tol]
    if items:
        return False, f"export pokladne nie je celý: {_fmt_items(items)}", items
    return True, f"{len(rows)} exportov pokladne: SPOLU == súčet bločkov", []


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
        return False, "denník aj predvaha prázdne — 0 nie je dôkaz", ["0 riadkov"]
    items = [f"{ym} {cc} účet {a}: denník MD {_money(jm)} / D {_money(jd)} ≠ predvaha MD {_money(tm)} / D {_money(td)}"
             for ym, cc, a, jm, tm, jd, td in rows if abs(float(jm) - float(tm)) > tol or abs(float(jd) - float(td)) > tol]
    if items:
        return False, f"denník ≠ predvaha ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows):,} obratov mesiac × stredisko × účet: denník == predvaha na cent", []


@check("pos_gl_match")
def pos_gl_match(con, tol: float = 0.01):
    """Pokladňa == účtovníctvo po predajni a dni (pokladničný softvér vs. denník): (a) súčet bločkov s DPH
    podľa spôsobu platby == zápisy 211 (hotovosť) / 315 (karta) proti 604 + 343; (b) tržby bez DPH z bločkov
    (po sadzbách) == celý účet 604 (D − MD) — zápis tržieb bez pokladne alebo presun z DPH do tržieb = FAIL."""
    a = con.execute("""
        WITH p AS (SELECT cc, day, payment, sum(gross) AS g FROM stg_pos GROUP BY 1, 2, 3),
             j AS (SELECT cc, day, CASE md WHEN '211' THEN 'H' ELSE 'K' END AS payment, sum(amount) AS g
                   FROM stg_journal WHERE md IN ('211', '315') AND d IN ('604', '343') GROUP BY 1, 2, 3)
        SELECT coalesce(p.cc, j.cc), coalesce(p.day, j.day), coalesce(p.payment, j.payment), coalesce(p.g, 0), coalesce(j.g, 0)
        FROM p FULL JOIN j ON p.cc = j.cc AND p.day = j.day AND p.payment = j.payment ORDER BY 1, 2, 3""").fetchall()
    b = con.execute("""
        WITH p AS (SELECT cc, day, sum(net) AS n FROM (
                     SELECT cc, day, round(CAST(sum(gross) AS DOUBLE) / (1 + vat_rate / 100.0), 2) AS net
                     FROM stg_pos GROUP BY cc, day, payment, vat_rate) GROUP BY 1, 2),
             j AS (SELECT cc, day, sum(CASE WHEN d = '604' THEN amount ELSE -amount END) AS n
                   FROM stg_journal WHERE (d = '604' OR md = '604') AND doklad NOT LIKE 'PS%' GROUP BY 1, 2)
        SELECT coalesce(p.cc, j.cc), coalesce(p.day, j.day), coalesce(p.n, 0), coalesce(j.n, 0)
        FROM p FULL JOIN j ON p.cc = j.cc AND p.day = j.day ORDER BY 1, 2""").fetchall()
    if not a:
        return False, "žiadna tržba — 0 nie je dôkaz", ["0 dní"]
    items = [f"{cc} {_day(d)} {'hotovosť' if pay == 'H' else 'karta'}: pokladňa {_money(p)} ≠ účtovníctvo {_money(j)} "
             f"(rozdiel {float(p - j):+,.2f} €)" for cc, d, pay, p, j in a if abs(float(p - j)) > tol]
    items += [f"{cc} {_day(d)}: tržby bez DPH z bločkov {_money(p)} ≠ účet 604 {_money(j)} (rozdiel {float(p) - float(j):+,.2f} €)"
              for cc, d, p, j in b if abs(float(p) - float(j)) > 0.05]        # zaokrúhlenie DPH po sadzbách a platbe
    if items:
        return False, f"pokladňa ↔ účtovníctvo nesedí ({len(items)}): {_fmt_items(items)}", items
    return True, (f"{len(b):,} predajných dní × predajňa: bločky == 211/315 po spôsobe platby a tržby bez DPH == celý účet 604"), []

@check("bank_balance")
def bank_balance(con, tol: float = 0.01):
    """Bankový výpis je celý: počiatočný zostatok + pohyby == konečný zostatok v každom výpise a
    konečný zostatok mesiaca == počiatočný zostatok nasledujúceho (vynechaný pohyb sa prezradí)."""
    rows = con.execute("""SELECT m.file, m.ym, m.opening, m.closing, coalesce((SELECT sum(amount) FROM stg_bank b WHERE b.file = m.file), 0)
                          FROM stg_bank_meta m ORDER BY m.ym""").fetchall()
    if not rows:
        return False, "žiadny výpis — 0 nie je dôkaz", ["0 výpisov"]
    items = []
    for i, (f, ym, op, cl, s) in enumerate(rows):
        if op is None or cl is None:
            items.append(f"{f}: chýba zostatok")
            continue
        if abs(float(op + s - cl)) > tol:
            items.append(f"{f}: počiatočný {_money(op)} + pohyby {_money(s)} ≠ konečný {_money(cl)}")
        if i and rows[i - 1][3] is not None and abs(float(rows[i - 1][3] - op)) > tol:
            items.append(f"{f}: počiatočný {_money(op)} ≠ konečný predchádzajúceho výpisu {_money(rows[i - 1][3])}")
    if items:
        return False, f"bankové výpisy nie sú celé: {_fmt_items(items)}", items
    return True, f"{len(rows)} výpisov: zostatky nadväzujú a sedia s pohybmi", []


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
        return False, "žiadny bankový pohyb — 0 nie je dôkaz", ["0 dní"]
    items = []
    for d, b, j in rows:
        if abs(float(b - j)) <= tol:
            continue
        items.append(f"{_day(d)}: banka {_money(b)} ≠ účet 221 {_money(j)} (rozdiel {float(b - j):+,.2f} €)")
        bank = [float(x[0]) for x in con.execute("SELECT amount FROM stg_bank WHERE day = ?", [d]).fetchall()]
        for doc, cc, text, v in con.execute(
                "SELECT doklad, cc, text, CASE WHEN md = '221' THEN amount ELSE -amount END FROM stg_journal "
                "WHERE day = ? AND (md = '221' OR d = '221') AND doklad NOT LIKE 'PS%' ORDER BY 1", [d]).fetchall():
            if float(v) in bank:
                bank.remove(float(v))
            else:
                items.append(f"  {_day(d)}: v denníku {doc} {cc} „{text}\" {_money(v)} — v banke chýba")
        items += [f"  {_day(d)}: v banke {_money(v)} — v denníku chýba" for v in bank]
    if items:
        return False, f"banka ↔ účtovníctvo nesedí: {_fmt_items(items)}", items
    return True, f"{len(rows)} bankových dní: výpis == účet 221 na cent", []

@check("bank_ap_match")
def bank_ap_match(con, internal: list, direct_pl_allowed: list):
    """Každý pohyb v banke má podklad: úhrada faktúry z knihy (VS = číslo faktúry, IČO protistrany = IČO
    faktúry a v číselníku, suma = faktúra), alebo menovitá interná platba z profilu (karty, vklad hotovosti,
    mzdy, odvody, úver, DPH, daň, dividenda). Iný pohyb = FAIL. Náklad či výnos zaúčtovaný priamo proti banke
    (bez faktúry) = FAIL, okrem účtov povolených profilom (úroky)."""
    rows = con.execute("""
        SELECT b.file, b.line, b.day, b.counterparty, b.vs, b.amount, right(b.iban, 8),
               i.invoice, i.ico, i.total,
               EXISTS (SELECT 1 FROM raw_dims d WHERE d.sheet = 'Dodávatelia' AND d.k = right(b.iban, 8))
        FROM stg_bank b LEFT JOIN stg_invoices i ON regexp_replace(i.invoice, '[^0-9]', '', 'g') = b.vs
        ORDER BY b.day, b.line""").fetchall()
    if not rows:
        return False, "žiadny bankový pohyb — 0 nie je dôkaz", ["0 pohybov"]
    items, n_inv, n_int = [], 0, 0
    for f, ln, d, who, vs, amt, ico, inv, inv_ico, total, known in rows:
        if any((who or "").startswith(x["counterparty_prefix"]) for x in internal):
            n_int += 1
            continue
        if inv is None:
            items.append(f"{f} r{ln} {_day(d)}: {who} {_money(amt)} (VS {vs}) — bez faktúry v knihe a nie je interná platba")
            continue
        n_inv += 1
        if ico != inv_ico or not known:
            items.append(f"{f} r{ln}: úhrada faktúry {inv} na IČO {ico}, faktúra má IČO {inv_ico}"
                         + ("" if known else " (dodávateľ nie je v číselníku)"))
        if abs(float(-amt) - float(total)) > 0.005:
            items.append(f"{f} r{ln}: úhrada {_money(-amt)} ≠ faktúra {inv} {_money(total)}")
    for doc, d, md, dd, v, cc, text in con.execute(
            "SELECT doklad, day, md, d, amount, cc, text FROM stg_journal WHERE doklad NOT LIKE 'PS%' AND "
            "((d = '221' AND substr(md, 1, 1) IN ('5', '6')) OR (md = '221' AND substr(d, 1, 1) IN ('5', '6'))) ORDER BY 2, 1").fetchall():
        acc = md if dd == "221" else dd
        if not any(acc.startswith(a) for a in direct_pl_allowed):
            items.append(f"denník {doc} {_day(d)} {cc}: účet {acc} priamo proti banke {_money(v)} „{text}\" — bez faktúry")
    if items:
        return False, f"pohyby bez podkladu ({len(items)}): {_fmt_items(items)}", items
    return True, f"{n_inv:,} úhrad faktúr (VS, IČO, suma) a {n_int:,} menovitých interných platieb — žiadny pohyb bez podkladu", []

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
        return False, "žiadne mzdy — 0 nie je dôkaz", ["0 miezd"]
    items = []
    for ym, cc, pg, jg, pe, je in rows:
        if abs(float(pg - jg)) > tol:
            items.append(f"{ym} {cc}: hrubé mzdy {_money(pg)} ≠ 521 {_money(jg)} (rozdiel {float(pg - jg):+,.2f} €)")
        if abs(float(pe - je)) > tol:
            items.append(f"{ym} {cc}: odvody {_money(pe)} ≠ 524 {_money(je)}")
    if items:
        return False, f"mzdy ↔ účtovníctvo nesedí: {_fmt_items(items)}", items
    return True, f"{len(rows)} stredísk × mesiacov: mzdy == 521 a 524 (MD − D) na cent", []

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
        return False, "žiadna faktúra — 0 nie je dôkaz", ["0 faktúr"]
    items = []
    for no, f, ln, it, jt, ib, jb, ia, ja, icc, jcc, iym, jym in rows:
        if jt is None:
            items.append(f"{f} r{ln}: faktúra {no} ({_money(it)}) nie je zaúčtovaná v denníku")
        elif it is None:
            items.append(f"denník: doklad {no} ({_money(jt)}) nemá faktúru v knihe")
        else:
            if abs(float(it - jt)) > tol or abs(float((ib or 0) - (jb or 0))) > tol or ia != ja:
                items.append(f"faktúra {no}: kniha {ia} {_money(ib)} / {_money(it)} ≠ denník {ja} {_money(jb)} / {_money(jt)}")
            if icc != jcc:
                items.append(f"faktúra {no}: stredisko v knihe {icc} ≠ v denníku {jcc}")
            if iym != jym:
                items.append(f"faktúra {no}: mesiac faktúry {iym} ≠ zaúčtované v {jym}")
    if items:
        return False, f"faktúry ↔ denník nesedí ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows):,} faktúr zaúčtovaných pod svojím číslom na správnom účte, stredisku, mesiaci a sume", []

@check("stock_consistency")
def stock_consistency(con, tol: float = 0.01):
    """Sklad je konzistentný: žiadna záporná zásoba; stav = počiatočný + príjem − výdaj; počiatočný stav
    mesiaca == konečný predchádzajúceho; príjem a výdaj v stave == súčet pohybov; príjem == účet 132 (MD)
    a výdaj == predaný tovar 504 (MD − D) po stredisku a mesiaci — aj stredisko bez skladu (centrála)."""
    items = []
    for f, cc, cat, cl in con.execute("SELECT file, cc, category, closing FROM stg_stock_state WHERE closing < 0 ORDER BY 1").fetchall():
        items.append(f"{f}: záporná zásoba {cc} {cat} {_money(cl)}")
    for f, cc, cat in con.execute("""SELECT file, cc, category FROM stg_stock_state
                                     WHERE abs(opening + received - issued - closing) > 0.005 ORDER BY 1""").fetchall():
        items.append(f"{f}: {cc} {cat} stav ≠ počiatočný + príjem − výdaj")
    for f, cc, cat, op, prev in con.execute("""
            SELECT s.file, s.cc, s.category, s.opening, p.closing FROM stg_stock_state s JOIN stg_stock_state p
            ON p.cc = s.cc AND p.category = s.category
            AND p.ym = strftime(CAST(s.ym || '-01' AS DATE) - INTERVAL 1 MONTH, '%Y-%m')
            WHERE abs(s.opening - p.closing) > 0.005 ORDER BY 1""").fetchall():
        items.append(f"{f}: {cc} {cat} počiatočný {_money(op)} ≠ konečný minulého mesiaca {_money(prev)}")
    for f, cc, cat, sr, si, mr, mi in con.execute("""
            WITH mv AS (SELECT ym, cc, category, sum(value) FILTER (WHERE kind = 'príjem') AS r,
                               sum(value) FILTER (WHERE kind = 'výdaj') AS i FROM stg_stock_moves GROUP BY 1, 2, 3)
            SELECT s.file, s.cc, s.category, s.received, s.issued, coalesce(mv.r, 0), coalesce(mv.i, 0)
            FROM stg_stock_state s LEFT JOIN mv USING (ym, cc, category)
            WHERE abs(s.received - coalesce(mv.r, 0)) > 0.005 OR abs(s.issued - coalesce(mv.i, 0)) > 0.005 ORDER BY 1""").fetchall():
        items.append(f"{f}: {cc} {cat} stav príjem/výdaj {_money(sr)}/{_money(si)} ≠ pohyby {_money(mr)}/{_money(mi)}")
    rows = con.execute("""
        WITH mv AS (SELECT ym, cc, sum(value) FILTER (WHERE kind = 'príjem') AS r, sum(value) FILTER (WHERE kind = 'výdaj') AS i
                    FROM stg_stock_moves GROUP BY 1, 2),
             j AS (SELECT ym, cc, sum(CASE WHEN md = '132' THEN amount WHEN d = '132' AND md <> '504' THEN -amount ELSE 0 END)
                                  FILTER (WHERE doklad NOT LIKE 'PS%') AS r,
                          sum(CASE WHEN md = '504' THEN amount WHEN d = '504' THEN -amount ELSE 0 END) AS i
                   FROM stg_journal WHERE md IN ('132', '504') OR d IN ('132', '504') GROUP BY 1, 2)
        SELECT coalesce(mv.ym, j.ym), coalesce(mv.cc, j.cc), coalesce(mv.r, 0), coalesce(j.r, 0), coalesce(mv.i, 0), coalesce(j.i, 0)
        FROM mv FULL JOIN j ON mv.ym = j.ym AND mv.cc = j.cc ORDER BY 1, 2""").fetchall()
    if not rows:
        return False, "žiadny pohyb skladu — 0 nie je dôkaz", ["0 pohybov"]
    for ym, cc, mr, jr, mi, ji in rows:
        if abs(float(mr - jr)) > tol:
            items.append(f"{ym} {cc}: príjem skladu {_money(mr)} ≠ 132 {_money(jr)}")
        if abs(float(mi - ji)) > tol:
            items.append(f"{ym} {cc}: výdaj skladu {_money(mi)} ≠ predaný tovar 504 {_money(ji)}")
    if items:
        return False, f"sklad nesedí ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows)} stredísk × mesiacov: zásoby nezáporné a nadväzujú, stav == pohyby, príjem == 132, výdaj == 504", []


@check("posting_policy")
def posting_policy(con, policy: list):
    """Predkontácie: každý riadok denníka zodpovedá povolenej kombinácii
    typ dokladu × MD × D z účtovej politiky profilu. Náklad cez medziúčet bez dokladu (518/379,
    501/211, 518/331) inak prejde všetkými párovaniami zdroj ↔ zdroj — tu padne menovite."""
    if not policy:
        return False, "profil nemá účtovú politiku predkontácií — 0 nie je dôkaz", ["posting_policy prázdne"]
    con.execute("CREATE OR REPLACE TEMP TABLE _policy (doc VARCHAR, md VARCHAR, d VARCHAR)")
    con.executemany("INSERT INTO _policy VALUES (?, ?, ?)", [tuple(p) for p in policy])
    rows = con.execute("""
        SELECT j.file, j.line, j.doklad, j.md, j.d, j.amount, j.cc
        FROM stg_journal j LEFT JOIN _policy p
          ON p.doc = regexp_extract(j.doklad, '^[A-Z]+') AND p.md = j.md AND p.d = j.d
        WHERE p.doc IS NULL ORDER BY j.file, j.line""").fetchall()
    total = con.execute("SELECT count(*) FROM stg_journal").fetchone()[0]
    if not total:
        return False, "prázdny denník — 0 nie je dôkaz", ["0 riadkov denníka"]
    items = [f"{f} r{ln}: {doc} {md}/{d} {_money(a)} {cc} — predkontácia nie je v účtovej politike"
             for f, ln, doc, md, d, a, cc in rows]
    if items:
        return False, f"zápisy mimo účtovej politiky ({len(items)}): {_fmt_items(items)}", items
    return True, f"{total:,} riadkov denníka: každý na povolenej predkontácii ({len(policy)} vzorov z profilu)", []


@check("liability_settlement")
def liability_settlement(con, accounts: dict, tol: float = 0.01):
    """Úhrady záväzkov: úhrada z banky na účet záväzku (331 mzdy, 336 odvody,
    342 daň zo mzdy, 341 preddavky dane, 343 DPH) v mesiaci == záväzok predchádzajúceho mesiaca; kladný
    záväzok bez úhrady = FAIL. Pravidlo z profilu: 'accrual' = pohyb účtu mimo banky za predchádzajúci mesiac
    (záporný → 0, preplatok sa neprenáša), 'balance' = zostatok ku koncu predchádzajúceho mesiaca (s prenosom
    nároku, DPH). Rozsah: po stredisku ('cc') alebo za firmu ('company')."""
    if not accounts:
        return False, "profil nemá účty záväzkov na úhradu — 0 nie je dôkaz", ["settlement_accounts prázdne"]
    months = [r[0] for r in con.execute("SELECT DISTINCT ym FROM stg_journal WHERE ym IS NOT NULL ORDER BY 1").fetchall()]
    items, n = [], 0
    for acc, rule in accounts.items():
        key = "cc" if rule["scope"] == "cc" else "'firma'"
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
                        what = "zostatok ku koncu" if rule["rule"] == "balance" else "záväzok za"
                        items.append(f"{ym} {k} účet {acc}: úhrada v banke {_money(paid)} ≠ {what} "
                                     f"predchádzajúceho mesiaca {_money(due)}")
                bal += accr - paid
                prev = accr
    if not n and not items:
        return False, "žiadna úhrada záväzku — 0 nie je dôkaz", ["0 úhrad"]
    if items:
        return False, f"úhrady záväzkov nesedia ({len(items)}): {_fmt_items(items)}", items
    return True, f"{n} úhrad záväzkov ({', '.join(accounts)}) == záväzok predchádzajúceho mesiaca", []


@check("card_settlement")
def card_settlement(con, tol: float = 0.01):
    """Zúčtovanie kariet: poplatok za karty 568 po predajni a mesiaci == tržby kartou
    z pokladne za zúčtované dni − pripísané bankou; zostatok 315 == tržby kartou, ktoré banka ešte nepripísala.
    Poplatok ani odpis pohľadávky sa nedá pridať bez stopy v banke a pokladni."""
    rows = con.execute("""
        WITH pos AS (SELECT cc, day, sum(gross) AS g FROM stg_pos WHERE payment = 'K' GROUP BY 1, 2),
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
        return False, "žiadne zúčtovanie kariet — 0 nie je dôkaz", ["0 zúčtovaní"]
    items = [f"{ym} {cc}: poplatok 568 {_money(jf)} ≠ tržby kartou − pripísané bankou {_money(pf)} "
             f"(rozdiel {float(jf - pf):+,.2f} €)" for cc, ym, pf, jf in rows if abs(float(pf - jf)) > tol]
    open_ = con.execute("""
        WITH pos AS (SELECT cc, day, sum(gross) AS g FROM stg_pos WHERE payment = 'K' GROUP BY 1, 2),
             st AS (SELECT DISTINCT regexp_extract(text, '^Settlement (\\S+) ', 1) AS cc,
                           CAST(try_strptime(regexp_extract(text, '(\\d{2}\\.\\d{2}\\.\\d{4})$', 1), '%d.%m.%Y') AS DATE) AS sale
                    FROM stg_bank WHERE text LIKE 'Settlement %'),
             un AS (SELECT pos.cc, sum(pos.g) AS g FROM pos LEFT JOIN st ON st.cc = pos.cc AND st.sale = pos.day
                    WHERE st.cc IS NULL GROUP BY 1),
             b AS (SELECT cc, sum(CASE WHEN md = '315' THEN amount ELSE -amount END) AS bal
                   FROM stg_journal WHERE md = '315' OR d = '315' GROUP BY 1)
        SELECT coalesce(b.cc, un.cc), coalesce(un.g, 0), coalesce(b.bal, 0)
        FROM b FULL JOIN un ON b.cc = un.cc ORDER BY 1""").fetchall()
    items += [f"{cc}: zostatok 315 {_money(bal)} ≠ tržby kartou, ktoré banka ešte nepripísala {_money(g)}"
              for cc, g, bal in open_ if abs(float(g - bal)) > tol]
    if items:
        return False, f"zúčtovanie kariet nesedí ({len(items)}): {_fmt_items(items)}", items
    return True, (f"{len(rows)} predajní × mesiacov: poplatok 568 == tržby kartou − pripísané bankou; "
                  f"zostatok 315 == nepripísané tržby"), []


@check("loan_schedule")
def loan_schedule(con, loan: dict, tol: float = 0.01):
    """Úver podľa zmluvy: úrok 562 v mesiaci == zostatok úveru na začiatku mesiaca ×
    ročná sadzba / 12 a splátka istiny == mesačná splátka zo zmluvy (údaje zmluvy v profile, nie z generátora)."""
    if not loan:
        return False, "profil nemá úverovú zmluvu — 0 nie je dôkaz", ["loan_contract prázdne"]
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
        return False, "žiadny pohyb úveru — 0 nie je dôkaz", ["0 pohybov"]
    items, bal = [], opening
    for ym, net, repaid, interest in rows:
        exp_i = round(bal * loan["rate_pa"] / 12, 2)
        if abs(float(interest) - exp_i) > tol:
            items.append(f"{ym}: úrok {ia} {_money(interest)} ≠ zmluva {_money(exp_i)} "
                         f"(zostatok {_money(bal)} × {loan['rate_pa'] * 100:.2f} % / 12)")
        due = min(loan["monthly_repayment"], bal) if bal > tol else 0.0     # posledná splátka = zvyšok
        if abs(float(repaid) - due) > tol:
            items.append(f"{ym}: splátka istiny {_money(repaid)} ≠ zmluva {_money(due)}")
        bal += float(net)
    if items:
        return False, f"úver nesedí so zmluvou ({len(items)}): {_fmt_items(items)}", items
    return True, f"{len(rows)} mesiacov: úrok == zostatok × sadzba / 12 a splátka == zmluva", []


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
        t.update({("Spolu", r): sum(t[(s, r)] for s in shops) for r in profile["pl_rows"]})
        return t

    def cell(src, s, r, months):
        return sum(src.get((s, p, mo), 0.0) for p in parts(r) for mo in months)
    if not con.execute("SELECT count(*) FROM bp_rows").fetchone()[0]:
        return False, "board pack prázdny — 0 nie je dôkaz", ["bp_rows prázdne"]
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
            items.append(f"{label}: board pack ≠ druhá cesta ({'vyššie' if float(got or 0) > float(want or 0) else 'nižšie'})")
    # 1. mesačná mriežka
    grid = con.execute("SELECT shop, row, mo, actual, plan, ly FROM bp_grid").fetchall()
    for s, r, mo, a, p, l_ in grid:
        diff(f"{s} · {r} · mesiac {mo} skutočnosť", a, act.get((s, r, mo), 0.0) if mo <= am else 0.0)
        diff(f"{s} · {r} · mesiac {mo} plán", p, pm.get((s, r, mo), 0.0))
        diff(f"{s} · {r} · mesiac {mo} minulý rok", l_, ly.get((s, r, mo), 0.0))
    if len(grid) != len(shops) * len(base) * 12:
        items.append(f"mriežka: {len(grid)} buniek ≠ {len(shops) * len(base) * 12}")
    # 2. odhad po stredisku × riadku × mesiaci
    got_fc = {(s, r, mo): float(v or 0) for s, r, mo, v in con.execute(
        "SELECT shop, row, mo, sum(amount) FROM bp_forecast GROUP BY 1, 2, 3").fetchall()}
    for k in sorted(set(got_fc) | set(fc)):
        diff(f"{k[0]} · {k[1]} · mesiac {k[2]} odhad", got_fc.get(k, 0.0), fc.get(k, 0.0))
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
            items.append(f"{s} · {r}: vo výsledovke je, v board packe chýba")
            continue
        for c in cols:
            diff(f"{s} · {r} · {c}", rows[(s, r)][c], want[c][(s, r)])
    items += [f"{s} · {r}: v board packe navyše (výsledovka ho nemá)" for s, r in rows if (s, r) not in ytd]
    # 4. odchýlky voči plánu aj minulému roku a poradie
    var = con.execute("SELECT shop, row, d_plan, d_ly FROM bp_variance ORDER BY rk").fetchall()
    want_var = sorted(((s, r, ytd[(s, r)] - want["ytd_plan"][(s, r)], ytd[(s, r)] - ytd_prev[(s, r)])
                       for s in shops for r in bpc["variance_rows"]), key=lambda x: (-abs(x[2]), x[0], x[1]))
    for (s, r, d, dl), (ws, wr, wd, wdl) in zip(var[:bpc["variance_top"]], want_var[:bpc["variance_top"]]):
        if (s, r) != (ws, wr) or abs(float(d) - wd) > tol or abs(float(dl) - wdl) > tol:
            items.append(f"odchýlky: poradie alebo suma nesedí ({s} · {r} vs. druhá cesta {ws} · {wr})")
            break
    if len(var) != len(want_var):
        items.append(f"odchýlky: {len(var)} riadkov ≠ {len(want_var)} (stredisko × riadok odchýlok)")
    # 5. pravidlá rizík a citlivosti s €: tempo tržieb, nákladový skok (mix kategórie = limit)
    want_ro, mn = {}, bpc["ro_min_eur"]
    for s in sorted(shops):
        a, p = cell(act, s, "Tržby", rr), cell(pm, s, "Tržby", rr)
        ay, py = cell(act, s, "Tržby", ytdm), cell(pm, s, "Tržby", ytdm)
        if p and py and ay and abs(a / p - ay / py) >= bpc["ro"]["revenue_pace"]["min_gap"]:
            imp = (cell(pm, s, "Tržby", rest) * ay / py - cell(fc, s, "Tržby", rest)) * cell(act, s, "Hrubá marža", ytdm) / ay
            if abs(imp) >= mn:
                want_ro[f"citlivost|tempo_trzieb|{s}"] = imp
    cs = bpc["ro"]["cost_spike_repeat"]
    tot = lambda src, r, ms: sum(cell(src, s, r, ms) for s in shops)  # noqa: E731
    for r in [x for x in parts(bpc["ebitda_row"]) if x not in cs.get("exclude", []) and x != "Tržby"]:
        lr = tot(ly, r, rr)
        rr_yoy = tot(act, r, rr) / lr - 1 if lr else 0.0
        for q in range(1, (am - n) // 3 + 1):
            lq = tot(ly, r, range(3 * q - 2, 3 * q + 1))
            if lq and tot(act, r, range(3 * q - 2, 3 * q + 1)) / lq - 1 >= cs["min_yoy"] and rr_yoy < cs["min_yoy"] / 2:
                imp = tot(ly, r, rest) * (tot(act, r, range(3 * q - 2, 3 * q + 1)) / lq) - tot(fc, r, rest)
                if abs(imp) >= mn:
                    want_ro[f"ro|skok_nakladu|{r}|Q{q}"] = imp
    got_ro = {x["key"]: x["number"] for x in ro if x["rule"] in ("revenue_pace", "cost_spike_repeat")}
    for k in sorted(set(got_ro) | set(want_ro)):
        if k not in got_ro or k not in want_ro:
            items.append(f"riziká: položka {k} {'chýba' if k not in got_ro else 'navyše'} voči druhej ceste")
        else:
            diff(f"riziká: {k}", got_ro[k], want_ro[k])
    # 6. plán úplný
    unmapped = [r[0] for r in con.execute(
        "SELECT DISTINCT account FROM stg_plan WHERE amount <> 0 AND account NOT IN (SELECT account FROM pl_map) "
        "ORDER BY 1").fetchall()]
    items += [f"plán: účet {a} nie je zaradený do výsledovky — plán by sa stratil" for a in unmapped]
    src, got = con.execute("""
        SELECT (SELECT sum(CASE WHEN account LIKE '6%' THEN amount ELSE -amount END) FROM stg_plan
                WHERE cc IN (SELECT cc FROM cost_centers)),
               (SELECT sum(plan) FROM bp_grid_raw)""").fetchone()
    if abs(float(src or 0) - float(got or 0)) > tol:
        items.append(f"plán: board pack {float(got or 0):,.2f} ≠ zdroj plánu {float(src or 0):,.2f} (riadky sa stratili)")
    lost = con.execute("SELECT count(*) FROM stg_plan WHERE cc NOT IN (SELECT cc FROM cost_centers) AND amount <> 0").fetchone()[0]
    if lost:
        items.append(f"plán: {lost} riadkov s neznámym strediskom")
    if items:
        return False, f"board pack ≠ druhá cesta ({len(items)}): {_fmt_items(items)}", items
    return True, (f"board pack == druhá cesta na cent: {len(grid)} buniek mriežky, {len(fc)} buniek odhadu, "
                  f"{len(rows)} riadkov (YTD, plán, minulý rok, odhad roka), odchýlky a poradie, {len(want_ro)} "
                  f"pravidiel rizík s €; plán úplný"), []

# ---------------------------------------------------------------- zmluva reportu
def _pct_after(text: str, after: str):
    """Prvé percento v texte za slovom `after` ('' = prvé v texte): '−34,3 %' → -34.3."""
    i = text.find(after) if after else 0
    if i < 0:
        return None
    mt = re.search(r"([+−-]?\d+(?:,\d+)?)\s*%", text[i + len(after):])
    return float(mt.group(1).replace("−", "-").replace(",", ".")) if mt else None


def _contract_cell(wb, loc: dict):
    """Hodnota bunky zmluvy z hotového xlsx podľa NÁZVOV (nie súradníc): (hodnota, adresa) alebo
    (None, dôvod). Vzorec v bunke = nie hodnota (výstup pre board je bez vzorcov)."""
    if loc["sheet"] not in wb.sheetnames:
        return None, f"hárok '{loc['sheet']}' chýba"
    ws = wb[loc["sheet"]]
    rows = list(ws.iter_rows())
    if "text_prefix" in loc:
        for r in rows:
            for c in r:
                if isinstance(c.value, str) and c.value.startswith(loc["text_prefix"]):
                    v = _pct_after(c.value, loc["after"])
                    return (v, c.coordinate) if v is not None else (None, f"{c.coordinate}: v texte chýba percento")
        return None, f"riadok zistenia začínajúci '{loc['text_prefix']}' chýba"
    if "label" in loc:
        for r in rows:
            if r and r[0].value == loc["label"] and len(r) > 1:
                return r[1].value, r[1].coordinate
        return None, f"riadok '{loc['label']}' chýba"
    head = [c.value for c in rows[0]] if rows else []
    if loc["col"] not in head:
        return None, f"stĺpec '{loc['col']}' chýba"
    ci = head.index(loc["col"])
    for r in rows[1:]:
        if r[0].value == loc["row"]:
            return r[ci].value, r[ci].coordinate
    return None, f"riadok '{loc['row']}' chýba"


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
        return False, "zmluva nemá žiadne číslo — 0 nie je dôkaz", ["zmluva prázdna"]
    safe, full = [], []

    def bad(s_txt, f_txt=None):
        safe.append(s_txt)
        full.append(f_txt or s_txt)
    want_anchors = contract.get("anchors") or []
    if sorted(want_anchors) != sorted(anchors):
        bad(f"kotvy behu {sorted(anchors)} ≠ kotvy zmluvy {sorted(want_anchors)}")
    valid = {}
    for name in want_anchors:
        a = anchors.get(name)
        if not a:
            bad(f"kotva {name} chýba")
        elif a.get("_meta", {}).get("delivery_sha256") != delivery_sha:
            bad(f"kotva {name} nie je pre túto dodávku (iný odtlačok) — golden pre ňu neexistuje")
        elif as_of and a.get("_meta", {}).get("as_of") != as_of:
            bad(f"kotva {name} je pre obdobie {a['_meta'].get('as_of')}, report je k {as_of} — golden pre ne neexistuje")
        else:
            valid[name] = a
    if len(want_anchors) < 2:
        bad(f"zmluva menuje {len(want_anchors)} kotvu — podmienka 2 žiada obe (generátor aj nezávislý prepočet)")
    if want_anchors and len(valid) < len(want_anchors):
        bad(f"platné kotvy {len(valid)}/{len(want_anchors)} — {len(pts)} čísel zmluvy nemá kontrolu, report sa nevydá")
        if full_out is not None:
            full_out.extend(full)
        return False, f"zmluva reportu nesplnená: {_fmt_items(safe)}", safe
    tol = contract["tolerance"]
    if not (0 < tol.get("eur", 0) and 0 < tol.get("pct_display", 0)):
        return False, "zmluva nemá toleranciu eur a pct_display", ["tolerancia chýba"]
    wb = load_workbook(xlsx)                                   # bez data_only: vzorec ostane textom
    n_ok = 0
    fmt_ok = {"eur": "#,##0.00", "fraction": "0.0%"}          # zobrazenie bunky = to, čo board vidí
    for p in pts:
        pid, unit, lab = p["id"], p["unit"], p["label"]
        if unit not in ("eur", "pct", "fraction"):
            bad(f"{pid} {lab}: neznáma jednotka '{unit}' (povolené eur, pct, fraction)")
            continue
        for c in p.get("checks", []):
            if not check_status.get(c):
                bad(f"{pid} {lab}: kontrola {c} neprebehla alebo FAIL")
        want = {n: a["values"].get(pid) for n, a in valid.items()}
        if any(w is None for w in want.values()):
            bad(f"{pid} {lab}: bez hodnoty v kotve — číslo nemá kontrolu")
            continue
        if unit in ("pct", "fraction"):
            same = lambda shown, w: abs(shown - w) <= tol["pct_display"] + 1e-9  # noqa: E731  správne zaokrúhlená kotva
            agree = lambda a, b: abs(a - b) <= 0.01  # noqa: E731
        else:
            same = lambda shown, w: abs(shown - w) <= tol["eur"] + 1e-9  # noqa: E731
            agree = lambda a, b: abs(a - b) <= 0.01  # noqa: E731
        wv = list(want.items())
        if any(not agree(wv[0][1], w) for _, w in wv[1:]):
            bad(f"{pid} {lab}: kotvy sa navzájom nezhodujú ({', '.join(n for n, _ in wv)})",
                f"{pid} {lab}: kotvy sa nezhodujú ({', '.join(f'{n} {w}' for n, w in wv)})")
        ok_here = True
        for loc in [p["locate"]] + p.get("also", []):
            lu = loc.get("unit", unit)                      # umiestnenie môže niesť vlastnú jednotku (G16: text + KPI)
            if lu not in ("eur", "pct", "fraction") or (lu == "pct") != ("text_prefix" in loc) or \
                    (lu == "eur") != (unit == "eur"):
                ok_here = False
                bad(f"{pid} {lab}: jednotka '{lu}' nesedí s umiestnením {loc.get('sheet')} (povolené: pct = text zistenia,"
                    f" fraction = bunka podielu, eur = bunka sumy)")
                continue
            scale = 100.0 if lu == "fraction" else 1.0      # bunka ako podiel (0,25) vs. kotva v % (25,0)
            v, where = _contract_cell(wb, loc)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and lu in fmt_ok and \
                    wb[loc["sheet"]][where].number_format != fmt_ok[lu]:
                ok_here = False
                bad(f"{pid} {lab}: {loc['sheet']}!{where} má iný formát než dohodnutý '{fmt_ok[lu]}' — board by videl "
                    f"iné číslo")                           # podstrčený formát sa nevypisuje
                continue
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
                ok_here = False
                bad(f"{pid} {lab}: {where if v is None else f'{where} nie je číslo'}",
                    f"{pid} {lab}: {where if v is None else f'{where} nie je číslo ({v!r})'}")
                continue
            if lu == "fraction":                            # porovnáva sa ZOBRAZENÉ: × 100, 1 desatinné miesto
                from decimal import ROUND_HALF_UP, Decimal
                v = float((Decimal(str(v)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            else:
                v = float(v) * scale
            for n, w in want.items():
                if not same(float(v), w):
                    ok_here = False
                    u = "€" if unit == "eur" else "p. b."
                    ls, lf = _lineage(p, valid, engine_detail)
                    smer = "vyššie" if float(v) > w else "nižšie"
                    bad(f"{pid} {lab}: report {loc['sheet']}!{where} {smer} než kotva {n}{ls}",
                        f"{pid} {lab}: report {loc['sheet']}!{where} = {float(v):,.2f} ≠ kotva {n} {w:,.2f} "
                        f"(rozdiel {float(v) - w:+,.2f} {u}){lf}")
        n_ok += ok_here
    if safe:
        if full_out is not None:
            full_out.extend(full)
        return False, f"zmluva reportu nesplnená ({len(safe)}): {_fmt_items(safe)}", safe
    return True, (f"{n_ok}/{len(pts)} čísel zmluvy z hotového {Path(xlsx).name} sedí s {len(valid)} kotvami mimo "
                  f"motora (±{tol['eur']:.0f} €; percentá = správne zaokrúhlená kotva)"), []


def _lineage(p: dict, anchors: dict, engine_detail) -> tuple:
    """Cesta k vstupu: (text pre súbor bez súm, text so sumami pre obrazovku). Keď odtlačok
    sedí, vstup je ten istý — rozdiel po mesiacoch znamená, že ho STROJ prečítal inak."""
    src = p.get("source", {})
    if "text" in src:
        t = f" — vstup: {src['text']}"
        return t, t
    det = next((a["detail"].get(p["id"]) for a in anchors.values() if a.get("detail")), None)
    cc = src.get("cost_center") or "všetky"
    base = f"{src.get('files')} · stredisko {cc} · účty {', '.join(src.get('accounts', []))}"
    if det is None or engine_detail is None:
        return f" — vstup: {base}", f" — vstup: {base}"
    eng = engine_detail(p) or {}
    diff = [(ym, eng.get(ym, 0.0), det.get(ym, 0.0)) for ym in sorted(set(eng) | set(det))
            if abs(eng.get(ym, 0.0) - det.get(ym, 0.0)) > 0.005]
    if not diff:
        t = f" — vstup prečítaný zhodne s kotvou po mesiacoch ({base}); rozdiel vznikol vo výpočte alebo zápise reportu"
        return t, t
    more = f" … (+{len(diff) - 3} mesiacov)" if len(diff) > 3 else ""
    s_txt = " — stroj prečítal " + "; ".join(f"predvaha_{ym}.xlsx · stredisko {cc} inak než kotva"
                                            for ym, e, d in diff[:3]) + more
    f_txt = " — stroj prečítal " + "; ".join(f"predvaha_{ym}.xlsx · stredisko {cc}: {e:,.2f} € ≠ kotva {d:,.2f} €"
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
            items.append(f"výnimka #{i}: neznáma kontrola '{e.get('check')}'")
        if len(str(e.get("match", "")).strip()) < 5:
            items.append(f"výnimka #{i}: match '{e.get('match', '')}' je kratší než 5 znakov")
        if not _r.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(e.get("valid_until", "")), _r.ASCII):
            items.append(f"výnimka #{i}: valid_until '{e.get('valid_until')}' nie je RRRR-MM")
        if not str(e.get("reason", "")).strip():
            items.append(f"výnimka #{i}: chýba dôvod")
        if e.get("check") in known_checks and e.get("check") not in EXCEPTABLE:
            items.append(f"výnimka #{i}: kontrolu '{e.get('check')}' výnimkou kryť nesmie — výnimky sú "
                         f"vypnuté do rozhodnutia vedenia, ktoré odchýlky smie board prijať")
        vu = str(e.get("valid_until", ""))
        if as_of and _r.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", vu, _r.ASCII) \
                and _months_between(as_of, vu) > MAX_EXCEPTION_MONTHS:
            items.append(f"výnimka #{i}: platnosť {vu} je viac než {MAX_EXCEPTION_MONTHS} mesiacov po {as_of}")
    if items:
        return False, f"neplatné výnimky: {_fmt_items(items)}", items
    return True, f"{len(exceptions)} výnimiek v platnom tvare", []


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
            items.append(f"{name}: linka {'chýba' if got is None else ('vyššie' if float(got) > float(want) else 'nižšie')}"
                         f" než etalón")
            if full_out is not None:
                full_out.append(f"{name}: linka {_fmt_num(got)} vs etalón {_fmt_num(want)}")
    for k, v in truth.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                cmp(f"{k}[{kk}]", results.get(k, {}).get(kk), vv)
        else:
            cmp(k, results.get(k), v)
    if n == 0:
        return False, "etalón prázdny — 0 nie je dôkaz", ["etalón prázdny"]
    if items:
        return False, f"{len(items)} z {n} čísel nesedí s etalónom: {_fmt_items(items)}", items
    return True, f"{n}/{n} čísel sedí s etalónom na cent", []


@check("xlsx_readback")
def xlsx_readback(path: Path, expected: dict, expected_texts: list = None,
                  unchecked_sheets: tuple = ("Kontroly", "Kontrolný panel", "Chybné riadky"), expected_headers: dict = None,
                  main_sheet: str | None = "Prehľad"):
    """Hotový prehlad.xlsx sa znovu NAČÍTA Z DISKU (nie premenná writera):
    každé číslo vo VŠETKÝCH hárkoch (okrem protokolu kontrol) = výpočet na cent,
    žiadne navyše ani chýbajúce; hlavičky a popisy riadkov = výpočet; VŠETKY
    texty hárku Prehľad (aj stĺpec A) = presne to, čo motor vyrobil; vzorec
    kdekoľvek = FAIL (číslo, ktoré nevyrobil stroj); hárok navyše = FAIL.
    Porovnáva s hodnotami výpočtu — chytí chybu ZÁPISU, nie chybu výpočtu
. Hárky kontrolného panelu
 overuje control_panel_readback; pivotka.xlsx sa overuje tou istou kontrolou s main_sheet=None."""
    from openpyxl import load_workbook
    path = Path(path)
    if not path.is_file():
        return False, f"výstup chýba: {path.name}", [f"chýba {path.name}"]
    try:
        wb = load_workbook(path, data_only=False)
    except Exception as e:  # noqa: BLE001
        return False, f"výstup sa nedá otvoriť ({type(e).__name__})", [str(e)]
    want_sheets = {k[0] for k in expected} | ({main_sheet} if main_sheet else set()) | set(expected_headers or {})   # prázdny hárok s hlavičkou
    rows_ok = {sh: {k[1] for k in expected if k[0] == sh} for sh in want_sheets}
    cols_ok = {sh: {k[2] for k in expected if k[0] == sh} for sh in want_sheets}
    got, foreign, owned, texts = {}, [], 0, []
    for sh in wb.sheetnames:
        if sh in unchecked_sheets:
            continue
        if sh not in want_sheets:
            foreign.append(f"hárok '{sh}' navyše")
            continue
        ws = wb[sh]
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" or (isinstance(c.value, str) and c.value.startswith("=")):
                    foreign.append(f"{sh}!{c.coordinate} vzorec '{c.value}'")
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
            foreign.append(f"{sh}: stĺpce navyše {extra_cols}")
        if expected_headers is not None and list(head) != list(expected_headers.get(sh, [])):
            foreign.append(f"{sh}: hlavička {list(head)} ≠ výpočet {expected_headers.get(sh)}")
        for r in rows[1:]:
            if r[0] not in rows_ok[sh]:
                if any(v is not None for v in r):
                    foreign.append(f"{sh}: riadok '{r[0]}' výpočet neurčil")
                continue
            for col, v in zip(head[1:], r[1:]):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    got[(sh, r[0], col)] = v
                elif v is not None and isinstance(expected.get((sh, r[0], col)), str):
                    got[(sh, r[0], col)] = str(v)      # text, ktorý výpočet určil (board pack: príčina, komentár)
                elif v is not None:
                    foreign.append(f"{sh}/{r[0]}/{col}='{v}' (nie číslo)")
    for sh in want_sheets - set(wb.sheetnames):
        foreign.append(f"hárok '{sh}' chýba")
    n_txt = 0
    for k, v in got.items():
        want = expected.get(k)
        if want is None:
            foreign.append(f"{k[0]}/{k[1]}/{k[2]}={v} (výpočet ho neurčil)")
        elif isinstance(want, str) or isinstance(v, str):
            if str(v) != str(want):
                foreign.append(f"{k[0]}/{k[1]}/{k[2]}: text '{str(v)[:60]}' ≠ výpočet '{str(want)[:60]}'")
            else:
                n_txt += 1
        elif round(float(v) * 100) != round(float(want) * 100):
            foreign.append(f"{k[0]}/{k[1]}/{k[2]}={v} vs výpočet {want:.2f}")
        else:
            owned += 1
    missing = [f"{k[0]}/{k[1]}/{k[2]} chýba" for k in expected if k not in got]
    if expected_texts is not None and texts != list(expected_texts):
        extra = [x for x in texts if x not in expected_texts][:3]
        lost = [x for x in expected_texts if x not in texts][:3]
        foreign.append(f"texty Prehľadu nesedia (navyše {extra}, chýba {lost})")
    items = foreign + missing
    n = len(expected) - sum(isinstance(v, str) for v in expected.values())
    if items:
        return False, f"od stroja {owned}/{n}, nesedí {len(items)}: {_fmt_items(items)}", items
    if n == 0:
        return True, "výstup bez čísel pre board (verdikt NESEDÍ — vydaný len protokol); texty sedia", []
    return True, (f"od stroja {owned}/{n} čísel" + (f" + {len(texts)} textov {main_sheet}" if main_sheet else "")
                  + (f" + {n_txt} textov {'board packu' if main_sheet else 'dátových hárkov'}" if n_txt else "") + f" v {path.name} "
                  f"(znovu načítané z disku, na cent, bez vzorcov; protokol kontrol sa neoveruje)"), []


# ------------------------------------------------------------------ pivotka + kontrolný panel
_PANEL_LIGHT = {"PASS": "🟢 PASS", "FAIL": "🔴 FAIL", "VÝNIMKA": "🟡 VÝNIMKA"}


@check("pivot_pl_match")
def pivot_pl_match(path: Path, ytd: dict, bp_rows: dict | None, profile: dict):
    """Pivotka z HOTOVÉHO pivotka.xlsx (hárok Fakty, po účtoch) sa sčíta druhou cestou — po stredisku a riadku
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
        return False, f"pivotka chýba: {path.name}", [f"chýba {path.name}"]
    if bp_rows is None:
        return False, "pivotka bez board packu nemá kotvu pre minulý rok a plán", ["chýba bp_rows"]
    wb = load_workbook(path, data_only=False)
    if "Fakty" not in wb.sheetnames:
        return False, "pivotka bez hárku Fakty", ["chýba hárok Fakty"]
    rows = list(wb["Fakty"].iter_rows(values_only=True))
    head = list(rows[0]) if rows else []
    need = ["Druh", "Mesiac", "Stredisko", "Účet", "Riadok výsledovky", "Suma (€)"]
    if any(h not in head for h in need):
        return False, f"Fakty: hlavička {head} nemá {need}", ["hlavička Fakty"]
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
            items.append(f"Fakty r{i}: suma '{v}' nie je číslo")
            continue
        if s not in shops or row not in base or k not in ("skutočnosť", "plán"):
            items.append(f"Fakty r{i}: neznámy druh/stredisko/riadok {k}/{s}/{row}")
            continue
        if resolve_account(str(account), profile["pl_mapping"]) != row:
            items.append(f"Fakty r{i}: účet {account} nepatrí do riadku {row} podľa profilu")
            continue
        if ym[:4] not in (y1, y2) or (k == "skutočnosť" and ym > as_of) or (k == "plán" and ym[:4] != y2):
            items.append(f"Fakty r{i}: mesiac {ym} mimo obdobia ({k})")
            continue
        if ym[:4] == y2:
            by_month[(k, row, ym)] = by_month.get((k, row, ym), 0.0) + float(v)
        if k == "plán":
            acc[("plan", s, row)] += float(v)
        elif ym[:4] == y1:
            acc[("ly", s, row)] += float(v)
        elif ym <= as_of:
            acc[("ytd", s, row)] += float(v)
    if items:
        return False, f"pivotka nesedí ({len(items)}): {_fmt_items(items)}", items
    if n_rows == 0:
        return False, "pivotka bez faktov — 0 riadkov nie je výsledok", ["0 faktov"]
    for k in ("ytd", "ly", "plan"):
        for sub, parts in profile["pl_subtotals"].items():
            for s in shops:
                acc[(k, s, sub)] = sum(acc[(k, s, p)] for p in parts)
        for r in profile["pl_rows"]:
            acc[(k, "Spolu", r)] = sum(acc[(k, s, r)] for s in shops)
    tax = profile.get("board_pack", {}).get("tax_row")
    tax_rows = {r for r, parts in profile["pl_subtotals"].items() if tax in parts} | {tax}
    n = 0
    for s in shops + ["Spolu"]:
        for r in profile["pl_rows"]:
            n += 1
            if _cents(acc[("ytd", s, r)]) != _cents(ytd[(s, r)]):
                items.append(f"skutočnosť YTD {s} · {r}: pivotka {acc[('ytd', s, r)]:,.2f} ≠ výsledovka {ytd[(s, r)]:,.2f}")
            n += 1
            if _cents(acc[("ly", s, r)]) != _cents(bp_rows[(s, r)]["fy_ly"]):
                items.append(f"minulý rok {s} · {r}: pivotka {acc[('ly', s, r)]:,.2f} ≠ board pack {bp_rows[(s, r)]['fy_ly']:,.2f}")
            if r in tax_rows:
                continue
            n += 1
            if _cents(acc[("plan", s, r)]) != _cents(bp_rows[(s, r)]["fy_plan"]):
                items.append(f"plán roka {s} · {r}: pivotka {acc[('plan', s, r)]:,.2f} ≠ board pack {bp_rows[(s, r)]['fy_plan']:,.2f}")
    n_piv = 0
    for title, kind in (("Pivot skutočnosť", "skutočnosť"), ("Pivot plán", "plán")):
        if title not in wb.sheetnames:
            items.append(f"chýba hárok {title}")
            continue
        prow = list(wb[title].iter_rows(values_only=True))
        cols = list(prow[0][1:]) if prow else []
        labels = [r[0] for r in prow[1:] if r[0] is not None]
        if labels != profile["pl_rows"]:            # poradie výsledovky a žiadny riadok dvakrát
            items.append(f"{title}: riadky {labels} ≠ výsledovka profilu (poradie, duplicita alebo navyše)")
        seen = set()
        for r in prow[1:]:
            if r[0] is None:
                continue
            seen.add(r[0])
            parts = [r[0]] if r[0] not in profile["pl_subtotals"] else _flat_parts(profile, r[0])
            tot = 0.0
            for c, v in zip(cols, r[1:]):
                n_piv += 1
                if c == "Spolu":
                    want = tot
                else:
                    want = sum(by_month.get((kind, p, str(c)), 0.0) for p in parts)
                    tot += want
                if not isinstance(v, (int, float)) or isinstance(v, bool) or _cents(float(v)) != _cents(want):
                    items.append(f"{title} {r[0]} {c}: {v} ≠ fakty {want:,.2f}")
        missing = [r for r in profile["pl_rows"] if r not in seen]
        if missing:
            items.append(f"{title}: chýbajú riadky {missing}")
    if items:
        return False, f"pivotka nesedí s výsledovkou ({len(items)}): {_fmt_items(items)}", items
    return True, (f"pivotka == výsledovka na cent: {n_rows} faktov (účet → riadok podľa profilu) → {n} buniek (skutočnosť YTD "
                  f"po strediskách a riadkoch, minulý rok a plán roka vs board pack bez dane) + {n_piv} buniek hárkov Pivot "
                  f"vrátane Spolu == fakty; čítané z hotového súboru"), []


def _flat_parts(profile: dict, row: str) -> list:
    subs = profile["pl_subtotals"]
    return [x for p in subs[row] for x in _flat_parts(profile, p)] if row in subs else [row]


@check("control_panel_readback")
def control_panel_readback(path: Path, panel: dict, results: list):
    """Kontrolný panel z HOTOVÉHO prehlad.xlsx: každá kontrola behu (results) je na paneli práve raz, v skupine
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
        items.append(f"kontroly bez skupiny v profile (control_panel.groups): {', '.join(panel['ungrouped'])}")
    if not path.is_file():
        return False, f"výstup chýba: {path.name}", items + [f"chýba {path.name}"]
    wb = load_workbook(path, data_only=False)
    for sh in ("Kontrolný panel", "Chybné riadky"):
        if sh not in wb.sheetnames:
            items.append(f"chýba hárok {sh}")
    if items:
        return False, f"kontrolný panel nesedí ({len(items)}): {_fmt_items(items)}", items
    wp, we = wb["Kontrolný panel"], wb["Chybné riadky"]
    ran = {cid for cid, *_ in results}
    if [c.value for c in wp[3]] != panel["panel_head"] or [c.value for c in we[1]] != panel["err_head"]:
        items.append("hlavičky hárkov Kontrolný panel / Chybné riadky ≠ kontrakt")
    head = [c.value for c in wp[1]]
    if head[:4] != ["Kontrolný panel", panel["company"], f"stav k {panel['as_of']}", f"Verdikt: {panel['verdict']}"]:
        items.append(f"panel: hlavička {head[:4]} ≠ firma / obdobie / verdikt behu ({panel['verdict']})")
    foot = [c.value for row in wp.iter_rows(values_only=False) for c in row[:1] if isinstance(c.value, str) and c.value.startswith("Nad hotovým súborom")]
    if foot != [panel["footnote"]]:
        items.append("panel: veta o kontrolách nad hotovým súborom chýba alebo je zmenená")
    expected = {r["cid"]: r for r in panel["rows"]}
    got, links = {}, {}
    for row in wp.iter_rows(min_row=4):
        a, g, cid, detail, n, link = (row[i].value if i < len(row) else None for i in range(6))
        if cid in expected and a in _PANEL_LIGHT.values():
            if cid in got:
                items.append(f"panel: kontrola {cid} dvakrát")
            got[cid] = (a, g, detail, n)
            links[cid] = row[5].hyperlink.location if row[5].hyperlink else None
    err_rows = {}
    for i, row in enumerate(we.iter_rows(min_row=2, values_only=False), start=2):
        cid = row[1].value
        if cid is None:
            continue
        if cid not in ran:
            items.append(f"chybné riadky r{i}: kontrola '{cid}' v tomto behu nebežala")
            continue
        err_rows.setdefault(cid, []).append((i, row[2].value, row[3].value, row[4].value,
                                             [row[5 + k].hyperlink.target if row[5 + k].hyperlink else None for k in range(3)]))
        for k in range(3):                      # text odkazu = meno súboru cieľa
            h = row[5 + k].hyperlink.target if row[5 + k].hyperlink else None
            if (h.rsplit("/", 1)[-1] if h else None) != row[5 + k].value:
                items.append(f"chybné riadky r{i}: text odkazu '{row[5 + k].value}' ≠ cieľ {h}")
    for cid in sorted(ran - {"control_panel_readback"}):
        if cid not in expected:
            if cid not in panel["ungrouped"]:
                items.append(f"kontrola {cid} bežala, ale model panelu ju nemá")
            continue
        r = expected[cid]
        if cid not in got:
            items.append(f"panel: kontrola {cid} chýba")
            continue
        a, g, detail, n = got[cid]
        if a != r["light"] or g != r["group"] or n != r["n"] or detail != r["detail"]:
            items.append(f"panel: {cid} má {a}/{g}/{n} ≠ protokol {r['light']}/{r['group']}/{r['n']}")
        rows_c = err_rows.get(cid, [])
        if len(rows_c) != r["n"]:               # aj 0 nálezov = 0 riadkov
            items.append(f"chybné riadky: {cid} má {len(rows_c)} riadkov ≠ {r['n']} nálezov")
        if r["n"]:
            loc = links.get(cid)
            if not loc or not rows_c or loc != f"'Chybné riadky'!A{rows_c[0][0]}":
                items.append(f"panel: {cid} nemá preklik na svoje chybné riadky ({loc})")
    for cid in got:
        if cid not in ran:
            items.append(f"panel: kontrola {cid} na paneli, ale nebežala")
    want_err = {}
    for x in panel["err"]:
        want_err.setdefault(x["cid"], []).append(x)
    for cid, rows_c in err_rows.items():
        for (i, f, ln, txt, hrefs), x in zip(rows_c, want_err.get(cid, [])):
            want_h = (x["hrefs"] + [None] * 3)[:3]
            if f != x["file"] or ln != x["line"] or hrefs != want_h:
                items.append(f"chybné riadky r{i}: {f}/{ln}/{hrefs} ≠ model {x['file']}/{x['line']}/{want_h}")
            if txt != x["text"]:
                items.append(f"chybné riadky r{i}: text nálezu ≠ protokol ('{str(txt)[:50]}')")
            for href in hrefs:
                if href and not (path.parent / href).is_file():
                    items.append(f"chybné riadky r{i}: odkaz na súbor {href} nevedie na existujúci súbor")
    src = {}
    for row in wp.iter_rows(min_row=4, values_only=True):
        if row[0] in {s["label"] for s in panel["sources"]} and isinstance(row[1], (int, float)):
            src[row[0]] = tuple(row[1:6])
    for s in panel["sources"]:
        want = (s["expected"], s["got"], s["rows"], s["bad"], s["light"])
        if src.get(s["label"]) != want:
            items.append(f"zdroje: {s['label']} {src.get(s['label'])} ≠ model {want}")
    if items:
        return False, f"kontrolný panel nesedí ({len(items)}): {_fmt_items(items)}", items
    n_fail = sum(1 for r in panel["rows"] if r["status"] != "PASS")
    return True, (f"panel == protokol: {len(got)} kontrol v {len({r['group'] for r in panel['rows']})} skupinách, "
                  f"{n_fail} so semaforom mimo PASS, {len(panel['err'])} chybných riadkov s preklikom, "
                  f"{len(panel['sources'])} zdrojov; čítané z hotového súboru"), []
