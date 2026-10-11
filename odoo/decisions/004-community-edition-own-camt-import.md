# 004 — Odoo Community, with the bank import and matching as our own script

- **Date:** example
- **Decided by:** Finance (role)
- **Status:** example (fictional company)

## Context
Odoo 17 Community has vendor bills, analytic accounts, bank statements and the full ledger.
It does *not* have the CAMT.053 import or the bank reconciliation screen — both are Enterprise
features. Demo Retail has one bank account and about thirty payments a month.

## Options
1. **Enterprise** — import and matching screen out of the box; a licence per user; rules live
   in the UI and are hard to test.
2. **Community + own import script over the ORM** — the CAMT file is parsed by our code, the
   statement lines are created through the API, and a line is matched to a bill only by rules
   we wrote down: reference + amount, else counterparty + amount + date with exactly one
   candidate. Everything else is an open item with a reason.

## Decision
Option 2, honestly labelled: this is not "Odoo does bank reconciliation", it is "our script does
it through Odoo's ORM". The matched line is reconciled the way Odoo's own widget does it
internally (the suspense counterpart is re-pointed to payables and reconciled with the bill),
so the result in the ledger is the standard one.

## Consequences
- The matching rules are code with tests, including the cases that must *not* match (one cent
  off, two candidates, outside the date window).
- Every run ends with a verdict: RECONCILED only if the statement is complete, every line is
  matched or explained, and Odoo's closing balance equals the file.
- If the company grows to many accounts or currencies, this decision is revisited.

## How we will know it was wrong
Open items that need a person every week above a handful, or a second bank account with a
different file format.
