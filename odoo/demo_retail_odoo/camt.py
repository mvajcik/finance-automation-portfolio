"""Fictional CAMT.053 bank statements, one per month, derived from the bills plan.

The bank pays every bill due in the month on its due date (next business day if it falls on a
weekend). The statement also carries what a real statement carries and the ledger does not yet
know: two bank fees and one refund from a vendor. Every sixth payment loses its reference, the
way banks truncate remittance information — the matcher has to cope with that.

Written with the standard library only (xml.etree); namespace is the ISO 20022 camt.053.001.02.
"""
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal

from . import master_data as md

NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"
OPENING_BALANCE = Decimal("90000.00")          # opening of the first statement; each month opens where the last closed
STATEMENT_MONTH = (2026, 9)
STATEMENT_MONTHS = [(2026, 7), (2026, 8), (2026, 9)]
# bills whose payment the bank has NOT executed in the month (they stay open in the weekly pack)
UNPAID_REFS = {"DPS-202608-005"}        # due 24.9., paid in October: the classic month-end open payable

FEES = [(date(2026, 7, 15), Decimal("-3.12"), "SEPA TRANSFER FEES JULY"), (date(2026, 7, 31), Decimal("-12.50"), "ACCOUNT MAINTENANCE FEE"),
        (date(2026, 8, 14), Decimal("-3.60"), "SEPA TRANSFER FEES AUGUST"), (date(2026, 8, 31), Decimal("-12.50"), "ACCOUNT MAINTENANCE FEE"),
        (date(2026, 9, 15), Decimal("-3.84"), "SEPA TRANSFER FEES SEPTEMBER"), (date(2026, 9, 30), Decimal("-12.50"), "ACCOUNT MAINTENANCE FEE")]
REFUNDS = [(date(2026, 9, 21), Decimal("126.40"), "energy", "REFUND ANNUAL SETTLEMENT 2025")]


