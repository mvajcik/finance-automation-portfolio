# 002 — The store on a cost line comes from a rule, not from the person typing

- **Date:** example
- **Decided by:** Finance (role)
- **Status:** example (fictional company)

## Context
Every cost line needs a store (decision 001). Most vendors always belong to one place:
the landlord of Store North is never Store Centre; the accountant is always head office.
Typing the store on every line is the step that gets forgotten at month end.

## Options
1. **Store typed on every bill line** — flexible; depends on the person, fails silently.
2. **Analytic distribution models** — Odoo fills the store from the vendor (or product,
   account) automatically; the line can still be overridden when a vendor serves several stores.

## Decision
Option 2. Vendors with one location (rent, head-office services) get a distribution model
vendor → store 100 %. Vendors that serve all stores (energy, cleaning, security) put the store on
each line of the bill, one line per store.

## Consequences
- A new vendor needs one decision at onboarding: one store, or per line.
- A readback check must compare the analytic lines with the ledger: if any expense line has no
  store, the two totals differ. In the demo this is check W3 of the weekly pack.
- Lesson from the demo: a model keyed on the vendor applies to *every* line that carries the
  vendor — including the payable counterpart of a bank payment. The import script has to clear
  the distribution there explicitly, and W3 is the check that caught it.

## How we will know it was wrong
More than a handful of lines per month overridden by hand, or a vendor whose "one store" changes
every few months.
