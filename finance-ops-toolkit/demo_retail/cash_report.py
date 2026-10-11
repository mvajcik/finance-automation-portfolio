"""Monthly cash report (cash flow by store) that ties to the cent.

Built from the ledger, written to Excel, then read back from the finished
file and tied out against three independent sources:
  the ledger (every cell), the bank statement (via the reconciliation)
  and the payroll tape (net payroll).
"""
import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .checks import Result

INFLOWS = ["Card receipts", "Cash receipts"]
OUTFLOWS = ["Goods", "Logistics", "Energy", "Rent", "Services", "Other", "Payroll"]
SHEET = "Cash report"


def _ledger(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute(ledger_csv, opening, stores):
    cols = stores + ["HQ"]
    cell = defaultdict(Decimal)
    for l in _ledger(ledger_csv):
        cell[(l["category"], l["store"])] += Decimal(l["amount"])
    rows = {cat: [cell[(cat, c)] for c in cols] for cat in INFLOWS + OUTFLOWS}
    net = [sum(rows[cat][i] for cat in rows) for i in range(len(cols))]
    total_net = sum(net)
    return {"cols": cols, "rows": rows, "net": net, "opening": Decimal(opening),
            "closing": Decimal(opening) + total_net}


def write_xlsx(model, recon, out_path):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    bold, grey = Font(bold=True), PatternFill("solid", fgColor="EEEEEE")
    line = Border(top=Side(style="thin"))
    ws.append(["Demo Retail s.r.o. — Cash report, October 2026 (EUR)"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["", *model["cols"], "Total"])
    for c in ws[3]:
        c.font, c.fill = bold, grey
        c.alignment = Alignment(horizontal="right")
    ws.append(["Opening balance", *[None] * len(model["cols"]), float(model["opening"])])
    for title, cats in (("Inflows", INFLOWS), ("Outflows", OUTFLOWS)):
        ws.append([title])
        ws.cell(ws.max_row, 1).font = bold
        for cat in cats:
            vals = model["rows"][cat]
            ws.append([f"  {cat}", *[float(v) if v else None for v in vals], float(sum(vals))])
    ws.append(["Net cash flow", *[float(v) for v in model["net"]], float(sum(model["net"]))])
    ws.append(["Closing balance (ledger 221)", *[None] * len(model["cols"]), float(model["closing"])])
    for r in (ws.max_row - 1, ws.max_row):
        for c in ws[r]:
            c.font, c.border = bold, line
    ws.append([])
    ws.append(["Tie-out to bank"])
    ws.cell(ws.max_row, 1).font = bold
    ws.append(["  Closing balance per ledger", *[None] * len(model["cols"]), float(model["closing"])])
    ws.append(["  + bank items not yet booked", *[None] * len(model["cols"]), float(recon["open_bank_sum"])])
    ws.append(["  + payments in transit (booked, not yet debited)", *[None] * len(model["cols"]), float(-recon["open_ledger_sum"])])
    ws.append(["  = Closing balance per bank statement", *[None] * len(model["cols"]),
               float(recon["bank_closing"])])
    ws.cell(ws.max_row, 1).font = bold
    ws.column_dimensions["A"].width = 38
    for i in range(len(model["cols"]) + 1):
        ws.column_dimensions[chr(ord("B") + i)].width = 15
    for row in ws.iter_rows(min_row=4, min_col=2):
        for c in row:
            c.number_format = "#,##0.00"
            c.alignment = Alignment(horizontal="right")
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    # no author, no company in the file metadata
    wb.properties.creator = None
    wb.properties.lastModifiedBy = None
    wb.properties.created = wb.properties.modified = datetime(2026, 9, 30, 8, 0)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def _d(v):
    # an empty cell in a value row means zero (the report leaves zeros blank for readability)
    return Decimal(str(v)).quantize(Decimal("0.01")) if v is not None else Decimal("0.00")


def readback(xlsx_path, model, recon, payroll_net):
    """Read the finished file and tie it out. Never trust the model that wrote it."""
    ws = load_workbook(xlsx_path, data_only=True)[SHEET]
    by_label = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        if row[0]:
            by_label[row[0].strip()] = [_d(v) for v in row[1:]]
    n = len(model["cols"])
    r = Result()

    cell_diff = []
    for cat in INFLOWS + OUTFLOWS:
        got = by_label.get(cat)
        exp = model["rows"][cat]
        if got is None:
            cell_diff.append(f"{cat}: row missing")
        elif got[:n] != exp:
            cell_diff.append(f"{cat}: file {got[:n]} vs ledger {exp}")
    r.add("M1", "Every store x category cell == ledger (to the cent)", cell_diff)

    row_diff = [cat for cat in INFLOWS + OUTFLOWS if cat in by_label
                and by_label[cat][n] != sum(v for v in by_label[cat][:n])]
    net = by_label.get("Net cash flow", [None] * (n + 1))
    for i in range(n + 1):   # net cash flow of every store, HQ and the total == sum of its column
        if net[i] != sum((by_label[c][i] for c in INFLOWS + OUTFLOWS if c in by_label), Decimal(0)):
            row_diff.append("Net cash flow" + ("" if i == n else f" ({model['cols'][i]})"))
    r.add("M2", "Totals in the file add up (rows and net cash flow)", row_diff)

    opening = by_label.get("Opening balance", [None] * (n + 1))[n]
    closing = by_label.get("Closing balance (ledger 221)", [None] * (n + 1))[n]
    r.add("M3", "Opening + net cash flow == closing == ledger closing",
          [] if opening is not None and net[n] is not None and opening + net[n] == closing == model["closing"]
          else [f"{opening} + {net[n]} vs {closing} vs ledger {model['closing']}"])

    bank_line = by_label.get("= Closing balance per bank statement", [None] * (n + 1))[n]
    tie = (by_label.get("Closing balance per ledger", [None] * (n + 1))[n] or 0) + \
          (by_label.get("+ bank items not yet booked", [None] * (n + 1))[n] or 0) + \
          (by_label.get("+ payments in transit (booked, not yet debited)", [None] * (n + 1))[n] or 0)
    r.add("M4", "Tie-out lands on the bank statement closing balance",
          [] if bank_line == tie == recon["bank_closing"] else
          [f"file {bank_line}, computed {tie}, statement {recon['bank_closing']}"])

    r.add("M5", "Payroll outflow == net pay on the payroll tape",
          [] if by_label.get("Payroll", [None] * (n + 1))[n] == -payroll_net else
          [f"file {by_label.get('Payroll', [None] * (n + 1))[n]} vs tape {-payroll_net}"])
    return r