def business_day(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def statement_lines(plan=None, month=STATEMENT_MONTH):
    """The lines of the month's statement as plain dicts (date, amount, counterparty, iban, reference, text)."""
    plan = plan or md.bills_plan()
    y, m = month
    lines, n = [], 0
    for b in plan:
        pay = business_day(b["due_date"])
        if (pay.year, pay.month) != (y, m) or b["ref"] in UNPAID_REFS:
            continue
        v = md.VENDOR[b["vendor"]]
        n += 1
        truncated = n % 6 == 0
        lines.append({"date": pay, "amount": -md.bill_total(b), "name": v["name"], "iban": v["iban"] or "",
                      "end_to_end": "NOTPROVIDED" if truncated else b["ref"],
                      "text": "SUPPLIER PAYMENT" if truncated else f"INV {b['ref']}", "bill_ref": b["ref"]})
    for d, amt, text in FEES:
        if (d.year, d.month) != (y, m):
            continue
        lines.append({"date": d, "amount": amt, "name": "", "iban": "", "end_to_end": "NOTPROVIDED", "text": text, "bill_ref": None})
    for d, amt, vendor, text in REFUNDS:
        if (d.year, d.month) != (y, m):
            continue
        v = md.VENDOR[vendor]
        lines.append({"date": d, "amount": amt, "name": v["name"], "iban": v["iban"] or "", "end_to_end": "NOTPROVIDED",
                      "text": text, "bill_ref": None})
    lines.sort(key=lambda l: (l["date"], l["end_to_end"], l["text"]))
    return lines


def closing_balance(lines, opening=OPENING_BALANCE):
    return opening + sum(l["amount"] for l in lines)


def statements(plan=None, months=STATEMENT_MONTHS, opening=OPENING_BALANCE):
    """(month, opening, lines, document bytes) for every month; each month opens where the previous one closed."""
    out = []
    for month in months:
        lines = statement_lines(plan, month)
        out.append((month, opening, lines, build_camt053(lines, month, opening)))
        opening = closing_balance(lines, opening)
    return out


def _sub(parent, tag, text=None, **attrib):
    el = ET.SubElement(parent, f"{{{NS}}}{tag}", attrib)
    if text is not None:
        el.text = str(text)
    return el


def build_camt053(lines=None, month=STATEMENT_MONTH, opening=OPENING_BALANCE):
    """Return the CAMT.053 document as bytes."""
    lines = lines if lines is not None else statement_lines(month=month)
    y, m = month
    first = date(y, m, 1)
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    ET.register_namespace("", NS)
    root = ET.Element(f"{{{NS}}}Document")
    bk = _sub(root, "BkToCstmrStmt")
    hdr = _sub(bk, "GrpHdr")
    _sub(hdr, "MsgId", f"DEMO-STMT-{y}{m:02d}")
    _sub(hdr, "CreDtTm", f"{last.isoformat()}T23:59:00")
    st = _sub(bk, "Stmt")
    _sub(st, "Id", f"{y}{m:02d}-001")
    _sub(st, "ElctrncSeqNb", (y - 2026) * 12 + m)
    _sub(st, "CreDtTm", f"{last.isoformat()}T23:59:00")
    per = _sub(st, "FrToDt")
    _sub(per, "FrDtTm", f"{first.isoformat()}T00:00:00")
    _sub(per, "ToDtTm", f"{last.isoformat()}T23:59:59")
    acct = _sub(st, "Acct")
    _sub(_sub(acct, "Id"), "IBAN", md.COMPANY["iban"])
    _sub(acct, "Ccy", "EUR")
    _sub(_sub(acct, "Ownr"), "Nm", md.COMPANY["name"])
    for code, amount, d in (("OPBD", opening, first), ("CLBD", closing_balance(lines, opening), last)):
        bal = _sub(st, "Bal")
        _sub(_sub(_sub(bal, "Tp"), "CdOrPrtry"), "Cd", code)
        _sub(bal, "Amt", f"{abs(amount):.2f}", Ccy="EUR")
        _sub(bal, "CdtDbtInd", "CRDT" if amount >= 0 else "DBIT")
        _sub(_sub(bal, "Dt"), "Dt", d.isoformat())
    for i, l in enumerate(lines, 1):
        ntry = _sub(st, "Ntry")
        _sub(ntry, "NtryRef", f"{y}{m:02d}-{i:04d}")
        _sub(ntry, "Amt", f"{abs(l['amount']):.2f}", Ccy="EUR")
        _sub(ntry, "CdtDbtInd", "CRDT" if l["amount"] >= 0 else "DBIT")
        _sub(ntry, "Sts", "BOOK")
        _sub(_sub(ntry, "BookgDt"), "Dt", l["date"].isoformat())
        _sub(_sub(ntry, "ValDt"), "Dt", l["date"].isoformat())
        _sub(ntry, "AcctSvcrRef", f"ACSR{y}{m:02d}{i:05d}")
        dtls = _sub(_sub(ntry, "NtryDtls"), "TxDtls")
        _sub(_sub(dtls, "Refs"), "EndToEndId", l["end_to_end"])
        if l["name"]:
            side = "Cdtr" if l["amount"] < 0 else "Dbtr"
            parties = _sub(dtls, "RltdPties")
            _sub(_sub(parties, side), "Nm", l["name"])
            if l["iban"]:
                _sub(_sub(_sub(parties, side + "Acct"), "Id"), "IBAN", l["iban"])
        _sub(_sub(dtls, "RmtInf"), "Ustrd", l["text"])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_camt053(data):
    """Read a CAMT.053 file back into statement header + lines. Used by the import and by the checks."""
    root = ET.fromstring(data)
    ns = {"c": NS}
    st = root.find("c:BkToCstmrStmt/c:Stmt", ns)

    def amount(el):
        v = Decimal(el.find("c:Amt", ns).text)
        return v if el.find("c:CdtDbtInd", ns).text == "CRDT" else -v

    bal = {b.find("c:Tp/c:CdOrPrtry/c:Cd", ns).text: amount(b) for b in st.findall("c:Bal", ns)}
    header = {"id": st.find("c:Id", ns).text, "iban": st.find("c:Acct/c:Id/c:IBAN", ns).text,
              "from": st.find("c:FrToDt/c:FrDtTm", ns).text[:10], "to": st.find("c:FrToDt/c:ToDtTm", ns).text[:10],
              "opening": bal["OPBD"], "closing": bal["CLBD"]}
    lines = []
    for e in st.findall("c:Ntry", ns):
        tx = e.find("c:NtryDtls/c:TxDtls", ns)
        side = "Cdtr" if e.find("c:CdtDbtInd", ns).text == "DBIT" else "Dbtr"
        name = tx.find(f"c:RltdPties/c:{side}/c:Nm", ns)
        iban = tx.find(f"c:RltdPties/c:{side}Acct/c:Id/c:IBAN", ns)
        lines.append({"ref": e.find("c:NtryRef", ns).text, "date": e.find("c:BookgDt/c:Dt", ns).text,
                      "amount": amount(e), "end_to_end": tx.find("c:Refs/c:EndToEndId", ns).text,
                      "name": name.text if name is not None else "", "iban": iban.text if iban is not None else "",
                      "text": tx.find("c:RmtInf/c:Ustrd", ns).text})
    return header, lines


if __name__ == "__main__":
    import sys
    from pathlib import Path
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    for (y, m), opening, lines, data in statements():
        path = out_dir / f"camt053-{y}-{m:02d}.xml"
        path.write_bytes(data)
        h, ls = parse_camt053(data)
        print(f"{path}: {len(ls)} entries, opening {h['opening']:.2f}, closing {h['closing']:.2f}")
