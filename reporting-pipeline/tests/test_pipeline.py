"""Testy reporting pipeline (papiernictvo2): čistý beh, zasadené chyby a zuby kontrol.

Každá kontrola má test, že VIE ZLYHAŤ na sabotovanom vstupe, + čistý beh. Dáta vyrobí
generátor (tools/gen_papiernictvo2.py) — conftest ich pred testami vygeneruje, ak chýbajú.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PIPELINE = ROOT / "pipeline"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_checks = _load("zl_checks", _PIPELINE / "checks.py")
CHECKS = _checks.CHECKS


def _engine():
    return _load("zl_engine", _PIPELINE / "engine.py")


def _line_of(out, cid):
    return next(l for l in out.splitlines() if f"] {cid} —" in l)


_P2 = ROOT / "profiles" / "papiernictvo2"


def _p2_dataset(tmpdir, name="clean"):
    import shutil
    dst = tmpdir / f"p2_{name}"
    shutil.copytree(_P2 / "data" / name, dst)
    return dst


def _p2_run(tmpdir, inp, truth=True):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _engine().run(_P2, inp, tmpdir / "p2_out", (_P2 / "truth.json") if truth is True else (truth or None))
    return rc, buf.getvalue(), tmpdir / "p2_out"


def test_full_clean_is_sedi(tmpdir):
    """Papiernictvo2 (9 zdrojov, 2025-01..2026-09): SEDÍ, všetkých 16 kontrol PASS, etalón generátora
    na cent (plná výsledovka po čistý zisk + počty riadkov), výstup z disku; board = hračky 3 štvrťroky;
    žiadne falošné zistenie o centrále bez tržieb ani koncentrácia z čistého zisku."""
    rc, out, o = _p2_run(tmpdir, _p2_dataset(tmpdir))
    assert rc == 0 and "VERDICT: TIES" in out, [l for l in out.splitlines() if "FAIL" in l or "STOP" in l]
    import re
    tm = re.search(r"truth_meter — (\d+)/(\d+) ", out)     # 44 výsledovka + board pack (počet top odchýlok a R&O podľa dát)
    assert tm and tm[1] == tm[2] and int(tm[1]) >= 100 and out.count("[PASS]") >= 24, out[-600:]
    board = [l for l in out.splitlines() if l.startswith("[BOARD]")]
    assert any("Toys: year-on-year decline 3 quarters" in b for b in board), board
    assert not any("Head office" in b for b in board), board
    assert not any("EBITDA in a single month" in b for b in board), board        # EBITDA, nie čistý zisk
    from openpyxl import load_workbook
    ws = load_workbook(o / "overview.xlsx", read_only=True)["P&L YTD"]
    rows = [r[0] for r in ws.iter_rows(values_only=True)]
    assert rows[1:] == ["Revenue", "Cost of goods sold", "Gross margin", "Staff", "Rent", "Energy", "Marketing",
                        "Services", "Other", "EBITDA", "Depreciation", "EBIT", "Interest and financial", "Profit before tax",
                        "Income tax", "Net profit"], rows


def test_full_planted_errors_named(tmpdir):
    """Zasadené chyby E1–E7 papiernictva2: každá menovite v kontrole, ktorá ju má chytiť; NESEDÍ."""
    import json
    rc, out, _ = _p2_run(tmpdir, _p2_dataset(tmpdir, "with_errors"), truth=False)
    assert rc == 1 and "VERDICT: DOES NOT TIE" in out, out[-600:]
    pe = {e["id"]: e for e in json.loads((_P2 / "planted_errors.json").read_text(encoding="utf-8"))}
    line = lambda cid: next(l for l in out.splitlines() if f"] {cid} —" in l)  # noqa: E731
    assert f"invoice {pe['E1']['where']}" in line("ap_gl_match") and "is not posted" in line("ap_gl_match")
    assert "2026-06 S02: gross pay" in line("payroll_gl_match"), line("payroll_gl_match")
    assert "no invoice in the register" in line("bank_ap_match") and "31.07.2026" in line("bank_gl_match")
    assert "stock_levels_2026-03.csv: negative stock S04 Books" in line("stock_consistency"), line("stock_consistency")
    assert "2026-08 S01 account 518100" in line("journal_tb_match"), line("journal_tb_match")
    assert "pos_S03_2026-02.csv: TOTAL" in line("pos_control_total") and "S03 28.02.2026" in line("pos_gl_match")
    assert "02.09.2026" in line("bank_gl_match") and "bank_2026-08.csv: opening" in line("bank_balance")
    assert "S01 “Cards" in line("bank_gl_match") and "missing in the bank" in line("bank_gl_match"), line("bank_gl_match")
    assert "[BOARD]" not in out


def test_full_no_stories_no_findings(tmpdir):
    """Bez príbehov (vyrovnaná sezóna, bez skoku nájmu, poklesu hračiek, energií a školy) board mlčí."""
    import subprocess
    gen = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_papiernictvo2.py"), "--out", str(tmpdir / "ns"),
                          "--no-stories"], capture_output=True, text=True)
    assert gen.returncode == 0, gen.stderr
    rc, out, _ = _p2_run_prof(tmpdir, _p2_profile_copy(tmpdir, contract=False), tmpdir / "ns" / "clean",
                              truth=tmpdir / "ns" / "truth.json")                     # iná dodávka než demo zmluvy
    assert rc == 0 and "VERDICT: TIES" in out, out[-600:]
    assert "[BOARD]" not in out, [l for l in out.splitlines() if "BOARD" in l]
    md = (tmpdir / "p2_out" / "report.md").read_text(encoding="utf-8")
    ro = md.split("### Risks and opportunities")[1].split("##")[0]
    assert "the machine found no item above the profile thresholds" in ro, ro   # bez príbehov ani riziká a príležitosti


def test_full_committed_data_equals_generator(tmpdir):
    """Commitnuté dáta papiernictva2 = výstup generátora BAJTOVO (aj xlsx — generátor je deterministický)."""
    import subprocess
    gen = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_papiernictvo2.py"), "--out", str(tmpdir / "g")],
                         capture_output=True, text=True)
    assert gen.returncode == 0, gen.stderr
    for sub in ("clean", "with_errors"):
        a, b = _P2 / "data" / sub, tmpdir / "g" / sub
        names = sorted(p.name for p in a.iterdir())
        assert names == sorted(p.name for p in b.iterdir()), f"{sub}: different files"
        bad = [n for n in names if (a / n).read_bytes() != (b / n).read_bytes()]
        assert not bad, f"{sub}: ≠ generator: {bad[:5]}"


def test_full_parse_and_duplicates_and_coverage(tmpdir):
    """Cielené sabotáže kontrol, ktoré zasadené chyby nepokryjú: neplatný dátum a bodka namiesto čiarky
    v pokladni, neplatný účet v denníku (stg_parse_contract); dvakrát nahratý riadok denníka
    (full_duplicate_keys); prázdne mzdy za mesiac (full_coverage) — každé menovite."""
    inp = _p2_dataset(tmpdir)
    p = inp / "pos_S02_2026-04.csv"
    ls = p.read_text(encoding="utf-8").splitlines()
    f = ls[6].split(";")
    f[1] = "31.04.2026 10:00"
    f[7] = f[7].replace(",", ".")
    ls[6] = ";".join(f)
    p.write_text("\n".join(ls) + "\n", encoding="utf-8")
    j = inp / "journal_2026-05.csv"
    raw = j.read_bytes().decode("utf-8-sig").splitlines()
    raw.append(raw[1])                                                  # riadok denníka 2×
    x = raw[2].split(",")
    x[2] = "ABC"
    raw[2] = ",".join(x)
    j.write_bytes(b"\xef\xbb\xbf" + ("\n".join(raw) + "\n").encode("utf-8"))
    m = inp / "payroll_2026-04.csv"
    m.write_bytes(m.read_bytes().decode("cp1250").splitlines()[0].encode("cp1250") + b"\n")
    rc, out, _ = _p2_run(tmpdir, inp, truth=False)
    line = lambda cid: next(l for l in out.splitlines() if f"] {cid} —" in l)  # noqa: E731
    assert rc == 1 and "pos_S02_2026-04.csv r7: unreadable" in line("stg_parse_contract"), line("stg_parse_contract")
    assert "datetime" in line("stg_parse_contract") and "total_incl_vat" in line("stg_parse_contract")
    assert "journal_2026-05.csv r3: unreadable dr" in line("stg_parse_contract"), line("stg_parse_contract")
    assert "journal row 2×" in line("full_duplicate_keys"), line("full_duplicate_keys")
    assert "payroll: 2026-04 without data" in line("full_coverage"), line("full_coverage")


def _p2_post(inp, ym, doc, day, md, d, amount, cc, text):
    """Sabotáž, ktorú by ľudia urobili KONZISTENTNE: riadok do denníka AJ do predvahy (obe strany),
    aby prešlo párovanie denník ↔ predvaha — kontroly musia chytiť nesúlad s iným zdrojom."""
    from openpyxl import load_workbook
    j = inp / f"journal_{ym}.csv"
    raw = j.read_bytes().decode("utf-8-sig")
    j.write_bytes(b"\xef\xbb\xbf" + (raw + f'{doc},{day},{md},{d},{amount:.2f},{cc},"{text}"\n').encode("utf-8"))
    f = inp / f"trial_balance_{ym}.xlsx"
    wb = load_workbook(f)
    ws = wb["Trial balance"]
    for acc, col in ((md, 5), (d, 6)):
        for r in range(2, ws.max_row + 1):
            if ws.cell(r, 2).value == cc and str(ws.cell(r, 3).value) == acc:
                ws.cell(r, col).value = (ws.cell(r, col).value or 0) + amount
                break
        else:
            ws.append([ym, cc, acc, "sabotage", amount if col == 5 else 0.0, amount if col == 6 else 0.0])
    wb.save(f)


def test_full_check_consistent_sabotage(tmpdir):
    """zmeny, ktoré prejdú denníkom aj predvahou zhodne, zmenia EBITDA — a musia
    padnúť na inom zdroji: tržba bez pokladne (T1), presun DPH do tržieb (T2), náklad zaplatený priamo
    z banky mimo faktúr (T8), predaný tovar na centrále (T12), storno mzdy na strane D (T16), faktúra
    zaúčtovaná na iné stredisko (T3). Každé menovite, verdikt NESEDÍ."""
    inp = _p2_dataset(tmpdir)
    _p2_post(inp, "2026-03", "OF2026000001", "15.03.2026", "311", "604", 50000.0, "S01", "Wholesale revenue")
    _p2_post(inp, "2026-04", "PK2026999999", "15.04.2026", "343", "604", 100.0, "S02", "VAT transfer")
    _p2_post(inp, "2026-05", "BV2026999998", "14.05.2026", "518200", "221", 5000.0, "C00", "Consulting")
    _p2_post(inp, "2026-06", "ID2026999997", "30.06.2026", "504", "132", 20000.0, "C00", "Goods sold")
    _p2_post(inp, "2026-07", "MZ2026999996", "31.07.2026", "331", "521", 2000.0, "S03", "Payroll correction")
    rc, out, _ = _p2_run(tmpdir, inp, truth=False)
    line = lambda cid: next(l for l in out.splitlines() if f"] {cid} —" in l)  # noqa: E731
    assert rc == 1 and "[PASS] journal_tb_match" in out, "the sabotage must be consistent in the journal and the trial balance"
    assert "S01 15.03.2026: revenue excl. VAT from receipts" in line("pos_gl_match"), line("pos_gl_match")
    assert "S02 15.04.2026: revenue excl. VAT from receipts" in out, line("pos_gl_match")
    assert "BV2026999998" in line("bank_ap_match") and "directly against the bank" in line("bank_ap_match"), line("bank_ap_match")
    assert "2026-06 C00: stock issued" in line("stock_consistency"), line("stock_consistency")
    assert "2026-07 S03: gross pay" in line("payroll_gl_match"), line("payroll_gl_match")


def test_full_check_invoice_moved_and_foreign_payment(tmpdir):
    """faktúra za nájom zaúčtovaná na iné stredisko (denník aj predvaha zhodne) →
    ap_gl_match; úhrada „Fiktívny Príjemca DEMO" z banky (interný tvar IBAN) s konzistentnými zostatkami →
    bank_ap_match (nie je faktúra ani menovitá interná platba)."""
    import csv
    import io
    inp = _p2_dataset(tmpdir)
    j = inp / "journal_2026-05.csv"
    rows = list(csv.reader(io.StringIO(j.read_bytes().decode("utf-8-sig"))))
    doc = next(r[0] for r in rows[1:] if r[2] == "518100" and r[5] == "S03")
    for r in rows[1:]:
        if r[0] == doc:
            r[5] = "S01"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    j.write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))
    from openpyxl import load_workbook
    f = inp / "trial_balance_2026-05.xlsx"
    wb = load_workbook(f); ws = wb["Trial balance"]
    for r in range(2, ws.max_row + 1):
        cc, acc = ws.cell(r, 2).value, str(ws.cell(r, 3).value)
        for x in [y for y in rows[1:] if y[0] == doc]:
            v = float(x[4])
            if acc == x[2] and cc in ("S01", "S03"):
                ws.cell(r, 5).value += v if cc == "S01" else -v
            if acc == x[3] and cc in ("S01", "S03"):
                ws.cell(r, 6).value += v if cc == "S01" else -v
    wb.save(f)
    b = inp / "bank_2026-06.csv"
    ls = b.read_text(encoding="utf-8").splitlines()
    ls.insert(5, "15.06.2026;Fictitious Payee DEMO;SK0000000000000000000002;;-500,00;EUR;Payment")
    close = ls[-1].split(";")
    from decimal import Decimal
    close[1] = str(Decimal(close[1].replace(",", ".")) - 500).replace(".", ",")
    ls[-1] = ";".join(close)
    b.write_text("\n".join(ls) + "\n", encoding="utf-8")
    rc, out, _ = _p2_run(tmpdir, inp, truth=False)
    line = lambda cid: next(l for l in out.splitlines() if f"] {cid} —" in l)  # noqa: E731
    assert rc == 1 and f"invoice {doc}: cost centre in the register S03 ≠ in the journal S01" in line("ap_gl_match"), line("ap_gl_match")
    assert "Fictitious Payee DEMO" in line("bank_ap_match") and "not an internal payment" in line("bank_ap_match"), line("bank_ap_match")


def test_full_check_stock_category_encoding(tmpdir):
    """prázdne skladové súbory (T11), preklep kategórie v pokladni (T15), záporné
    a nečíselné množstvo (T20), mzdy v UTF-8 namiesto cp1250 (T13a), stav skladu ≠ pohyby (T23)."""
    inp = _p2_dataset(tmpdir)
    (inp / "stock_moves_2026-03.csv").write_text("document;date;type;store;category;cost_value\n", encoding="utf-8")
    p = inp / "pos_S03_2025-05.csv"
    ls = p.read_text(encoding="utf-8").splitlines()
    ls[6] = ls[6].replace(";Toys;", ";Toyz;") if ";Toys;" in ls[6] else ls[6].replace(";Stationery;", ";Stationary;")
    f = ls[7].split(";")
    f[4] = "-7"
    ls[7] = ";".join(f)
    p.write_text("\n".join(ls) + "\n", encoding="utf-8")
    m = inp / "payroll_2025-09.csv"
    txt = m.read_bytes().decode("cp1250")       # anglické mzdy sú čisté ASCII — bez znaku mimo ASCII sa kódovanie nedá rozlíšiť
    assert "store manager" in txt
    m.write_bytes(txt.replace("store manager", "store manager – deputy", 1).encode("utf-8"))
    s = inp / "stock_levels_2025-11.csv"
    sl = s.read_text(encoding="utf-8").splitlines()
    x = sl[1].split(";")
    x[3] = f"{float(x[3]) + 10:.2f}"
    x[5] = f"{float(x[5]) + 10:.2f}"
    sl[1] = ";".join(x)
    s.write_text("\n".join(sl) + "\n", encoding="utf-8")
    rc, out, _ = _p2_run(tmpdir, inp, truth=False)
    line = lambda cid: next(l for l in out.splitlines() if f"] {cid} —" in l)  # noqa: E731
    assert rc == 1 and "stock movements: 2026-03 without data" in line("full_coverage"), line("full_coverage")
    assert "pos_S03_2025-05.csv r7: unreadable category" in line("stg_parse_contract"), line("stg_parse_contract")
    assert "pos_S03_2025-05.csv r8: unreadable quantity" in line("stg_parse_contract"), line("stg_parse_contract")
    assert "payroll_2025-09.csv: file is in UTF-8" in line("inputs_contract"), line("inputs_contract")
    assert "stock_levels_2025-11.csv" in line("stock_consistency") and "≠ movements" in out, line("stock_consistency")


def _p2_bank_add(inp, ym, row, delta):
    """Pohyb do bankového výpisu posledného mesiaca obdobia (2026-09) + konečný zostatok — výpis ostane celý."""
    from decimal import Decimal
    b = inp / f"bank_{ym}.csv"
    ls = b.read_text(encoding="utf-8").splitlines()
    ls.insert(5, row)
    close = ls[-1].split(";")
    close[1] = str(Decimal(close[1].replace(",", ".")) + Decimal(str(delta))).replace(".", ",")
    ls[-1] = ";".join(close)
    b.write_text("\n".join(ls) + "\n", encoding="utf-8")


def test_full_check_r2_cost_without_document_and_settlements(tmpdir):
    """náklad cez medziúčet bez dokladu (518200/379, 501/211), výplata „miezd"
    inou sumou s nákladom cez 331, nafúknutý úrok proti banke a poplatok za karty proti 315 — všetko
    konzistentne v denníku, predvahe aj banke. Predtým SEDÍ, teraz každé menovite."""
    inp = _p2_dataset(tmpdir)
    _p2_post(inp, "2026-03", "ID2026000001", "31.03.2026", "518200", "379", 5000.0, "C00", "IT accrual")
    _p2_post(inp, "2026-03", "ID2026000002", "31.03.2026", "501", "211", 800.0, "S01", "Small purchase")
    _p2_post(inp, "2026-09", "BV2026999997", "30.09.2026", "331", "221", 5000.0, "C00", "Payout")
    _p2_post(inp, "2026-09", "MZ2026999997", "30.09.2026", "521", "331", 5000.0, "C00", "Bonus")
    _p2_bank_add(inp, "2026-09", "30.09.2026;Payroll payout C00;SK0000000000000000000000;PAYROLL202609C00;-5000,00;EUR;Payout", -5000)
    _p2_post(inp, "2026-09", "BV2026999996", "30.09.2026", "562", "221", 2000.0, "C00", "Interest")
    _p2_bank_add(inp, "2026-09", "30.09.2026;Bank DEMO — loan;;LOAN;-2000,00;EUR;Extraordinary interest", -2000)
    _p2_post(inp, "2026-03", "BV2026999995", "31.03.2026", "568", "315", 700.0, "S01", "Card fee")
    rc, out, _ = _p2_run(tmpdir, inp, truth=False)
    line = lambda cid: next(l for l in out.splitlines() if f"] {cid} —" in l)  # noqa: E731
    assert rc == 1 and "[PASS] journal_tb_match" in out and "[PASS] bank_balance" in out, \
        "the sabotage must be consistent in the journal, the trial balance and the statement"
    assert "ID2026000001 518200/379" in line("posting_policy") and "ID2026000002 501/211" in line("posting_policy"), \
        line("posting_policy")
    assert "2026-09 C00 account 331: payment in the bank" in line("liability_settlement"), line("liability_settlement")
    assert "2026-09: interest 562" in line("loan_schedule"), line("loan_schedule")
    assert "2026-03 S01: fee 568" in line("card_settlement") and "+€700.00" in line("card_settlement"), \
        line("card_settlement")


def test_full_check_r3_legit_cases_pass_broken_fail(tmpdir):
    """legitímne situácie nesmú dať falošné NESEDÍ — vratka zákazníka v pokladni,
    posledná splátka úveru (zvyšok < splátka), vrátenie nadmerného odpočtu DPH. A zuby ostanú: vratka s kladnou
    sumou, iná posledná splátka, iné vrátenie DPH = FAIL."""
    import duckdb
    inp = _p2_dataset(tmpdir)
    prof = _p2_profile_copy(tmpdir, contract=False)       # upravená dodávka ≠ demo dodávka zmluvy
    f = inp / "pos_S01_2026-03.csv"
    ls = f.read_text(encoding="utf-8").split("\n")
    i = next(k for k, l in enumerate(ls) if l.startswith("S01-"))
    ls[i + 1:i + 1] = ["S01-1-9999990;31.03.2026 18:00;1;Books;1;4,77;5;4,77;cash",
                       "S01-1-9999991;31.03.2026 18:05;1;Books;-1;4,77;5;-4,77;cash"]
    f.write_text("\n".join(ls), encoding="utf-8")
    rc, out, _ = _p2_run_prof(tmpdir, prof, inp)
    assert rc == 0 and "[PASS] stg_parse_contract" in out, [l for l in out.splitlines() if "FAIL" in l]
    f.write_text(f.read_text(encoding="utf-8").replace(";-1;4,77;5;-4,77;cash", ";-1;4,77;5;4,77;cash"), encoding="utf-8")
    rc, out, _ = _p2_run_prof(tmpdir, prof, inp)
    assert rc == 1 and "quantity*price<>total" in out, "a refund with a positive amount must fail"
    c = duckdb.connect()
    c.execute("CREATE TABLE stg_journal(doklad VARCHAR, day DATE, md VARCHAR, d VARCHAR, amount DECIMAL(18,2), cc VARCHAR, ym VARCHAR)")
    loan = {"account": "461", "interest_account": "562", "rate_pa": 0.052, "monthly_repayment": 3000.0}
    base = [("PS1", "2025-01-01", "701", "461", 4000, "C00", "2025-01"), ("BV1", "2025-01-20", "562", "221", 17.33, "C00", "2025-01"),
            ("BV2", "2025-01-20", "461", "221", 3000, "C00", "2025-01"), ("BV3", "2025-02-20", "562", "221", 4.33, "C00", "2025-02")]
    c.executemany("INSERT INTO stg_journal VALUES (?,?,?,?,?,?,?)", base + [("BV4", "2025-02-20", "461", "221", 1000, "C00", "2025-02")])
    assert CHECKS["loan_schedule"](c, loan)[0], "last repayment = the rest of the loan is legitimate"
    c.execute("UPDATE stg_journal SET amount = 900 WHERE doklad = 'BV4'")
    ok, d, _ = CHECKS["loan_schedule"](c, loan)
    assert not ok and "2025-02: principal repayment" in d, d
    c.execute("DELETE FROM stg_journal")
    c.executemany("INSERT INTO stg_journal VALUES (?,?,?,?,?,?,?)",
                  [("FD1", "2025-01-10", "343", "321", 500, "S01", "2025-01"), ("BV1", "2025-02-25", "221", "343", 500, "C00", "2025-02")])
    vat = {"343": {"scope": "company", "rule": "balance"}}
    assert CHECKS["liability_settlement"](c, vat)[0], "a refund of excess VAT deduction is legitimate"
    c.execute("UPDATE stg_journal SET amount = 400 WHERE doklad = 'BV1'")
    ok, d, _ = CHECKS["liability_settlement"](c, vat)
    assert not ok and "account 343" in d, d


def _p2_profile_copy(tmpdir, sql_dir=None, contract=True):
    """Kópia profilu papiernictvo2 (komentáre kontrolóra, iná SQL vrstva, bez zmluvy pre inú dodávku než demo — zmluva
    viaže na jednu dodávku) — skutočný profil sa v teste nemení."""
    import json
    import shutil
    dst = tmpdir / "p2_profile"
    shutil.copytree(_P2, dst, ignore=shutil.ignore_patterns("data"))
    p = json.loads((dst / "profile.json").read_text(encoding="utf-8"))
    if sql_dir is not None:
        p["sql_dir"] = str(sql_dir)
    if not contract:
        p.pop("contract", None)
    (dst / "profile.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst


def _p2_run_prof(tmpdir, prof, inp, truth=False):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _engine().run(prof, inp, tmpdir / "p2_out", (_P2 / "truth.json") if truth is True else (truth or None))
    return rc, buf.getvalue(), tmpdir / "p2_out"


def test_bp_clean_board_pack(tmpdir):
    """Board pack na čistých dátach: odhad roka a plán sedia s kotvou A (generátor, 92 čísel), najväčšia odchýlka =
    nájom OC s príčinou „od 2026-04", riziká menujú hračky (sezónny podiel) a energie (zimný skok); komentáre stroja;
    šablóna komentárov pre kontrolóra vznikne; hárky spätne načítané vrátane textov."""
    from openpyxl import load_workbook
    rc, out, o = _p2_run(tmpdir, _p2_dataset(tmpdir))
    import re
    tm = re.search(r"truth_meter — (\d+)/(\d+) ", out)
    assert rc == 0 and tm and tm[1] == tm[2] and int(tm[1]) >= 100 and "[PASS] boardpack_consistency" in out, out[-900:]
    assert "texts of the board pack" in _line_of(out, "xlsx_readback"), _line_of(out, "xlsx_readback")
    wb = load_workbook(o / "overview.xlsx", read_only=True)
    assert {"Board pack", "Full-year forecast", "Variances", "Risks and opportunities", "Comments"} <= set(wb.sheetnames)
    var = list(wb["Variances"].iter_rows(values_only=True))
    assert var[1][0] == "Store OC · Rent" and var[1][5].startswith("since 2026-04, every month −€2"), var[1]
    ro = " ".join(str(r[3]) for r in list(wb["Risks and opportunities"].iter_rows(values_only=True))[1:])
    assert "Toys (decline" in ro and "Energy: in Q1 2026 +35.0%" in ro, ro
    kinds = {r[0]: r[1] for r in list(wb["Risks and opportunities"].iter_rows(values_only=True))[1:]}
    assert "forecast sensitivity" in kinds.values() and "risk" in kinds.values(), kinds
    com = list(wb["Comments"].iter_rows(values_only=True))[1:]
    assert com and all(r[5] == "machine" for r in com), com[:2]
    assert (o / "comments_template.xlsx").is_file(), "the comment template for the controller is missing"
    md = (o / "report.md").read_text(encoding="utf-8")
    assert "## Board pack" in md and "Rest-of-year forecast: month = month's plan ×" in md


def test_bp_controller_comments_override_and_stale(tmpdir):
    """Komentár kontrolóra z profilu nahradí vetu stroja (ďalší beh ho nezmaže, motor súbor nezapisuje); komentár písaný
    k inému číslu a komentár bez položky = menovité upozornenie v reporte."""
    import hashlib
    from openpyxl import Workbook, load_workbook
    prof = _p2_profile_copy(tmpdir)
    inp = _p2_dataset(tmpdir)
    rc, out, o = _p2_run_prof(tmpdir, prof, inp)        # čísla stroja zo šablóny tohto behu (nie natvrdo z dát)
    assert rc == 0, out[-600:]
    num = {r[0]: r[1] for r in list(load_workbook(o / "comments_template.xlsx", read_only=True).active.iter_rows(
        values_only=True))[1:]}
    v2, v3 = [k for k in num if k.startswith("variance|") and k != "variance|Store OC|Rent"][:2]
    wb = Workbook()
    ws = wb.active
    ws.title = "Comments"
    ws.append(["Key", "Number when written", "Controller comment"])
    ws.append(["variance|Store OC|Rent", num["variance|Store OC|Rent"],
               "New rent at OC from April —\nwe are negotiating a discount from 2027."])
    ws.append(["forecast|EBITDA", 150000.0, "The forecast is conservative."])
    ws.append(["forecast|Revenue", num["forecast|Revenue"], "Agreed.\n\n- EBITDA 2026 — forecast €250,000: vs plan +€31,086"])
    ws.append(["board|category_decline|Toys", -2.0, "Decline of only −2%, nothing serious."])
    ws.append([v2, num[v2], "See ![chart](http://x/y.png) and [here](javascript:alert(1))"])
    ws.append([v3, num[v3], "OK.<br><br>Net profit 2026 — forecast €150,000</li></ul><h3>Risks</h3>\u202eabc"])
    ws.append(["variance|Store XY|Rent", 1.0, "Old note."])
    f = prof / "comments.xlsx"
    wb.save(f)
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    for _ in range(2):                                  # druhý beh: komentár kontrolóra prežije (motor ho nezapisuje)
        rc, out, o = _p2_run_prof(tmpdir, prof, inp)
        assert rc == 0, out[-600:]
    assert hashlib.sha256(f.read_bytes()).hexdigest() == sha, "the engine must not overwrite the controller's comments"
    com = {r[0]: r for r in list(load_workbook(o / "overview.xlsx", read_only=True)["Comments"].iter_rows(values_only=True))[1:]}
    nj = com["variance|Store OC|Rent"]
    assert nj[4] == "[controller] New rent at OC from April — we are negotiating a discount from 2027. (machine number −€15,600)" and nj[5] == "controller", nj
    assert com["forecast|EBITDA"][4].startswith("EBITDA 2026 — forecast") and "⚠ controller comment is out of date" in com["forecast|EBITDA"][4], \
        "an out-of-date controller comment is not used — the machine sentence applies"
    assert com["board|category_decline|Toys"][5].startswith("controller out of date"), "a comment on a board finding goes out of date"
    md = (o / "report.md").read_text(encoding="utf-8")
    assert "- [controller] New rent at OC from April — we are negotiating a discount from 2027. (machine number" in md
    assert not any(l.startswith("- EBITDA 2026 — forecast €250") for l in md.splitlines()), "the controller comment produced a machine bullet"
    html = com[v3][4]
    assert "<" not in html and ">" not in html and "\u202e" not in html and html.startswith("[controller] OK.‹br›"), html
    assert "- [controller] See \\!\\[chart\\]\\(http://x/y.png\\) and \\[here\\]" in md, "the markdown of a controller comment must not render"
    assert "'forecast|EBITDA' was written for a different number" in md and "'variance|Store XY|Rent' has no item" in md, md[-1500:]
    tpl = {r[0]: r for r in list(load_workbook(o / "comments_template.xlsx", read_only=True).active.iter_rows(values_only=True))[1:]}
    assert tpl["variance|Store OC|Rent"][2].startswith("New rent"), "the template carries the controller comment forward"


def test_bp_not_issued_on_nesedi(tmpdir):
    """Pri NESEDÍ sa board pack nevydá — ani hárky, ani sekcia reportu, ani šablóna komentárov (čísla boardu)."""
    from openpyxl import load_workbook
    rc, out, o = _p2_run(tmpdir, _p2_dataset(tmpdir, "with_errors"), truth=False)
    assert rc == 1 and "VERDICT: DOES NOT TIE" in out
    names = set(load_workbook(o / "overview.xlsx", read_only=True).sheetnames)
    assert not names & {"Board pack", "Full-year forecast", "Variances", "Risks and opportunities", "Comments"}, names
    assert "## Board pack" not in (o / "report.md").read_text(encoding="utf-8")
    assert not (o / "comments_template.xlsx").exists()


def test_bp_consistency_teeth_plan_and_sql(tmpdir):
    """boardpack_consistency má zuby: účet plánu mimo výsledovky (plán by sa ticho stratil) a pokazená SQL vrstva
    board packu (minulý rok posunutý o mesiac) = FAIL menovite."""
    import shutil
    from openpyxl import load_workbook
    inp = _p2_dataset(tmpdir)
    (tmpdir / "_c").mkdir()
    inp_clean = _p2_dataset(tmpdir / "_c")                # druhá čistá kópia pre pokazenú SQL vrstvu
    f = inp / "plan_2026.xlsx"
    wb = load_workbook(f)
    ws = wb.active
    ws.append(["549", "S01"] + [100.0] * 12)
    wb.save(f)
    rc, out, _ = _p2_run(tmpdir, inp, truth=False)
    assert rc == 1 and "plan: account 549 is not mapped to the P&L" in _line_of(out, "boardpack_consistency"), \
        _line_of(out, "boardpack_consistency")
    sql = tmpdir / "sql_bad"
    shutil.copytree(ROOT / "sql" / "papiernictvo2", sql)
    b = sql / "40_boardpack.sql"
    t = b.read_text(encoding="utf-8")
    assert t.count("l.ym = m.ym_ly") == 1
    b.write_text(t.replace("l.ym = m.ym_ly", "l.ym = strftime(CAST(m.ym_ly || '-01' AS DATE) + INTERVAL 1 MONTH, '%Y-%m')"),
                 encoding="utf-8")
    rc, out, _ = _p2_run_prof(tmpdir, _p2_profile_copy(tmpdir, sql), inp_clean)
    assert rc == 1 and "last year: board pack ≠ second path" in _line_of(out, "boardpack_consistency"), \
        _line_of(out, "boardpack_consistency")
    for i, (old, new, want) in enumerate((("r.ytd_act - r.ytd_plan AS d_plan", "(r.ytd_act - r.ytd_plan) * 0.5 AS d_plan",
                            "variances: order or amount does not tie"),
                           ("       coalesce(l.amount, 0) AS ly\n",
                            "       coalesce(l.amount, 0) * CASE WHEN m.mo > 9 THEN 0.9 ELSE 1 END AS ly\n",
                            "last year: board pack ≠ second path"),
                           ("THEN g.plan * r.act_rr / r.plan_rr", "THEN g.plan * r.act_rr / r.plan_rr * 1.1",
                            "forecast: board pack ≠ second path"),
                           ("r.ytd_act - r.ytd_ly AS d_ly", "(r.ytd_act - r.ytd_ly) * 0.5 AS d_ly",
                            "variances: order or amount does not tie"),
                           ("LEFT JOIN pl_base a ON a.ym = m.ym AND",
                            "LEFT JOIN pl_base a ON a.ym = CASE WHEN m.mo = 3 THEN replace(m.ym, '-03', '-04') "
                            "WHEN m.mo = 4 THEN replace(m.ym, '-04', '-03') ELSE m.ym END AND",
                            "month 3 actual: board pack ≠ second path"),
                           ("ELSE coalesce(r.act_rr, 0) / par.runrate_months END AS amount,",
                            "ELSE coalesce(r.act_rr, 0) / par.runrate_months END + CASE WHEN g.row = 'Staff' "
                            "THEN (CASE g.shop WHEN 'Store Centrum' THEN 1000 WHEN 'Store Mesto' THEN -1000 "
                            "ELSE 0 END) ELSE 0 END AS amount,",
                            "Store Centrum · Staff · month 10 forecast"))):
        sql2 = tmpdir / f"sql_bad_{i}"
        shutil.copytree(ROOT / "sql" / "papiernictvo2", sql2)
        t2 = (sql2 / "40_boardpack.sql").read_text(encoding="utf-8")
        assert t2.count(old) == 1, old
        (sql2 / "40_boardpack.sql").write_text(t2.replace(old, new), encoding="utf-8")
        (tmpdir / "p2_profile").exists() and shutil.rmtree(tmpdir / "p2_profile")
        rc, out, _ = _p2_run_prof(tmpdir, _p2_profile_copy(tmpdir, sql2), inp_clean)
        assert rc == 1 and want in _line_of(out, "boardpack_consistency"), _line_of(out, "boardpack_consistency")


def test_p2_contract_clean_17_of_17(tmpdir):
    """Zmluva papiernictvo2: 17 čísel prečítaných z HOTOVÉHO overview.xlsx (board pack, Prehľad, P&L, odhad roka,
    odchýlky, riziká, vety) sedí s kotvou A (generátor) aj B (nezávislý skript naživo); podpis kontrolóra platí → odoslanie
    povolené (zmena zmluvy alebo kotiev by ho zneplatnila — mechanika testovaná na v1)."""
    rc, out, _ = _p2_run(tmpdir, _p2_dataset(tmpdir))
    assert rc == 0 and "[PASS] report_contract — 17/17" in out, [l for l in out.splitlines() if "report_contract" in l]
    assert "CONTRACT: RELEASE ALLOWED" in out and "signed by controller (demo) 2026-09-27" in out, out[-500:]


def test_p2_contract_teeth_output_layer(tmpdir):
    """chyba výstupnej vrstvy — iné číslo v Prehľade, v hárku Board pack alebo
    percento vo vete odhadu — prejde spätným načítaním aj etalónom, zmluva ju chytí menovite (obe kotvy)."""
    import json
    import re
    from openpyxl import load_workbook
    eng = _engine()
    inp = _p2_dataset(tmpdir)
    rc, out, o = _p2_run(tmpdir, inp)
    assert rc == 0, out[-400:]
    z = json.loads((_P2 / "contract.json").read_text(encoding="utf-8"))
    _, anchors = eng._contract_state(_P2, {"contract": "contract.json"}, inp)
    sha, status = eng.delivery_fingerprint(inp), {c: True for p_ in z["points"] for c in p_["checks"]}
    for sheet, match, col, new, want in (
            ("Overview", "Full-year EBITDA forecast (€)", 1, 808982.11, "P07 EBITDA — full-year forecast: report Overview!"),
            ("Board pack", "Net profit", 6, 1.0, "P11 Net profit — full-year forecast: report Board pack!"),
            ("Overview", "EBITDA 2026 — forecast", 1, None, "P17 EBITDA — full-year forecast vs full-year plan")):
        x = tmpdir / f"x_{len(want)}.xlsx"
        wb = load_workbook(o / "overview.xlsx")
        ws = wb[sheet]
        for r in ws.iter_rows():
            if isinstance(r[0].value, str) and r[0].value == match:
                r[col].value = new
            elif sheet == "Overview" and isinstance(r[col].value, str) and r[col].value.startswith(match):
                r[col].value = re.sub(r"(vs plan [^()]*\()[−+][\d.]+%", r"\g<1>+99.9%", r[col].value, count=1)
        wb.save(x)
        ok, d, _ = CHECKS["report_contract"](x, z, anchors, sha, status, None, "2026-09")
        assert not ok and want in d, (want, d)


def test_p2_contract_anchors_independent(tmpdir):
    """Kotva A = generátor (pregenerovanie = súbor), kotva B = skript naživo; zhodné na cent, patria commitnutej
    dodávke; skript B neimportuje pipeline/ ani DuckDB; dokument zmluvy menuje každé číslo P01–P17."""
    import ast
    import json
    import subprocess
    b_path = ROOT / "tools" / "golden_independent_papiernictvo2.py"
    r = subprocess.run([sys.executable, str(b_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    b = json.loads(r.stdout)
    g = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_papiernictvo2.py"), "--out", str(tmpdir / "g")],
                       capture_output=True, text=True)
    assert g.returncode == 0, g.stderr
    a = json.loads((_P2 / "golden_generator.json").read_text(encoding="utf-8"))
    assert json.loads((tmpdir / "g" / "golden_generator.json").read_text(encoding="utf-8"))["values"] == a["values"], \
        "anchor A ≠ generator"
    assert a["_meta"]["delivery_sha256"] == b["_meta"]["delivery_sha256"] == _engine().delivery_fingerprint(
        _P2 / "data" / "clean"), "the anchors do not belong to the committed delivery"
    for k, v in a["values"].items():
        assert abs(v - b["values"][k]) <= 0.005, (k, v, b["values"][k])
    tree = ast.parse(b_path.read_text(encoding="utf-8"))
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
        {a_.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a_ in n.names}
    assert not any(m.startswith(("pipeline", "engine", "checks", "duckdb", "gen_")) for m in mods), mods
    assert "pipeline" not in b_path.read_text(encoding="utf-8").split('"""', 2)[2], "anchor B must not touch pipeline/"
    bad = tmpdir / "bad_anchor.py"
    bad.write_text("from pipeline import checks\nimport duckdb\n", encoding="utf-8")
    assert _engine().anchor_imports_forbidden(bad) == ["duckdb", "pipeline"]
    assert _engine().anchor_imports_forbidden(b_path) == []
    z = json.loads((_P2 / "contract.json").read_text(encoding="utf-8"))
    doc = (ROOT / z["document"]).read_text(encoding="utf-8")
    assert [p_["id"] for p_ in z["points"]] == [f"P{i:02d}" for i in range(1, 18)]
    assert all(f"| {p_['id']} |" in doc for p_ in z["points"]), "the contract document does not name every figure"


