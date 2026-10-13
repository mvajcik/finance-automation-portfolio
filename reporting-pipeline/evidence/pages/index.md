---
title: Papiernictvo DEMO — run overview
---

```sql run
select * from papiernictvo2.run_meta
```

```sql totals
select row, ytd_act, ytd_plan, d_plan, ytd_ly, d_ly, fy_est, fy_plan, d_fy
from papiernictvo2.board_rows where shop = 'Total' and not placeholder order by ord
```

```sql findings
select seq, text from papiernictvo2.findings order by seq
```

## {run[0].company} — as of {run[0].as_of}

**Verdict: {run[0].verdict}** · report contract: {run[0].contract_note} · run {run[0].run_at} · commit {run[0].git_commit}

{#if run[0].verdict === 'DOES NOT TIE'}

> **Figures for the board NOT ISSUED** — the checks do not tie. See the [control panel](/control-panel): which check failed and which file of the delivery holds the error.
> The same rule as in `overview.xlsx`: the machine does not give the board figures it knows do not tie.

{:else}

```sql kpi
select
  max(case when row = 'Revenue' then ytd_act end) as revenue, max(case when row = 'Revenue' then d_plan end) as revenue_d,
  max(case when row = 'EBITDA' then ytd_act end) as ebitda, max(case when row = 'EBITDA' then d_plan end) as ebitda_d,
  max(case when row = 'EBITDA' then fy_est end) as ebitda_fy, max(case when row = 'EBITDA' then d_fy end) as ebitda_fy_d,
  max(case when row = 'Net profit' then ytd_act end) as net_profit, max(case when row = 'Net profit' then d_ly end) as net_profit_d
from ${totals}
```

<BigValue data={kpi} value=revenue title="Revenue year to date (€)" fmt="#,##0" comparison=revenue_d comparisonTitle="vs plan" comparisonFmt="+#,##0;-#,##0" />
<BigValue data={kpi} value=ebitda title="EBITDA year to date (€)" fmt="#,##0" comparison=ebitda_d comparisonTitle="vs plan" comparisonFmt="+#,##0;-#,##0" />
<BigValue data={kpi} value=ebitda_fy title="Full-year EBITDA forecast (€)" fmt="#,##0" comparison=ebitda_fy_d comparisonTitle="vs full-year plan" comparisonFmt="+#,##0;-#,##0" />
<BigValue data={kpi} value=net_profit title="Net profit year to date (€)" fmt="#,##0" comparison=net_profit_d comparisonTitle="vs last year" comparisonFmt="+#,##0;-#,##0" />

### Findings for the board

<DataTable data={findings} rows=10>
  <Column id=text title="Finding" wrap=true />
</DataTable>

### P&L YTD (Total, €)

<DataTable data={totals} rows=20>
  <Column id=row title="Line" />
  <Column id=ytd_act title="Actual YTD" fmt="#,##0.00" />
  <Column id=ytd_plan title="Plan YTD" fmt="#,##0.00" />
  <Column id=d_plan title="Variance vs plan" fmt="+#,##0.00;-#,##0.00" contentType=delta />
  <Column id=ytd_ly title="Last year YTD" fmt="#,##0.00" />
  <Column id=fy_est title="Full-year forecast" fmt="#,##0.00" />
  <Column id=fy_plan title="Full-year plan" fmt="#,##0.00" />
</DataTable>

{/if}

### Where next

- [Board pack](/board-pack) — full-year forecast, variances, risks and opportunities, comments
- [P&L and months](/income-statement) — cost centres × lines, revenue by month
- [Control panel](/control-panel) — status of the checks, failed rows, what arrived
- [Pivot](/pivot) — flat table of facts (the same as in `pivot.xlsx`)

*Every figure comes from the run database (`warehouse/papiernictvo2.duckdb`), from the same marts as `overview.xlsx`; the source queries add only differences and totals that the Excel file has too. `python tools/evidence_check.py` compares every displayed cell with the Excel file (to the cent, texts exactly).*
