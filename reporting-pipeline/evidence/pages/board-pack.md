---
title: Board pack
---

```sql run
select * from papiernictvo2.run_meta
```

```sql rows
select * from papiernictvo2.board_rows where shop = 'Spolu' and not placeholder order by ord
```

```sql fy_by_shop
select shop, fy_est as "Odhad roka", fy_plan as "Plán roka" from papiernictvo2.board_rows where not placeholder and row = 'EBITDA' and shop <> 'Spolu' order by shop
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

{#if run[0].verdict === 'NESEDÍ'}

> **Board pack NEVYDANÝ** — verdikt {run[0].verdict}. Pozri [kontrolný panel](/kontrolny-panel).

{:else}

## Odhad roka {run[0].as_of.slice(0, 4)}

Metóda: odhad zvyšku roka = plán mesiaca × (skutočnosť ÷ plán za posledné 3 mesiace) po stredisku a riadku; daň = sadzba × odhad zisku pred zdanením.

<DataTable data={rows} rows=20>
  <Column id=row title="Riadok" />
  <Column id=ytd_act title="YTD skutočnosť" fmt="#,##0" />
  <Column id=ytd_plan title="YTD plán" fmt="#,##0" />
  <Column id=d_plan title="Rozdiel" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=ytd_ly title="YTD minulý rok" fmt="#,##0" />
  <Column id=fy_est title="Odhad roka" fmt="#,##0" />
  <Column id=fy_plan title="Plán roka" fmt="#,##0" />
  <Column id=d_fy title="Odhad − plán" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=fy_ly title="Minulý rok celý" fmt="#,##0" />
</DataTable>

<BarChart data={fy_by_shop} x=shop y={["Odhad roka", "Plán roka"]} type=grouped title="EBITDA — odhad roka vs plán po strediskách (€)" yFmt="#,##0" />

## Najväčšie odchýlky voči plánu (vplyv na EBITDA)

<DataTable data={variance} rows=10>
  <Column id=shop title="Stredisko" />
  <Column id=row title="Riadok" />
  <Column id=act title="YTD skutočnosť" fmt="#,##0" />
  <Column id=plan title="YTD plán" fmt="#,##0" />
  <Column id=d_plan title="Vplyv na EBITDA" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=d_ly title="Voči minulému roku" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=cause title="Príčina" />
</DataTable>

## Riziká a príležitosti

<DataTable data={ro} rows=20>
  <Column id=kind title="Typ" />
  <Column id=number title="Vplyv na EBITDA (€)" fmt="+#,##0;-#,##0" contentType=delta />
  <Column id=text title="Popis" wrap=true />
</DataTable>

*Položky „citlivosť odhadu" opravujú tú istú metódu odhadu — nesčítavať.*

## Komentáre

<DataTable data={comments} rows=30>
  <Column id=key title="Kľúč" />
  <Column id=status title="Stav" />
  <Column id=final title="Platný komentár" wrap=true />
</DataTable>

{/if}