def _b4_spy_run(tmpdir, inp, truth=True, prof=None):
    """Beh papiernictva2 so špiónmi: zachytí model panelu + results (argumenty control_panel_readback) a argumenty
    write_pivot (profil, marty) — teeth testy potom bijú hotové súbory a volajú kontroly s tými istými očakávaniami."""
    import contextlib
    import io
    eng = _engine()
    cap = {}
    real_cp, real_wp = eng.CHECKS["control_panel_readback"], eng.write_pivot

    def spy_cp(path, panel, results):
        cap["panel"], cap["results"] = panel, results
        return real_cp(path, panel, results)

    def spy_wp(out, profile, m):
        cap["pivot"] = (profile, m)
        cap["pivot_exp"] = real_wp(out, profile, m)
        return cap["pivot_exp"]
    eng.CHECKS["control_panel_readback"], eng.write_pivot = spy_cp, spy_wp
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = eng.run(prof or _P2, inp, tmpdir / "b4_out", (_P2 / "truth.json") if truth is True else (truth or None))
    finally:
        eng.CHECKS["control_panel_readback"], eng.write_pivot = real_cp, real_wp
    return rc, buf.getvalue(), tmpdir / "b4_out", cap


def test_b4_pivot_clean_and_teeth(tmpdir):
    """Pivotka na čistej dodávke: pivot.xlsx s tabuľkou Excelu Fakty + Pivot skutočnosť/plán + Návod; z disku
    == výsledovka na cent (pivot_pl_match) a == výpočet (xlsx_readback). Zuby: zmenený fakt, zmazaný fakt, zmenená
    bunka Pivotu, zmenený plán, text namiesto sumy, vzorec, chýbajúci hárok, chýbajúci súbor = FAIL menovite."""
    import shutil
    from openpyxl import load_workbook
    rc, out, o, cap = _b4_spy_run(tmpdir, _p2_dataset(tmpdir))
    assert rc == 0 and "[PASS] pivot_pl_match" in out and "[PASS] xlsx_readback — pivot" in out, out[-900:]
    path = o / "pivot.xlsx"
    wb = load_workbook(path)
    assert wb.sheetnames == ["Facts", "Pivot actual", "Pivot plan", "Guide"], wb.sheetnames
    assert "Facts" in wb["Facts"].tables and wb["Facts"].max_row > 1000, wb["Facts"].tables.keys()
    assert [r[0] for r in wb["Pivot actual"].iter_rows(min_row=2, values_only=True)] == _p2_profile()["pl_rows"]
    profile, m = cap["pivot"]
    exp, heads = cap["pivot_exp"]
    ok, d, _ = CHECKS["pivot_pl_match"](path, m["ytd"], m["bp_rows"], profile)
    assert ok, d
    ok, d, _ = CHECKS["xlsx_readback"](path, exp, None, unchecked_sheets=("Guide",), expected_headers=heads, main_sheet=None)
    assert ok, d

    def tamper(mode):
        p = tmpdir / f"piv_{mode}.xlsx"
        shutil.copy(path, p)
        wb = load_workbook(p)
        f = wb["Facts"]
        if mode == "edit":
            r = next(i for i in range(2, f.max_row + 1) if f.cell(i, 2).value == "actual" and f.cell(i, 3).value == "2026-03")
            f.cell(r, 10).value = f.cell(r, 10).value + 1
        elif mode == "delete":
            r = next(i for i in range(2, f.max_row + 1) if f.cell(i, 2).value == "actual" and f.cell(i, 3).value == "2026-05")
            for c in range(1, 12):
                f.cell(r, c).value = None
        elif mode == "pivot":
            wb["Pivot actual"].cell(2, 3).value = wb["Pivot actual"].cell(2, 3).value + 0.01
        elif mode == "plan":
            r = next(i for i in range(2, f.max_row + 1) if f.cell(i, 2).value == "plan" and f.cell(i, 3).value == "2026-02")
            f.cell(r, 10).value = f.cell(r, 10).value - 100
        elif mode == "text":
            f.cell(2, 10).value = "n/a"
        elif mode == "formula":
            f.cell(2, 10).value = "=SUM(1,2)"
        elif mode == "sheet":
            del wb["Pivot plan"]
        elif mode == "ly":
            r = next(i for i in range(2, f.max_row + 1) if f.cell(i, 2).value == "actual" and f.cell(i, 3).value == "2025-04")
            f.cell(r, 10).value = f.cell(r, 10).value + 1000
        elif mode == "ly_delete":
            r = next(i for i in range(2, f.max_row + 1) if f.cell(i, 2).value == "actual" and f.cell(i, 3).value == "2025-11")
            for c in range(1, 12):
                f.cell(r, c).value = None
        elif mode == "plan_future":   # plán 2026-11 + rovnaká zmena v hárku Pivot plán (konzistentný podvrh)
            r = next(i for i in range(2, f.max_row + 1) if f.cell(i, 2).value == "plan" and f.cell(i, 3).value == "2026-11"
                     and f.cell(i, 9).value == "Revenue")
            f.cell(r, 10).value = f.cell(r, 10).value + 1000
            wpl = wb["Pivot plan"]
            col = [c.value for c in wpl[1]].index("2026-11") + 1
            for rr in range(2, wpl.max_row + 1):
                if wpl.cell(rr, 1).value in ("Revenue", "Gross margin", "EBITDA", "EBIT", "Profit before tax", "Net profit"):
                    wpl.cell(rr, col).value += 1000
                    wpl.cell(rr, wpl.max_column).value += 1000
        elif mode == "account":
            f.cell(2, 7).value = "999999"
        elif mode == "total":
            wb["Pivot actual"].cell(2, wb["Pivot actual"].max_column).value += 1
        elif mode == "none":
            wb["Pivot actual"].cell(2, 3).value = None
        elif mode == "order":
            ws = wb["Pivot actual"]
            r2, r3 = [c.value for c in ws[2]], [c.value for c in ws[3]]
            for j, v in enumerate(r3 + r2, start=1):
                ws.cell(2 if j <= len(r3) else 3, j if j <= len(r3) else j - len(r3)).value = v
        elif mode == "dup_row":
            ws = wb["Pivot plan"]
            ws.append([c.value for c in ws[2]])
        wb.save(p)
        return p
    for mode in ("edit", "delete", "pivot", "plan", "text", "sheet", "ly", "ly_delete", "plan_future", "account", "total", "none",
                 "order", "dup_row"):
        ok, d, _ = CHECKS["pivot_pl_match"](tamper(mode), m["ytd"], m["bp_rows"], profile)
        assert not ok, f"{mode}: {d}"
    for mode in ("edit", "formula"):
        ok, d, _ = CHECKS["xlsx_readback"](tamper(mode), exp, None, unchecked_sheets=("Guide",), expected_headers=heads,
                                           main_sheet=None)
        assert not ok, f"{mode}: {d}"
    ok, d, _ = CHECKS["pivot_pl_match"](tmpdir / "none.xlsx", m["ytd"], m["bp_rows"], profile)
    assert not ok and "missing" in d, d
    ok, d, _ = CHECKS["pivot_pl_match"](path, m["ytd"], None, profile)
    assert not ok and "board pack" in d, d


