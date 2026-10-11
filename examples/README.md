# Example outputs

Outputs of `make demo`, committed so they can be opened without running
anything. The PDFs are print-outs of those outputs (the workbook sheets and the
`summary_*.html` pages); the conversion to PDF is not part of this repository. All data is fictional (generated); file metadata (author,
company, application) has been removed.

| File | What it is |
|---|---|
| [`reporting-pipeline/management-summary-en.pdf`](reporting-pipeline/management-summary-en.pdf) · [`…-sk.pdf`](reporting-pipeline/management-summary-sk.pdf) | **Start here.** One page for a manager, in English and in Slovak: result vs plan, full-year forecast, the three largest variances, what still waits for the finance manager |
| [`reporting-pipeline/errors-summary-en.pdf`](reporting-pipeline/errors-summary-en.pdf) · [`…-sk.pdf`](reporting-pipeline/errors-summary-sk.pdf) | The same page for a delivery with 7 planted errors: report not released, which check failed, in which file |
| [`reporting-pipeline/board-pack.pdf`](reporting-pipeline/board-pack.pdf) | Board pack of a clean delivery (verdict *SEDÍ* = ties): summary, P&L, plan vs actual, full-year forecast, variances, risks |
| [`reporting-pipeline/board-pack.xlsx`](reporting-pipeline/board-pack.xlsx) | The same workbook as delivered, including the check log and the control panel |
| [`reporting-pipeline/control-panel-with-errors.pdf`](reporting-pipeline/control-panel-with-errors.pdf) | A delivery with 7 planted errors: no board pack, the control panel names each failed reconciliation, file, row and amount |
| [`finance-ops-toolkit/sepa-payments.xml`](finance-ops-toolkit/sepa-payments.xml) | SEPA credit transfer file (pain.001.001.03) generated from the approved payment list |
| [`finance-ops-toolkit/sepa-checks.txt`](finance-ops-toolkit/sepa-checks.txt) | The checks run before and after the XML was written, and the live tamper |
| [`finance-ops-toolkit/bank-reconciliation.csv`](finance-ops-toolkit/bank-reconciliation.csv) · [`…-checks.txt`](finance-ops-toolkit/bank-reconciliation-checks.txt) | Every bank line matched or listed as an open item with its reason |
| [`finance-ops-toolkit/cash-report.xlsx`](finance-ops-toolkit/cash-report.xlsx) | Cash report by store, tied to the ledger, the bank statement and the payroll tape |

The one-page summaries are in English and in Slovak. Labels in the detailed
reporting pipeline outputs are in Slovak (*Tržby* = revenue, *Odhad roka* =
full-year forecast, *NESEDÍ* = does not tie). The detailed PDFs are dense
print-outs of the workbook; the workbook itself is the readable form.
