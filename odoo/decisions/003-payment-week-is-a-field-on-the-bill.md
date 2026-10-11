# 003 — The payment week is a field on the bill, not a formula in a spreadsheet

- **Date:** example
- **Decided by:** Finance (role)
- **Status:** example (fictional company)

## Context
Payments go out once a week. The weekly list ("what do we pay this week") used to be a
spreadsheet column computed from the due date, re-done by hand when a bill was postponed.
Two people, two spreadsheets, two answers.

## Options
1. **Compute the week from the due date at report time** — nothing to maintain; cannot express
   "postponed to next week" without changing the due date, which is a fact from the vendor.
2. **A custom field `x_payment_week` on the vendor bill** — filled automatically from the due
   date (ISO week, e.g. 2026-W39), visible on the bill form, editable when finance decides to
   pay later or earlier.

## Decision
Option 2. A custom field created through the ORM (no module, no code deployed into Odoo), shown
on the bill next to the due date. The weekly pack groups by this field only.

## Consequences
- One place to look: filter bills by payment week in the standard list view.
- The field is a *decision*, the due date is a *fact*; the two can differ on purpose.
- The readback check W1 compares the week sheet with Odoo's bills for that week both ways:
  nothing missing, nothing extra.

## How we will know it was wrong
Weeks with many manual changes to the field, or two bills of one vendor in different weeks for
no reason — then a payment term or a vendor rule is what is missing.
