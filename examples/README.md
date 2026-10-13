# Example outputs

Outputs of `make demo`, committed so they can be opened without running
anything. The PDFs are print-outs of those outputs (the workbook sheets and the
`summary.html` pages); the conversion to PDF is not part of this repository. All data is fictional (generated); file metadata (author,
company, application) has been removed.

| File | What it is |
|---|---|
| [`reporting-pipeline/management-summary.pdf`](reporting-pipeline/management-summary.pdf) | **Start here.** One page for a manager: result vs plan, full-year forecast, the three largest variances, what still waits for the finance manager |
| [`reporting-pipeline/errors-summary.pdf`](reporting-pipeline/errors-summary.pdf) | The same page for a delivery with 7 planted errors: report not released, which check failed, in which file |
| [`reporting-pipeline/board-pack.pdf`](reporting-pipeline/board-pack.pdf) | Board pack of a clean delivery (verdict TIES): summary, P&L, plan vs actual, full-year forecast, variances, risks |
| [`reporting-pipeline/board-pack.xlsx`](reporting-pipeline/board-pack.xlsx) | The same workbook as delivered, including the check log and the control panel |
| [`reporting-pipeline/control-panel-with-errors.pdf`](reporting-pipeline/control-panel-with-errors.pdf) | A delivery with 7 planted errors: no board pack, the control panel names each failed reconciliation, file, row and amount |
| [`finance-ops-toolkit/sepa-payments.xml`](finance-ops-toolkit/sepa-payments.xml) | SEPA credit transfer file (pain.001.001.03) generated from the approved payment list |
| [`finance-ops-toolkit/sepa-checks.txt`](finance-ops-toolkit/sepa-checks.txt) | The checks run before and after the XML was written, and the live tamper |
| [`finance-ops-toolkit/bank-reconciliation.csv`](finance-ops-toolkit/bank-reconciliation.csv) · [`…-checks.txt`](finance-ops-toolkit/bank-reconciliation-checks.txt) | Every bank line matched or listed as an open item with its reason |
| [`finance-ops-toolkit/cash-report.xlsx`](finance-ops-toolkit/cash-report.xlsx) | Cash report by store, tied to the ledger, the bank statement and the payroll tape |
| [`odoo/weekly-verdict-2026-W39.html`](odoo/weekly-verdict-2026-W39.html) | **Odoo demo, start here.** One page: verdict of the weekly pack (RELEASED), the five readback checks, bills due in the week by store, bank open items with reasons |
| [`odoo/weekly-pack-2026-W39.xlsx`](odoo/weekly-pack-2026-W39.xlsx) | The weekly pack as written from Odoo: Week · Stores · Open payables · Bank |
| [`odoo/weekly-verdict-2026-W39-tampered.html`](odoo/weekly-verdict-2026-W39-tampered.html) | The same pack after one cent was added to a bill in the finished file: BLOCKED, W1 and W2 name the bill |
| [`odoo/camt053-2026-09.xml`](odoo/camt053-2026-09.xml) · [`import-log-202609-001.txt`](odoo/import-log-202609-001.txt) | A fictional CAMT.053 statement and its import: every line matched by rule R1/R2 or an open item with a reason, checks B1–B5, verdict RECONCILED |
| [`odoo/setup-log.txt`](odoo/setup-log.txt) | The setup run: company, stores, vendors, 70 bills, readback PASS |

Everything is in English. The detailed PDFs are print-outs of the workbook sheets, one sheet per page in
landscape; the one-page summaries are the quick read.
