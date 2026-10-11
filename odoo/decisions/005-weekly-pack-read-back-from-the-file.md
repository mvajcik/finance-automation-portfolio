# 005 — The weekly pack is checked by reading the finished file, not the data that produced it

- **Date:** example
- **Decided by:** Finance (role)
- **Status:** example (fictional company)

## Context
The weekly pack (bills due this week by store, cost per store, open payables, bank open items)
is an Excel file that a manager opens. A number in that file is what gets acted on — not the
query that produced it.

## Options
1. **Trust the export** — compare the query result with itself; always green.
2. **Read the saved .xlsx back** and compare every cell with Odoo (bills, analytic lines,
   ledger, statement), then break the file on purpose and prove the check turns red.

## Decision
Option 2, the same pattern as the rest of this repository (`working-with-claude/skills/check-and-tamper`).
Five checks W1–W5; the pack is RELEASED only when all pass. Three tampers run live:
one cent on a bill, one open payable deleted, a value typed over the grand total.

## Consequences
- The checks are the slow part (a second XML-RPC round-trip); accepted.
- A check on the weekly pack without a tamper is not merged. The offline tests hold at least one
  tamper per check W1–W5. The statement checks B1–B5 of the import have no offline tampers yet;
  that gap is listed in the README under *Honest limits* until it is closed.

## How we will know it was wrong
A wrong number reaches a manager with the pack marked RELEASED. Then a check is missing, and the
first task is the tamper that would have caught it.