def test_b4_run_db_and_evidence_sources(tmpdir):
    """DB behu (--db): raw/stg/core/mart + run_meta, check_results, panel_*, bp_* tabuľky; zdrojové SQL Evidence
    (evidence/sources/papiernictvo2/*.sql) nad ňou: pri SEDÍ board_rows == výsledovka motora na cent a fakty == mart,
    pri NESEDÍ board_rows, months a facts dávajú 0 riadkov (Evidence čísla boardu nezobrazí), panel_rows == protokol.
    Starý súbor DB neprežije beh (recept, nie koláč)."""
    import contextlib
    import io
    import duckdb
    eng = _engine()
    src = sorted((ROOT / "evidence" / "sources" / "papiernictvo2").glob("*.sql"))
    assert len(src) >= 10, src

    def run_db(name, truth):
        db = tmpdir / f"{name}.duckdb"
        db.write_bytes(b"old db")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = eng.run(_P2, _p2_dataset(tmpdir, name), tmpdir / f"o_{name}", (_P2 / "truth.json") if truth else None, db)
        con = duckdb.connect(str(db), read_only=True)
        q = {}
        for f in src:                                   # posledný stĺpec placeholder (Evidence: prázdny dotaz = 1 riadok)
            rows = con.execute(f.read_text(encoding="utf-8")).fetchall()
            cols = [d[0] for d in con.description]
            q[f.stem] = [r for r in rows if not (cols[-1] == "placeholder" and r[-1])]
        return rc, con, q
    rc, con, q = run_db("clean", True)
    assert rc == 0 and q["run_meta"][0][2] == "TIES", q["run_meta"]
    ytd = {(s, r): v for s, r, v in con.execute("SELECT shop, row, ytd_act FROM bp_rows").fetchall()}
    pl = {(s, r): v for _, s, r, _, v, *_ in q["board_rows"]}
    assert len(pl) == 96 and all(round(pl[k] - ytd[k], 2) == 0 for k in pl), "board_rows ≠ bp_rows"
    assert len(q["facts"]) == con.execute("SELECT count(*) FROM mart_facts").fetchone()[0] == 1805
    assert len(q["panel_rows"]) == 25 and {r[4] for r in q["panel_rows"]} <= {r[2] for r in q["check_results"]}, q["panel_rows"][:2]
    assert q["check_results"] and all(s == "PASS" for _, s, _, _ in q["check_results"]), q["check_results"][:3]
    assert q["panel_counts"] == [(25, 0, 0, 25)] and len(q["pivot_months"]) == 99, (q["panel_counts"], len(q["pivot_months"]))
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    assert {"stg_journal", "core_postings", "pl_base", "mart_facts", "bp_rows", "run_meta", "check_results", "panel_rows",
            "panel_errors", "panel_sources", "bp_ro_items", "bp_comments", "pl_rows"} <= tables, tables
    rc, con, q = run_db("with_errors", False)
    assert rc == 1 and q["run_meta"][0][2] == "DOES NOT TIE"
    empty = ("board_rows", "months", "facts", "ro", "comments", "variance", "findings", "pivot_months")
    assert all(q[k] == [] for k in empty), {k: len(q[k]) for k in empty}
    assert q["panel_counts"] == [(10, 13, 0, 23)], q["panel_counts"]
    assert len(q["panel_errors"]) == 30 and sum(1 for r in q["panel_rows"] if r[2] == "FAIL") == 13, len(q["panel_errors"])
    assert con.execute("SELECT count(*) FROM pl_base").fetchone()[0] > 0      # SQL vrstva ostáva viditeľná aj pri NESEDÍ


