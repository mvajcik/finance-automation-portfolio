---
title: Pivotka
---

```sql run
select * from papiernictvo2.run_meta
```

```sql facts
select * from papiernictvo2.facts where not placeholder
```

```sql by_row_month
select row, ym, amount from papiernictvo2.pivot_months where not placeholder
  and row in ('Tržby', 'Náklady na predaný tovar', 'Personál', 'Nájom') order by row, ym
```

{#if run[0].verdict === 'NESEDÍ'}

> **Fakty NEVYDANÉ** — verdikt {run[0].verdict}.

{:else}

## Fakty — mesiac × stredisko × účet × skutočnosť/plán

Tie isté riadky ako hárok Fakty v `pivotka.xlsx` (mart `mart_facts`). Znamienko ako vo výsledovke: výnosy +, náklady −. Súčty po riadkoch a mesiacoch sú v hárkoch Pivot (`pivotka.xlsx`) a v grafe nižšie — stránka sama nesčítava.

<Dropdown data={facts} name=kind_f value=kind title="Druh" defaultValue="skutočnosť" />
<Dropdown data={facts} name=shop_f value=shop title="Stredisko">
  <DropdownOption value="%" valueLabel="všetky" />
</Dropdown>

```sql facts_f
select ym, cc, shop, account, account_name, row, amount, postings from ${facts}
where kind = '${inputs.kind_f.value}' and shop like '${inputs.shop_f.value}' order by ym, cc, account
```

<DataTable data={facts_f} rows=30 search=true>
  <Column id=ym title="Mesiac" />
  <Column id=shop title="Stredisko" />
  <Column id=account title="Účet" />
  <Column id=account_name title="Názov účtu" />
  <Column id=row title="Riadok výsledovky" />
  <Column id=amount title="Suma (€)" fmt="#,##0.00" />
  <Column id=postings title="Zápisov" />
</DataTable>

## Riadok výsledovky × mesiac {run[0].as_of.slice(0, 4)}

<BarChart data={by_row_month} x=ym y=amount series=row type=grouped sort=false yFmt="#,##0" title="Skutočnosť po mesiacoch (základné riadky) — == hárok Pivot skutočnosť" />

{/if}
