# Odoo rollout — a working demo and its decision log

A fictional retail chain, **Demo Retail s.r.o.** (three stores and a head office), set up in
**Odoo 17 Community** from one command, with the controls a finance team actually needs around
an ERP: every cost lands on a store, the bank statement is matched to bills by written rules,
and the weekly pack is read back from the finished Excel file before anyone sees it.

No Odoo Enterprise code, no module to install, no secrets: everything goes through the ORM
over XML-RPC with the standard library. The decisions behind the setup are in
[`decisions/`](decisions/); the story in [`CASE_STUDY.md`](CASE_STUDY.md).

```bash
make odoo-demo        # from the repository root; needs Docker (its own containers, port 8071)
make odoo-test        # offline tests: plan, CAMT, matcher, weekly-pack tampers — no Docker
make odoo-demo-down   # remove the demo containers and their data
```

Then open http://127.0.0.1:8071 (admin / admin, database `demo_retail`).

## What `make odoo-demo` does

| Step | What happens | How you know it is right |
|---|---|---|
| 1 Setup | Database with the Slovak chart of accounts, company, analytic plan *Stores* (3 stores + HQ), distribution models vendor → store, custom field `x_payment_week` on the bill form, 20 vendors, 70 posted vendor bills for July–September 2026 | **Readback:** bills in Odoo = the plan, bill by bill, to the cent, and every line has a store — else exit 1 |
| 2 Bank statements | A fictional CAMT.053 per month; each opens where the previous closed; every sixth payment has its reference truncated the way banks do | B1 opening + lines = closing |
| 3 Import + matching | Statement lines created over the ORM; matched to bills by **R1** reference + amount, else **R2** counterparty + amount + date with exactly one candidate; everything else is an open item with a reason | B2 Odoo closing = file · B3 every line matched or explained · B4 every matched bill shows *paid* · B5 bank account in the ledger = statement movements. Verdict `RECONCILED` / `NOT RECONCILED` |
| 4 Weekly pack | Excel: bills due in the payment week by store · net cost per store and month · open payables · bank open items | **Read back from the saved file:** W1 bills = Odoo both ways · W2 totals · W3 store matrix = analytic lines = ledger expense (no untagged line) · W4 open payables · W5 bank balances and reasons. Verdict `RELEASED` / `BLOCKED`, also as an HTML page |
| 5 Tampers | Three breaks of the finished file, one at a time: one cent on a bill, an open payable deleted, a value typed over the grand total | Each must be `BLOCKED` (W1+W2, W4, W3), or the demo fails |

Outputs land in `odoo/out/`; committed copies are in [`../examples/odoo/`](../examples/odoo/).

## Honest limits

- **Community has no bank reconciliation screen and no CAMT import** — both are Enterprise.
  The import and the matching here are this repository's scripts. A matched line is reconciled
  the way Odoo's own widget does it internally (the suspense counterpart is re-pointed to
  payables and reconciled with the bill with the standard `reconcile()`), so the ledger result
  is the standard one — but a person opens the statement line in Odoo, not a matching screen.
- **R2 never guesses.** Two open bills of the same vendor with the same amount in the window
  make an open item, not a match. That is the point.
- **The proposed reason of an open item comes from its shape** (fee, refund, unidentified).
  The script cannot know whether it is true; a person accepts it.
- **VAT is simplified:** 23 % on Slovak vendors, foreign vendors booked net, no reverse charge
  ([decision 006](decisions/006-vat-booked-only-for-domestic-vendors.md)).
- **The bank account has no opening entry in the ledger**, so B5 compares movements, not
  balances. A real rollout books the opening balance first.
- **One company, one bank account, EUR only.**
- **The import checks B1–B5 have no offline tamper tests yet** — the matcher rules R1/R2 do
  (one cent off, two candidates, outside the window, a bill matched twice). Closing that gap is
  the next task on this folder.

## Decision log

| # | Decision |
|---|---|
| [001](decisions/001-stores-as-analytic-accounts.md) | Stores are analytic accounts in one company, not separate companies |
| [002](decisions/002-distribution-models-decide-the-store.md) | The store on a cost line comes from a rule (distribution model), not from the person typing |
| [003](decisions/003-payment-week-is-a-field-on-the-bill.md) | The payment week is a field on the bill, not a spreadsheet formula |
| [004](decisions/004-community-edition-own-camt-import.md) | Community edition, with the bank import and matching as our own tested script |
| [005](decisions/005-weekly-pack-read-back-from-the-file.md) | The weekly pack is checked by reading the finished file, with a tamper per check |
| [006](decisions/006-vat-booked-only-for-domestic-vendors.md) | Simplification kept on purpose: VAT only on domestic vendors |

Template: [`decisions/000-template.md`](decisions/000-template.md).

## Files

```
docker-compose.yml          odoo:17.0 + postgres:15, port 8071, project name demo-retail
demo_retail_odoo/
  rpc.py                    XML-RPC client, database creation, module install
  master_data.py            company, stores, 20 vendors, the deterministic bills plan
  setup_demo.py             steps 1 + readback
  camt.py                   CAMT.053 writer and parser
  import_camt.py            statement import, matching rules R1/R2, reconciliation, checks B1–B5
  weekly_pack.py            Excel writer, readback checks W1–W5, tampers
  verdict_html.py           the one-page verdict
tests/                      offline: plan pinned, CAMT round trip, matcher rules and tampers, pack tampers
```

## About the data

Everything is invented and produced from a fixed seed. Vendor names are built to read as fake.
Eleven vendors carry official *example* IBANs from the SWIFT IBAN Registry; nine have no bank
account on file, so their payments appear in the statement without a counterparty IBAN, like
direct debits do. The company itself does not exist.