def _p2_profile():
    import json
    return json.loads((_P2 / "profile.json").read_text(encoding="utf-8"))


def test_b4_panel_errors_named_with_links(tmpdir):
    """Kontrolný panel na dodávke so zasadenými chybami: semafor 🔴 presne pre kontroly s FAIL v protokole, každý
    nález v hárku Chybné riadky s preklikom z panelu; E1 (faktúra r85) a bank_ap (r345) so súborom a riadkom,
    nálezy bez mena súboru s odvodeným súborom (mesiac × zdroje kontroly); každý odkaz vedie na existujúci súbor;
    zdroj Mzdy má 1 nečitateľný riadok (🔴); pivotka sa pri NESEDÍ nevydá — ani stará neprežije beh."""
    from openpyxl import load_workbook
    out_dir = tmpdir / "b4_out"
    out_dir.mkdir()
    (out_dir / "pivot.xlsx").write_bytes(b"old pivot")
    rc, out, o, cap = _b4_spy_run(tmpdir, _p2_dataset(tmpdir, "with_errors"), truth=False)
    assert rc == 1 and "VERDICT: DOES NOT TIE" in out and "[PASS] control_panel_readback" in out, out[-900:]
    assert not (o / "pivot.xlsx").exists(), "the pivot must not exist on DOES NOT TIE"
    fails = {ln.split("] ")[1].split(" —")[0] for ln in out.splitlines() if ln.startswith("[FAIL] ")}
    wb = load_workbook(o / "overview.xlsx")
    wp, we = wb["Control panel"], wb["Failed rows"]
    red = {r[2].value: r for r in wp.iter_rows(min_row=4) if r[0].value == "🔴 FAIL"}
    green = {r[2].value for r in wp.iter_rows(min_row=4) if r[0].value == "🟢 PASS"}
    assert set(red) == fails, (set(red) ^ fails)
    assert "loan_schedule" in green and "posting_policy" in green
    err = [(r[1].value, r[2].value, r[3].value, r[5].hyperlink.target if r[5].hyperlink else None)
           for r in we.iter_rows(min_row=2) if r[1].value]
    assert ("ap_gl_match", "invoices_2026-05.xlsx", 85, "../profiles/papiernictvo2/data/with_errors/invoices_2026-05.xlsx"
            ) not in err  # cesta je relatívna k výstupu v tmp, nie k repu — overuje sa existencia nižšie
    by = {}
    for cid, f, ln, href in err:
        by.setdefault(cid, []).append((f, ln, href))
    assert by["ap_gl_match"][0][:2] == ("invoices_2026-05.xlsx", 85), by["ap_gl_match"]
    assert by["bank_ap_match"][0][:2] == ("bank_2026-07.csv", 345), by["bank_ap_match"]
    assert by["journal_tb_match"][0][0] == "journal_2026-08.csv; trial_balance_2026-08.xlsx", by["journal_tb_match"]
    jr = next(r for r in we.iter_rows(min_row=2) if r[1].value == "journal_tb_match")     # každý odvodený súbor má odkaz
    assert jr[5].hyperlink and jr[6].hyperlink and jr[6].hyperlink.target.endswith("trial_balance_2026-08.xlsx") \
        and (o / jr[6].hyperlink.target).is_file(), [c.value for c in jr]
    assert wp["D1"].value == "Verdict: DOES NOT TIE"
    assert by["payroll_gl_match"][0][0] == "payroll_2026-06.csv; journal_2026-06.csv", by["payroll_gl_match"]
    assert sum(len(v) for v in by.values()) == sum(int(r[4].value) for r in red.values()), "findings ≠ failed rows"
    links = [href for _, _, _, href in err if href]
    assert len(links) >= 25 and all((o / h).is_file() for h in links), [h for h in links if not (o / h).is_file()]
    for cid, r in red.items():
        loc = r[5].hyperlink.location if r[5].hyperlink else None
        assert loc and loc.startswith("'Failed rows'!A"), (cid, loc)
        assert we[loc.split("!")[1]].offset(0, 1).value == cid, (cid, loc)
    src = {r[0].value: r for r in wp.iter_rows(min_row=4) if r[0].value in ("Payroll", "Journal")}
    assert src["Payroll"][4].value == 1 and src["Payroll"][5].value == "🔴 FAIL", [c.value for c in src["Payroll"]]
    assert src["Journal"][4].value == 0 and src["Journal"][5].value == "🟢 PASS"
    md = (o / "report.md").read_text(encoding="utf-8")
    assert "## Control panel" in md and "| 🔴 FAIL | Reconciliations source ↔ source | ap_gl_match | 1 |" in md


