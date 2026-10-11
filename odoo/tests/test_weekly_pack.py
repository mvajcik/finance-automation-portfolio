"""Offline tests of the weekly pack: write, read back, and every check has a tamper. No Odoo needed."""
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from demo_retail_odoo import weekly_pack as wp


def _src():
    bills = [
        {"ref": "A-1", "partner_id": [1, "Vendor A"], "invoice_date": "2026-09-10", "invoice_date_due": "2026-09-24",
         "x_payment_week": "2026-W39", "total": Decimal("123.00"), "residual": Decimal("0.00"), "payment_state": "paid",
         "stores": {"Store North": Decimal("100.00")}},
        {"ref": "B-1", "partner_id": [2, "Vendor B"], "invoice_date": "2026-09-12", "invoice_date_due": "2026-09-25",
         "x_payment_week": "2026-W39", "total": Decimal("61.50"), "residual": Decimal("61.50"), "payment_state": "not_paid",
         "stores": {"Store Centre": Decimal("50.00")}},
        {"ref": "C-1", "partner_id": [3, "Vendor C"], "invoice_date": "2026-09-20", "invoice_date_due": "2026-10-02",
         "x_payment_week": "2026-W40", "total": Decimal("24.60"), "residual": Decimal("24.60"), "payment_state": "not_paid",
         "stores": {"HQ": Decimal("20.00")}},
    ]
    matrix = {("2026-09", "Store North"): Decimal("100.00"), ("2026-09", "Store Centre"): Decimal("50.00"), ("2026-09", "HQ"): Decimal("20.00")}
    statements = [{"name": "STMT 1", "date": "2026-09-30", "opening": Decimal("1000.00"), "closing": Decimal("873.16"), "lines": [
        {"date": "2026-09-24", "amount": Decimal("-123.00"), "text": "INV A-1", "reconciled": True, "reason": ""},
        {"date": "2026-09-30", "amount": Decimal("-3.84"), "text": "FEES", "reconciled": False, "reason": "Bank fee"}]}]
    return {"week": "2026-W39", "company": "Demo Retail s.r.o.", "bills": bills, "matrix": matrix,
            "ledger_expense": Decimal("170.00"), "statements": statements}


@pytest.fixture
def pack(tmp_path):
    src = _src()
    path = tmp_path / "pack.xlsx"
    wp.write_pack(src, path)
    return src, path


def _failed(res):
    return {n.split()[0] for n, ok, _ in res if not ok}


def test_clean_pack_passes_every_check(pack):
    src, path = pack
    assert _failed(wp.checks(path, src)) == set()


def test_file_has_no_author_or_application_metadata(pack):
    import zipfile
    _, path = pack
    with zipfile.ZipFile(path) as z:        # the raw XML parts, not openpyxl's defaults
        core, app = z.read("docProps/core.xml").decode(), z.read("docProps/app.xml").decode()
    assert "dc:creator" not in core and "lastModifiedBy" not in core
    assert "Application" not in app and "Company" not in app


def test_tamper_one_cent_on_a_bill(pack):
    src, path = pack
    wp.tamper(path, "cent")
    assert {"W1", "W2"} <= _failed(wp.checks(path, src))


def test_tamper_deleted_open_payable(pack):
    src, path = pack
    wp.tamper(path, "row")
    assert "W4" in _failed(wp.checks(path, src))


def test_tamper_typed_over_grand_total(pack):
    src, path = pack
    wp.tamper(path, "total")
    assert "W3" in _failed(wp.checks(path, src))


def test_tamper_untagged_cost_in_the_ledger(pack):
    """A cost line without a store: the ledger grows, the analytic lines do not — W3 must see it."""
    src, path = pack
    src["ledger_expense"] += Decimal("0.01")
    assert "W3" in _failed(wp.checks(path, src))


def test_tamper_open_item_without_reason(tmp_path):
    src = _src()
    src["statements"][0]["lines"][1]["reason"] = ""
    path = tmp_path / "pack.xlsx"
    wp.write_pack(src, path)
    assert "W5" in _failed(wp.checks(path, src))


def test_tamper_closing_balance(pack):
    src, path = pack
    src["statements"][0]["closing"] += Decimal("1.00")       # Odoo says something else than the file
    assert "W5" in _failed(wp.checks(path, src))


def test_tamper_bill_missing_from_week(pack):
    src, path = pack
    src["bills"].append({"ref": "D-1", "partner_id": [4, "Vendor D"], "invoice_date": "2026-09-21", "invoice_date_due": "2026-09-26",
                         "x_payment_week": "2026-W39", "total": Decimal("10.00"), "residual": Decimal("10.00"),
                         "payment_state": "not_paid", "stores": {"HQ": Decimal("10.00")}})
    assert {"W1", "W2"} <= _failed(wp.checks(path, src))
