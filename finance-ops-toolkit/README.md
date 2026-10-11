# Finance ops toolkit

Four everyday finance jobs for the fictional **Demo Retail s.r.o.** (four
stores, one head office), each with checks that block the output when the
numbers do not agree, and tamper tests that prove the checks can fail.

```bash
make demo   # from the repository root
make test
```

## (a) Payment list → SEPA XML

**Before:** payments retyped from an approved list into internet banking.
**Now:** the approved list becomes a bank file (pain.001.001.03).

| Step | Checks |
|---|---|
| Before any XML exists | I1 IBAN checksum · I2 amount > 0, max 2 decimals · I3 EUR only · I4 name valid for SEPA · I5 no duplicate payment · I6 list total = approved total · I7 business day |
| Read the finished XML back | R1 count: header = block = file = list · R2 control sum to the cent · R3 every payment matches the list 1:1 (IBAN, amount, currency, name, reference) · R4 debtor is the company account · R5 every creditor IBAN valid · R6 execution date = approved date |

Verdict: `RELEASED` or `BLOCKED`.

**See the output:** [sepa-payments.xml](../examples/finance-ops-toolkit/sepa-payments.xml) · [sepa-checks.txt](../examples/finance-ops-toolkit/sepa-checks.txt)

## (b) Bank reconciliation

**Before:** statement and ledger ticked off line by line.
**Now:** lines are matched by reference + amount, then by amount within a
3-day window (only if exactly one candidate — no guessing). What remains is an
open item, and **every open item must have a reason** or the month does not reconcile.

```
open item  2026-10-15     -3.84  SEPA TRANSFER FEES        Bank fee not yet booked in the ledger
open item  2026-10-22    250.00  TRANSFER RECEIVED         Unidentified receipt: ask the bank for the sender
open item  2026-10-30  -1465.90  Supplier Test Rent d.o.o. Payment booked, not yet debited by the bank (in transit)
```

Checks: B1 statement complete (opening + lines = closing) · B2 openings agree ·
B3 every line used exactly once · B4 ledger + open items = bank, to the cent ·
B5 every open item explained. Verdict: `RECONCILED` / `NOT RECONCILED`.

**See the output:** [bank-reconciliation.csv](../examples/finance-ops-toolkit/bank-reconciliation.csv) · [bank-reconciliation-checks.txt](../examples/finance-ops-toolkit/bank-reconciliation-checks.txt)

## (c) Payroll: attendance × payroll tape × report

**Before:** three documents from three systems, compared by eye.
**Now:** P1 same people everywhere · P2 hours on the tape = hours clocked
(incl. Sundays) · P3 gross = hours × rate + 50 % Sunday premium, to the cent ·
P4 net = gross − deductions · P5 management report = tape per store.
Verdict: `APPROVE` / `HOLD`.

## (d) Cash report

Cash flow by store from the ledger, written to Excel, then **read back from the
finished file** and tied out: M1 every cell = ledger · M2 totals add up (every row, and net cash flow of every column) ·
M3 opening + net flow = closing · M4 tie-out lands on the bank statement
(through the reconciliation in b) · M5 payroll outflow = net pay on the tape (c).

**See the output:** [cash-report.xlsx](../examples/finance-ops-toolkit/cash-report.xlsx)

## What these checks do not catch

A check list is only honest with its limits next to it. An independent review
of this toolkit found these gaps; they are left visible on purpose.

- **SEPA:** the execution date is checked for weekends, not for public holidays
  or a date in the past. The debtor name and BIC in the finished file are not
  compared with the company record (the debtor IBAN is).
- **Bank reconciliation:** an open item gets a *proposed* reason from its shape
  (fee, receipt without reference, payment in transit). The tool cannot know
  whether the reason is true: an unidentified receipt or a payment booked just
  before period end still needs a person to accept it. B4 follows from B1–B3
  and cannot fail on its own.
- **Cash report:** two errors of the same size and opposite sign inside the
  bank tie-out lines cancel out and are not seen.
- **All four:** the checks compare sources with each other. A document that is
  wrong at the source in every system passes.

## Data

`generate_data.py` creates every input from a fixed seed. Company, suppliers
and employees are invented; IBANs are SWIFT IBAN Registry examples.