def test_b4_panel_teeth(tmpdir):
    """Zuby kontrolného panelu: v hotovom súbore prepnutý semafor, zmazaný chybný riadok, zrušený preklik, mŕtvy odkaz
    na súbor, iný počet riadkov zdroja, chýbajúca kontrola, kontrola navyše = FAIL menovite; kontrola bez skupiny
    v profile = FAIL a beh STOP so zmazaným výstupom (panel nesmie kontrolu ticho vynechať)."""
    import json
    import shutil
    from openpyxl import load_workbook
    from openpyxl.worksheet.hyperlink import Hyperlink
    rc, out, o, cap = _b4_spy_run(tmpdir, _p2_dataset(tmpdir, "with_errors"), truth=False)
    assert rc == 1 and "[PASS] control_panel_readback" in out
    path, panel, results = o / "overview.xlsx", cap["panel"], cap["results"]
    ok, d, _ = CHECKS["control_panel_readback"](path, panel, results)
    assert ok, d

    def tamper(mode):
        p = tmpdir / f"pan_{mode}.xlsx"
        shutil.copy(path, p)
        wb = load_workbook(p)
        wp, we = wb["Control panel"], wb["Failed rows"]
        row = next(r for r in wp.iter_rows(min_row=4) if r[2].value == "ap_gl_match")
        if mode == "light":
            row[0].value = "🟢 PASS"
        elif mode == "count":
            row[4].value = 0
        elif mode == "nolink":
            row[5].hyperlink = None
        elif mode == "wronglink":
            row[5].hyperlink = Hyperlink(ref=row[5].coordinate, location="'Failed rows'!A2")
        elif mode == "delete_err":
            e = next(r for r in we.iter_rows(min_row=2) if r[1].value == "stock_consistency")
            for c in e:
                c.value = None
            e[5].hyperlink = None
        elif mode == "dead_file":
            e = next(r for r in we.iter_rows(min_row=2) if r[1].value == "ap_gl_match")
            e[5].hyperlink = "../nowhere/invoices_2026-05.xlsx"
        elif mode == "source":
            s = next(r for r in wp.iter_rows(min_row=4) if r[0].value == "Payroll")
            s[4].value = 0
            s[5].value = "🟢 PASS"
        elif mode == "missing_check":
            for c in row:
                c.value = None
            row[5].hyperlink = None
        elif mode == "extra_check":
            wp.append(["🟢 PASS", "Reconciliations source ↔ source", "made_up_check", "everything ties", 0, None])
        elif mode == "nosheet":
            del wb["Failed rows"]
        elif mode == "verdict":
            wp["D1"].value = "Verdict: TIES"
        elif mode == "footnote":
            for r in wp.iter_rows():
                if isinstance(r[0].value, str) and r[0].value.startswith("On the finished file"):
                    r[0].value = "All checks passed."
        elif mode == "finding_text":
            e = next(r for r in we.iter_rows(min_row=2) if r[1].value == "ap_gl_match")
            e[4].value = "the invoice is fine"
        elif mode == "fake_cid_row":
            we.append([99, "made_up_check", None, None, "nothing", None])
        elif mode == "second_link_dead":
            e = next(r for r in we.iter_rows(min_row=2) if r[1].value == "journal_tb_match")
            e[6].hyperlink = "../nowhere/trial_balance_2026-08.xlsx"
        elif mode == "fake_row_passed":
            e = next(r for r in we.iter_rows(min_row=2) if r[1].value == "ap_gl_match")
            we.append([99, "inputs_contract", e[2].value, 1, "made-up finding", e[5].value])
            we.cell(we.max_row, 6).hyperlink = e[5].hyperlink.target
        elif mode == "link_label":
            e = next(r for r in we.iter_rows(min_row=2) if r[1].value == "ap_gl_match")
            e[5].value = "invoices_2026-01.xlsx"
        elif mode == "err_head":
            we["C1"].value = "File"
        elif mode == "panel_head":
            wp["A3"].value = "State"
        wb.save(p)
        return p
    for mode in ("light", "count", "nolink", "wronglink", "delete_err", "dead_file", "source", "missing_check",
                 "nosheet", "verdict", "footnote", "finding_text", "fake_cid_row", "second_link_dead", "fake_row_passed",
                 "link_label", "err_head", "panel_head"):
        ok, d, _ = CHECKS["control_panel_readback"](tamper(mode), panel, results)
        assert not ok, f"{mode}: {d}"
    ok, d, _ = CHECKS["control_panel_readback"](tamper("extra_check"), panel, results + [("made_up_check", True, "x", [])])
    assert not ok and "the panel model does not have it" in d, d
    # kontrola bez skupiny: profil, ktorému zo skupín vypadne ap_gl_match → beh STOP, výstup zmazaný
    prof = _p2_profile_copy(tmpdir, contract=False)
    pj = json.loads((prof / "profile.json").read_text(encoding="utf-8"))
    pj["control_panel"]["groups"]["Reconciliations source ↔ source"].remove("ap_gl_match")
    (prof / "profile.json").write_text(json.dumps(pj, ensure_ascii=False), encoding="utf-8")
    rc, out, o2 = _p2_run_prof(tmpdir, prof, tmpdir / "p2_with_errors", truth=False)   # tá istá dodávka s chybami
    assert rc == 1 and "[FAIL] control_panel_readback" in out and "checks without a group" in out and "ap_gl_match" in out, out[-700:]
    assert "ENGINE: STOP" in out and not (o2 / "overview.xlsx").exists() and not (o2 / "pivot.xlsx").exists()


