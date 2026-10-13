---
title: P&L and months
---

```sql run
select * from papiernictvo2.run_meta
```

```sql pl
select shop, row, ord, ytd_act from papiernictvo2.board_rows where not placeholder
```

<!-- strediská z dát (PIVOT), nie natvrdo: nové alebo premenované stredisko sa ukáže samo -->
```sql pl_pivot
select * exclude (ord) from (pivot ${pl} on shop using first(ytd_act) group by row, ord) order by ord
```

```sql months
select * from papiernictvo2.months where not placeholder
```

{#if run[0].verdict === 'DOES NOT TIE'}

> **Figures NOT ISSUED** — verdict {run[0].verdict}. See the [control panel](/control-panel).

{:else}

## P&L YTD as of {run[0].as_of} (€)

<DataTable data={pl_pivot} rows=20>
  <Column id=row title="Line" />
  {#each Object.keys(pl_pivot[0] ?? {}).filter((c) => c !== 'row') as c}
    <Column id={c} title={c} fmt="#,##0" />
  {/each}
</DataTable>

## Revenue by month and cost centre (€)

<LineChart data={months} x=ym y=revenue series=shop yFmt="#,##0" title="Revenue excl. VAT by month" />

<DataTable data={months} rows=25>
  <Column id=ym title="Month" />
  <Column id=shop title="Cost centre" />
  <Column id=revenue title="Revenue (€)" fmt="#,##0.00" />
</DataTable>

{/if}
