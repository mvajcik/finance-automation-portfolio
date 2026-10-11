---
title: Výsledovka a mesiace
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

{#if run[0].verdict === 'NESEDÍ'}

> **Čísla NEVYDANÉ** — verdikt {run[0].verdict}. Pozri [kontrolný panel](/kontrolny-panel).

{:else}

## Výsledovka YTD k {run[0].as_of} (€)

<DataTable data={pl_pivot} rows=20>
  <Column id=row title="Riadok" />
  {#each Object.keys(pl_pivot[0] ?? {}).filter((c) => c !== 'row') as c}
    <Column id={c} title={c} fmt="#,##0" />
  {/each}
</DataTable>

## Tržby po mesiacoch a strediskách (€)

<LineChart data={months} x=ym y=revenue series=shop yFmt="#,##0" title="Tržby bez DPH po mesiacoch" />

<DataTable data={months} rows=25>
  <Column id=ym title="Mesiac" />
  <Column id=shop title="Stredisko" />
  <Column id=revenue title="Tržby (€)" fmt="#,##0.00" />
</DataTable>

{/if}
