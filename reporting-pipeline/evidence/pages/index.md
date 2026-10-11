---
title: Papiernictvo DEMO — prehľad behu
---

```sql run
select * from papiernictvo2.run_meta
```

```sql spolu
select row, ytd_act, ytd_plan, d_plan, ytd_ly, d_ly, fy_est, fy_plan, d_fy
from papiernictvo2.board_rows where shop = 'Spolu' and not placeholder order by ord
```

```sql findings
select seq, text from papiernictvo2.findings order by seq
```

## {run[0].company} — stav k {run[0].as_of}

**Verdikt: {run[0].verdict}** · zmluva reportu: {run[0].contract_note} · beh {run[0].run_at} · commit {run[0].git_commit}

{#if run[0].verdict === 'NESEDÍ'}

> **Čísla pre board NEVYDANÉ** — kontroly nesedia. Pozri [kontrolný panel](/kontrolny-panel): ktorá kontrola padla a v ktorom súbore dodávky je chyba.
> Tie isté pravidlo ako v `prehlad.xlsx`: stroj nedá boardu čísla, o ktorých vie, že nesedia.

{:else}

```sql kpi
select
  max(case when row = 'Tržby' then ytd_act end) as trzby, max(case when row = 'Tržby' then d_plan end) as trzby_d,
  max(case when row = 'EBITDA' then ytd_act end) as ebitda, max(case when row = 'EBITDA' then d_plan end) as ebitda_d,
  max(case when row = 'EBITDA' then fy_est end) as ebitda_fy, max(case when row = 'EBITDA' then d_fy end) as ebitda_fy_d,
  max(case when row = 'Čistý zisk' then ytd_act end) as zisk, max(case when row = 'Čistý zisk' then d_ly end) as zisk_d
from ${spolu}
```

<BigValue data={kpi} value=trzby title="YTD tržby (€)" fmt="#,##0" comparison=trzby_d comparisonTitle="voči plánu" comparisonFmt="+#,##0;-#,##0" />
<BigValue data={kpi} value=ebitda title="YTD EBITDA (€)" fmt="#,##0" comparison=ebitda_d comparisonTitle="voči plánu" comparisonFmt="+#,##0;-#,##0" />
<BigValue data={kpi} value=ebitda_fy title="Odhad EBITDA roka (€)" fmt="#,##0" comparison=ebitda_fy_d comparisonTitle="voči plánu roka" comparisonFmt="+#,##0;-#,##0" />
<BigValue data={kpi} value=zisk title="YTD čistý zisk (€)" fmt="#,##0" comparison=zisk_d comparisonTitle="voči minulému roku" comparisonFmt="+#,##0;-#,##0" />

### Zistenia pre board

<DataTable data={findings} rows=10>
  <Column id=text title="Zistenie" wrap=true />
</DataTable>

### Výsledovka YTD (Spolu, €)

<DataTable data={spolu} rows=20>
  <Column id=row title="Riadok" />
  <Column id=ytd_act title="YTD skutočnosť" fmt="#,##0.00" />
  <Column id=ytd_plan title="YTD plán" fmt="#,##0.00" />
  <Column id=d_plan title="Rozdiel voči plánu" fmt="+#,##0.00;-#,##0.00" contentType=delta />
  <Column id=ytd_ly title="YTD minulý rok" fmt="#,##0.00" />
  <Column id=fy_est title="Odhad roka" fmt="#,##0.00" />
  <Column id=fy_plan title="Plán roka" fmt="#,##0.00" />
</DataTable>

{/if}

### Kam ďalej

- [Board pack](/board-pack) — odhad roka, odchýlky, riziká a príležitosti, komentáre
- [Výsledovka a mesiace](/vysledovka) — strediská × riadky, tržby po mesiacoch
- [Kontrolný panel](/kontrolny-panel) — semafor kontrol, chybné riadky, čo prišlo
- [Pivotka](/pivotka) — plochá tabuľka faktov (tie isté ako `pivotka.xlsx`)

*Každé číslo je z DB behu (`warehouse/papiernictvo2.duckdb`), z tých istých martov ako `prehlad.xlsx`; zdrojové dotazy pridávajú len rozdiely a súčty, ktoré má aj Excel. Každú zobrazenú bunku porovnáva s Excelom `make evidence-check` (na cent, texty presne).*
