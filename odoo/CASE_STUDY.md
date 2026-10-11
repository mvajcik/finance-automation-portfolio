# Case study — from ground zero to a weekly pack that checks itself

*Fictional company, generated data. The sequence and the lessons are real; the numbers are not.*

## Ground zero

A retail chain with three stores and a head office. Vendor bills arrive by e-mail, get paid
from one bank account once a week, and the month-end "cost per store" is a spreadsheet nobody
trusts because the store column is typed by hand. The bank statement is ticked off against the
bill folder, line by line.

The question was not "which ERP". It was: *what has to be true every week for the numbers to be
right, and how do we know?*

## Step 1 — one company, stores as a dimension

The first instinct is one company per store, because the board wants a P&L per store.
That buys a balance sheet per store nobody asked for, at the price of intercompany entries
on every shared cost. Decision 001: one legal entity, stores as analytic accounts.
The check that makes this safe is simple: analytic lines must equal ledger expense. If a cost
line has no store, the two totals differ by exactly that line.

## Step 2 — the store comes from a rule

Typing the store is the step that gets forgotten. Vendors with one location (the landlord, the
accountant) get a distribution model: vendor → store 100 %. Vendors serving all stores (energy,
cleaning, security) put one line per store on the bill. Decision 002.

What the demo taught us: a rule keyed on the vendor applies to *every* line with that vendor —
including the payable side of a bank payment. The first import wrote analytic lines for payments
and the store totals were too high by the sum of those payments. The check from step 1 caught it
(W3, analytic ≠ ledger), the import now clears the distribution on payment lines, and the lesson
is in the decision file. A check that only confirms is theatre; this one earned its place.

## Step 3 — the payment week is a decision, the due date is a fact

The weekly payment run groups bills by a field on the bill, `x_payment_week`, filled from the due
date and visible on the bill form. Finance can move a bill to another week without touching the
vendor's due date. Decision 003. No module: the field and the form line are created through the
ORM, so the setup is reproducible from one command.

## Step 4 — the bank, with rules written down

Odoo Community has no bank matching screen. Instead of buying it, the matching is a script with
two rules and a refusal to guess: a bill is matched when its reference appears in the payment and
the amount equals the open amount; or when the counterparty, the amount and a five-day window
point to exactly one bill. Two candidates are an open item, not a match. Decision 004.

Every statement line that is not matched carries a reason — a bank fee, a vendor refund without
a credit note, a receipt nobody recognises — and the month is RECONCILED only when the statement
is complete, every line is matched or explained, and the closing balance in Odoo equals the file.

## Step 5 — read the file, not the query

The weekly pack is an Excel file. The checks open that file again and compare it with Odoo:
bills of the week both ways, totals, the store matrix against the analytic lines and the ledger,
open payables, bank balances and reasons. Then the demo breaks the file on purpose — one cent on
a bill — and shows the pack turning BLOCKED. Decision 005; the same pattern as everywhere else in
this repository.

## What is deliberately left out

VAT is simplified (decision 006). The weekly reporting calendar of a real retailer, with its
own week numbering, is not modelled — ISO weeks are enough to show the mechanism. One bank
account, one currency, no opening balances.

## What a reader should take from it

- An ERP rollout is a list of decisions with a check attached to each. Write both down.
- The check must be able to fail. Break the output on purpose before anyone relies on it.
- "The system does X" and "our script does X through the system" are different sentences.
  Say the true one.
