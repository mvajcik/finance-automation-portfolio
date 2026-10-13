# Report contract — Papiernictvo DEMO s.r.o. (board pack, `overview.xlsx`)

Fictional company, generated data. The machine-readable form of the contract is `contract.json` (check `report_contract`);
the signature = a fingerprint of the contract content and of both anchors in the `signed` field (`tools/sign_contract.py`).
Any change to the contract or to an anchor after signing → the machine reports that the signature is not valid and
does not allow the release.

## 1. Reader and purpose

Owner / board of a fictional chain of 4 stores + head office. The report as of **2026-09-30** answers: how much the
company earned in 9 months and against the plan, **where the year will end** against the plan, what the largest variance
is, and which risk or weakness of the forecast follows from the data. **Only `overview.xlsx`** is sent out; `report.md`
is a technical record.

## 2. Figures the reader reads (17)

A cell is found by sheet, row and column (or by the start of the sentence), not by its coordinate. "Anchors" =
comparison with both anchor A and anchor B (§4); other places where the same figure appears are verified as well.

| ID | Figure | Where in the report | Definition | Tolerance |
|---|---|---|---|---|
| P01 | Revenue, actual YTD | Board pack · Revenue · Actual YTD | Σ of the Revenue line (§2a), 01–09/2026 | €1 |
| P02 | Revenue, plan YTD | Board pack · Revenue · Plan YTD | Σ of the plan of the Revenue line 01–09 (§2b) | €1 |
| P03 | Revenue, full-year forecast | Board pack · Revenue · Full-year forecast | P01 + forecast 10–12 (§2c) | €1 |
| P04 | Revenue, full-year plan | Board pack · Revenue · Full-year plan | Σ of the plan 01–12 | €1 |
| P05 | EBITDA, actual YTD | Board pack · EBITDA · Actual YTD | Σ of the lines Revenue … Other, 01–09 | €1 |
| P06 | EBITDA, plan YTD | Board pack · EBITDA · Plan YTD | as P02 for the EBITDA lines | €1 |
| P07 | EBITDA, full-year forecast | Board pack · EBITDA · Full-year forecast | P05 + forecast 10–12 | €1 |
| P08 | EBITDA, full-year plan | Board pack · EBITDA · Full-year plan | Σ of the plan of the EBITDA lines 01–12 | €1 |
| P09 | Net profit, actual YTD | Board pack · Net profit | all lines of §2a including depreciation, interest and tax | €1 |
| P10 | Net profit, plan YTD | Board pack · Net profit · Plan YTD | plan of the lines + plan tax (§2b) | €1 |
| P11 | Net profit, full-year forecast | Board pack · Net profit · Full-year forecast | P09 + forecast 10–12 including tax | €1 |
| P12 | Net profit, full-year plan | Board pack · Net profit · Full-year plan | plan + plan tax 01–12 | €1 |
| P13 | Largest variance: OC · Rent | Variances · "Store OC · Rent" | actual − plan of the Rent line, S03, 01–09 | €1 |
| P14 | Risk: energy | Risks and opportunities · energy Q1 | last year 10–12 Energy × (Q1 2026 ÷ Q1 2025) − forecast 10–12 | €1 |
| P15 | Forecast sensitivity: stationery | Risks and opportunities · category mix | impact of the change in category mix on forecast EBITDA | €1 |
| P16 | Toys: year-on-year change in Q3 | Overview · finding "Toys:" | Toys revenue incl. VAT 07–09/2026 ÷ 07–09/2025 − 1 | ≤ 0.05 pp |
| P17 | EBITDA forecast vs full-year plan (%) | Overview · sentence "EBITDA 2026 — forecast …" | (P07 − P08) ÷ \|P08\| | ≤ 0.05 pp |

### 2a. P&L lines (Σ Cr − Dr from the journal)

Revenue 604 · Cost of goods sold 504 · Staff 521, 524 · Rent 518100 · Energy 502 · Marketing 518500 ·
Services 511, 518200, 518300, 518400 · Other 501, 568 · **EBITDA** · Depreciation 551 · Interest and financial 562 ·
**Profit before tax** · Income tax 591 · **Net profit**.

### 2b. Plan

`plan_2026.xlsx` (account × cost centre × month). The plan has no tax → plan tax = −21% × planned profit before tax.

### 2c. Rest-of-year forecast (10–12/2026)

Month = plan of the month × (actual ÷ plan for 07–09/2026). **The method is a choice** — the anchors guard the
calculation, not whether the method is right; the report shows its weaknesses in the "Forecast sensitivity" part (P15).

## 3. Release conditions (all at once)

1. Machine verdict **TIES** (all source ↔ source checks passed).
2. All 17 figures from the **finished file** agree with **both anchors** within tolerance.
3. The contract is signed and the signature is valid.

Otherwise the machine does not issue the report — only a log naming the reason. Exceptions: none.

## 4. Anchors (golden values outside the engine code)

- **Anchor A — generator** (`golden_generator.json`): 17 figures from the journal, plan and receipts from which the
  generator produced the delivery; binds the contract to the delivery (fingerprint) and to the period 2026-09.
- **Anchor B — independent recalculation** (`tools/golden_independent_papiernictvo2.py`, live on every run): without
  the engine, the generator or DuckDB. An anchor B that imports engine code or DuckDB is refused at run time.

## 5. What the contract does not cover

Whether postings are right in substance, the authenticity of documents, the choice of forecast method, other periods
and deliveries, the controller's comments (they are marked "[controller]" and carry the machine's figure) and figures
outside the 17 points (their calculation is guarded by `boardpack_consistency`, their rendering only by tests).
