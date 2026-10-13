---
title: Control panel
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

## {run[0].company} — verdict {run[0].verdict}

<BigValue data={counts} value=n_pass title="Checks PASS" />
<BigValue data={counts} value=n_fail title="Checks FAIL" />
<BigValue data={counts} value=n_exc title="Exceptions" />

## Checks by area

<DataTable data={panel} rows=40 groupBy=grp groupType=section>
  <Column id=light title="Status" />
  <Column id=check_id title="Check" />
  <Column id=detail title="Result" wrap=true />
  <Column id=n_items title="Findings" />
</DataTable>

*The checks on the finished file (xlsx_readback, control_panel_readback, pivot_pl_match) are not listed here — their FAIL deletes the output. Their result is on the screen of the run.*

## Failed rows — where to look in the delivery

<DataTable data={errors} rows=50>
  <Column id=check_id title="Check" />
  <Column id=files title="Files (where detected)" />
  <Column id=line title="Row" />
  <Column id=text title="Finding" wrap=true />
</DataTable>

*The file is where the error was detected, not necessarily where it was caused. The link to the delivery file is in `overview.xlsx`, sheet Failed rows.*

## Inputs — what arrived

<DataTable data={sources} rows=12>
  <Column id=label title="Source" />
  <Column id=files_expected title="Files expected" />
  <Column id=files_got title="Files received" />
  <Column id=rows_loaded title="Rows read" fmt="#,##0" />
  <Column id=rows_bad title="Unreadable rows" />
  <Column id=light title="Status" />
</DataTable>
