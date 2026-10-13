---
title: Board pack
---

```sql run
select * from papiernictvo2.run_meta
```

```sql rows
select * from papiernictvo2.board_rows where shop = 'Total' and not placeholder order by ord
```

```sql fy_by_shop
select shop, fy_est as "Full-year forecast", fy_plan as "Full-year plan" from papiernictvo2.board_rows where not placeholder and row = 'EBITDA' and shop <> 'Total' order by shop
```

```sql variance
select * from papiernictvo2.variance where not placeholder order by rk
```

```sql ro
select * from papiernictvo2.ro where not placeholder order by rk
```

```sql comments
select * from papiernictvo2.comments
```

{#if run[0].verdict === 'DOES NOT TIE'}

> **Board pack NOT ISSUED** — verdict {run[0].verdict}. See the [control panel](/control-panel).

{:else}

## Full-year forecast {run[0].as_of.slice(0, 4)}

Method: rest-of-year forecast = month's plan × (actual ÷ plan over the last 3 months) by cost centre and line; tax = rate × forecast profit before tax.

<DataTable data={rows} rows=20>
  <Column id=row title="Line" />
  <Column id=ytd_act title="Actual YTD" fmt="#,##0" />
  <Column id=ytd_plan title="Plan YTD" fmt="#,##0" />
  <Column id=d_plan title="Variance vs plan" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=ytd_ly title="Last year YTD" fmt="#,##0" />
  <Column id=fy_est title="Full-year forecast" fmt="#,##0" />
  <Column id=fy_plan title="Full-year plan" fmt="#,##0" />
  <Column id=d_fy title="Forecast − plan" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=fy_ly title="Last year full" fmt="#,##0" />
</DataTable>

<BarChart data={fy_by_shop} x=shop y={["Full-year forecast", "Full-year plan"]} type=grouped title="EBITDA — full-year forecast vs plan by cost centre (€)" yFmt="#,##0" />

## Largest variances vs plan (EBITDA impact)

<DataTable data={variance} rows=10>
  <Column id=shop title="Cost centre" />
  <Column id=row title="Line" />
  <Column id=act title="Actual YTD" fmt="#,##0" />
  <Column id=plan title="Plan YTD" fmt="#,##0" />
  <Column id=d_plan title="EBITDA impact vs plan" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=d_ly title="Impact vs last year" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=cause title="Cause" />
</DataTable>

## Risks and opportunities

<DataTable data={ro} rows=20>
  <Column id=kind title="Type" />
  <Column id=number title="EBITDA impact (€)" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=text title="Description" wrap=true />
</DataTable>

*The "forecast sensitivity" items correct the same forecast method — do not add them up.*

## Comments

<DataTable data={comments} rows=30>
  <Column id=key title="Key" />
  <Column id=status title="Status" />
  <Column id=final title="Valid comment" wrap=true />
</DataTable>

{/if}
