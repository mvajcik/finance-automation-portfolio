"""Offline tests: the bills plan, the CAMT file, the matcher. No Odoo needed."""
from datetime import date
from decimal import Decimal

import pytest

from demo_retail_odoo import camt, master_data as md
from demo_retail_odoo.import_camt import match

PLAN = md.bills_plan()


# ---- regression: the plan is deterministic and pinned
def test_plan_is_pinned():
    assert len(PLAN) == 70
    assert sum(md.bill_total(b) for b in PLAN) == Decimal("101036.86")
    assert md.bills_plan() == PLAN                      # same seed, same plan


def test_plan_every_ref_unique_and_every_line_has_a_store():
    refs = [b["ref"] for b in PLAN]
    assert len(refs) == len(set(refs))
    assert all(md.line_analytic(b, l) in md.STORES + [md.HQ] for b in PLAN for l in b["lines"])


def test_payment_week_is_iso_week():
    assert md.payment_week(date(2026, 9, 24)) == "2026-W39"
    assert md.payment_week(date(2026, 1, 1)) == "2026-W01"
    assert md.payment_week(date(2027, 1, 1)) == "2026-W53"    # ISO: 1 Jan 2027 belongs to week 53 of 2026


def test_vat_only_for_slovak_vendors():
    assert md.vat_rate("accounting") == Decimal("0.23")
    assert md.vat_rate("energy") == Decimal("0")
    sk = [b for b in PLAN if md.VENDOR[b["vendor"]]["country"] == "SK"]
    assert all(md.bill_total(b) > md.bill_net(b) for b in sk)


# ---- CAMT: what is written is what is read back, and the statement is complete
def test_camt_roundtrip_and_balances():
    lines = camt.statement_lines(PLAN)
    header, parsed = camt.parse_camt053(camt.build_camt053(lines))
    assert len(parsed) == len(lines) == 27
    assert header["opening"] == camt.OPENING_BALANCE
    assert header["opening"] + sum(l["amount"] for l in parsed) == header["closing"]
    assert [l["amount"] for l in parsed] == [l["amount"] for l in lines]
    assert sum(1 for l in lines if l["bill_ref"] and l["end_to_end"] == "NOTPROVIDED") == 4   # truncated references


def test_three_months_chain_and_every_due_bill_is_paid_once():
    sts = camt.statements(PLAN)
    assert [m for m, _, _, _ in sts] == [(2026, 7), (2026, 8), (2026, 9)]
    for i in range(1, len(sts)):
        assert sts[i][1] == camt.closing_balance(sts[i - 1][2], sts[i - 1][1])      # opening = previous closing
    paid = [l["bill_ref"] for _, _, lines, _ in sts for l in lines if l["bill_ref"]]
    assert len(paid) == len(set(paid))
    due_by_sept = {b["ref"] for b in PLAN if camt.business_day(b["due_date"]) <= date(2026, 9, 30)}
    assert set(paid) == due_by_sept - camt.UNPAID_REFS


def test_camt_unpaid_bill_stays_out_of_the_statement():
    refs = {l["bill_ref"] for l in camt.statement_lines(PLAN)}
    assert camt.UNPAID_REFS.isdisjoint(refs)
    assert all(camt.business_day(date(2026, 9, d)).weekday() < 5 for d in range(1, 31))


# ---- matcher: rules and their tampers
def _bills():
    return [{"id": 1, "ref": "A-1", "partner_id": [1, "Vendor A"], "amount_residual": Decimal("100.00"), "due": date(2026, 9, 10)},
            {"id": 2, "ref": "B-1", "partner_id": [2, "Vendor B"], "amount_residual": Decimal("250.00"), "due": date(2026, 9, 12)},
            {"id": 3, "ref": "B-2", "partner_id": [2, "Vendor B"], "amount_residual": Decimal("250.00"), "due": date(2026, 9, 13)}]


def _line(amount, name="", e2e="NOTPROVIDED", text="SUPPLIER PAYMENT", d="2026-09-10"):
    return {"ref": "x", "date": d, "amount": Decimal(amount), "end_to_end": e2e, "name": name, "iban": "", "text": text}


def test_r1_reference_and_amount():
    m, o = match([_line("-100.00", "Vendor A", e2e="A-1")], _bills())
    assert [b["ref"] for _, b, _ in m] == ["A-1"] and not o


def test_r1_reference_with_wrong_amount_is_an_open_item():
    m, o = match([_line("-100.01", "Vendor A", e2e="A-1")], _bills())      # one cent off
    assert not m and len(o) == 1


def test_r2_unique_amount_and_counterparty():
    m, o = match([_line("-100.00", "Vendor A", d="2026-09-12")], _bills())
    assert [r for _, _, r in m] == ["R2 counterparty + amount + date"] and not o


def test_r2_two_candidates_means_no_guess():
    m, o = match([_line("-250.00", "Vendor B", d="2026-09-12")], _bills())  # B-1 and B-2 both fit
    assert not m and "2 bills" in o[0][1]


def test_r2_outside_date_window_is_open():
    m, o = match([_line("-100.00", "Vendor A", d="2026-09-30")], _bills())
    assert not m and len(o) == 1


def test_open_items_get_a_reason():
    _, o = match([_line("-3.84", text="SEPA TRANSFER FEES"), _line("126.40", "Vendor A", text="REFUND"), _line("77.00", text="TRANSFER")], _bills())
    reasons = [r for _, r in o]
    assert "Bank fee" in reasons[0] and "refund" in reasons[1] and "Unidentified" in reasons[2]


def test_a_bill_is_matched_only_once():
    m, o = match([_line("-100.00", "Vendor A", e2e="A-1"), _line("-100.00", "Vendor A", e2e="A-1")], _bills())
    assert len(m) == 1 and len(o) == 1
