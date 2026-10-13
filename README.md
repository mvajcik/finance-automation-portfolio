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
| ERP set up by hand, bank ticked off line by line, cost per store typed | [`odoo/`](odoo/) — Odoo 17 Community demo from one command: stores as analytic accounts, CAMT import + matching over the ORM, weekly pack · [see the output](examples/odoo/weekly-verdict-2026-W39.html) and the [decision log](odoo/decisions/) | Setup read back bill by bill; the month is RECONCILED only if every bank line is matched or explained; the weekly pack is read back from the saved Excel and tied to the ledger |
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
chain. When every check passes, the board pack is issued:

![Board pack](docs/img/pipeline-board-pack.png)

**See the output:** [one-page management summary](examples/reporting-pipeline/management-summary.pdf) · full detail: [board-pack.pdf](examples/reporting-pipeline/board-pack.pdf) · [board-pack.xlsx](examples/reporting-pipeline/board-pack.xlsx)

When the delivery contains errors (here 7 were planted on purpose), there is no
board pack. Instead, the control panel names each failed reconciliation, the
file, the row and the amount:

![Control panel with caught errors](docs/img/pipeline-control-panel.png)

**See the output:** [one page on what failed and where](examples/reporting-pipeline/errors-summary.pdf) · full detail: [control-panel-with-errors.pdf](examples/reporting-pipeline/control-panel-with-errors.pdf) · all example files: [`examples/`](examples/)

## Try it

Every path below ends with the same command, `make demo`, and the same result. Pick the row that fits you:

| You have | Path | What you install |
|---|---|---|
| Only a web browser (Windows, Mac, anything) | [A. Binder](#a-in-the-browser-no-account-binder) | nothing, no account |
| A GitHub account | [B. Codespaces](#b-in-the-browser-with-a-github-account-codespaces) | nothing |
| A Mac or Linux and you are fine with a terminal | [C. On your computer](#c-on-your-mac-or-linux) | Python 3.12+, `git`, `make` |
| Windows and you want it on your computer | [D. Windows with WSL](#d-on-windows-with-wsl) | WSL (Ubuntu) |

On Windows the easy way is A or B. The demo does not run in plain PowerShell or Command Prompt.

### A. In the browser, no account (Binder)

1. Open **<https://mybinder.org/v2/gh/mvajcik/finance-automation-portfolio/main?urlpath=lab>**
2. Wait until JupyterLab opens. Usually a minute or two; the first start after a change in this repository takes longer.
3. Click the **Terminal** tile, type `make demo` and press Enter.

Binder is a free public service: it can be slow or busy, and the session disappears after a few minutes without activity.

### B. In the browser, with a GitHub account (Codespaces)

1. Sign in to GitHub and open **<https://codespaces.new/mvajcik/finance-automation-portfolio>**, then click **Create codespace**.
2. Wait about a minute for the editor to open. If it asks whether you trust the authors, click **Trust Folder & Continue**.
3. In the **Terminal** panel at the bottom, type `make demo` and press Enter.
4. When you are done, delete the codespace at <https://github.com/codespaces> (three dots → Delete) so it does not use up your free hours.

### C. On your Mac or Linux

Requires Python 3.12 or newer, `git` and `make`. On a Mac, `git` and `make` come with the Xcode Command Line
Tools (`xcode-select --install`); the `python3` that comes with macOS is too old, install a current one from
[python.org](https://www.python.org/downloads/). The block can be pasted into a terminal as it is:

```bash
git clone https://github.com/mvajcik/finance-automation-portfolio.git
cd finance-automation-portfolio
make demo
```

### D. On Windows, with WSL

1. Open PowerShell as administrator, run `wsl --install` and restart the computer. This installs Ubuntu.
2. Open **Ubuntu** from the Start menu and paste:

```bash
sudo apt update && sudo apt install -y git make python3-venv
git clone https://github.com/mvajcik/finance-automation-portfolio.git
cd finance-automation-portfolio
make demo
```

### What you should see

The first run creates a virtual environment, installs the packages and generates the data, then runs every
tool. It takes about a minute. The lines that matter:

```text
TOOLKIT: 4/4 tools PASS, every live tamper caught
   checks PASS: 29, FAIL: 0
   VERDICT: TIES — output exports/papiernictvo2/overview.xlsx
   checks FAIL: 13
   VERDICT: DOES NOT TIE — output exports/papiernictvo2_errors/overview.xlsx
######## demo finished: every step above ended as expected ########
```

TIES: the clean delivery passed all 29 checks and the board pack was issued. DOES NOT TIE: the second delivery
has 7 errors planted on purpose, the checks caught them and no board pack was issued. Both are the expected
result.

### How this is tested

[![demo](https://github.com/mvajcik/finance-automation-portfolio/actions/workflows/demo.yml/badge.svg)](https://github.com/mvajcik/finance-automation-portfolio/actions/workflows/demo.yml)

On every change, `make demo` runs automatically on Linux and macOS (Python 3.12 and 3.14, together with
`make test`) and on Windows inside WSL Ubuntu. Paths A and B were run by hand in a browser.

### Further commands

Run from the same folder:

| Command | What it does |
|---|---|
| `make test` | all checks and tamper tests (about 2 minutes) |
| `make test-fast` | the same without the reporting pipeline (seconds) |
| `make odoo-demo` | the Odoo 17 Community demo (needs Docker; own containers on port 8071) |

## About the data

- **Demo Retail s.r.o.** and **papiernictvo2** (a fictional stationery chain) are
  invented. Their data is produced by generators in this repository. The Odoo demo uses the
  same Demo Retail fiction with three of its stores.
- IBANs in the finance ops toolkit are official example IBANs from the SWIFT IBAN
  Registry; the reporting pipeline generator uses obviously fake ones (zeros and nines).
- Names of suppliers and employees are invented and intentionally read as fake.
- All outputs are in English. The fictional company is Slovak, so account numbers follow the Slovak chart of
  accounts and a few names are Slovak (*Papiernictvo* = stationery shop). Comments inside the reporting pipeline
  code are in Slovak.
