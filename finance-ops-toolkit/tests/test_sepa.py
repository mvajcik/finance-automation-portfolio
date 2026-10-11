"""SEPA tool: the happy path, plus tampers.

A tamper deliberately breaks the input or the finished XML and asserts that
the checks catch it. A check that cannot fail is not a check.
"""
import csv
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from demo_retail import sepa

DATA = Path(__file__).parents[1] / "data"
APPROVAL = json.loads((DATA / "payments_approval.json").read_text(encoding="utf-8"))
EXEC = date.fromisoformat(APPROVAL["execution_date"])


def rows():
    return sepa.read_payments(DATA / "payments.csv")


def write_csv(path, rs):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rs[0]))
        w.writeheader()
        w.writerows(rs)
    return path


def failed(result):
    return {c.code for c in result.checks if not c.ok}


def test_clean_run_is_released(tmp_path):
    status, inp, rb, xml = sepa.run(DATA / "payments.csv", APPROVAL["approved_total"], EXEC, tmp_path)
    assert status == "RELEASED", (failed(inp), rb and failed(rb))
    assert xml.exists()


# --- input tampers: the XML must never be produced -------------------------

def _run_input(tmp_path, rs, total=None, when=EXEC):
    total = total if total is not None else sum(Decimal(r["amount"]) for r in rs)
    return sepa.run(write_csv(tmp_path / "p.csv", rs), total, when, tmp_path / "out")


def test_tamper_iban_typo(tmp_path):
    rs = rows()
    rs[3]["iban"] = rs[3]["iban"][:-1] + str((int(rs[3]["iban"][-1]) + 1) % 10)
    status, inp, _, xml = _run_input(tmp_path, rs)
    assert status == "BLOCKED" and "I1" in failed(inp) and xml is None


def test_tamper_three_decimals(tmp_path):
    rs = rows()
    rs[0]["amount"] = "120.005"
    status, inp, _, _ = _run_input(tmp_path, rs)
    assert status == "BLOCKED" and "I2" in failed(inp)


def test_tamper_duplicate_payment(tmp_path):
    rs = rows()
    rs.append(dict(rs[5]))
    status, inp, _, _ = _run_input(tmp_path, rs)
    assert status == "BLOCKED" and "I5" in failed(inp)


def test_tamper_list_differs_from_approval(tmp_path):
    rs = rows()
    status, inp, _, _ = _run_input(tmp_path, rs, total=Decimal(APPROVAL["approved_total"]) - Decimal("0.01"))
    assert status == "BLOCKED" and failed(inp) == {"I6"}


def test_tamper_weekend(tmp_path):
    status, inp, _, _ = _run_input(tmp_path, rows(), when=date(2026, 10, 10))
    assert status == "BLOCKED" and failed(inp) == {"I7"}


def test_tamper_missing_beneficiary_name(tmp_path):
    rs = rows()
    rs[1]["name"] = "   "
    status, inp, _, _ = _run_input(tmp_path, rs)
    assert status == "BLOCKED" and "I4" in failed(inp)


def test_tamper_duplicate_payment_amount_written_differently(tmp_path):
    rs = rows()
    twin = dict(rs[5])
    twin["amount"] = f"{Decimal(twin['amount']):.2f}0"   # same amount, one more trailing zero
    rs.append(twin)
    status, inp, _, _ = _run_input(tmp_path, rs)
    assert status == "BLOCKED" and "I5" in failed(inp)


def test_tamper_foreign_currency(tmp_path):
    rs = rows()
    rs[2]["currency"] = "CZK"
    status, inp, _, _ = _run_input(tmp_path, rs)
    assert status == "BLOCKED" and "I3" in failed(inp)


# --- output tampers: someone edits the finished XML ------------------------

@pytest.fixture
def released(tmp_path):
    status, _, _, xml = sepa.run(DATA / "payments.csv", APPROVAL["approved_total"], EXEC, tmp_path)
    assert status == "RELEASED"
    return xml


def _edit(xml, fn):
    xml.write_text(fn(xml.read_text(encoding="utf-8")), encoding="utf-8")
    return sepa.check_readback(xml, rows(), EXEC)


def test_tamper_xml_one_cent(released):
    def bump(x):
        m = re.search(r"<InstdAmt Ccy=\"EUR\">([\d.]+)</InstdAmt>", x)
        new = Decimal(m.group(1)) + Decimal("0.01")
        return x[:m.start(1)] + f"{new:.2f}" + x[m.end(1):]
    assert {"R2", "R3"} <= failed(_edit(released, bump))


def test_tamper_xml_dropped_payment(released):
    drop = lambda x: re.sub(r"\s*<CdtTrfTxInf>.*?</CdtTrfTxInf>", "", x, count=1, flags=re.S)
    assert {"R1", "R2", "R3"} <= failed(_edit(released, drop))


def test_tamper_xml_redirected_iban(released):
    redirect = lambda x: x.replace("NL91ABNA0417164300", "ES9121000418450200051332", 1)
    assert "R3" in failed(_edit(released, redirect))


def test_tamper_xml_invalid_creditor_iban(released):
    broken = lambda x: x.replace("NL91ABNA0417164300", "NL91ABNA0417164301", 1)
    assert {"R3", "R5"} <= failed(_edit(released, broken))


def test_tamper_xml_currency(released):
    usd = lambda x: x.replace('Ccy="EUR"', 'Ccy="USD"', 1)
    assert failed(_edit(released, usd)) == {"R3"}


def test_tamper_xml_beneficiary_name(released):
    def rename(x):
        m = re.search(r"<Cdtr>\s*<Nm>([^<]+)</Nm>", x)
        return x[:m.start(1)] + "Somebody Else Ltd" + x[m.end(1):]
    assert failed(_edit(released, rename)) == {"R3"}


def test_tamper_xml_wrong_debtor(released):
    debtor = lambda x: x.replace("SK3112000000198742637541", "FR1420041010050500013M02606", 1)
    assert failed(_edit(released, debtor)) == {"R4"}


def test_tamper_xml_execution_date(released):
    later = lambda x: re.sub(r"<ReqdExctnDt>[\d-]+</ReqdExctnDt>", "<ReqdExctnDt>2026-12-24</ReqdExctnDt>", x)
    assert failed(_edit(released, later)) == {"R6"}


def test_tamper_xml_header_sum_only(released):
    def hdr(x):
        return re.sub(r"(<GrpHdr>.*?<CtrlSum>)([\d.]+)", lambda m: m.group(1) + "1.00", x, count=1, flags=re.S)
    assert failed(_edit(released, hdr)) == {"R2"}


def test_tamper_xml_duplicated_payment(released):
    def dup(x):
        m = re.search(r"\s*<CdtTrfTxInf>.*?</CdtTrfTxInf>", x, flags=re.S)
        return x[:m.end()] + m.group(0) + x[m.end():]
    assert {"R1", "R3"} <= failed(_edit(released, dup))
