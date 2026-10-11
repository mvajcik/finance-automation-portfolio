"""Payroll three-way check: attendance x payroll tape x management report.

Three documents describe the same month from three systems (time clock,
payroll provider, management report). They must tell the same story,
per employee and per store, before the payroll is approved.
"""
import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .checks import Result

CENT = Decimal("0.01")
SUNDAY_PREMIUM = Decimal("0.5")


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(attendance_csv, tape_csv, report_csv):
    att, tape, rep = _read(attendance_csv), _read(tape_csv), _read(report_csv)
    r = Result()

    hours, sunday = defaultdict(Decimal), defaultdict(Decimal)
    for a in att:
        h = Decimal(a["hours"])
        hours[a["employee_id"]] += h
        if date.fromisoformat(a["date"]).weekday() == 6:
            sunday[a["employee_id"]] += h

    ids_att, ids_tape = set(hours), {t["employee_id"] for t in tape}
    r.add("P1", "Same people in attendance and on the payroll tape",
          [f"only in attendance: {i}" for i in sorted(ids_att - ids_tape)] +
          [f"only on tape: {i}" for i in sorted(ids_tape - ids_att)])

    r.add("P2", "Hours on tape == hours clocked (total and Sunday), per employee",
          [f"{t['employee_id']}: tape {t['hours']}/{t['sunday_hours']} vs clock {hours[t['employee_id']]}/"
           f"{sunday[t['employee_id']]}" for t in tape
           if Decimal(t["hours"]) != hours[t["employee_id"]] or Decimal(t["sunday_hours"]) != sunday[t["employee_id"]]])

    bad_gross = []
    for t in tape:
        rate = Decimal(t["hourly_rate"])
        expected = (hours[t["employee_id"]] * rate + sunday[t["employee_id"]] * rate * SUNDAY_PREMIUM) \
            .quantize(CENT, ROUND_HALF_UP)
        if Decimal(t["gross"]) != expected:
            bad_gross.append(f"{t['employee_id']}: tape {t['gross']} vs recomputed {expected}")
    r.add("P3", "Gross pay == clocked hours x rate (+50 % Sunday premium), to the cent", bad_gross)

    r.add("P4", "Net == gross - deductions, per employee",
          [t["employee_id"] for t in tape
           if Decimal(t["net"]) != Decimal(t["gross"]) - Decimal(t["deductions"])])

    by_store = defaultdict(lambda: [0, Decimal(0), Decimal(0)])
    for t in tape:
        s = by_store[t["store"]]
        s[0] += 1
        s[1] += Decimal(t["hours"])
        s[2] += Decimal(t["gross"])
    store_diff = []
    for row in rep:
        exp = by_store.get(row["store"], [0, Decimal(0), Decimal(0)])
        got = [int(row["headcount"]), Decimal(row["hours"]), Decimal(row["gross"])]
        if got != exp:
            store_diff.append(f"{row['store']}: report {got[0]}/{got[1]}/{got[2]} vs tape {exp[0]}/{exp[1]}/{exp[2]}")
    missing = set(by_store) - {row["store"] for row in rep}
    store_diff += [f"{s}: missing in report" for s in sorted(missing)]
    r.add("P5", "Management report == tape per store (headcount, hours, gross)", store_diff)

    totals = {"employees": len(tape), "hours": sum(Decimal(t["hours"]) for t in tape),
              "gross": sum(Decimal(t["gross"]) for t in tape), "net": sum(Decimal(t["net"]) for t in tape)}
    return ("APPROVE" if r.ok else "HOLD"), r, totals
