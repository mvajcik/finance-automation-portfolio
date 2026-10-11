"""Payment list (CSV) -> SEPA credit transfer XML (pain.001.001.03).

The point is not the XML. The point is that nothing leaves the building
unless two independent sides agree:

  1. input checks   — is the payment list itself sane?  (before any XML exists)
  2. readback checks — read the finished XML back and prove it says exactly
                       what the approved list says, to the cent.

If any check fails, the XML is not released (status BLOCKED).
"""
import csv
import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import iban as ibanlib
from .checks import Result
from .company import COMPANY

NS = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
SEPA_CHARS = re.compile(r"^[A-Za-z0-9/\-?:().,'+ ]*$")


def read_payments(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _amount(raw):
    try:
        return Decimal(raw)
    except (InvalidOperation, TypeError):
        return None


def check_input(rows, approved_total: Decimal, execution_date: date) -> Result:
    r = Result()
    r.add("I1", "IBAN checksum (mod-97)",
          [f"row {i}: {p['iban']}" for i, p in enumerate(rows, 1) if not ibanlib.is_valid(p["iban"])])
    bad_amt = []
    for i, p in enumerate(rows, 1):
        a = _amount(p["amount"])
        if a is None or a <= 0 or a.as_tuple().exponent < -2:
            bad_amt.append(f"row {i}: {p['amount']!r}")
    r.add("I2", "Amount > 0 with max 2 decimals", bad_amt)
    r.add("I3", "Currency is EUR",
          [f"row {i}: {p['currency']}" for i, p in enumerate(rows, 1) if p["currency"] != "EUR"])
    r.add("I4", "Beneficiary name present, SEPA charset, <= 70 chars",
          [f"row {i}: {p['name']!r}" for i, p in enumerate(rows, 1)
           if not p["name"].strip() or len(p["name"]) > 70 or not SEPA_CHARS.match(_ascii(p["name"]))])
    seen, dups = set(), []
    for i, p in enumerate(rows, 1):
        key = (ibanlib.normalize(p["iban"]), _amount(p["amount"]), p["reference"])   # 120.5 == 120.50
        if key in seen:
            dups.append(f"row {i}: {p['name']} {p['amount']} {p['reference']}")
        seen.add(key)
    r.add("I5", "No duplicate payment (IBAN + amount + reference)", dups)
    total = sum((_amount(p["amount"]) or Decimal(0)) for p in rows)
    r.add("I6", "List total == approved total",
          [] if total == approved_total else [f"list {total} vs approved {approved_total}"])
    r.add("I7", "Execution date is a business day",
          [] if execution_date.weekday() < 5 else [f"{execution_date} is a weekend"])
    return r


def _ascii(s):
    # SEPA allows a Latin subset; diacritics are transliterated before sending
    table = str.maketrans("áäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽöüßÖÜ", "aacdeillnoorstuyzAACDEILLNOORSTUYZouSOU")
    return s.translate(table)


def build_xml(rows, execution_date: date, msg_id: str) -> bytes:
    ET.register_namespace("", NS)
    q = lambda t: f"{{{NS}}}{t}"
    total = sum(Decimal(p["amount"]) for p in rows)

    def sub(parent, tag, text=None, **attrib):
        el = ET.SubElement(parent, q(tag), attrib)
        if text is not None:
            el.text = str(text)
        return el

    doc = ET.Element(q("Document"))
    init = sub(doc, "CstmrCdtTrfInitn")
    hdr = sub(init, "GrpHdr")
    sub(hdr, "MsgId", msg_id)
    sub(hdr, "CreDtTm", f"{execution_date.isoformat()}T08:00:00")
    sub(hdr, "NbOfTxs", len(rows))
    sub(hdr, "CtrlSum", f"{total:.2f}")
    sub(sub(hdr, "InitgPty"), "Nm", COMPANY["name"])

    pmt = sub(init, "PmtInf")
    sub(pmt, "PmtInfId", f"{msg_id}-1")
    sub(pmt, "PmtMtd", "TRF")
    sub(pmt, "NbOfTxs", len(rows))
    sub(pmt, "CtrlSum", f"{total:.2f}")
    sub(sub(sub(pmt, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
    sub(pmt, "ReqdExctnDt", execution_date.isoformat())
    sub(sub(pmt, "Dbtr"), "Nm", COMPANY["name"])
    sub(sub(sub(pmt, "DbtrAcct"), "Id"), "IBAN", COMPANY["iban"])
    sub(sub(sub(pmt, "DbtrAgt"), "FinInstnId"), "BIC", COMPANY["bic"])
    sub(pmt, "ChrgBr", "SLEV")

    for i, p in enumerate(rows, 1):
        tx = sub(pmt, "CdtTrfTxInf")
        sub(sub(tx, "PmtId"), "EndToEndId", f"{msg_id}-{i:03d}")
        sub(sub(tx, "Amt"), "InstdAmt", f"{Decimal(p['amount']):.2f}", Ccy="EUR")
        sub(sub(tx, "Cdtr"), "Nm", _ascii(p["name"]))
        sub(sub(sub(tx, "CdtrAcct"), "Id"), "IBAN", ibanlib.normalize(p["iban"]))
        sub(sub(tx, "RmtInf"), "Ustrd", p["reference"])

    ET.indent(doc)
    return ET.tostring(doc, encoding="utf-8", xml_declaration=True)


def check_readback(xml_path, rows, execution_date: date) -> Result:
    """Re-read the finished file and compare it with the approved list and the approved execution date."""
    r = Result()
    ns = {"p": NS}
    root = ET.parse(xml_path).getroot()
    txs = root.findall(".//p:CdtTrfTxInf", ns)
    amounts = [Decimal(t.find("p:Amt/p:InstdAmt", ns).text) for t in txs]
    expected_total = sum(Decimal(p["amount"]) for p in rows)

    hdr_n = int(root.find(".//p:GrpHdr/p:NbOfTxs", ns).text)
    pmt_n = int(root.find(".//p:PmtInf/p:NbOfTxs", ns).text)
    r.add("R1", "Transaction count: header == block == file == list",
          [] if hdr_n == pmt_n == len(txs) == len(rows) else
          [f"header {hdr_n}, block {pmt_n}, file {len(txs)}, list {len(rows)}"])

    hdr_s = Decimal(root.find(".//p:GrpHdr/p:CtrlSum", ns).text)
    pmt_s = Decimal(root.find(".//p:PmtInf/p:CtrlSum", ns).text)
    r.add("R2", "Control sum: header == block == sum of payments == list (to the cent)",
          [] if hdr_s == pmt_s == sum(amounts) == expected_total else
          [f"header {hdr_s}, block {pmt_s}, payments {sum(amounts)}, list {expected_total}"])

    in_file = sorted((t.find("p:CdtrAcct/p:Id/p:IBAN", ns).text,
                      f"{Decimal(t.find('p:Amt/p:InstdAmt', ns).text):.2f}",
                      t.find("p:RmtInf/p:Ustrd", ns).text,
                      t.find("p:Amt/p:InstdAmt", ns).get("Ccy"),
                      t.find("p:Cdtr/p:Nm", ns).text) for t in txs)
    in_list = sorted((ibanlib.normalize(p["iban"]), f"{Decimal(p['amount']):.2f}", p["reference"],
                      p["currency"], _ascii(p["name"])) for p in rows)
    diff = [f"only in file: {x}" for x in sorted(set(in_file) - set(in_list))] + \
           [f"only in list: {x}" for x in sorted(set(in_list) - set(in_file))]
    if not diff and in_file != in_list:
        diff = ["same payments, different multiplicity (duplicate or missing copy)"]
    r.add("R3", "Every payment in the file matches the list 1:1 (IBAN, amount, currency, name, reference)", diff)

    dbtr = root.find(".//p:DbtrAcct/p:Id/p:IBAN", ns).text
    r.add("R4", "Debtor account is the company account",
          [] if dbtr == COMPANY["iban"] else [f"{dbtr}"])
    r.add("R5", "Every creditor IBAN passes mod-97",
          [t.find("p:CdtrAcct/p:Id/p:IBAN", ns).text for t in txs
           if not ibanlib.is_valid(t.find("p:CdtrAcct/p:Id/p:IBAN", ns).text)])
    dates = [e.text for e in root.findall(".//p:PmtInf/p:ReqdExctnDt", ns)]
    r.add("R6", "Execution date in the file == approved execution date",
          [] if dates == [execution_date.isoformat()] else
          [f"file {', '.join(dates) or 'none'}, approved {execution_date.isoformat()}"])
    return r


def run(payments_csv, approved_total, execution_date, out_dir, msg_id="DEMO-PAY-0001"):
    """Full flow. Returns (status, input_result, readback_result, xml_path|None)."""
    rows = read_payments(payments_csv)
    inp = check_input(rows, Decimal(approved_total), execution_date)
    if not inp.ok:
        return "BLOCKED", inp, None, None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    xml_path = out / f"{msg_id}.xml"
    xml_path.write_bytes(build_xml(rows, execution_date, msg_id))
    rb = check_readback(xml_path, rows, execution_date)
    return ("RELEASED" if rb.ok else "BLOCKED"), inp, rb, xml_path
