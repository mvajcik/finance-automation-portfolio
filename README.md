# Finance automation portfolio

**A finance controller's toolkit for numbers that have to be right before anyone sees them.**

I work as a financial controller, not a software engineer. Over the past year I
have used AI (Claude) to automate the parts of finance work that are repetitive,
error-prone and expensive when they go wrong: monthly reporting, payment runs,
bank reconciliation, payroll checks and management reports.

Everything in this repository runs on **fictional companies and generated data**.
No client, employer or person is represented here.

## What problems this solves

| Problem in a finance team | What is here | How you know it is right |
|---|---|---|
| Monthly reporting from many sources takes days and breaks silently | [`reporting-pipeline/`](reporting-pipeline/) — source files → checks → board pack in Excel · [see the output](examples/reporting-pipeline/board-pack.pdf) | 12 source-to-source reconciliations; the board pack is not issued if any fails |
| Payment runs typed or copied by hand | [`finance-ops-toolkit/`](finance-ops-toolkit/) (a) — payment list → SEPA XML · [see the output](examples/finance-ops-toolkit/sepa-payments.xml) | The finished XML is read back and must equal the approved list to the cent |
| Bank statement matched line by line | (b) bank reconciliation · [see the output](examples/finance-ops-toolkit/bank-reconciliation.csv) | Every line matched or listed as an open item with a reason |
| Payroll: attendance, payroll tape and report disagree | (c) payroll three-way check | Hours × rate = tape = report, per employee |
| Management cash report built by hand | (d) cash report · [see the output](examples/finance-ops-toolkit/cash-report.xlsx) | Ties to the ledger to the cent |
| ERP rollout decisions get lost | [`odoo/`](odoo/) — implementation decisions log | — |
| "How do you actually work with AI?" | [`working-with-claude/`](working-with-claude/) — templates and skills I use daily | — |

## The one idea behind all of it

**A check that cannot fail is not a check.**

Every tool here checks its own output, and every check in the finance ops
toolkit has a *tamper test*: the
test deliberately breaks the data (one cent, a swapped IBAN, a missing row) and
proves the check catches it. If a check stays green while the data is wrong,
the test suite fails.

`make demo` runs every tool on the fictional data, then breaks each output once
on purpose and shows which check caught it:

![make demo output](docs/img/toolkit-demo.png)

The cash report is read back from the finished Excel file and tied to the
ledger, the bank statement and the payroll tape, to the cent:

![Cash report](docs/img/cash-report.png)

**See the output:** [cash-report.xlsx](examples/finance-ops-toolkit/cash-report.xlsx) · [SEPA XML](examples/finance-ops-toolkit/sepa-payments.xml) and [its checks](examples/finance-ops-toolkit/sepa-checks.txt)

## Reporting pipeline in two pictures

Nine kinds of source files, 21 months, about 380,000 rows for a fictional stationery
chain. When every check passes, the board pack is issued (labels are in Slovak:
*Tržby* = revenue, *Odhad roka* = full-year forecast):

![Board pack](docs/img/pipeline-board-pack.png)

**See the output:** one-page management summary [in English](examples/reporting-pipeline/management-summary-en.pdf) / [po slovensky](examples/reporting-pipeline/management-summary-sk.pdf) · full detail: [board-pack.pdf](examples/reporting-pipeline/board-pack.pdf) · [board-pack.xlsx](examples/reporting-pipeline/board-pack.xlsx)

When the delivery contains errors (here 7 were planted on purpose), there is no
board pack. Instead, the control panel names each failed reconciliation, the
file, the row and the amount:

![Control panel with caught errors](docs/img/pipeline-control-panel.png)

**See the output:** one page on what failed and where [in English](examples/reporting-pipeline/errors-summary-en.pdf) / [po slovensky](examples/reporting-pipeline/errors-summary-sk.pdf) · full detail: [control-panel-with-errors.pdf](examples/reporting-pipeline/control-panel-with-errors.pdf) · all example files: [`examples/`](examples/)

## Try it

Requires Python 3.11+ and `make`.

```bash
git clone <this repo>
cd finance-automation-portfolio
make demo   # runs every tool on the fictional data and prints the verdicts
make test   # all checks and tamper tests (about 2 minutes; `make test-fast` skips the pipeline)
```

## About the data

- **Demo Retail s.r.o.** and **papiernictvo2** (a fictional stationery chain) are
  invented. Their data is produced by generators in this repository.
- IBANs in the finance ops toolkit are official example IBANs from the SWIFT IBAN
  Registry; the reporting pipeline generator uses obviously fake ones (zeros and nines).
- Names of suppliers and employees are invented and intentionally read as fake.
- The reporting pipeline keeps its original Slovak labels; this README and the
  finance-ops-toolkit are in English.
