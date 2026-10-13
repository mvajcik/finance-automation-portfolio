# Reporting pipeline — from nine messy source files to a board pack you can sign

**The problem.** A monthly board pack is built from many systems: tills, the accounting journal, the trial
balance, the purchase ledger, payroll, the bank, stock. Each export has its own quirks (semicolons, decimal
commas, Windows-1250 encoding, totals in a footer row). Copy-paste reporting breaks silently: one truncated
till export or one hand-edited trial-balance cell and the EBITDA the board reads is wrong — and nobody knows.

**What this does.** One command turns 21 months of source files for a fictional stationery chain
(*Papiernictvo DEMO s.r.o.*, 4 stores + head office, ~380,000 rows) into an Excel board pack — but only after
every source has been reconciled against an independent one. If anything does not tie, the board pack is
**not issued**; you get a control protocol that names the file, the row and the amount instead.

```
sources (9 kinds)    →  load as received  →  21 checks         →  P&L, plan vs actual, full-year forecast
                                                    │                              │
                                              any FAIL = DOES NOT TIE       board pack in Excel,
                                              (protocol only)               read back from disk
                                                                            and checked against a
                                                                            signed "report contract"
```

## What is checked (examples)

| Reconciliation | What it catches |
|---|---|
| Till export total row == sum of receipts | a truncated export |
| Journal == trial balance, per month × cost centre × account, to the cent | a hand-edited trial balance |
| Till sales == cash/card accounts and revenue account, per store per day | sales not booked, or booked twice |
| Bank statement == bank account in the ledger, per day; opening balance == last closing balance | a missing or duplicated statement |
| Every bank payment has an invoice or a named internal transfer | a payment to an unknown supplier |
| Payroll export == wage cost accounts | payroll booked with the wrong amount |
| Purchase ledger == journal (number, account, cost centre, month, amount) | an invoice never booked |
| Stock: no negative stock, movements == stock change == accounts 132/504 | issues without stock |
| Card fees == card sales − amounts the bank credited | a missing card settlement |
| Board pack == a second, independent calculation path, to the cent | a bug in the reporting SQL |

On top of that, 17 numbers the board actually reads (revenue, EBITDA, net profit — actual, plan, forecast —
plus the largest variance and risks) are compared **from the finished Excel file** with two anchors computed
outside the engine. That is the *report contract* (`profiles/papiernictvo2/CONTRACT.md`); changing it or the
anchors invalidates the sign-off.

**See the output:** [one-page management summary](../examples/reporting-pipeline/management-summary.pdf) · when the checks fail, [one page on what failed and where](../examples/reporting-pipeline/errors-summary.pdf) · [board-pack.pdf](../examples/reporting-pipeline/board-pack.pdf) · [board-pack.xlsx](../examples/reporting-pipeline/board-pack.xlsx) · [control panel of a delivery with 7 planted errors](../examples/reporting-pipeline/control-panel-with-errors.pdf)

## Run it

```bash
make demo   # generates the data, runs the clean delivery (TIES) and a delivery with 7 planted errors (DOES NOT TIE)
make test   # 24 tests: clean run, each planted error named, teeth of every check (~2 min)
```

`make demo` takes about 15 seconds once set up. The very first run also creates the virtual environment and
installs three packages (time depends on your network) and generates the data (about 10 seconds). Output: `exports/papiernictvo2/overview.xlsx` (board pack, P&L, variances,
risks and opportunities, control panel), `exports/papiernictvo2/pivot.xlsx` (flat facts table for a pivot) and
`summary.html` — one readable page for a manager (`tools/summary_page.py`). The page only
reads the finished workbook: every figure comes from the board pack sheets, and the only arithmetic on the page is
two summed lines, the differences and the percentages, all derived from those figures. Its "when it arose"
column is calculated from the monthly pattern; it is not an explanation of the cause, and the page says how many
comments still wait for the controller.

The data is produced by a deterministic generator (`tools/gen_papiernictvo2.py`): same seed, byte-identical
files. All companies, suppliers and IDs are invented; tax rates and public holidays are public Slovak
parameters; other calibration values are labelled `BEST GUESS` in `calibration.json`.

## Language

Every output is in English: source files, workbooks, check messages, the summary page. The fictional company
is Slovak, so account numbers follow the Slovak chart of accounts (604 revenue, 221 bank, 321 suppliers) and
document types keep their short codes (PK till, FD supplier invoice, BV bank statement, MZ payroll). Comments
inside the code are in Slovak.

## How to view the dashboard (optional)

The same numbers are available as a browser dashboard built with [Evidence](https://evidence.dev), reading
the run database (`warehouse/papiernictvo2.duckdb`). It needs Node.js 18+ and is not part of `make demo`:

```bash
make demo-clean            # writes warehouse/papiernictvo2.duckdb
cd evidence
npm install
npm run sources            # database → parquet for the pages
npm run dev                # opens http://localhost:3000
```

`python tools/evidence_check.py` then proves the dashboard shows the same numbers as the Excel file, to the
cent (`--tamper` proves the comparison can fail).

## Layout

```
pipeline/   engine.py (one engine, company = profile) · checks.py (all checks) · boardpack.py
sql/        papiernictvo2/ 10_stg → 20_core → 30_mart → 40_boardpack → 50_pivot
profiles/   papiernictvo2/ profile, calibration, report contract, generator anchors
tools/      data generator · independent anchor · contract signing · dashboard check
tests/      pytest suite
evidence/   dashboard pages and source queries
```
