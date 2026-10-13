---
title: Pivot
---

```sql run
select * from papiernictvo2.run_meta
```

```sql facts
select * from papiernictvo2.facts where not placeholder
```

```sql by_row_month
select row, ym, amount from papiernictvo2.pivot_months where not placeholder
  and row in ('Revenue', 'Cost of goods sold', 'Staff', 'Rent') order by row, ym
```

{#if run[0].verdict === 'DOES NOT TIE'}

> **Facts NOT ISSUED** — verdict {run[0].verdict}.

{:else}

## Facts — month × cost centre × account × actual/plan

The same rows as the Facts sheet in `pivot.xlsx` (mart `mart_facts`). Sign as in the P&L: revenue +, costs −. Totals by line and month are in the Pivot sheets (`pivot.xlsx`) and in the chart below — the page itself adds nothing up.

<Dropdown data={facts} name=kind_f value=kind title="Kind" defaultValue="actual" />
<Dropdown data={facts} name=shop_f value=shop title="Cost centre">
  <DropdownOption value="%" valueLabel="all" />
</Dropdown>

```sql facts_f
select ym, cc, shop, account, account_name, row, amount, postings from ${facts}
where kind = '${inputs.kind_f.value}' and shop like '${inputs.shop_f.value}' order by ym, cc, account
```

<DataTable data={facts_f} rows=30 search=true>
  <Column id=ym title="Month" />
  <Column id=shop title="Cost centre" />
  <Column id=account title="Account" />
  <Column id=account_name title="Account name" />
  <Column id=row title="P&L line" />
  <Column id=amount title="Amount (€)" fmt="#,##0.00" />
  <Column id=postings title="Postings" />
</DataTable>

## P&L line × month {run[0].as_of.slice(0, 4)}

<BarChart data={by_row_month} x=ym y=amount series=row type=grouped sort=false yFmt="#,##0" title="Actual by month (base lines) — == sheet Pivot actual" />

{/if}
