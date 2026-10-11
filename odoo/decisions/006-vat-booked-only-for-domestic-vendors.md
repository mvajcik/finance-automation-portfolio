# 006 — Simplification kept on purpose: VAT only on domestic vendors, no reverse charge

- **Date:** example
- **Decided by:** Finance (role)
- **Status:** example (fictional company) — a known simplification, not a recommendation

## Context
The demo has Slovak vendors (23 % VAT on the bill) and vendors with foreign example IBANs.
Real intra-EU purchases carry reverse-charge VAT: a tax line in and out, net effect zero,
reported on the VAT return.

## Options
1. **Model reverse charge** — the Slovak chart has the taxes; the demo gains VAT-return detail
   and loses clarity about what it is showing (payables, matching, store P&L).
2. **Book foreign vendors net, domestic vendors with 23 %** and say so.

## Decision
Option 2 for the demo. The point of the demo is the control chain (bill → store → bank → weekly
pack), not the VAT return.

## Consequences
- The VAT return of Demo Retail would be wrong; the ledger totals of expenses, payables and
  bank are right.
- A real rollout reverses this decision on day one: tax positions by vendor country, with a check
  that every foreign vendor bill carries the reverse-charge taxes.

## How we will know it was wrong
Someone reads the demo as tax advice.
