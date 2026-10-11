# 001 — Stores are analytic accounts in one company, not separate companies

- **Date:** example
- **Decided by:** Finance (role)
- **Status:** example (fictional company)

## Context
Demo Retail s.r.o. runs several stores under one legal entity. Management wants a
P&L per store every month; statutory reporting needs one set of books.

## Options
1. **One company per store** — clean store balance sheets; but intercompany
   entries for every shared cost, a VAT setup and a close per store.
2. **One company, stores as analytic accounts** — one close, one VAT return;
   store P&L comes from analytic tags on every revenue and cost line.

## Decision
Option 2. A store is a management view, not a legal entity; the cost of
intercompany bookkeeping is not justified by a balance sheet nobody asked for.

## Consequences
- Every POS, purchase and expense line must carry the store's analytic account;
  head-office costs get an "HQ" account and an allocation key.
- A monthly check: revenue by analytic account must equal revenue in the ledger
  (no untagged lines). This is the same readback idea as in `finance-ops-toolkit/`.

## How we will know it was wrong
Untagged lines above 1 % of monthly cost two months in a row, or a request for
store-level balance sheets from a bank or investor.
