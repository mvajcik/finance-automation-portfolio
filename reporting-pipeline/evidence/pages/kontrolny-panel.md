---
title: Kontrolný panel
---

```sql run
select * from papiernictvo2.run_meta
```

```sql panel
select * from papiernictvo2.panel_rows order by seq
```

```sql sources
select * from papiernictvo2.panel_sources order by seq
```

```sql errors
select * from papiernictvo2.panel_errors order by seq
```

```sql counts
select * from papiernictvo2.panel_counts
```

## {run[0].company} — verdikt {run[0].verdict}

<BigValue data={counts} value=n_pass title="Kontroly PASS" />
<BigValue data={counts} value=n_fail title="Kontroly FAIL" />
<BigValue data={counts} value=n_exc title="Výnimky" />

## Kontroly po skupinách

<DataTable data={panel} rows=40 groupBy=grp groupType=section>
  <Column id=light title="Semafor" />
  <Column id=check_id title="Kontrola" />
  <Column id=detail title="Výsledok" wrap=true />
  <Column id=n_items title="Nálezov" />
</DataTable>

*Kontroly nad hotovým súborom (xlsx_readback, control_panel_readback, pivot_pl_match) tu nie sú — ich FAIL výstup zmaže. Ich výsledok je na obrazovke behu.*

## Chybné riadky — kde v dodávke hľadať

<DataTable data={errors} rows=50>
  <Column id=check_id title="Kontrola" />
  <Column id=files title="Súbory (miesto detekcie)" />
  <Column id=line title="Riadok" />
  <Column id=text title="Nález" wrap=true />
</DataTable>

*Súbor je miesto detekcie, nie nutne príčiny. Odkaz na súbor dodávky je v `prehlad.xlsx`, hárok Chybné riadky.*

## Vstupy — čo prišlo

<DataTable data={sources} rows=12>
  <Column id=label title="Zdroj" />
  <Column id=files_expected title="Súbory očakávané" />
  <Column id=files_got title="Súbory prišli" />
  <Column id=rows_loaded title="Riadky načítané" fmt="#,##0" />
  <Column id=rows_bad title="Nečitateľné" />
  <Column id=light title="Semafor" />
</DataTable>
